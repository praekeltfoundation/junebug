import json

from twisted.web import http
from functools import wraps
from vumi.message import JSONMessageEncoder


def response(req, description, data, code=http.OK):
    req.setHeader('Content-Type', 'application/json')
    req.setResponseCode(code)

    return json.dumps({
        'status': code,
        'code': http.RESPONSES[code],
        'description': description,
        'result': data,
    }, cls=JSONMessageEncoder)


def json_body(fn):
    @wraps(fn)
    def wrapper(api, req, *a, **kw):
        body = json.loads(req.content.read())
        return fn(api, req, body, *a, **kw)

    return wrapper
