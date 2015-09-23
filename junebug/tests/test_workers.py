import json

import treq
from klein import Klein

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.client import HTTPConnectionPool
from twisted.web.server import Site

from vumi.application.tests.helpers import ApplicationHelper
from vumi.message import TransportUserMessage, TransportEvent
from vumi.tests.helpers import PersistenceHelper

from junebug.utils import conjoin, api_from_event
from junebug.workers import MessageForwardingWorker
from junebug.tests.helpers import JunebugTestBase


class RequestLoggingApi(object):
    app = Klein()

    def __init__(self):
        self.requests = []

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


class TestMessageForwardingWorker(JunebugTestBase):
    @inlineCallbacks
    def setUp(self):
        self.logging_api = RequestLoggingApi()
        port = reactor.listenTCP(
            0, Site(self.logging_api.app.resource()),
            interface='127.0.0.1')
        self.addCleanup(port.stopListening)
        addr = port.getHost()
        self.url = "http://%s:%s" % (addr.host, addr.port)

        self.worker = yield self.get_worker()
        connection_pool = HTTPConnectionPool(reactor, persistent=False)
        treq._utils.set_global_pool(connection_pool)

    @inlineCallbacks
    def get_worker(self, config=None):
        '''Get a new MessageForwardingWorker with the provided config'''
        if config is None:
            config = {}

        app_helper = ApplicationHelper(MessageForwardingWorker)
        yield app_helper.setup()
        self.addCleanup(app_helper.cleanup)

        persistencehelper = PersistenceHelper()
        yield persistencehelper.setup()
        self.addCleanup(persistencehelper.cleanup)

        config = conjoin(persistencehelper.mk_config({
            'transport_name': 'testtransport',
            'mo_message_url': self.url.decode('utf-8'),
            'inbound_ttl': 60,
            'outbound_ttl': 60 * 60 * 24 * 2,
        }), config)

        worker = yield app_helper.get_application(config)
        returnValue(worker)

    def assert_was_logged(self, msg):
        return any(
            msg in log.getMessage()
            for log in self.logging_handler.buffer)

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
            dict((k, v) for k, v in body.iteritems()),
            body)

    @inlineCallbacks
    def test_channel_id(self):
        worker = yield self.get_worker({'transport_name': 'foo'})
        self.assertEqual(worker.channel_id, 'foo')

    @inlineCallbacks
    def test_send_message(self):
        '''A sent message should be forwarded to the configured URL'''
        msg = TransportUserMessage.send(to_addr='+1234', content='testcontent')
        yield self.worker.consume_user_message(msg)
        [req] = self.logging_api.requests

        self.assert_request(req, method='POST', headers={
            'content-type': ['application/json']
        })

        self.assert_body_contains(req, to='+1234', content='testcontent')

    @inlineCallbacks
    def test_send_message_bad_response(self):
        '''If there is an error sending a message to the configured URL, the
        error and message should be logged'''
        self.patch_logger()
        self.worker = yield self.get_worker({
            'transport_name': 'testtransport',
            'mo_message_url': self.url + '/bad/',
            })
        msg = TransportUserMessage.send(to_addr='+1234', content='testcontent')
        yield self.worker.consume_user_message(msg)

        self.assert_was_logged("'content': 'testcontent'")
        self.assert_was_logged("'to': '+1234'")
        self.assert_was_logged('500')
        self.assert_was_logged('test-error-response')

    @inlineCallbacks
    def test_send_message_storing(self):
        '''Inbound messages should be stored in the InboundMessageStore'''
        msg = TransportUserMessage.send(to_addr='+1234', content='testcontent')
        yield self.worker.consume_user_message(msg)

        redis = self.worker.redis
        key = '%s:inbound_messages:%s' % (
            self.worker.config['transport_name'], msg['message_id'])
        msg_json = yield redis.hget(key, 'message')
        self.assertEqual(TransportUserMessage.from_json(msg_json), msg)

    @inlineCallbacks
    def test_forward_ack(self):
        event = TransportEvent(
            event_type='ack',
            user_message_id='msg-21',
            sent_message_id='msg-21',
            timestamp='2015-09-22 15:39:44.827794')

        yield self.worker.outbounds.store_event_url(
            self.worker.channel_id, 'msg-21', self.url)

        yield self.worker.consume_ack(event)
        [req] = self.logging_api.requests

        self.assert_request(
            req,
            method='POST',
            headers={'content-type': ['application/json']},
            body=api_from_event(self.worker.channel_id, event))

    @inlineCallbacks
    def test_forward_ack_bad_response(self):
        self.patch_logger()

        event = TransportEvent(
            event_type='ack',
            user_message_id='msg-21',
            sent_message_id='msg-21',
            timestamp='2015-09-22 15:39:44.827794')

        yield self.worker.outbounds.store_event_url(
            self.worker.channel_id, 'msg-21', "%s/bad/" % self.url)

        yield self.worker.consume_ack(event)

        self.assert_was_logged(repr(event))
        self.assert_was_logged('500')
        self.assert_was_logged('test-error-response')

    @inlineCallbacks
    def test_forward_ack_no_message(self):
        self.patch_logger()

        event = TransportEvent(
            event_type='ack',
            user_message_id='msg-21',
            sent_message_id='msg-21',
            timestamp='2015-09-22 15:39:44.827794')

        yield self.worker.consume_ack(event)

        self.assertEqual(self.logging_api.requests, [])

    @inlineCallbacks
    def test_forward_nack(self):
        event = TransportEvent(
            event_type='nack',
            user_message_id='msg-21',
            nack_reason='too many foos',
            timestamp='2015-09-22 15:39:44.827794')

        yield self.worker.outbounds.store_event_url(
            self.worker.channel_id, 'msg-21', self.url)

        yield self.worker.consume_nack(event)
        [req] = self.logging_api.requests

        self.assert_request(
            req,
            method='POST',
            headers={'content-type': ['application/json']},
            body=api_from_event(self.worker.channel_id, event))

    @inlineCallbacks
    def test_forward_nack_bad_response(self):
        self.patch_logger()

        event = TransportEvent(
            event_type='nack',
            user_message_id='msg-21',
            nack_reason='too many foos',
            timestamp='2015-09-22 15:39:44.827794')

        yield self.worker.outbounds.store_event_url(
            self.worker.channel_id, 'msg-21', self.url)

        yield self.worker.consume_nack(event)

        self.assert_was_logged(repr(event))
        self.assert_was_logged('500')
        self.assert_was_logged('test-error-response')

    @inlineCallbacks
    def test_forward_nack_no_message(self):
        self.patch_logger()

        event = TransportEvent(
            event_type='nack',
            user_message_id='msg-21',
            nack_reason='too many foos',
            timestamp='2015-09-22 15:39:44.827794')

        yield self.worker.consume_nack(event)

        self.assertEqual(self.logging_api.requests, [])

    @inlineCallbacks
    def test_forward_dr(self):
        event = TransportEvent(
            event_type='delivery_report',
            user_message_id='msg-21',
            delivery_status='pending',
            timestamp='2015-09-22 15:39:44.827794')

        yield self.worker.outbounds.store_event_url(
            self.worker.channel_id, 'msg-21', self.url)

        yield self.worker.consume_delivery_report(event)
        [req] = self.logging_api.requests

        self.assert_request(
            req,
            method='POST',
            headers={'content-type': ['application/json']},
            body=api_from_event(self.worker.channel_id, event))

    @inlineCallbacks
    def test_forward_dr_bad_response(self):
        self.patch_logger()

        event = TransportEvent(
            event_type='delivery_report',
            user_message_id='msg-21',
            delivery_status='pending',
            timestamp='2015-09-22 15:39:44.827794')

        yield self.worker.outbounds.store_event_url(
            self.worker.channel_id, 'msg-21', "%s/bad/" % self.url)

        yield self.worker.consume_delivery_report(event)

        self.assert_was_logged(repr(event))
        self.assert_was_logged('500')
        self.assert_was_logged('test-error-response')

    @inlineCallbacks
    def test_forward_dr_no_message(self):
        self.patch_logger()

        event = TransportEvent(
            event_type='delivery_report',
            user_message_id='msg-21',
            delivery_status='pending',
            timestamp='2015-09-22 15:39:44.827794')

        yield self.worker.consume_delivery_report(event)

        self.assertEqual(self.logging_api.requests, [])

    @inlineCallbacks
    def test_forward_event_bad_event(self):
        self.patch_logger()

        event = TransportEvent(
            event_type='ack',
            user_message_id='msg-21',
            sent_message_id='msg-21',
            timestamp='2015-09-22 15:39:44.827794')

        event['event_type'] = 'bad'

        yield self.worker.outbounds.store_event_url(
            self.worker.channel_id, 'msg-21', self.url)

        yield self.worker.forward_event(event)

        self.assertEqual(self.logging_api.requests, [])
        self.assert_was_logged("Discarding unrecognised event %r" % (event,))
