import json
from twisted.internet.defer import inlineCallbacks, returnValue
from vumi.tests.helpers import (
    MessageHelper, PersistenceHelper, WorkerHelper, VumiTestCase)

import junebug
from junebug.utils import conjoin
from junebug.logging_service import JunebugLoggerService
from junebug.router import (
    Router, InvalidRouterConfig, InvalidRouterDestinationConfig, RouterNotFound
)
from junebug.router.base import InvalidRouterType
from junebug.tests.helpers import JunebugTestBase, TestRouter, DummyLogFile


class RouterTests(JunebugTestBase):
    @inlineCallbacks
    def setUp(self):
        yield self.start_server()

    def test_creating_uuid(self):
        """If a router isn't given an id, then it should generate one."""
        config = self.create_router_config()
        router = Router(self.api, config)
        self.assertFalse(router.router_config.get('id') is None)

        config = self.create_router_config(id='test-uuid')
        router = Router(self.api, config)
        self.assertEqual(router.router_config.get('id'), 'test-uuid')

    @inlineCallbacks
    def test_get_all(self):
        """get_all should return a list of all router ids"""
        self.assertEqual(
            (yield Router.get_all(self.api.router_store)), [])

        config = self.create_router_config(id='test-uuid1')
        yield self.api.router_store.save_router(config)
        self.assertEqual(
            (yield Router.get_all(self.api.router_store)), ['test-uuid1'])

        config = self.create_router_config(id='test-uuid2')
        yield self.api.router_store.save_router(config)
        self.assertEqual(
            (yield Router.get_all(self.api.router_store)),
            ['test-uuid1', 'test-uuid2'])

    @inlineCallbacks
    def test_save(self):
        """save should save the configuration of the router and all the
        destinations into the router store"""
        config = self.create_router_config()
        router = Router(self.api, config)
        dest_config = self.create_destination_config()
        destination = router.add_destination(dest_config)

        self.assertEqual((yield self.api.router_store.get_router_list()), [])
        self.assertEqual(
            (yield self.api.router_store.get_router_destination_list(
                router.id)), [])
        yield router.save()
        self.assertEqual(
            (yield self.api.router_store.get_router_list()), [router.id])
        self.assertEqual(
            (yield self.api.router_store.get_router_destination_list(
                router.id)), [destination.id])

    @inlineCallbacks
    def test_validate_config(self):
        """validate_config should run the validate config function on the
        router worker class"""
        config = self.create_router_config(config={'test': 'pass'})
        router = Router(self.api, config)
        yield router.validate_config()

        with self.assertRaises(InvalidRouterConfig):
            config = self.create_router_config(config={'test': 'fail'})
            router = Router(self.api, config)
            yield router.validate_config()

    @inlineCallbacks
    def test_validate_config_invalid_worker_name(self):
        """If validate_config is given a config with an unknown worker name,
        an appropriate error should be raised."""
        config = self.create_router_config(type='invalid')
        router = Router(self.api, config)

        with self.assertRaises(InvalidRouterType):
            yield router.validate_config()

    @inlineCallbacks
    def test_validate_destination_config(self):
        """validate_destination_config should run the validate destination
        config on the router worker class"""
        router_config = self.create_router_config()
        router = Router(self.api, router_config)

        destination_config = {'target': 'valid'}
        yield router.validate_destination_config(destination_config)

        with self.assertRaises(InvalidRouterDestinationConfig):
            destination_config = {'target': 'invalid'}
            yield router.validate_destination_config(destination_config)

    def test_start(self):
        """start should start the router worker with the correct config"""
        config = self.create_router_config()
        router = Router(self.api, config)
        router.start(self.service)

        router_worker = self.service.namedServices[router.id]
        self.assertEqual(router_worker.parent, self.service)
        router_worker_config = config['config']
        for k, v in router_worker_config.items():
            self.assertEqual(router_worker.config[k], v)

    @inlineCallbacks
    def test_start_all(self):
        """start_all should start all of the stored routers"""
        config = self.create_router_config()
        router = Router(self.api, config)
        yield router.save()

        yield Router.start_all_routers(self.api)

        router_worker = self.service.namedServices[router.id]
        self.assertEqual(router_worker.parent, self.service)
        router_worker_config = config['config']
        for k, v in router_worker_config.items():
            self.assertEqual(router_worker.config[k], v)

    @inlineCallbacks
    def test_stop(self):
        """stop should stop the router worker if it is running"""
        config = self.create_router_config()
        router = Router(self.api, config)
        router.start(self.service)

        self.assertIn(router.id, self.service.namedServices)

        yield router.stop()

        self.assertNotIn(router.id, self.service.namedServices)

    @inlineCallbacks
    def test_stop_already_stopped(self):
        """Calling stop on a non-running router should not raise any
        exceptions"""

        config = self.create_router_config()
        router = Router(self.api, config)
        router.start(self.service)

        self.assertIn(router.id, self.service.namedServices)

        yield router.stop()

        self.assertNotIn(router.id, self.service.namedServices)

        yield router.stop()

    @inlineCallbacks
    def test_status(self):
        """status should return the current config of the router"""
        config = self.create_router_config()
        router = Router(self.api, config)
        status = yield router.status()
        self.assertEqual(status, router.router_config)

    @inlineCallbacks
    def test_start_router_logging(self):
        '''When the router is started, the logging worker should be started
        along with it.'''
        config = self.create_router_config()
        router = Router(self.api, config)
        router.start(self.service)
        router_logger = yield router.router_worker.getServiceNamed(
            'Junebug Worker Logger')

        self.assertTrue(isinstance(router_logger, JunebugLoggerService))

    @inlineCallbacks
    def test_router_logging(self):
        '''All logs from the router should go to the logging worker.'''
        router = yield self.create_test_router(self.service)

        router_logger = router.router_worker.getServiceNamed(
            'Junebug Worker Logger')

        router_logger.startService()
        router.router_worker.test_log('Test message1')
        router.router_worker.test_log('Test message2')

        [log1, log2] = router_logger.logfile.logs
        self.assertEqual(json.loads(log1)['message'], 'Test message1')
        self.assertEqual(json.loads(log2)['message'], 'Test message2')

    @inlineCallbacks
    def test_multiple_router_logging(self):
        '''All logs from the router should go to the logging worker.'''
        self.patch(junebug.logging_service, 'LogFile', DummyLogFile)

        router1 = yield self.create_test_router(self.service)
        router2 = yield self.create_test_router(self.service)

        router_logger1 = router1.router_worker.getServiceNamed(
            'Junebug Worker Logger')

        router_logger2 = router2.router_worker.getServiceNamed(
            'Junebug Worker Logger')

        router_logger1.startService()
        router_logger2.startService()
        router1.router_worker.test_log('Test message1')
        router1.router_worker.test_log('Test message2')

        [log1, log2] = router_logger1.logfile.logs
        self.assertEqual(json.loads(log1)['message'], 'Test message1')
        self.assertEqual(json.loads(log2)['message'], 'Test message2')

        router2.router_worker.test_log('Test message3')

        [log3] = router_logger2.logfile.logs
        self.assertEqual(json.loads(log3)['message'], 'Test message3')

    @inlineCallbacks
    def test_from_id(self):
        """from_id should be able to restore a router, given just the id"""
        config = self.create_router_config()
        router = Router(self.api, config)
        yield router.save()
        router.start(self.api.service)

        restored_router = yield Router.from_id(
            self.api, router.router_config['id'])

        self.assertEqual(router.router_config, restored_router.router_config)
        self.assertEqual(router.router_worker, restored_router.router_worker)

    @inlineCallbacks
    def test_from_id_doesnt_exist(self):
        """If we don't have a router for the specified ID, then we should raise
        the appropriate error"""
        with self.assertRaises(RouterNotFound):
            yield Router.from_id(self.api, 'bad-router-id')

    @inlineCallbacks
    def test_delete_router(self):
        """Removes the router config from the store"""
        config = self.create_router_config()
        router = Router(self.api, config)
        yield router.save()
        self.assertEqual(
            (yield self.api.router_store.get_router_list()),
            [router.router_config['id']])

        yield router.delete()
        self.assertEqual((yield self.api.router_store.get_router_list()), [])

    @inlineCallbacks
    def test_delete_router_not_in_store(self):
        """Removing a non-existing router should not result in an error"""
        config = self.create_router_config()
        router = Router(self.api, config)
        self.assertEqual((yield self.api.router_store.get_router_list()), [])

        yield router.delete()
        self.assertEqual((yield self.api.router_store.get_router_list()), [])

    def test_add_destination(self):
        """add_destination should create and add the destination"""
        config = self.create_router_config()
        router = Router(self.api, config)

        self.assertEqual(router.destinations, {})

        destination = router.add_destination(self.create_destination_config())

        self.assertEqual(router.destinations, {destination.id: destination})

    def test_destinations_are_passed_to_router_worker(self):
        """The destination configs should be passed to the router worker when
        the router is started."""
        config = self.create_router_config()
        router = Router(self.api, config)
        destination_config = self.create_destination_config()
        destination = router.add_destination(destination_config)

        router.start(self.service)
        router_worker = self.service.namedServices[router.id]
        self.assertEqual(
            router_worker.config['destinations'],
            [destination.destination_config])

    @inlineCallbacks
    def test_destination_save(self):
        """Saving a destination should save the destination's configuration to
        the router store"""
        router_store = self.api.router_store
        router_config = self.create_router_config()
        router = Router(self.api, router_config)
        destination_config = self.create_destination_config()
        destination = router.add_destination(destination_config)

        self.assertEqual(
            (yield router_store.get_router_destination_list(router.id)), [])
        yield destination.save()
        self.assertEqual(
            (yield router_store.get_router_destination_list(router.id)),
            [destination.id])

    @inlineCallbacks
    def test_destination_status(self):
        """Getting the destination status should return the configuration of
        the destination"""
        router_config = self.create_router_config()
        router = Router(self.api, router_config)
        destination_config = self.create_destination_config()
        destination = router.add_destination(destination_config)

        self.assertEqual(destination_config, (yield destination.status()))

    @inlineCallbacks
    def test_destinations_restored_on_router_from_id(self):
        """Creating a router object from id should also restore the
        destinations for that router"""
        router_config = self.create_router_config()
        router = Router(self.api, router_config)
        router.start(self.api.service)
        destination_config = self.create_destination_config()
        destination = router.add_destination(destination_config)
        yield router.save()

        restored_router = yield Router.from_id(self.api, router.id)
        self.assertEqual(
            router.destinations.keys(), restored_router.destinations.keys())
        self.assertEqual(
            router.destinations[destination.id].destination_config,
            restored_router.destinations[destination.id].destination_config)

    def test_get_destination_list(self):
        """Getting the destination list of a router should return a list of
        destination ids for that router"""
        router_config = self.create_router_config()
        router = Router(self.api, router_config)
        router.start(self.api.service)
        destination_config = self.create_destination_config()
        destination = router.add_destination(destination_config)

        self.assertEqual(router.get_destination_list(), [destination.id])

    @inlineCallbacks
    def test_remove_destination(self):
        """Removing a destination should remove it from the router store and
        the list of destinations on the router."""
        router_config = self.create_router_config()
        router = Router(self.api, router_config)

        destination_config = self.create_destination_config()
        destination = router.add_destination(destination_config)

        yield router.save()

        self.assertIn(destination.id, router.destinations)
        self.assertIn(
            destination.id,
            (yield self.api.router_store.get_router_destination_list(
                router.id))
        )

        yield destination.delete()

        self.assertNotIn(destination.id, router.destinations)
        self.assertNotIn(
            destination.id,
            (yield self.api.router_store.get_router_destination_list(
                router.id))
        )


