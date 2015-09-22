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


def api_from_message(msg):
    ret = {}
    ret['to'] = msg['to_addr']
    ret['from'] = msg['from_addr']
    ret['message_id'] = msg['message_id']
    ret['channel_id'] = msg['transport_name']
    ret['timestamp'] = msg['timestamp']
    ret['reply_to'] = msg['in_reply_to']
    ret['content'] = msg['content']
    ret['channel_data'] = msg['helper_metadata']

    if msg.get('continue_session') is not None:
        ret['channel_data']['continue_session'] = msg['continue_session']
    if msg.get('session_event') is not None:
        ret['channel_data']['session_event'] = msg['session_event']

    return ret


def message_from_api(channel_id, msg):
    ret = {}

    if 'reply_to' not in msg:
        ret['to_addr'] = msg.get('to')
        ret['from_addr'] = msg.get('from')

    ret['content'] = msg['content']
    ret['transport_name'] = channel_id

    channel_data = msg.get('channel_data', {})
    if channel_data.get('continue_session') is not None:
        ret['continue_session'] = channel_data.pop('continue_session')

    if channel_data.get('session_event') is not None:
        ret['session_event'] = channel_data.pop('session_event')

    ret['helper_metadata'] = channel_data
    ret['transport_name'] = channel_id
    return ret
