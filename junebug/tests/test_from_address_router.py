from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log
import uuid
from vumi.tests.helpers import MessageHelper, PersistenceHelper, WorkerHelper

from junebug.router import (
    Router, InvalidRouterConfig, InvalidRouterDestinationConfig)
from junebug.router.from_address import FromAddressRouter
from junebug.tests.helpers import JunebugTestBase
from junebug.utils import conjoin, api_from_message


class TestRouter(JunebugTestBase):
    DEFAULT_ROUTER_WORKER_CONFIG = {
        'inbound_ttl': 60,
        'outbound_ttl': 60 * 60 * 24 * 2,
        'metric_window': 1.0,
        'destinations': [],
    }

    @inlineCallbacks
    def setUp(self):
        yield self.start_server()

        self.workerhelper = WorkerHelper()
        self.addCleanup(self.workerhelper.cleanup)

        self.persistencehelper = PersistenceHelper()
        yield self.persistencehelper.setup()
        self.addCleanup(self.persistencehelper.cleanup)

        self.messagehelper = MessageHelper()
        self.addCleanup(self.messagehelper.cleanup)

    @inlineCallbacks
    def get_router_worker(self, config=None):
        if config is None:
            config = {}

        config = conjoin(
            self.persistencehelper.mk_config(
                self.DEFAULT_ROUTER_WORKER_CONFIG),
            config)

        FromAddressRouter._create_worker = self.workerhelper.get_worker
        worker = yield self.workerhelper.get_worker(FromAddressRouter, config)
        returnValue(worker)

    @inlineCallbacks
    def test_validate_router_config_invalid_channel_uuid(self):
        """
        If the provided channel UUID is not a valid UUID a config error should
        be raised
        """
        with self.assertRaises(InvalidRouterConfig) as e:
            yield FromAddressRouter.validate_router_config(
                self.api, {'channel': "bad-uuid"})

        self.assertEqual(
            e.exception.message,
            "Field 'channel' is not a valid UUID")

    @inlineCallbacks
    def test_validate_router_config_missing_channel(self):
        """
        If the provided channel UUID is not for an existing channel, a config
        error should be raised
        """
        channel_id = str(uuid.uuid4())

        with self.assertRaises(InvalidRouterConfig) as e:
            yield FromAddressRouter.validate_router_config(
                self.api, {'channel': channel_id})

        self.assertEqual(
            e.exception.message,
            "Channel {} does not exist".format(channel_id))

    @inlineCallbacks
    def test_validate_router_config_existing_destination(self):
        """
        If the specified channel already has a destination specified, then
        a config error should be raised
        """
        channel = yield self.create_channel(self.api.service, self.redis)

        with self.assertRaises(InvalidRouterConfig) as e:
            yield FromAddressRouter.validate_router_config(
                self.api, {'channel': channel.id})

        self.assertEqual(
            e.exception.message,
            "Channel {} already has a destination specified".format(
                channel.id))

    @inlineCallbacks
    def test_validate_router_config_existing_router(self):
        """
        If an existing router is already listening to the specified channel,
        then a config error should be raised
        """
        channel = yield self.create_channel(
            self.api.service, self.redis, properties={
                'type': 'telnet',
                'config': {
                    'twisted_endpoint': 'tcp:0',
                },
            })

        config = self.create_router_config(
            config={'test': 'pass', 'channel': channel.id})
        router = Router(self.api, config)
        yield router.save()
        router.start(self.api.service)

        with self.assertRaises(InvalidRouterConfig) as e:
            yield FromAddressRouter.validate_router_config(
                self.api, {'channel': channel.id})

        self.assertEqual(
            e.exception.message,
            "Router {} is already routing channel {}".format(
                router.id, channel.id))

    @inlineCallbacks
    def test_get_destination_channel(self):
        """
        The get_destination_channel method should return the channel that was
        configured on the router.
        """
        router = yield self.get_router_worker({
            'destinations': [{
                'id': "test-destination1",
                'amqp_queue': "testqueue1",
                'config': {'regular_expression': '^1.*$'},
            }, {
                'id': "test-destination2",
                'amqp_queue': "testqueue2",
                'config': {'regular_expression': '^2.*$'},
            }],
            'channel': '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14',
        })

        channel_id = yield router.get_destination_channel(
            "test-destination1", {})
        self.assertEqual(channel_id, '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14')

        channel_id = yield router.get_destination_channel(
            "test-destination2", {})
        self.assertEqual(channel_id, '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14')

    @inlineCallbacks
    def test_validate_router_destination_config_invalid_regex(self):
        """
        If invalid regex is passed into the regex field, a config error should
        be raised
        """
        with self.assertRaises(InvalidRouterDestinationConfig) as e:
            yield FromAddressRouter.validate_destination_config(
                self.api, {'regular_expression': "("})

        self.assertEqual(
            e.exception.message,
            "Field 'regular_expression' is not a valid regular expression: "
            "unbalanced parenthesis")

    @inlineCallbacks
    def test_validate_router_destination_config_missing_field(self):
        """
        regular_expression should be a required field
        """
        with self.assertRaises(InvalidRouterDestinationConfig) as e:
            yield FromAddressRouter.validate_destination_config(
                self.api, {})

        self.assertEqual(
            e.exception.message,
            "Missing required config field 'regular_expression'")

    @inlineCallbacks
    def test_inbound_message_routing(self):
        """
        Inbound messages should be routed to the correct destination worker(s)
        """
        yield self.get_router_worker({
            'destinations': [{
                'id': "test-destination1",
                'amqp_queue': "testqueue1",
                'config': {'regular_expression': '^1.*$'},
            }, {
                'id': "test-destination2",
                'amqp_queue': "testqueue2",
                'config': {'regular_expression': '^2.*$'},
            }, {
                'id': "test-destination3",
                'amqp_queue': "testqueue3",
                'config': {'regular_expression': '^2.*$'},
            }],
            'channel': '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14',
        })

        inbound = self.messagehelper.make_inbound(
            'test message', to_addr='1234')
        yield self.workerhelper.dispatch_inbound(
            inbound, '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14')
        [message] = yield self.workerhelper.wait_for_dispatched_inbound(
            connector_name='testqueue1')
        self.assertEqual(inbound, message)

        inbound = self.messagehelper.make_inbound(
            'test message', to_addr='2234')
        yield self.workerhelper.dispatch_inbound(
            inbound, '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14')
        [message] = yield self.workerhelper.wait_for_dispatched_inbound(
            connector_name='testqueue2')
        self.assertEqual(inbound, message)
        [message] = yield self.workerhelper.wait_for_dispatched_inbound(
            connector_name='testqueue3')
        self.assertEqual(inbound, message)

    @inlineCallbacks
    def test_inbound_message_routing_no_to_addr(self):
        """
        If an inbound message doesn't have a to address, then an error should
        be logged
        """
        yield self.get_router_worker({
            'channel': '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14',
        })
        logs = []
        log.addObserver(logs.append)

        inbound = self.messagehelper.make_inbound('test message', to_addr=None)
        yield self.workerhelper.dispatch_inbound(
            inbound, '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14')
        [error_log] = logs
        self.assertIn(
            "Message has no to address, cannot route message: ",
            error_log['log_text'])

    @inlineCallbacks
    def test_inbound_event_routing(self):
        """
        Inbound events should be routed to the correct destination worker(s)
        """
        yield self.get_router_worker({
            'destinations': [{
                'id': "test-destination1",
                'amqp_queue': "testqueue1",
                'config': {'regular_expression': '^1.*$'},
            }, {
                'id': "test-destination2",
                'amqp_queue': "testqueue2",
                'config': {'regular_expression': '^2.*$'},
            }, {
                'id': "test-destination3",
                'amqp_queue': "testqueue3",
                'config': {'regular_expression': '^2.*$'},
            }],
            'channel': '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14',
        })

        outbound = self.messagehelper.make_outbound(
            "test message", from_addr="1234")
        yield self.workerhelper.dispatch_outbound(outbound, 'testqueue1')
        ack = self.messagehelper.make_ack(outbound)
        yield self.workerhelper.dispatch_event(
            ack, '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14')
        [event] = yield self.workerhelper.wait_for_dispatched_events(
            connector_name='testqueue1')
        self.assertEqual(ack, event)

        outbound = self.messagehelper.make_outbound(
            "test message", from_addr="2234")
        yield self.workerhelper.dispatch_outbound(outbound, 'testqueue2')
        ack = self.messagehelper.make_ack(outbound)
        yield self.workerhelper.dispatch_event(
            ack, '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14')
        [event] = yield self.workerhelper.wait_for_dispatched_events(
            connector_name='testqueue2')
        self.assertEqual(ack, event)
        [event] = yield self.workerhelper.wait_for_dispatched_events(
            connector_name='testqueue3')
        self.assertEqual(ack, event)

    @inlineCallbacks
    def test_inbound_event_store(self):
        """
        Inbound events should be stored to the correct destinations
        """
        worker = yield self.get_router_worker({
            'destinations': [{
                'id': "test-destination1",
                'amqp_queue': "testqueue1",
                'config': {'regular_expression': '^1.*$'},
            }, {
                'id': "test-destination2",
                'amqp_queue': "testqueue2",
                'config': {'regular_expression': '^2.*$'},
            }, {
                'id': "test-destination3",
                'amqp_queue': "testqueue3",
                'config': {'regular_expression': '^2.*$'},
            }],
            'channel': '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14',
        })

        message_worker = worker.namedServices['test-destination2']

        outbound = self.messagehelper.make_outbound(
            "test message", from_addr="2234")
        yield self.workerhelper.dispatch_outbound(outbound, 'testqueue2')
        ack = self.messagehelper.make_ack(outbound)
        yield self.workerhelper.dispatch_event(
            ack, '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14')

        [event] = yield self.workerhelper.wait_for_dispatched_events(
            connector_name='testqueue2')

        [stored_event] = yield message_worker.outbounds.load_all_events(
            "test-destination2", outbound["message_id"])

        self.assertEqual(event, stored_event)

    @inlineCallbacks
    def test_inbound_event_routing_no_inbound_message(self):
        """
        If no message can be found in the message store for the event, then an
        error message should be logged
        """
        yield self.get_router_worker({
            'destinations': [{
                'id': "test-destination1",
                'amqp_queue': "testqueue1",
                'config': {'regular_expression': '^1.*$'},
            }],
            'channel': '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14',
        })
        logs = []
        log.addObserver(logs.append)

        ack = self.messagehelper.make_ack()
        yield self.workerhelper.dispatch_event(
            ack, '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14')
        [error_log] = logs
        self.assertIn("Cannot find message", error_log['log_text'])
        self.assertIn("for event, not routing event: ", error_log['log_text'])

    @inlineCallbacks
    def test_inbound_event_routing_no_from_address(self):
        """
        If the message for an event doesn't have a from address, then an error
        message should be logged
        """
        yield self.get_router_worker({
            'destinations': [{
                'id': "test-destination1",
                'amqp_queue': "testqueue1",
                'config': {'regular_expression': '^1.*$'},
            }],
            'channel': '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14',
        })
        logs = []
        log.addObserver(logs.append)

        outbound = self.messagehelper.make_outbound(
            "test message", from_addr=None)
        yield self.workerhelper.dispatch_outbound(outbound, 'testqueue1')
        ack = self.messagehelper.make_ack(outbound)
        yield self.workerhelper.dispatch_event(
            ack, '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14')
        [error_log] = logs
        self.assertIn(
            "Message has no from address, cannot route event: ",
            error_log['log_text'])

    @inlineCallbacks
    def test_outbound_message_routing(self):
        """
        Outbound messages should be routed to the configured channel, no matter
        which destination they came from. They should also be stored so that
        events can be routed correctly.
        """
        worker = yield self.get_router_worker({
            'destinations': [{
                'id': "test-destination1",
                'amqp_queue': "testqueue1",
                'config': {'regular_expression': '^1.*$'},
            }, {
                'id': "test-destination2",
                'amqp_queue': "testqueue2",
                'config': {'regular_expression': '^2.*$'},
            }],
            'channel': '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14',
        })

        outbound = self.messagehelper.make_outbound('test message')
        yield self.workerhelper.dispatch_outbound(outbound, 'testqueue1')
        [message] = yield self.workerhelper.wait_for_dispatched_outbound(
            connector_name='41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14')
        self.assertEqual(outbound, message)
        stored_message = yield worker.outbounds.load_message(
            '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14', outbound['message_id'])
        self.assertEqual(api_from_message(outbound), stored_message)

        yield self.workerhelper.clear_dispatched_outbound(
            connector_name='41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14')
        outbound = self.messagehelper.make_outbound('test message')
        yield self.workerhelper.dispatch_outbound(outbound, 'testqueue2')
        [message] = yield self.workerhelper.wait_for_dispatched_outbound(
            connector_name='41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14')
        self.assertEqual(outbound, message)
        stored_message = yield worker.outbounds.load_message(
            '41e58f4a-2acc-442f-b3e5-3cf2b2f1cf14', outbound['message_id'])
        self.assertEqual(api_from_message(outbound), stored_message)
