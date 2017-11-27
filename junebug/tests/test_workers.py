import treq
from base64 import b64encode

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.client import HTTPConnectionPool

from vumi.application.tests.helpers import ApplicationHelper
from vumi.message import TransportUserMessage, TransportEvent, TransportStatus
from vumi.tests.helpers import PersistenceHelper

from junebug.utils import conjoin, api_from_event, api_from_status
from junebug.workers import ChannelStatusWorker, MessageForwardingWorker
from junebug.tests.helpers import JunebugTestBase, RequestLoggingApi


class TestMessageForwardingWorker(JunebugTestBase):
    @inlineCallbacks
    def setUp(self):
        self.logging_api = RequestLoggingApi()
        self.logging_api.setup()
        self.addCleanup(self.logging_api.teardown)
        self.url = self.logging_api.url

        self.worker = yield self.get_worker()
        connection_pool = HTTPConnectionPool(reactor, persistent=False)
        treq._utils.set_global_pool(connection_pool)

    @inlineCallbacks
    def get_worker(self, config=None, start=True):
        '''Get a new MessageForwardingWorker with the provided config'''
        if config is None:
            config = {}

        self.app_helper = ApplicationHelper(MessageForwardingWorker)
        yield self.app_helper.setup()
        self.addCleanup(self.app_helper.cleanup)

        persistencehelper = PersistenceHelper()
        yield persistencehelper.setup()
        self.addCleanup(persistencehelper.cleanup)

        config = conjoin(persistencehelper.mk_config({
            'transport_name': 'testtransport',
            'mo_message_url': self.url.decode('utf-8'),
            'inbound_ttl': 60,
            'outbound_ttl': 60 * 60 * 24 * 2,
            'metric_window': 1.0,
        }), config)

        worker = yield self.app_helper.get_application(config, start=start)
        returnValue(worker)

    @inlineCallbacks
    def assert_event_stored(self, event):
        key = '%s:outbound_messages:%s' % (
            self.worker.config['transport_name'], 'msg-21')
        event_json = yield self.worker.redis.hget(key, event['event_id'])
        self.assertEqual(event_json, event.to_json())

    @inlineCallbacks
    def test_channel_id(self):
        worker = yield self.get_worker({'transport_name': 'foo'})
        self.assertEqual(worker.channel_id, 'foo')

    @inlineCallbacks
    def test_send_message_http(self):
        '''A sent message should be forwarded to the configured URL if a URL
        is set.'''
        msg = TransportUserMessage.send(to_addr='+1234', content='testcontent')
        yield self.worker.consume_user_message(msg)
        [req] = self.logging_api.requests

        self.assert_request(req, method='POST', headers={
            'content-type': ['application/json']
        })

        self.assert_body_contains(req, to='+1234', content='testcontent')

    @inlineCallbacks
    def test_send_message_amqp(self):
        '''A sent message should be forwarded to the correct AMQP queue if
        the config option is set.'''
        worker = yield self.get_worker(config={
            'message_queue': 'testqueue'
        })
        msg = TransportUserMessage.send(to_addr='+1234', content='testcontent')
        yield worker.consume_user_message(msg)

        [dispatched_msg] = self.app_helper.get_dispatched(
            'testqueue', 'inbound', TransportUserMessage)

        self.assertEqual(dispatched_msg, msg)

    @inlineCallbacks
    def test_send_message_with_basic_auth(self):
        '''If there is an error sending a message to the configured URL, the
        error and message should be logged'''
        self.patch_logger()

        # Inject the auth parameters
        url = self.url.replace('http://', 'http://foo:bar@') + '/auth/'

        self.worker = yield self.get_worker({
            'transport_name': 'testtransport',
            'mo_message_url': url,
        })
        msg = TransportUserMessage.send(to_addr='+1234', content='testcontent')
        yield self.worker.consume_user_message(msg)

        [logged_request] = self.logging_api.requests
        self.assertEqual(logged_request, {
            'Authorization': ['Basic %s' % (b64encode('foo:bar'),)]
        })

    @inlineCallbacks
    def test_send_message_with_token_auth(self):
        '''If there is an error sending a message to the configured URL, the
        error and message should be logged'''
        self.patch_logger()

        self.worker = yield self.get_worker({
            'transport_name': 'testtransport',
            'mo_message_url': self.url + '/auth/',
            'mo_message_url_auth_token': 'the-auth-token'
        })
        msg = TransportUserMessage.send(to_addr='+1234', content='testcontent')
        yield self.worker.consume_user_message(msg)

        [logged_request] = self.logging_api.requests
        self.assertEqual(logged_request, {
            'Authorization': ['Token the-auth-token']
        })

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
    def test_send_message_imploding_response(self):
        '''If there is an error connecting to the configured URL, the
        error and message should be logged'''
        self.patch_logger()
        self.worker = yield self.get_worker({
            'transport_name': 'testtransport',
            'mo_message_url': self.url + '/implode/',
            })
        msg = TransportUserMessage.send(to_addr='+1234', content='testcontent')
        yield self.worker.consume_user_message(msg)

        self.assert_was_logged('Post to %s/implode/ failed because of' % (
            self.url,))
        self.assert_was_logged('ConnectionDone')

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
    def test_receive_message_amqp(self):
        '''A received message on the configured queue should be forwarded to
        the transport queue if the config option is set.'''
        worker = yield self.get_worker(config={
            'message_queue': 'testqueue'
        })
        msg = TransportUserMessage.send(to_addr='+1234', content='testcontent')
        yield self.app_helper.dispatch_outbound(
            msg, connector_name='testqueue')

        [dispatched_msg] = yield self.app_helper.wait_for_dispatched_outbound(
            connector_name=worker.transport_name)
        self.assertEqual(dispatched_msg, msg)

    @inlineCallbacks
    def test_forward_event_no_message_id(self):
        '''
        If we receive an event, and we don't have a message ID to associate
        the event to, then we should log the event and carry on.
        '''
        self.patch_logger()

        event = TransportEvent(
            event_type='ack',
            user_message_id=None,
            sent_message_id='msg-21',
            timestamp='2015-09-22 15:39:44.827794')

        yield self.worker.consume_ack(event)
        self.assert_was_logged('Cannot store event')
        self.assert_was_logged('Cannot find event URL')
        self.assert_was_logged('%r' % event)

    @inlineCallbacks
    def test_forward_ack_http(self):
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
        yield self.assert_event_stored(event)

    @inlineCallbacks
    def test_forward_ack_http_with_token_auth(self):
        event = TransportEvent(
            event_type='ack',
            user_message_id='msg-21',
            sent_message_id='msg-21',
            timestamp='2015-09-22 15:39:44.827794')

        yield self.worker.outbounds.store_event_url(
            self.worker.channel_id, 'msg-21', self.url + '/auth/')
        yield self.worker.outbounds.store_event_auth_token(
            self.worker.channel_id, 'msg-21', "the-auth-token"
        )

        yield self.worker.consume_ack(event)
        [req] = self.logging_api.requests

        self.assertEqual(req, {
            'Authorization': ['Token the-auth-token']
        })
        yield self.assert_event_stored(event)

    @inlineCallbacks
    def test_forward_ack_http_with_basic_auth(self):
        event = TransportEvent(
            event_type='ack',
            user_message_id='msg-21',
            sent_message_id='msg-21',
            timestamp='2015-09-22 15:39:44.827794')

        # Inject the auth parameters
        url = self.url.replace('http://', 'http://foo:bar@') + '/auth/'
        yield self.worker.outbounds.store_event_url(
            self.worker.channel_id, 'msg-21', url)

        yield self.worker.consume_ack(event)
        [req] = self.logging_api.requests

        self.assertEqual(req, {
            'Authorization': ['Basic %s' % (b64encode('foo:bar'),)]
        })
        yield self.assert_event_stored(event)

    @inlineCallbacks
    def test_forward_ack_amqp(self):
        '''A sent ack event should be forwarded to the correct AMQP queue if
        the config option is set.'''
        worker = yield self.get_worker(config={
            'message_queue': 'testqueue'
        })
        event = TransportEvent(
            event_type='ack',
            user_message_id='msg-21',
            sent_message_id='msg-21',
            timestamp='2015-09-22 15:39:44.827794')

        yield worker.consume_ack(event)

        [dispatched_msg] = self.app_helper.get_dispatched(
            'testqueue', 'event', TransportEvent)

        self.assertEqual(dispatched_msg['event_id'], event['event_id'])

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
        yield self.assert_event_stored(event)

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
        yield self.assert_event_stored(event)

    @inlineCallbacks
    def test_forward_nack_http(self):
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
        yield self.assert_event_stored(event)

    @inlineCallbacks
    def test_forward_nack_amqp(self):
        '''A sent nack event should be forwarded to the correct AMQP queue if
        the config option is set.'''
        worker = yield self.get_worker(config={
            'message_queue': 'testqueue'
        })
        event = TransportEvent(
            event_type='nack',
            user_message_id='msg-21',
            nack_reason='too many foos',
            timestamp='2015-09-22 15:39:44.827794')

        yield worker.consume_nack(event)

        [dispatched_msg] = self.app_helper.get_dispatched(
            'testqueue', 'event', TransportEvent)

        self.assertEqual(dispatched_msg['event_id'], event['event_id'])

    @inlineCallbacks
    def test_forward_nack_bad_response(self):
        self.patch_logger()

        event = TransportEvent(
            event_type='nack',
            user_message_id='msg-21',
            nack_reason='too many foos',
            timestamp='2015-09-22 15:39:44.827794')

        yield self.worker.outbounds.store_event_url(
            self.worker.channel_id, 'msg-21', "%s/bad/" % (self.url,))

        yield self.worker.consume_nack(event)

        self.assert_was_logged(repr(event))
        self.assert_was_logged('500')
        self.assert_was_logged('test-error-response')
        yield self.assert_event_stored(event)

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
        yield self.assert_event_stored(event)

    @inlineCallbacks
    def test_forward_dr_http(self):
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
        yield self.assert_event_stored(event)

    @inlineCallbacks
    def test_forward_dr_amqp(self):
        '''A sent delivery report event should be forwarded to the correct
        AMQP queue if the config option is set.'''
        worker = yield self.get_worker(config={
            'message_queue': 'testqueue'
        })
        event = TransportEvent(
            event_type='delivery_report',
            user_message_id='msg-21',
            delivery_status='pending',
            timestamp='2015-09-22 15:39:44.827794')

        yield worker.consume_nack(event)

        [dispatched_msg] = self.app_helper.get_dispatched(
            'testqueue', 'event', TransportEvent)

        self.assertEqual(dispatched_msg['event_id'], event['event_id'])

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
        yield self.assert_event_stored(event)

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
        yield self.assert_event_stored(event)

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

        yield self.worker._forward_event(event)

        self.assertEqual(self.logging_api.requests, [])
        self.assert_was_logged("Discarding unrecognised event %r" % (event,))

    @inlineCallbacks
    def test_outbound_message_rates(self):
        '''Outbound messages should increase the message send rates.'''
        clock = self.patch_message_rate_clock()

        worker = yield self.get_worker({
            'message_rate_bucket': 1.0,
        })

        msg = TransportUserMessage.send(to_addr='+1234', content='testcontent')
        yield worker.consume_user_message(msg)

        clock.advance(1)

        self.assertEqual((yield worker.message_rate.get_messages_per_second(
            'testtransport', 'inbound', 1.0)), 1.0)

    @inlineCallbacks
    def test_submitted_event_rates(self):
        '''Acknowledge events should increase the submitted event rates.'''
        clock = self.patch_message_rate_clock()

        worker = yield self.get_worker({
            'message_rate_bucket': 1.0,
        })

        event = TransportEvent(
            event_type='ack',
            user_message_id='msg-21',
            sent_message_id='msg-21',
            timestamp='2015-09-22 15:39:44.827794')
        yield worker.consume_ack(event)

        clock.advance(1)

        self.assertEqual((yield worker.message_rate.get_messages_per_second(
            'testtransport', 'submitted', 1.0)), 1.0)

    @inlineCallbacks
    def test_rejected_event_rates(self):
        '''Not-acknowledge events should increase the rejected event rates.'''
        clock = self.patch_message_rate_clock()

        worker = yield self.get_worker({
            'message_rate_bucket': 1.0,
        })

        event = TransportEvent(
            event_type='nack',
            nack_reason='bad message',
            user_message_id='msg-21',
            timestamp='2015-09-22 15:39:44.827794')
        yield worker.consume_nack(event)

        clock.advance(1)

        self.assertEqual((yield worker.message_rate.get_messages_per_second(
            'testtransport', 'rejected', 1.0)), 1.0)

    @inlineCallbacks
    def test_delivery_succeeded_event_rates(self):
        '''Delivered delivery reports should increase the delivery_succeeded
        event rates.'''
        clock = self.patch_message_rate_clock()

        worker = yield self.get_worker({
            'message_rate_bucket': 1.0,
        })

        event = TransportEvent(
            event_type='delivery_report',
            user_message_id='msg-21',
            delivery_status='delivered',
            timestamp='2015-09-22 15:39:44.827794')
        yield worker.consume_delivery_report(event)

        clock.advance(1)

        self.assertEqual((yield worker.message_rate.get_messages_per_second(
            'testtransport', 'delivery_succeeded', 1.0)), 1.0)

    @inlineCallbacks
    def test_delivery_failed_event_rates(self):
        '''Failed delivery reports should increase the delivery_failed
        event rates.'''
        clock = self.patch_message_rate_clock()

        worker = yield self.get_worker({
            'message_rate_bucket': 1.0,
        })

        event = TransportEvent(
            event_type='delivery_report',
            user_message_id='msg-21',
            delivery_status='failed',
            timestamp='2015-09-22 15:39:44.827794')
        yield worker.consume_delivery_report(event)

        clock.advance(1)

        self.assertEqual((yield worker.message_rate.get_messages_per_second(
            'testtransport', 'delivery_failed', 1.0)), 1.0)

    @inlineCallbacks
    def test_delivery_pending_event_rates(self):
        '''Pending delivery reports should increase the delivery_pending
        event rates.'''
        clock = self.patch_message_rate_clock()

        worker = yield self.get_worker({
            'message_rate_bucket': 1.0,
        })

        event = TransportEvent(
            event_type='delivery_report',
            user_message_id='msg-21',
            delivery_status='pending',
            timestamp='2015-09-22 15:39:44.827794')
        yield worker.consume_delivery_report(event)

        clock.advance(1)

        self.assertEqual((yield worker.message_rate.get_messages_per_second(
            'testtransport', 'delivery_pending', 1.0)), 1.0)

    @inlineCallbacks
    def test_teardown_without_startup(self):
        '''If the teardown method is called before the worker was started up
        correctly, the teardown should still succeed.'''
        worker = yield self.get_worker(start=False)

        self.assertEqual(getattr(worker, 'redis', None), None)

        yield worker.teardown_application()