class TestBaseRouterWorker(VumiTestCase, JunebugTestBase):
    DEFAULT_ROUTER_WORKER_CONFIG = {
        'inbound_ttl': 60,
        'outbound_ttl': 60 * 60 * 24 * 2,
        'metric_window': 1.0,
        'destinations': [],
    }

    @inlineCallbacks
    def setUp(self):
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

        TestRouter._create_worker = self.workerhelper.get_worker
        worker = yield self.workerhelper.get_worker(TestRouter, config)
        returnValue(worker)

    @inlineCallbacks
    def test_start_router_worker_no_destinations(self):
        """
        If there are no destinations specified, no workers should be started.
        The setup_router function should be called on the implementation.
        """
        worker = yield self.get_router_worker()
        self.assertEqual(len(worker.namedServices), 0)
        self.assertTrue(worker.setup_called)

    @inlineCallbacks
    def test_start_router_with_destinations(self):
        """
        If there are destinations specified, then a worker should be started
        for every destination.
        """
        worker = yield self.get_router_worker({
            'destinations': [
                {
                    'id': 'test-destination1',
                },
                {
                    'id': 'test-destination2',
                },
            ],
        })
        self.assertTrue(worker.setup_called)
        self.assertEqual(sorted(worker.namedServices.keys()), [
            'test-destination1', 'test-destination2'])

        for connector in worker.connectors.values():
            self.assertFalse(connector.paused)

    @inlineCallbacks
    def test_teardown_router(self):
        """
        Tearing down a router should pause all connectors, and call the
        teardown method of the router implementation
        """
        worker = yield self.get_router_worker({
            'destinations': [{'id': 'test-destination1'}],
        })

        self.assertFalse(worker.teardown_called)
        for connector in worker.connectors.values():
            self.assertFalse(connector.paused)

        yield worker.teardown_worker()

        self.assertTrue(worker.teardown_called)
        for connector in worker.connectors.values():
            self.assertTrue(connector.paused)

    @inlineCallbacks
    def test_consume_channel(self):
        """
        consume_channel should set up the appropriate connector, as well as
        attach the specified callbacks for messages and events.
        """
        worker = yield self.get_router_worker({})

        messages = []
        events = []

        def message_callback(channelid, message):
            assert channelid == 'testchannel'
            messages.append(message)

        def event_callback(channelid, event):
            assert channelid == 'testchannel'
            events.append(event)

        yield worker.consume_channel(
            'testchannel', message_callback, event_callback)

        # Because this is only called in setup, and we're creating connectors
        # after setup, we need to unpause them
        worker.unpause_connectors()

        self.assertEqual(messages, [])
        inbound = self.messagehelper.make_inbound('test message')
        yield self.workerhelper.dispatch_inbound(inbound, 'testchannel')
        self.assertEqual(messages, [inbound])

        self.assertEqual(events, [])
        event = self.messagehelper.make_ack()
        yield self.workerhelper.dispatch_event(event, 'testchannel')
        self.assertEqual(events, [event])

    @inlineCallbacks
    def test_send_inbound_to_destination(self):
        """
        send_inbound_to_destination should send the provided inbound message
        to the specified destination worker
        """
        worker = yield self.get_router_worker({
            'destinations': [{
                'id': 'test-destination',
                'amqp_queue': 'testqueue',
            }],
        })

        inbound = self.messagehelper.make_inbound('test_message')
        yield worker.send_inbound_to_destination('test-destination', inbound)

        [message] = yield self.workerhelper.wait_for_dispatched_inbound(
            connector_name='testqueue')
        self.assertEqual(message, inbound)

    @inlineCallbacks
    def test_send_event_to_destination(self):
        """
        send_event_to_destination should send the provided event message
        to the specified destination worker
        """
        worker = yield self.get_router_worker({
            'destinations': [{
                'id': 'test-destination',
                'amqp_queue': 'testqueue',
            }],
        })

        ack = self.messagehelper.make_ack()
        yield worker.send_event_to_destination('test-destination', ack)

        [event] = yield self.workerhelper.wait_for_dispatched_events(
            connector_name='testqueue')
        self.assertEqual(event, ack)

    @inlineCallbacks
    def test_consume_destination(self):
        """
        If a callback is attached to a destination, then that callback should
        be called when an outbound is sent from a destination
        """
        worker = yield self.get_router_worker({
            'destinations': [{
                'id': 'test-destination',
                'amqp_queue': 'testqueue',
            }],
        })

        messages = []

        def message_callback(destinationid, message):
            assert destinationid == 'test-destination'
            messages.append(message)

        yield worker.consume_destination('test-destination', message_callback)
        # Because this is only called in setup, and we're creating connectors
        # after setup, we need to unpause them
        worker.unpause_connectors()

        self.assertEqual(messages, [])
        msg = self.messagehelper.make_outbound('testmessage')
        yield self.workerhelper.dispatch_outbound(msg, 'test-destination')
        self.assertEqual(messages, [msg])

    @inlineCallbacks
    def test_send_outbound_to_channel(self):
        """
        send_outbound_to_channel should send the provided outbound message to
        the specified channel
        """
        worker = yield self.get_router_worker({})

        yield worker.consume_channel('testchannel', lambda m: m, lambda e: e)

        outbound = self.messagehelper.make_outbound('test message')
        yield worker.send_outbound_to_channel('testchannel', outbound)

        [message] = yield self.workerhelper.wait_for_dispatched_outbound(
            connector_name='testchannel')
        self.assertEqual(message, outbound)
