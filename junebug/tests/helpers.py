from copy import deepcopy
import logging
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial.unittest import TestCase
from twisted.web.server import Site
from txamqp.client import TwistedDelegate
from vumi.utils import vumi_resource_path
from vumi.service import get_spec
from vumi.tests.fake_amqp import FakeAMQPBroker, FakeAMQClient, FakeAMQPChannel
from vumi.tests.helpers import PersistenceHelper, WorkerHelper

from junebug import JunebugApi
from junebug.amqp import JunebugAMQClient
from junebug.channel import Channel
from junebug.service import JunebugService


class FakeAmqpFactory(object):
    def __init__(self, amqp_client):
        self.amqp_client = amqp_client

    def get_client(self):
        return self.amqp_client


class FakeAmqpClient(JunebugAMQClient):
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


class JunebugTestBase(TestCase):
    '''Base test case that all junebug tests inherit from. Contains useful
    helper functions'''

    default_channel_config = {
        'type': 'telnet',
        'config': {
            'transport_name': 'dummy_transport1',
            'twisted_endpoint': 'tcp:0',
        },
        'mo_url': 'http://foo.bar',
    }

    def patch_logger(self):
        ''' Patches the logger with an in-memory logger, which is acccessable
        at "self.logging_handler".'''
        self.logging_handler = logging.handlers.MemoryHandler(100)
        logging.getLogger().addHandler(self.logging_handler)
        self.addCleanup(self._cleanup_logging_patch)

    def _cleanup_logging_patch(self):
        self.logging_handler.close()
        logging.getLogger().removeHandler(self.logging_handler)

    @inlineCallbacks
    def create_channel(
            self, service, redis, transport_class,
            config=default_channel_config, id=None):
        '''Creates and starts, and saves a channel, with a
        TelnetServerTransport transport'''
        config = deepcopy(config)
        channel = Channel(redis, {}, config, id=id)
        config['config']['worker_name'] = channel.id
        config['config']['transport_name'] = channel.id
        transport_worker = yield WorkerHelper().get_worker(
            transport_class, config['config'])
        yield channel.start(self.service, transport_worker)
        yield channel.save()
        self.addCleanup(channel.stop)
        returnValue(channel)

    def create_channel_from_id(self, service, redis, id):
        '''Creates an existing channel given the channel id'''
        return Channel.from_id(redis, {}, id, service)

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
    def start_server(self):
        '''Starts a junebug server. Stores the service to "self.service", and
        the url at "self.url"'''
        redis = yield self.get_redis()
        self.service = JunebugService('127.0.0.1', 0, redis._config, {})
        self.api = JunebugApi(
            self.service, redis._config, {'hostname': '', 'port': ''})
        self.api.redis = redis

        self.api.amqp_factory = self._get_amqp_factory()

        port = reactor.listenTCP(
            0, Site(self.api.app.resource()),
            interface='127.0.0.1')
        self.addCleanup(port.stopListening)
        addr = port.getHost()
        self.url = "http://%s:%s" % (addr.host, addr.port)

    def _get_amqp_factory(self):
        spec = get_spec(vumi_resource_path('amqp-spec-0-8.xml'))
        client = FakeAmqpClient(spec)
        return FakeAmqpFactory(client)

    @inlineCallbacks
    def patch_worker_creation(
            self, transport_class, config=default_channel_config):
        '''Patches the channel start function to start a worker with the given
        worker class and config using a worker helper.'''
        worker_helper = WorkerHelper()
        transport_worker = yield worker_helper.get_worker(
            transport_class, config['config'])
        yield transport_worker.startService()
        self.addCleanup(transport_worker.stopService)
        self._original_channel_start = old_start = Channel.start

        def new_start(self, service):
            return old_start(
                self, service, transport_worker)

        Channel.start = new_start
        self.addCleanup(self._unpatch_worker_creation)

    def _unpatch_worker_creation(self):
        Channel.start = self._original_channel_start

    def get_dispatched_messages(self, queue):
        amqp_client = self.api.amqp_factory.get_client()
        return amqp_client.broker.get_messages(
            'vumi', queue)
