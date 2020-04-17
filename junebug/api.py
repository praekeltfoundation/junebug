from functools import partial
from klein import Klein

from twisted.python import log
from werkzeug.exceptions import HTTPException
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web import http

from twisted.internet import defer
from vumi.persist.txredis_manager import TxRedisManager
from vumi.utils import load_class_by_string

from junebug.amqp import MessageSender
from junebug.channel import Channel
from junebug.error import JunebugError
from junebug.rabbitmq import RabbitmqManagementClient
from junebug.router import Router
from junebug.utils import api_from_event, json_body, response
from junebug.validate import body_schema, validate
from junebug.stores import (
    InboundMessageStore, MessageRateStore, OutboundMessageStore, RouterStore)


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

        self.router_store = RouterStore(self.redis)

        self.plugins = []
        for plugin_config in self.config.plugins:
            cls = load_class_by_string(plugin_config['type'])
            plugin = cls()
            yield plugin.start_plugin(plugin_config, self.config)
            self.plugins.append(plugin)

        yield Channel.start_all_channels(
            self.redis, self.config, self.service, self.plugins)

        yield Router.start_all_routers(self)

        if self.config.rabbitmq_management_interface:
            self.rabbitmq_management_client = RabbitmqManagementClient(
                self.config.rabbitmq_management_interface,
                self.amqp_config['username'],
                self.amqp_config['password'])

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
        channel = Channel(
            self.redis, self.config, body, self.plugins)
        yield channel.start(self.service)
        yield channel.save()
        returnValue(response(
            request, 'channel created', (yield channel.status()),
            code=http.CREATED))

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
                'event_auth_token': {'type': 'string'},
                'priority': {'type': 'string'},
                'channel_data': {'type': 'object'},
            },
            'required': ['content'],
            'additionalProperties': False,
        }))
    @inlineCallbacks
    def send_message(self, request, body, channel_id):
        '''Send an outbound (mobile terminated) message'''
        channel = yield Channel.from_id(
            self.redis, self.config, channel_id, self.service, self.plugins)

        if (channel.has_destination):
            msg = yield self.send_message_on_channel(channel_id, body)

            returnValue(response(
                request, 'message submitted', msg, code=http.CREATED))
        else:
            raise ApiUsageError(
                'This channel has no "mo_url" or "amqp_queue"')

    @app.route(
        '/channels/<string:channel_id>/messages/<string:message_id>',
        methods=['GET'])
    @inlineCallbacks
    def get_message_status(self, request, channel_id, message_id):
        '''Retrieve the status of a message'''
        channel = yield Channel.from_id(
            self.redis, self.config, channel_id, self.service, self.plugins)

        if (channel.has_destination):
            data = yield self.get_message_events(
                request, channel_id, message_id)
            returnValue(response(request, 'message status', data))
        else:
            raise ApiUsageError(
                'This channel has no "mo_url" or "amqp_queue"')

    @app.route('/routers/', methods=['GET'])
    def get_router_list(self, request):
        """List all routers"""
        d = Router.get_all(self.router_store)
        d.addCallback(partial(response, request, 'routers retrieved'))
        return d

    @app.route('/routers/', methods=['POST'])
    @json_body
    @validate(
        body_schema({
            'type': 'object',
            'properties': {
                'type': {'type': 'string'},
                'label': {'type': 'string'},
                'config': {'type': 'object'},
                'metadata': {'type': 'object'},
            },
            'additionalProperties': False,
            'required': ['type', 'config'],
        }))
    @inlineCallbacks
    def create_router(self, request, body):
        """Create a new router"""
        router = Router(self, body)
        yield router.validate_config()
        router.start(self.service)
        yield router.save()
        returnValue(response(
            request,
            'router created',
            (yield router.status()),
            code=http.CREATED
        ))

    @app.route('/routers/<string:router_id>', methods=['GET'])
    def get_router(self, request, router_id):
        """Get the configuration details and status of a specific router"""
        d = Router.from_id(self, router_id)
        d.addCallback(lambda router: router.status())
        d.addCallback(partial(response, request, 'router found'))
        return d

    @app.route('/routers/<string:router_id>', methods=['PUT'])
    @json_body
    @validate(
        body_schema({
            'type': 'object',
            'properties': {
                'type': {'type': 'string'},
                'label': {'type': 'string'},
                'config': {'type': 'object'},
                'metadata': {'type': 'object'},
            },
            'additionalProperties': False,
            'required': ['type', 'config'],
        }))
    @inlineCallbacks
    def replace_router_config(self, request, body, router_id):
        """Replace the router config with the one specified"""
        router = yield Router.from_id(self, router_id)

        for field in ['type', 'label', 'config', 'metadata']:
            router.router_config.pop(field, None)
        router.router_config.update(body)
        yield router.validate_config()

        # Stop and start the router for the worker to get the new config
        yield router.stop()
        router.start(self.service)
        yield router.save()
        returnValue(response(
            request, 'router updated', (yield router.status())))

    @app.route('/routers/<string:router_id>', methods=['PATCH'])
    @json_body
    @validate(
        body_schema({
            'type': 'object',
            'properties': {
                'type': {'type': 'string'},
                'label': {'type': 'string'},
                'config': {'type': 'object'},
                'metadata': {'type': 'object'},
            },
            'additionalProperties': False,
            'required': [],
        }))
    @inlineCallbacks
    def update_router_config(self, request, body, router_id):
        """Update the router config with the one specified"""
        router = yield Router.from_id(self, router_id)

        router.router_config.update(body)
        yield router.validate_config()

        # Stop and start the router for the worker to get the new config
        yield router.stop()
        router.start(self.service)
        yield router.save()
        returnValue(response(
            request, 'router updated', (yield router.status())))

    @app.route('/routers/<string:router_id>', methods=['DELETE'])
    @inlineCallbacks
    def delete_router(self, request, router_id):
        router = yield Router.from_id(self, router_id)
        yield router.stop()
        yield router.delete()
        returnValue(response(request, 'router deleted', {}))

    @app.route('/routers/<string:router_id>/logs', methods=['GET'])
    @inlineCallbacks
    def get_router_logs(self, request, router_id):
        '''Get the last N logs for a router, sorted reverse
        chronologically.'''
        n = request.args.get('n', None)
        if n is not None:
            n = int(n[0])
        router = yield Router.from_id(self, router_id)
        logs = yield router.get_logs(n)
        returnValue(response(request, 'logs retrieved', logs))

    @app.route('/routers/<string:router_id>/destinations/', methods=['POST'])
    @json_body
    @validate(
        body_schema({
            'type': 'object',
            'properties': {
                'label': {'type': 'string'},
                'config': {'type': 'object'},
                'metadata': {'type': 'object'},
                'mo_url': {'type': 'string'},
                'mo_url_token': {'type': 'string'},
                'amqp_queue': {'type': 'string'},
                'character_limit': {
                    'type': 'integer',
                    'minimum': 0,
                },
            },
            'additionalProperties': False,
            'required': ['config'],
        }))
    @inlineCallbacks
    def create_router_destination(self, request, body, router_id):
        """Create a new destination for the router"""
        router = yield Router.from_id(self, router_id)
        yield router.validate_destination_config(body['config'])

        destination = router.add_destination(body)
        yield router.stop()
        router.start(self.service)
        yield destination.save()

        returnValue(response(
            request, 'destination created', (yield destination.status()),
            code=http.CREATED
        ))

    @app.route('/routers/<string:router_id>/destinations/', methods=['GET'])
    def get_router_destination_list(self, request, router_id):
        """Get the list of destinations for a router"""
        d = Router.from_id(self, router_id)
        d.addCallback(lambda router: router.get_destination_list())
        d.addCallback(partial(response, request, 'destinations retrieved'))
        return d

    @app.route(
        '/routers/<string:router_id>/destinations/<string:destination_id>',
        methods=['GET'])
    @inlineCallbacks
    def get_destination(self, request, router_id, destination_id):
        """Get the config and status of a destination"""
        router = yield Router.from_id(self, router_id)
        destination = router.get_destination(destination_id)
        returnValue(response(
            request, 'destination found', (yield destination.status())
        ))

    @app.route(
        '/routers/<string:router_id>/destinations/<string:destination_id>',
        methods=['PUT'])
    @json_body
    @validate(
        body_schema({
            'type': 'object',
            'properties': {
                'label': {'type': 'string'},
                'config': {'type': 'object'},
                'metadata': {'type': 'object'},
                'mo_url': {'type': 'string'},
                'mo_url_token': {'type': 'string'},
                'amqp_queue': {'type': 'string'},
                'character_limit': {
                    'type': 'integer',
                    'minimum': 0,
                },
            },
            'additionalProperties': False,
            'required': ['config'],
        }))
    @inlineCallbacks
    def replace_router_destination(
            self, request, body, router_id, destination_id):
        """Replace the config of a router destination"""
        router = yield Router.from_id(self, router_id)
        yield router.validate_destination_config(body['config'])

        destination = router.get_destination(destination_id)
        destination.destination_config = body
        destination.destination_config['id'] = destination_id

        # Stop and start the router for the worker to get the new config
        yield router.stop()
        router.start(self.service)
        yield destination.save()
        returnValue(response(
            request, 'destination updated', (yield destination.status())))

    @app.route(
        '/routers/<string:router_id>/destinations/<string:destination_id>',
        methods=['PATCH'])
    @json_body
    @validate(
        body_schema({
            'type': 'object',
            'properties': {
                'label': {'type': 'string'},
                'config': {'type': 'object'},
                'metadata': {'type': 'object'},
                'mo_url': {'type': 'string'},
                'mo_url_token': {'type': 'string'},
                'amqp_queue': {'type': 'string'},
                'character_limit': {
                    'type': 'integer',
                    'minimum': 0,
                },
            },
            'additionalProperties': False,
            'required': [],
        }))
    @inlineCallbacks
    def update_router_destination(
            self, request, body, router_id, destination_id):
        """Update the config of a router destination"""
        router = yield Router.from_id(self, router_id)
        if 'config' in body:
            yield router.validate_destination_config(body['config'])

        destination = router.get_destination(destination_id)
        destination.destination_config.update(body)

        # Stop and start the router for the worker to get the new config
        yield router.stop()
        router.start(self.service)
        yield destination.save()
        returnValue(response(
            request, 'destination updated', (yield destination.status())))

    @app.route(
        '/routers/<string:router_id>/destinations/<string:destination_id>',
        methods=['DELETE'])
    @inlineCallbacks
    def delete_router_destination(self, request, router_id, destination_id):
        """Delete and stop the router destination"""
        router = yield Router.from_id(self, router_id)
        destination = router.get_destination(destination_id)

        yield router.stop()
        yield destination.delete()
        router.start(self.service)

        returnValue(response(request, 'destination deleted', {}))

    @app.route(
        '/routers/<string:router_id>/destinations/<string:destination_id>/messages/',  # noqa
        methods=['POST'])
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
                'event_auth_token': {'type': 'string'},
                'priority': {'type': 'string'},
                'channel_data': {'type': 'object'},
            },
            'required': ['content'],
            'additionalProperties': False,
        }))
    @inlineCallbacks
    def send_destination_message(
            self, request, body, router_id, destination_id):
        '''Send an outbound (mobile terminated) message'''
        router = yield Router.from_id(self, router_id)
        router.get_destination(destination_id)
        channel_id = yield router.router_worker.get_destination_channel(
            destination_id, body)

        in_msg = None
        if 'reply_to' in body:
            in_msg = yield self.inbounds.load_vumi_message(
                destination_id, body['reply_to'])

        msg = yield self.send_message_on_channel(
            channel_id, body, in_msg)

        self.outbounds.store_message(destination_id, msg)

        returnValue(response(
            request, 'message submitted', msg, code=http.CREATED))

    @app.route(
        '/routers/<string:router_id>/destinations/<string:destination_id>/messages/<string:message_id>',  # noqa
        methods=['GET'])
    @inlineCallbacks
    def get_destination_message_status(
            self, request, router_id, destination_id, message_id):

        router = yield Router.from_id(self, router_id)
        router.get_destination(destination_id)

        data = yield self.get_message_events(
            request, destination_id, message_id)

        returnValue(response(request, 'message status', data))

    @inlineCallbacks
    def get_message_events(self, request, location_id, message_id):
        events = yield self.outbounds.load_all_events(location_id, message_id)
        events = sorted(
            (api_from_event(location_id, e) for e in events),
            key=lambda e: e['timestamp'])

        last_event = events[-1] if events else None
        last_event_type = last_event['event_type'] if last_event else None
        last_event_timestamp = last_event['timestamp'] if last_event else None

        returnValue({
            'id': message_id,
            'last_event_type': last_event_type,
            'last_event_timestamp': last_event_timestamp,
            'events': events,
        })

    @inlineCallbacks
    def send_message_on_channel(self, channel_id, body, in_msg=None):
        if 'to' not in body and 'reply_to' not in body:
            raise ApiUsageError(
                'Either "to" or "reply_to" must be specified')

        channel = yield Channel.from_id(
            self.redis, self.config, channel_id, self.service, self.plugins)

        if 'reply_to' in body:
            msg = yield channel.send_reply_message(
                self.message_sender, self.outbounds, self.inbounds, body,
                allow_expired_replies=self.config.allow_expired_replies,
                in_msg=in_msg)
        else:
            msg = yield channel.send_message(
                self.message_sender, self.outbounds, body)

        yield self.message_rate.increment(
            channel_id, 'outbound', self.config.metric_window)

        returnValue(msg)

    @app.route('/health', methods=['GET'])
    def health_status(self, request):
        if self.config.rabbitmq_management_interface:

            def get_queues(queue_data):

                gets = []

                for _, queue_ids in queue_data:
                    for queue_id in queue_ids:
                        for sub in ['inbound', 'outbound', 'event']:
                            queue_name = "%s.%s" % (queue_id, sub)

                            get = self.rabbitmq_management_client.get_queue(
                                self.amqp_config['vhost'], queue_name)
                            gets.append(get)

                return gets

            def return_queue_results(results):
                queues = []
                stuck = False

                for _, queue in results:

                    if ('messages' in queue):
                        details = {
                            'name': queue['name'],
                            'stuck': False,
                            'messages': queue.get('messages'),
                            'rate':
                                queue['messages_stats']['ack_details']['rate']
                        }
                        if (details['messages'] > 0 and details['rate'] == 0):
                            stuck = True
                            details['stuck'] = True

                        queues.append(details)

                status = 'queues ok'
                code = http.OK
                if stuck:
                    status = "queues stuck"
                    code = http.INTERNAL_SERVER_ERROR

                return response(request, status, queues, code=code)

            def get_routers_objects(router_ids):
                gets = []
                for router_id in router_ids:
                    get = Router.from_id(self, router_id)
                    gets.append(get)

                return gets

            def get_destinations(routers):
                destinations = []
                for _, router in routers:
                    destinations.extend(router.get_destination_list())
                return destinations

            d1 = Channel.get_all(self.redis)
            d2 = Router.get_all(self.router_store)
            d2.addCallback(get_routers_objects)
            d2.addCallback(defer.DeferredList)
            d2.addCallback(get_destinations)

            d = defer.DeferredList([d1, d2])
            d.addCallback(get_queues)
            d.addCallback(defer.DeferredList)
            d.addCallback(return_queue_results)
            return d
        else:
            return response(request, 'health ok', {})
