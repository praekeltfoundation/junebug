import collections
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


def conjoin(a, b):
    result = {}
    result.update(a)
    result.update(b)
    return result


def omit(collection, *fields):
    return dict((k, v) for k, v in collection.iteritems() if k not in fields)


def api_from_message(msg):
    ret = {}
    ret['to'] = msg['to_addr']
    ret['from'] = msg['from_addr']
    ret['group'] = msg['group']
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
        ret['group'] = msg.get('group')

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


def api_from_event(channel_id, event):
    parser = {
        'ack': _api_from_event_ack,
        'nack': _api_from_event_nack,
        'delivery_report': _api_from_event_dr,
    }.get(event['event_type'], lambda *a, **kw: {})

    return conjoin({
        'channel_id': channel_id,
        'timestamp': event['timestamp'],
        'message_id': event['user_message_id'],
        'event_details': {},
        'event_type': None,
    }, parser(channel_id, event))


def api_from_status(channel_id, status):
    return {
        'channel_id': channel_id,
        'component': status['component'],
        'status': status['status'],
        'type': status['type'],
        'message': status['message'],
        'details': status['details'],
    }


def _api_from_event_ack(channel_id, event):
    return {
        'event_type': 'submitted',
        'event_details': {}
    }


def _api_from_event_nack(channel_id, event):
    return {
        'event_type': 'rejected',
        'event_details': {'reason': event['nack_reason']}
    }


def _api_from_event_dr(channel_id, event):
    return {
        'event_type': {
            'pending': 'delivery_pending',
            'failed': 'delivery_failed',
            'delivered': 'delivery_succeeded',
        }.get(event['delivery_status']),
    }


def channel_public_http_properties(properties):
    config = properties.get('config', {})
    results = conjoin({
        'enabled': True,
        'web_path': config.get('web_path'),
        'web_port': config.get('web_port'),
    }, properties.get('public_http', {}))

    if results['web_path'] is None or results['web_port'] is None:
        return None
    else:
        return results


def convert_unicode(data):
    """Converts unicode to strings"""
    if isinstance(data, basestring):
        return str(data)
    elif isinstance(data, collections.Mapping):
        return dict(map(convert_unicode, data.iteritems()))
    elif isinstance(data, collections.Iterable):
        return type(data)(map(convert_unicode, data))
    else:
        return data
