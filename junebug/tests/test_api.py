import json
import treq
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase
from twisted.web import http
from twisted.web.server import Site

from junebug.api import JunebugApi


class TestJunebugApi(TestCase):
    @inlineCallbacks
    def setUp(self):
        yield self.start_server()

    @inlineCallbacks
    def tearDown(self):
        yield self.stop_server()

    @inlineCallbacks
    def start_server(self):
        self.app = JunebugApi()
        self.server = yield reactor.listenTCP(0, Site(self.app.app.resource()))
        addr = self.server.getHost()
        self.url = "http://%s:%s" % (addr.host, addr.port)

    @inlineCallbacks
    def stop_server(self):
        yield self.server.loseConnection()

    def get(self, url):
        return treq.get("%s%s" % (self.url, url), persistent=False)

    def post(self, url, data, headers=None):
        return treq.post(
            "%s%s" % (self.url, url),
            json.dumps(data),
            persistent=False,
            headers=headers)

    @inlineCallbacks
    def assert_response(self, response, code, description, result):
        data = yield response.json()
        self.assertEqual(data, {
            'status': code,
            'code': http.RESPONSES[code],
            'description': description,
            'result': result,
        })
        self.assertEqual(response.code, code)

    @inlineCallbacks
    def test_get_channel_list(self):
        resp = yield self.get('/channels')
        yield self.assert_response(
            resp, http.INTERNAL_SERVER_ERROR, 'generic error', {
                'errors': [{
                    'message': '',
                    'type': 'NotImplementedError',
                    }]
                })
