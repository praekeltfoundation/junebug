from junebug.amqp import AmqpFactory, JunebugAMQClient
from junebug.tests.helpers import JunebugTestBase
from twisted.internet.defer import inlineCallbacks
from vumi.tests.fake_amqp import FakeAMQClient


class TestJunebugApi(JunebugTestBase):
    @inlineCallbacks
    def test_amqp_factory_create_client(self):
        factory = AmqpFactory('amqp-spec-0-8.xml', {
            'vhost': '/'})
        client1 = factory.buildProtocol('localhost')
        self.assertTrue(isinstance(client1, JunebugAMQClient))
        self.assertEqual(client1.vhost, '/')

        factory.amqp_client_d.callback(None)
        factory.amqp_client = client1
        client2 = yield factory.get_client()
        self.assertEqual(client1, client2)

