from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase
from vumi.tests.helpers import PersistenceHelper

from junebug.service import JunebugService


class TestJunebugService(TestCase):
    @inlineCallbacks
    def setUp(self):
        self.persistencehelper = PersistenceHelper()
        yield self.persistencehelper.setup()
        self.redis = yield self.persistencehelper.get_redis_manager()

    @inlineCallbacks
    def test_start_service(self):
        service = JunebugService('localhost', 0, self.redis._config, {})

        yield service.startService()
        server = service._port
        self.assertTrue(server.connected)

        yield service.stopService()
        self.assertFalse(server.connected)