class TestChannelStatusWorker(JunebugTestBase):
    @inlineCallbacks
    def setUp(self):
        self.worker = yield self.get_worker()
        self.logging_api = RequestLoggingApi()
        self.logging_api.setup()
        self.addCleanup(self.logging_api.teardown)

        connection_pool = HTTPConnectionPool(reactor, persistent=False)
        treq._utils.set_global_pool(connection_pool)

    @inlineCallbacks
    def get_worker(self, config=None):
        '''Get a new ChannelStatusWorker with the provided config'''
        if config is None:
            config = {}

        app_helper = ApplicationHelper(ChannelStatusWorker)
        yield app_helper.setup()
        self.addCleanup(app_helper.cleanup)

        persistencehelper = PersistenceHelper()
        yield persistencehelper.setup()
        self.addCleanup(persistencehelper.cleanup)

        config = conjoin(persistencehelper.mk_config({
            'channel_id': 'testchannel',
        }), config)

        worker = yield app_helper.get_application(config)
        returnValue(worker)

    @inlineCallbacks
    def test_status_stored_in_redis(self):
        '''The published status gets consumed and stored in redis under the
        correct key'''
        status = TransportStatus(
            component='foo',
            status='ok',
            type='bar',
            message='Bar')
        yield self.worker.consume_status(status)

        redis_status = yield self.worker.store.redis.hget(
            'testchannel:status', 'foo')

        self.assertEqual(redis_status, status.to_json())

    @inlineCallbacks
    def test_status_sent_to_status_url(self):
        '''The published status gets consumed and sent to the configured
        status_url'''
        worker = yield self.get_worker({
            'channel_id': 'channel-23',
            'status_url': self.logging_api.url,
        })

        status = TransportStatus(
            component='foo',
            status='ok',
            type='bar',
            message='Bar')

        yield worker.consume_status(status)

        [req] = self.logging_api.requests

        self.assert_request(
            req,
            method='POST',
            headers={'content-type': ['application/json']},
            body=api_from_status('channel-23', status))

    @inlineCallbacks
    def test_status_send_to_status_url_bad_response(self):
        '''If there is an error sending a status to the configured status_url,
        the error and status should be logged'''
        self.patch_logger()

        worker = yield self.get_worker({
            'channel_id': 'channel-23',
            'status_url': "%s/bad/" % (self.logging_api.url,),
        })

        status = TransportStatus(
            component='foo',
            status='ok',
            type='bar',
            message='Bar')

        yield worker.consume_status(status)

        self.assert_was_logged('500')
        self.assert_was_logged('test-error-response')
        self.assert_was_logged(repr(status))
