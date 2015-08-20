from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase

from junebug.service import JunebugService


class TestJunebugService(TestCase):
    @inlineCallbacks
    def test_start_service(self):
        service = JunebugService('localhost', 0)

        server = yield service.startService()
        self.assertTrue(server.connected)

        yield service.stopService()
        self.assertFalse(server.connected)
