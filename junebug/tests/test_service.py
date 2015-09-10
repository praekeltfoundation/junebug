from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase

from junebug import JunebugApi
from junebug.service import JunebugService
from junebug.config import JunebugConfig


class TestJunebugService(TestCase):
    def setUp(self):
        self.old_setup = JunebugApi.setup
        self.old_teardown = JunebugApi.teardown

        def do_nothing(self):
            pass

        JunebugApi.setup = do_nothing
        JunebugApi.teardown = do_nothing

    def tearDown(self):
        JunebugApi.setup = self.old_setup
        JunebugApi.teardown = self.old_teardown

    @inlineCallbacks
    def test_start_service(self):
        service = JunebugService(JunebugConfig({
            'host': '127.0.0.1',
            'port': 0,
        }))

        yield service.startService()
        server = service._port
        self.assertTrue(server.connected)

        yield service.stopService()
        self.assertFalse(server.connected)
