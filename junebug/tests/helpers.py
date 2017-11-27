import json
from copy import deepcopy
import logging
import logging.handlers

from twisted.python.logfile import LogFile
from twisted.python.failure import Failure
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.internet.task import Clock
from twisted.internet.error import ConnectionDone
from twisted.trial.unittest import TestCase
from twisted.web.server import Site

from klein import Klein
from txamqp.client import TwistedDelegate

from vumi.utils import vumi_resource_path
from vumi.service import get_spec
from vumi.tests.fake_amqp import FakeAMQPBroker, FakeAMQPChannel
from vumi.tests.helpers import PersistenceHelper
from vumi.transports import Transport
from vumi.worker import BaseWorker

import junebug
from junebug import JunebugApi
from junebug.amqp import JunebugAMQClient, MessageSender
from junebug.channel import Channel
from junebug.plugin import JunebugPlugin
from junebug.router import InvalidRouterConfig
from junebug.service import JunebugService
from junebug.config import JunebugConfig
from junebug.stores import MessageRateStore


class DummyLogFile(object):
    '''Dummy log file used for testing.'''
    def __init__(
            self, worker_id, directory, rotateLength, maxRotatedFiles):
        self.worker_id = worker_id
        self.directory = directory
        self.rotateLength = rotateLength
        self.maxRotatedFiles = maxRotatedFiles
        self.closed_count = 0
        self.logfile = LogFile(
            worker_id, directory, rotateLength=rotateLength,
            maxRotatedFiles=maxRotatedFiles)
        self.path = self.logfile.path

    @property
    def logs(self):
        reader = self.logfile.getCurrentLog()
        logs = []
        lines = reader.readLines()
        while lines:
            logs.extend(lines)
            lines = reader.readLines()
        return logs

    def write(self, data):
        self.logfile.write(data)
        self.logfile.flush()

    def close(self):
        self.closed_count += 1

    def listLogs(self):
        return []


class FakeAmqpClient(JunebugAMQClient):
    '''Amqp client, base upon the real JunebugAMQClient, that uses a
    FakeAMQPBroker instead of a real broker'''
    def __init__(self, spec):
        super(FakeAmqpClient, self).__init__(TwistedDelegate(), '', spec)
        self.broker = FakeAMQPBroker()

    @inlineCallbacks
    def channel(self, id):
        yield self.channelLock.acquire()
        try:
            try:
                ch = self.channels[id]
            except KeyError:
                ch = FakeAMQPChannel(id, self)
                self.channels[id] = ch
        finally:
            self.channelLock.release()
        returnValue(ch)


class RequestLoggingApi(object):
    app = Klein()

    def __init__(self):
        self.requests = []
        self.url = None

    def setup(self):
        self.port = reactor.listenTCP(
            0, Site(self.app.resource()), interface='127.0.0.1')

        addr = self.port.getHost()
        self.url = "http://%s:%s" % (addr.host, addr.port)

    def teardown(self):
        self.port.stopListening()

    @app.route('/')
    def log_request(self, request):
        self.requests.append({
            'request': request,
            'body': request.content.read(),
            })
        return ''

    @app.route('/bad/')
    def bad_request(self, request):
        self.requests.append({
            'request': request,
            'body': request.content.read(),
            })
        request.setResponseCode(500)
        return 'test-error-response'

    @app.route('/auth/')
    def auth_token(self, request):
        headers = request.requestHeaders
        self.requests.append({
            'Authorization': headers.getRawHeaders('Authorization'),
        })
        request.setResponseCode(200)
        return 'auth-response'

    @app.route('/implode/')
    def imploding_request(self, request):
        request.transport.connectionLost(reason=Failure(ConnectionDone()))


class LoggingTestTransport(Transport):
    def test_log(self, message='Test log'):
        self.log.msg(message, source=self)


class TestRouter(BaseWorker):
    """Router used for testing the API."""
    # TODO: Create a proper base class for Junebug routers
    @classmethod
    def validate_config(cls, config):
        """Testing config requires the ``test`` parameter to be ``pass``"""
        if config.get('test') != 'pass':
            raise InvalidRouterConfig('test must be pass')


