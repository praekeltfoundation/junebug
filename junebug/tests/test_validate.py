import json

from twisted.web import http
from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

import treq
from klein import Klein

from junebug.tests.utils import ToyServer
from junebug.utils import json_body
from junebug.validate import body_schema, validate


class TestValidate(TestCase):
    @inlineCallbacks
    def test_validate_fail(self):
        class Api(object):
            app = Klein()

            @app.route('/')
            @validate(
                lambda _: errs1,
                lambda _: None,
                lambda _: errs2)
            def route(self, req):
                pass

        errs1 = [{
            'type': '1',
            'message': 'a'
        }]

        errs2 = [{
            'type': 'b',
            'message': 'B'
        }]

        srv = yield ToyServer.from_test(self, Api().app)
        resp = yield treq.get(srv.url, persistent=False)
        self.assertEqual(resp.code, http.BAD_REQUEST)
        content = yield resp.json()
        self.assertEqual(content['result'], {
            'errors': sorted(errs1 + errs2)
        })
        self.assertEqual(content['status'], 400)
        self.assertEqual(content['code'], 'Bad Request')
        self.assertEqual(content['description'], 'api usage error')

    @inlineCallbacks
    def test_validate_pass(self):
        class Api(object):
            app = Klein()

            @app.route('/')
            @validate(
                lambda _: None,
                lambda _: None)
            def route(self, req):
                return 'ok'

        srv = yield ToyServer.from_test(self, Api().app)
        resp = yield treq.get(srv.url, persistent=False)
        self.assertEqual(resp.code, http.OK)
        self.assertEqual((yield resp.content()), 'ok')

    @inlineCallbacks
    def test_body_schema(self):
        class Api(object):
            app = Klein()

            @app.route('/')
            @json_body
            @validate(body_schema({'properties': {'foo': {'type': 'string'}}}))
            def route(self, req, body):
                pass

        srv = yield ToyServer.from_test(self, Api().app)
        resp = yield treq.get(
            srv.url,
            persistent=False,
            data=json.dumps({'foo': 23}))

        content = yield resp.json()
        self.assertEqual(content['result'], {
            'errors': [{
                'type': 'invalid_body',
                'message': "23 is not of type 'string'",
                'schema_path': ['properties', 'foo', 'type'],
            }]
        })
        self.assertEqual(content['status'], 400)
        self.assertEqual(content['code'], 'Bad Request')
        self.assertEqual(content['description'], 'api usage error')

        resp = yield treq.get(
            srv.url,
            persistent=False,
            data=json.dumps({'foo': 'bar'}))

        self.assertEqual(resp.code, http.OK)
