from twisted.internet.defer import inlineCallbacks

from junebug.router import Router, InvalidRouterConfig
from junebug.router.base import InvalidRouterType
from junebug.tests.helpers import JunebugTestBase


class TestRouter(JunebugTestBase):
    @inlineCallbacks
    def setUp(self):
        yield self.start_server()

    def test_creating_uuid(self):
        """If a router isn't given an id, then it should generate one."""
        config = self.create_router_config()
        router = Router(self.api.router_store, self.api.config, config)
        self.assertFalse(router.router_config.get('id') is None)

        config = self.create_router_config(id='test-uuid')
        router = Router(self.api.router_store, self.api.config, config)
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
        """save should save the configuration into the router store"""
        config = self.create_router_config()
        router = Router(self.api.router_store, self.api.config, config)

        self.assertEqual((yield self.api.router_store.get_router_list()), [])
        yield router.save()
        self.assertEqual(
            (yield self.api.router_store.get_router_list()),
            [router.router_config['id']])

    @inlineCallbacks
    def test_validate_config(self):
        """validate_config should run the validate config function on the
        router worker class"""
        config = self.create_router_config(config={'test': 'pass'})
        router = Router(self.api.router_store, self.api.config, config)
        yield router.validate_config()

        with self.assertRaises(InvalidRouterConfig):
            config = self.create_router_config(config={'test': 'fail'})
            router = Router(self.api.router_store, self.api.config, config)
            yield router.validate_config()

    @inlineCallbacks
    def test_validate_config_invalid_worker_name(self):
        """If validate_config is given a config with an unknown worker name,
        an appropriate error should be raised."""
        config = self.create_router_config(type='invalid')
        router = Router(self.api.router_store, self.api.config, config)

        with self.assertRaises(InvalidRouterType):
            yield router.validate_config()

    def test_start(self):
        """start should start the router worker with the correct config"""
        config = self.create_router_config()
        router = Router(self.api.router_store, self.api.config, config)
        router.start(self.service)

        id = router.router_config['id']
        transport = self.service.namedServices[id]
        self.assertEqual(transport.parent, self.service)
        self.assertEqual(transport.config, config['config'])

    @inlineCallbacks
    def test_status(self):
        """status should return the current config of the router"""
        config = self.create_router_config()
        router = Router(self.api.router_store, self.api.config, config)
        status = yield router.status()
        self.assertEqual(status, router.router_config)