class JunebugTestBase(TestCase):
    '''Base test case that all junebug tests inherit from. Contains useful
    helper functions'''

    default_channel_properties = {
        'type': 'telnet',
        'config': {
            'twisted_endpoint': 'tcp:0',
        },
        'mo_url': 'http://foo.bar',
    }

    default_router_properties = {
        'type': 'testing',
        'config': {
            'test': 'pass',
        },
    }

    default_channel_config = {
        'ttl': 60,
        'routers': {
            'testing': 'junebug.tests.helpers.TestRouter',
        }
    }

    def patch_logger(self):
        ''' Patches the logger with an in-memory logger, which is acccessable
        at "self.logging_handler".'''
        self.logging_handler = logging.handlers.MemoryHandler(100)
        logging.getLogger().addHandler(self.logging_handler)
        self.addCleanup(self._cleanup_logging_patch)

    def patch_message_rate_clock(self):
        '''Patches the message rate clock, and returns the clock'''
        clock = Clock()
        self.patch(MessageRateStore, 'get_seconds', lambda _: clock.seconds())
        return clock

    def _cleanup_logging_patch(self):
        self.logging_handler.close()
        logging.getLogger().removeHandler(self.logging_handler)

    def create_channel_properties(self, **kw):
        properties = deepcopy(self.default_channel_properties)
        config = kw.pop('config', {})
        properties['config'].update(config)
        properties.update(kw)
        return properties

    @inlineCallbacks
    def create_channel_config(self, **kw):
        self.persistencehelper = PersistenceHelper()
        yield self.persistencehelper.setup()
        self.addCleanup(self.persistencehelper.cleanup)

        config = deepcopy(self.default_channel_config)
        config.update(kw)
        channel_config = self.persistencehelper.mk_config(config)
        channel_config['redis'] = channel_config['redis_manager']
        returnValue(JunebugConfig(channel_config))

    def create_router_config(self, **kw):
        properties = deepcopy(self.default_router_properties)
        config = kw.pop('config', {})
        properties['config'].update(config)
        properties.update(kw)
        return properties

    @inlineCallbacks
    def create_channel(
            self, service, redis, transport_class=None,
            properties=default_channel_properties, id=None, config=None,
            plugins=[]):
        '''Creates and starts, and saves a channel, with a
        TelnetServerTransport transport'''
        self.patch(junebug.logging_service, 'LogFile', DummyLogFile)
        if transport_class is None:
            transport_class = 'vumi.transports.telnet.TelnetServerTransport'

        properties = deepcopy(properties)
        logpath = self.mktemp()
        if config is None:
            config = yield self.create_channel_config(
                channels={
                    properties['type']: transport_class
                },
                logging_path=logpath)

        channel = Channel(
            redis, config, properties, id=id, plugins=plugins)
        yield channel.start(self.service)

        properties['config']['transport_name'] = channel.id

        yield channel.save()
        self.addCleanup(channel.stop)
        returnValue(channel)

    @inlineCallbacks
    def create_channel_from_id(self, redis, config, id, service):
        '''Creates an existing channel given the channel id'''
        config = yield self.create_channel_config(**config)
        channel = yield Channel.from_id(redis, config, id, service)
        returnValue(channel)

    @inlineCallbacks
    def get_redis(self):
        '''Creates and returns a redis manager'''
        if hasattr(self, 'redis'):
            returnValue(self.redis)
        persistencehelper = PersistenceHelper()
        yield persistencehelper.setup()
        self.redis = yield persistencehelper.get_redis_manager()
        self.addCleanup(persistencehelper.cleanup)
        returnValue(self.redis)

    @inlineCallbacks
    def start_server(self, config=None):
        '''Starts a junebug server. Stores the service to "self.service", and
        the url at "self.url"'''
        # TODO: This setup is very manual, because we don't call
        # service.startService. This must be fixed to close mirror the real
        # program with our tests.
        if config is None:
            config = yield self.create_channel_config()
        self.service = JunebugService(config)
        self.api = JunebugApi(
            self.service, config)
        self.service.api = self.api

        redis = yield self.get_redis()
        yield self.api.setup(redis, self.get_message_sender())

        self.config = self.api.config
        self.redis = self.api.redis
        self.inbounds = self.api.inbounds
        self.outbounds = self.api.outbounds
        self.message_sender = self.api.message_sender

        port = reactor.listenTCP(
            0, Site(self.api.app.resource()),
            interface='127.0.0.1')
        self.service._port = port
        self.addCleanup(self.stop_server)
        addr = port.getHost()
        self.url = "http://%s:%s" % (addr.host, addr.port)

    @inlineCallbacks
    def stop_server(self):
        # TODO: This teardown is very messy, because we don't actually call
        # service.startService. This needs to be fixed in order to ensure that
        # our tests are mirroring the real program closely.
        yield self.service.stopService()
        for service in self.service:
            service.disownServiceParent()
        for service in self.service.namedServices.values():
            service.disownServiceParent()

    def get_message_sender(self):
        '''Creates a new MessageSender object, with a fake amqp client'''
        message_sender = MessageSender('amqp-spec-0-8.xml', None)
        spec = get_spec(vumi_resource_path('amqp-spec-0-8.xml'))
        client = FakeAmqpClient(spec)
        message_sender.client = client
        return message_sender

    def get_dispatched_messages(self, queue):
        '''Gets all messages that have been dispatched to the amqp broker.
        Should only be called after start_server, as it looks in the api for
        the amqp client'''
        amqp_client = self.api.message_sender.client
        return amqp_client.broker.get_messages(
            'vumi', queue)

    def assert_was_logged(self, msg):
        self.assertTrue(any(
            msg in log.getMessage()
            for log in self.logging_handler.buffer))

    def assert_request(self, req, method=None, body=None, headers=None):
        if method is not None:
            self.assertEqual(req['request'].method, 'POST')

        if headers is not None:
            for name, values in headers.iteritems():
                self.assertEqual(
                    req['request'].requestHeaders.getRawHeaders(name),
                    values)

        if body is not None:
            self.assertEqual(json.loads(req['body']), body)

    def assert_body_contains(self, req, **fields):
        body = json.loads(req['body'])

        self.assertEqual(
            dict((k, v) for k, v in body.iteritems() if k in fields),
            fields)

    def assert_log(self, log, expected):
        '''Assert that a log matches what is expected.'''
        timestamp = log.pop('timestamp')
        self.assertTrue(isinstance(timestamp, float))
        self.assertEqual(log, expected)

    def generate_status(
            self, level=None, components={}, inbound_message_rate=0,
            outbound_message_rate=0, submitted_event_rate=0,
            rejected_event_rate=0, delivery_succeeded_rate=0,
            delivery_failed_rate=0, delivery_pending_rate=0):
        '''Generates a status that the http API would respond with, given the
        same parameters'''
        return {
            'status': level,
            'components': components,
            'inbound_message_rate': inbound_message_rate,
            'outbound_message_rate': outbound_message_rate,
            'submitted_event_rate': submitted_event_rate,
            'rejected_event_rate': rejected_event_rate,
            'delivery_succeeded_rate': delivery_succeeded_rate,
            'delivery_failed_rate': delivery_failed_rate,
            'delivery_pending_rate': delivery_pending_rate,
        }

    def assert_status(self, status, **kwargs):
        '''Assert that the current channel status is correct'''
        self.assertEqual(status, self.generate_status(**kwargs))


class FakeJunebugPlugin(JunebugPlugin):
    def _add_call(self, func_name, *args):
        self.calls.append((func_name, args))

    def start_plugin(self, config, junebug_config):
        self.calls = []
        self._add_call('start_plugin', config, junebug_config)
        return succeed(None)

    def stop_plugin(self):
        self._add_call('stop_plugin')
        return succeed(None)

    def channel_started(self, channel):
        self._add_call('channel_started', channel)
        return succeed(None)

    def channel_stopped(self, channel):
        self._add_call('channel_stopped', channel)
        return succeed(None)
