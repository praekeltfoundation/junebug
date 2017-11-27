import mock

from treq.testing import StubTreq
from treq.testing import RequestSequence, StringStubbingResource
from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase
from twisted.web import http

from junebug.rabbitmq import RabbitmqManagementClient


class TestJunebugApi(TestCase):

    @inlineCallbacks
    def test_get_channels_health_check(self):

        url = b'http://rabbitmq:15672/api/queues/%2F/queue-1234-1234.inbound'

        async_failures = []
        sequence_stubs = RequestSequence(
            [((b'get', url, mock.ANY, mock.ANY, mock.ANY),
             (http.OK, {b'Content-Type': b'application/json'},
              b'{"messages": 1256, "messages_details": {"rate": 1.25}, "name": "queue-1234-1234.inbound"}'))],  # noqa
            async_failures.append)
        stub_treq = StubTreq(StringStubbingResource(sequence_stubs))

        def new_get(*args, **kwargs):
            return stub_treq.request("GET", args[0])

        rabbitmq_management_client = RabbitmqManagementClient(
            "rabbitmq:15672", "guest", "guest")

        with (mock.patch('treq.client.HTTPClient.get', side_effect=new_get)):
            with sequence_stubs.consume(self.fail):
                response = yield rabbitmq_management_client.get_queue(
                    "/", "queue-1234-1234.inbound")

                yield self.assertEqual(response, {
                    "messages": 1256,
                    "messages_details": {"rate": 1.25},
                    "name": "queue-1234-1234.inbound"})
