from klein import Klein
import logging
from werkzeug.exceptions import HTTPException
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web import http
from vumi.persist.txredis_manager import TxRedisManager

from junebug.amqp import MessageSender
from junebug.channel import Channel, ChannelNotFound
from junebug.error import JunebugError
from junebug.utils import json_body, response
from junebug.validate import body_schema, validate
from junebug.stores import InboundMessageStore, OutboundMessageStore

logging = logging.getLogger(__name__)


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

    @inlineCallbacks
    def teardown(self):
        yield self.redis.close_manager()

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
        return response(request, failure.value.description, {
            'errors': [{
                'type': failure.value.name,
                'message': failure.getErrorMessage(),
                }]
            }, code=failure.value.code)

    @app.handle_errors
    def generic_error(self, request, failure):
        logging.exception(failure)
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
            'required': ['type', 'config', 'mo_url'],
        }))
    @inlineCallbacks
    def create_channel(self, request, body):
        '''Create a channel'''
        channel = Channel(
            self.redis, self.config, body)
        yield channel.save()
        yield channel.start(self.service)
        returnValue(response(
            request, 'channel created', (yield channel.status())))

    @app.route('/channels/<string:channel_id>', methods=['GET'])
    @inlineCallbacks
    def get_channel(self, request, channel_id):
        '''Return the channel configuration and a nested status object'''
        channel = yield Channel.from_id(
            self.redis, self.config, channel_id, self.service)
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
                'status_url': {'type': 'string'},
                'mo_url': {'type': 'string'},
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
            self.redis, self.config, channel_id, self.service)
        resp = yield channel.update(body)
        returnValue(response(
            request, 'channel updated', resp))

    @app.route('/channels/<string:channel_id>', methods=['DELETE'])
    @inlineCallbacks
    def delete_channel(self, request, channel_id):
        '''Delete the channel'''
        channel = yield Channel.from_id(
            self.redis, self.config, channel_id, self.service)
        yield channel.stop()
        yield channel.delete()
        returnValue(response(
            request, 'channel deleted', {}))

    @app.route('/channels/<string:channel_id>/messages/', methods=['POST'])
    @json_body
    @validate(
        body_schema({
            'type': 'object',
            'properties': {
                'to': {'type': 'string'},
                'from': {'type': ['string', 'null']},
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

        try:
            self.service.getServiceNamed(channel_id)
        except KeyError:
            raise ChannelNotFound()

        if 'to' in body:
            msg = yield Channel.send_message(
                channel_id, self.message_sender, self.outbounds, body)
        else:
            msg = yield Channel.send_reply_message(
                channel_id, self.message_sender, self.outbounds,
                self.inbounds, body)

        returnValue(response(request, 'message sent', msg))

    @app.route(
        '/channels/<string:channel_id>/messages/<string:message_id>',
        methods=['GET'])
    def get_message_status(self, request, channel_id, message_id):
        '''Retrieve the status of a message'''
        raise NotImplementedError()

    @app.route('/health', methods=['GET'])
    def health_status(self, request):
        return response(request, 'health ok', {})
