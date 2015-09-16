import treq
import json
from klein import Klein
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.client import HTTPConnectionPool
from twisted.web.server import Site
from vumi.application.tests.helpers import ApplicationHelper
from vumi.message import TransportUserMessage
from vumi.tests.helpers import PersistenceHelper

from junebug.workers import MessageForwardingWorker
from junebug.tests.helpers import JunebugTestBase


class RequestLoggingApi(object):
    app = Klein()

    def __init__(self):
        self.requests = []

    @app.route('/')
    def log_request(self, request):
        self.requests.append({
            'request': request,
            'body': request.content.read(),
            })
        return ''

    @app.route('/bad/')
    def bad_request(self, request):
        self.requests.append({
            'request': request,
            'body': request.content.read(),
            })
        request.setResponseCode(500)
        return 'test-error-response'


class TestMessageForwardingWorker(JunebugTestBase):
    @inlineCallbacks
    def setUp(self):
        self.logging_api = RequestLoggingApi()
        port = reactor.listenTCP(
            0, Site(self.logging_api.app.resource()),
            interface='127.0.0.1')
        self.addCleanup(port.stopListening)
        addr = port.getHost()
        self.url = "http://%s:%s" % (addr.host, addr.port)

        persistencehelper = PersistenceHelper()
        yield persistencehelper.setup()
        self.addCleanup(persistencehelper.cleanup)

        app_config = persistencehelper.mk_config({
            'transport_name': 'testtransport',
            'mo_message_url': self.url.decode('utf-8'),
        })
        self.worker = yield self.get_worker(app_config)

        connection_pool = HTTPConnectionPool(reactor, persistent=False)
        treq._utils.set_global_pool(connection_pool)

    @inlineCallbacks
    def get_worker(self, config):
        '''Get a new MessageForwardingWorker with the provided config'''
        app_helper = ApplicationHelper(MessageForwardingWorker)
        yield app_helper.setup()
        self.addCleanup(app_helper.cleanup)
        worker = yield app_helper.get_application(config)
        returnValue(worker)

    @inlineCallbacks
    def test_send_message(self):
        '''A sent message should be forwarded to the configured URL'''
        msg = TransportUserMessage.send(to_addr='+1234', content='testcontent')
        yield self.worker.consume_user_message(msg)
        [request] = self.logging_api.requests
        req = request['request']
        body = json.loads(request['body'])

        self.assertEqual(
            req.requestHeaders.getRawHeaders('content-type'),
            ['application/json'])
        self.assertEqual(req.method, 'POST')
        self.assertEqual(body['content'], 'testcontent')
        self.assertEqual(body['to'], '+1234')

    @inlineCallbacks
    def test_send_message_bad_response(self):
        '''If there is an error sending a message to the configured URL, the
        error and message should be logged'''
        self.patch_logger()
        self.worker = yield self.get_worker({
            'transport_name': 'testtransport',
            'mo_message_url': self.url + '/bad/'})
        msg = TransportUserMessage.send(to_addr='+1234', content='testcontent')
        yield self.worker.consume_user_message(msg)

        self.assertTrue(any(
            '"content": "testcontent"' in l.getMessage()
            for l in self.logging_handler.buffer))
        self.assertTrue(any(
            '"to": "+1234"' in l.getMessage()
            for l in self.logging_handler.buffer))
        self.assertTrue(any(
            '500' in l.getMessage()
            for l in self.logging_handler.buffer))
        self.assertTrue(any(
            'test-error-response' in l.getMessage()
            for l in self.logging_handler.buffer))
