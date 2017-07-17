from klein import Klein
from twisted.python import log
from werkzeug.exceptions import HTTPException
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web import http
from vumi.persist.txredis_manager import TxRedisManager
from vumi.utils import load_class_by_string

from junebug.amqp import MessageSender
from junebug.channel import Channel
from junebug.error import JunebugError
from junebug.utils import api_from_event, json_body, response
from junebug.validate import body_schema, validate
from junebug.stores import (
    InboundMessageStore, MessageRateStore, OutboundMessageStore)


class ApiUsageError(JunebugError):
    '''Exception that is raised whenever the API is used incorrectly.
    Used for incorrect requests and invalid data.'''
    name = 'ApiUsageError'
    description = 'api usage error'
    code = http.BAD_REQUEST


class JunebugApi(object):
    app = Klein()

    def __init__(self, service, config):
        self.service = service
        self.redis_config = config.redis
        self.amqp_config = config.amqp
        self.config = config

    @inlineCallbacks
    def setup(self, redis=None, message_sender=None):
        if redis is None:
            redis = yield TxRedisManager.from_config(self.redis_config)

        if message_sender is None:
            message_sender = MessageSender(
                'amqp-spec-0-8.xml', self.amqp_config)

        self.redis = redis
        self.message_sender = message_sender
        self.message_sender.setServiceParent(self.service)

        self.inbounds = InboundMessageStore(
            self.redis, self.config.inbound_message_ttl)

        self.outbounds = OutboundMessageStore(
            self.redis, self.config.outbound_message_ttl)

        self.message_rate = MessageRateStore(self.redis)

        self.plugins = []
        for plugin_config in self.config.plugins:
            cls = load_class_by_string(plugin_config['type'])
            plugin = cls()
            yield plugin.start_plugin(plugin_config, self.config)
            self.plugins.append(plugin)

        yield Channel.start_all_channels(
            self.redis, self.config, self.service, self.plugins)

    @inlineCallbacks
    def teardown(self):
        yield self.redis.close_manager()
        for plugin in self.plugins:
            yield plugin.stop_plugin()

    @app.handle_errors(JunebugError)
    def generic_junebug_error(self, request, failure):
        return response(request, failure.value.description, {
            'errors': [{
                'type': failure.value.name,
                'message': failure.getErrorMessage(),
                }]
            }, code=failure.value.code)

    @app.handle_errors(HTTPException)
    def http_error(self, request, failure):
        error = {
            'code': failure.value.code,
            'type': failure.value.name,
            'message': failure.getErrorMessage(),
        }
        if getattr(failure.value, 'new_url', None) is not None:
            request.setHeader('Location', failure.value.new_url)
            error['new_url'] = failure.value.new_url

        return response(request, failure.value.description, {
            'errors': [error],
            }, code=failure.value.code)

    @app.handle_errors
    def generic_error(self, request, failure):
        log.err(failure)
        return response(request, 'generic error', {
            'errors': [{
                'type': failure.type.__name__,
                'message': failure.getErrorMessage(),
                }]
            }, code=http.INTERNAL_SERVER_ERROR)

    @app.route('/channels/', methods=['GET'])
    @inlineCallbacks
    def get_channel_list(self, request):
        '''List all channels'''
        ids = yield Channel.get_all(self.redis)
        returnValue(response(request, 'channels listed', sorted(ids)))

    @app.route('/channels/', methods=['POST'])
    @json_body
    @validate(
        body_schema({
            'type': 'object',
            'properties': {
                'type': {'type': 'string'},
                'label': {'type': 'string'},
                'config': {'type': 'object'},
                'metadata': {'type': 'object'},
                'status_url': {'type': 'string'},
                'mo_url': {'type': 'string'},
                'mo_url_auth_token': {'type': 'string'},
                'amqp_queue': {'type': 'string'},
                'rate_limit_count': {
                    'type': 'integer',
                    'minimum': 0,
                },
                'rate_limit_window': {
                    'type': 'integer',
                    'minimum': 0,
                },
                'character_limit': {
                    'type': 'integer',
                    'minimum': 0,
                },
            },
            'required': ['type', 'config'],
        }))
    @inlineCallbacks
    def create_channel(self, request, body):
        '''Create a channel'''
        if not (body.get('mo_url') or body.get('amqp_queue')):
            raise ApiUsageError(
                'One or both of "mo_url" and "amqp_queue" must be specified')

        channel = Channel(
            self.redis, self.config, body, self.plugins)
        yield channel.start(self.service)
        yield channel.save()
        returnValue(response(
            request, 'channel created', (yield channel.status())))

    @app.route('/channels/<string:channel_id>', methods=['GET'])
    @inlineCallbacks
    def get_channel(self, request, channel_id):
        '''Return the channel configuration and a nested status object'''
        channel = yield Channel.from_id(
            self.redis, self.config, channel_id, self.service, self.plugins)
        resp = yield channel.status()
        returnValue(response(
            request, 'channel found', resp))

    @app.route('/channels/<string:channel_id>', methods=['POST'])
    @json_body
    @validate(
        body_schema({
            'type': 'object',
            'properties': {
                'type': {'type': 'string'},
                'label': {'type': 'string'},
                'config': {'type': 'object'},
                'metadata': {'type': 'object'},
                'status_url': {'type': ['string', 'null']},
                'mo_url': {'type': ['string', 'null']},
                'rate_limit_count': {
                    'type': 'integer',
                    'minimum': 0,
                },
                'rate_limit_window': {
                    'type': 'integer',
                    'minimum': 0,
                },
                'character_limit': {
                    'type': 'integer',
                    'minimum': 0,
                },
            },
        }))
    @inlineCallbacks
    def modify_channel(self, request, body, channel_id):
        '''Mondify the channel configuration'''
        channel = yield Channel.from_id(
            self.redis, self.config, channel_id, self.service, self.plugins)
        resp = yield channel.update(body)
        returnValue(response(
            request, 'channel updated', resp))

    @app.route('/channels/<string:channel_id>', methods=['DELETE'])
    @inlineCallbacks
    def delete_channel(self, request, channel_id):
        '''Delete the channel'''
        channel = yield Channel.from_id(
            self.redis, self.config, channel_id, self.service, self.plugins)
        yield channel.stop()
        yield channel.delete()
        returnValue(response(
            request, 'channel deleted', {}))

    @app.route('/channels/<string:channel_id>/restart', methods=['POST'])
    @inlineCallbacks
    def restart_channel(self, request, channel_id):
        '''Restart a channel.'''
        channel = yield Channel.from_id(
            self.redis, self.config, channel_id, self.service, self.plugins)
        yield channel.stop()
        yield channel.start(self.service)
        returnValue(response(request, 'channel restarted', {}))

    @app.route('/channels/<string:channel_id>/logs', methods=['GET'])
    @inlineCallbacks
    def get_logs(self, request, channel_id):
        '''Get the last N logs for a channel, sorted reverse
        chronologically.'''
        n = request.args.get('n', None)
        if n is not None:
            n = int(n[0])
        channel = yield Channel.from_id(
            self.redis, self.config, channel_id, self.service, self.plugins)
        logs = yield channel.get_logs(n)
        returnValue(response(request, 'logs retrieved', logs))

    @app.route('/channels/<string:channel_id>/messages/', methods=['POST'])
    @json_body
    @validate(
        body_schema({
            'type': 'object',
            'properties': {
                'to': {'type': 'string'},
                'from': {'type': ['string', 'null']},
                'group': {'type': ['string', 'null']},
                'reply_to': {'type': 'string'},
                'content': {'type': ['string', 'null']},
                'event_url': {'type': 'string'},
                'priority': {'type': 'string'},
                'channel_data': {'type': 'object'},
            },
            'required': ['content'],
            'additionalProperties': False,
        }))
    @inlineCallbacks
    def send_message(self, request, body, channel_id):
        '''Send an outbound (mobile terminated) message'''
        if 'to' not in body and 'reply_to' not in body:
            raise ApiUsageError(
                'Either "to" or "reply_to" must be specified')

        if 'to' in body and 'reply_to' in body:
            raise ApiUsageError(
                'Only one of "to" and "reply_to" may be specified')

        if 'from' in body and 'reply_to' in body:
            raise ApiUsageError(
                'Only one of "from" and "reply_to" may be specified')

        channel = yield Channel.from_id(
            self.redis, self.config, channel_id, self.service, self.plugins)

        if 'to' in body:
            msg = yield channel.send_message(
                self.message_sender, self.outbounds, body)
        else:
            msg = yield channel.send_reply_message(
                self.message_sender, self.outbounds, self.inbounds, body)

        yield self.message_rate.increment(
            channel_id, 'outbound', self.config.metric_window)

        returnValue(response(request, 'message sent', msg))

    @app.route(
        '/channels/<string:channel_id>/messages/<string:message_id>',
        methods=['GET'])
    @inlineCallbacks
    def get_message_status(self, request, channel_id, message_id):
        '''Retrieve the status of a message'''
        events = yield self.outbounds.load_all_events(channel_id, message_id)
        events = sorted(
            (api_from_event(channel_id, e) for e in events),
            key=lambda e: e['timestamp'])

        last_event = events[-1] if events else None
        last_event_type = last_event['event_type'] if last_event else None
        last_event_timestamp = last_event['timestamp'] if last_event else None

        returnValue(response(request, 'message status', {
            'id': message_id,
            'last_event_type': last_event_type,
            'last_event_timestamp': last_event_timestamp,
            'events': events,
        }))

    @app.route('/health', methods=['GET'])
    def health_status(self, request):
        return response(request, 'health ok', {})
