from copy import deepcopy
import json
import uuid
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web import http
from vumi.message import TransportUserMessage
from vumi.service import WorkerCreator
from vumi.servicemaker import VumiOptions

from junebug.logging_service import JunebugLoggerService, read_logs
from junebug.stores import StatusStore, MessageRateStore
from junebug.utils import (
    api_from_message, message_from_api, api_from_status, convert_unicode)
from junebug.error import JunebugError


class MessageNotFound(JunebugError):
    '''Raised when a message is not found.'''
    name = 'MessageNotFound'
    description = 'message not found'
    code = http.BAD_REQUEST


class ChannelNotFound(JunebugError):
    '''Raised when a channel's data cannot be found.'''
    name = 'ChannelNotFound'
    description = 'channel not found'
    code = http.NOT_FOUND


class InvalidChannelType(JunebugError):
    '''Raised when an invalid channel type is specified'''
    name = 'InvalidChannelType',
    description = 'invalid channel type'
    code = http.BAD_REQUEST


class MessageTooLong(JunebugError):
    '''Raised when a message exceeds the configured character limit'''
    name = 'MessageTooLong'
    description = 'message too long'
    code = http.BAD_REQUEST


transports = {
    'telnet': 'vumi.transports.telnet.TelnetServerTransport',
    'xmpp': 'vumi.transports.xmpp.XMPPTransport',
    'smpp': 'vumi.transports.smpp.SmppTransceiverTransport',
    'dmark': 'vumi.transports.dmark.DmarkUssdTransport',
}

allowed_message_fields = [
    'transport_name', 'timestamp', 'in_reply_to', 'to_addr', 'from_addr',
    'content', 'session_event', 'helper_metadata', 'message_id']
# excluded fields: from_addr_type, group, provider, routing_metadata,
# to_addr_type, from_addr_type, message_version, transport_metadata,
# message_type, transport_type


class Channel(object):
    OUTBOUND_QUEUE = '%s.outbound'
    APPLICATION_ID = 'application:%s'
    STATUS_APPLICATION_ID = 'status:%s'
    APPLICATION_CLS_NAME = 'junebug.workers.MessageForwardingWorker'
    STATUS_APPLICATION_CLS_NAME = 'junebug.workers.ChannelStatusWorker'
    JUNEBUG_LOGGING_SERVICE_CLS = JunebugLoggerService

    def __init__(self, redis_manager, config, properties, plugins=[], id=None):
        '''Creates a new channel. ``redis_manager`` is the redis manager, from
        which a sub manager is created using the channel id. If the channel id
        is not supplied, a UUID one is generated. Call ``save`` to save the
        channel data. It can be started using the ``start`` function.'''
        self._properties = properties
        self.redis = redis_manager
        self.id = id
        self.config = config
        if self.id is None:
            self.id = str(uuid.uuid4())

        self.options = deepcopy(VumiOptions.default_vumi_options)
        self.options.update(self.config.amqp)

        self.transport_worker = None
        self.application_worker = None
        self.status_application_worker = None

        self.sstore = StatusStore(self.redis)
        self.plugins = plugins

        self.message_rates = MessageRateStore(self.redis)

    @property
    def application_id(self):
        return self.APPLICATION_ID % (self.id,)

    @property
    def status_application_id(self):
        return self.STATUS_APPLICATION_ID % (self.id,)

    @property
    def character_limit(self):
        return self._properties.get('character_limit')

    @inlineCallbacks
    def start(self, service, transport_worker=None):
        '''Starts the relevant workers for the channel. ``service`` is the
        parent of under which the workers should be started.'''
        self._start_transport(service, transport_worker)
        self._start_application(service)
        self._start_status_application(service)
        for plugin in self.plugins:
            yield plugin.channel_started(self)

    @inlineCallbacks
    def stop(self):
        '''Stops the relevant workers for the channel'''
        yield self._stop_application()
        yield self._stop_status_application()
        yield self._stop_transport()
        for plugin in self.plugins:
            yield plugin.channel_stopped(self)

    @inlineCallbacks
    def save(self):
        '''Saves the channel data into redis.'''
        properties = json.dumps(self._properties)
        channel_redis = yield self.redis.sub_manager(self.id)
        yield channel_redis.set('properties', properties)
        yield self.redis.sadd('channels', self.id)

    @inlineCallbacks
    def update(self, properties):
        '''Updates the channel configuration, saves the updated configuration,
        and (if needed) restarts the channel with the new configuration.
        Returns the updated configuration and status.'''
        self._properties.update(properties)
        yield self.save()
        service = self.transport_worker.parent

        # Only restart if the channel config has changed
        if 'config' in properties:
            yield self._stop_transport()
            yield self._start_transport(service)

        if 'mo_url' in properties or 'amqp_queue' in properties:
            yield self._stop_application()
            yield self._start_application(service)

        returnValue((yield self.status()))

    @inlineCallbacks
    def delete(self):
        '''Removes the channel data from redis'''
        channel_redis = yield self.redis.sub_manager(self.id)
        yield channel_redis.delete('properties')
        yield self.redis.srem('channels', self.id)

    @inlineCallbacks
    def status(self):
        '''Returns a dict with the configuration and status of the channel'''
        status = deepcopy(self._properties)
        status['id'] = self.id
        status['status'] = yield self._get_status()
        returnValue(status)

    def _get_message_rate(self, label):
        return self.message_rates.get_messages_per_second(
            self.id, label, self.config.metric_window)

    @inlineCallbacks
    def _get_status(self):
        components = yield self.sstore.get_statuses(self.id)
        components = dict(
            (k, api_from_status(self.id, v)) for k, v in components.iteritems()
        )

        status_values = {
            'down': 0,
            'degraded': 1,
            'ok': 2,
        }

        try:
            status = min(
                (c['status'] for c in components.values()),
                key=status_values.get)
        except ValueError:
            # No statuses
            status = None

        returnValue({
            'components': components,
            'status': status,
            'inbound_message_rate': (
                yield self._get_message_rate('inbound')),
            'outbound_message_rate': (
                yield self._get_message_rate('outbound')),
            'submitted_event_rate': (
                yield self._get_message_rate('submitted')),
            'rejected_event_rate': (
                yield self._get_message_rate('rejected')),
            'delivery_succeeded_rate': (
                yield self._get_message_rate('delivery_succeeded')),
            'delivery_failed_rate': (
                yield self._get_message_rate('delivery_failed')),
            'delivery_pending_rate': (
                yield self._get_message_rate('delivery_pending')),
        })

    @classmethod
    @inlineCallbacks
    def from_id(cls, redis, config, id, parent, plugins=[]):
        '''Creates a channel by loading the data from redis, given the
        channel's id, and the parent service of the channel'''
        channel_redis = yield redis.sub_manager(id)
        properties = yield channel_redis.get('properties')
        if properties is None:
            raise ChannelNotFound()
        properties = json.loads(properties)

        obj = cls(redis, config, properties, plugins, id=id)
        obj._restore(parent)

        returnValue(obj)

    @classmethod
    @inlineCallbacks
    def get_all(cls, redis):
        '''Returns a set of keys of all of the channels'''
        channels = yield redis.smembers('channels')
        returnValue(channels)

    @classmethod
    @inlineCallbacks
    def start_all_channels(cls, redis, config, parent, plugins=[]):
        '''Ensures that all of the stored channels are running'''
        for id in (yield cls.get_all(redis)):
            if id not in parent.namedServices:
                properties = json.loads((
                    yield redis.get('%s:properties' % id)))
                channel = cls(redis, config, properties, plugins, id=id)
                yield channel.start(parent)

    @inlineCallbacks
    def send_message(self, sender, outbounds, msg):
        '''Sends a message.'''
        event_url = msg.get('event_url')
        event_auth_token = msg.get('event_auth_token', None)
        msg = message_from_api(self.id, msg)
        msg = TransportUserMessage.send(**msg)
        msg = yield self._send_message(sender, outbounds, event_url, msg,
                                       event_auth_token)
        returnValue(api_from_message(msg))

    @inlineCallbacks
    def send_reply_message(self, sender, outbounds, inbounds, msg,
                           allow_expired_replies=False):
        '''Sends a reply message.'''
        in_msg = yield inbounds.load_vumi_message(self.id, msg['reply_to'])
        # NOTE: If we have a `reply_to` that cannot be found but also are
        #       given a `to` and the config says we can send expired
        #       replies then pop the `reply_to` from the message
        #       and handle it like a normal outbound message.
        if in_msg is None and msg.get('to') and allow_expired_replies:
            msg.pop('reply_to')
            returnValue((yield self.send_message(sender, outbounds, msg)))
        elif in_msg is None:
            raise MessageNotFound(
                "Inbound message with id %s not found" % (msg['reply_to'],))

        event_url = msg.get('event_url')
        event_auth_token = msg.get('event_auth_token', None)
        msg = message_from_api(self.id, msg)
        msg = in_msg.reply(**msg)
        msg = yield self._send_message(sender, outbounds, event_url, msg,
                                       event_auth_token)
        returnValue(api_from_message(msg))

    def get_logs(self, n):
        '''Returns the last `n` logs. If `n` is greater than the configured
        limit, only returns the configured limit amount of logs. If `n` is
        None, returns the configured limit amount of logs.'''
        if n is None:
            n = self.config.max_logs
        n = min(n, self.config.max_logs)
        logfile = self.transport_worker.getServiceNamed(
            'Junebug Worker Logger').logfile
        return read_logs(logfile, n)

    @property
    def _transport_config(self):
        config = self._properties['config']
        config = convert_unicode(config)
        config['transport_name'] = self.id
        config['worker_name'] = self.id
        config['publish_status'] = True
        return config

    @property
    def _application_config(self):
        return {
            'transport_name': self.id,
            'mo_message_url': self._properties.get('mo_url'),
            'mo_message_url_auth_token': self._properties.get(
                'mo_url_auth_token'),
            'message_queue': self._properties.get('amqp_queue'),
            'redis_manager': self.config.redis,
            'inbound_ttl': self.config.inbound_message_ttl,
            'outbound_ttl': self.config.outbound_message_ttl,
            'metric_window': self.config.metric_window,
        }

    @property
    def _status_application_config(self):
        return {
            'redis_manager': self.config.redis,
            'channel_id': self.id,
            'status_url': self._properties.get('status_url'),
        }

    @property
    def _available_transports(self):
        if self.config.replace_channels:
            return self.config.channels
        else:
            channels = {}
            channels.update(transports)
            channels.update(self.config.channels)
            return channels

    @property
    def _transport_cls_name(self):
        cls_name = self._available_transports.get(self._properties.get('type'))

        if cls_name is None:
            raise InvalidChannelType(
                'Invalid channel type %r, must be one of: %s' % (
                    self._properties.get('type'),
                    ', '.join(self._available_transports.keys())))

        return cls_name

    def _start_transport(self, service, transport_worker=None):
        # transport_worker parameter is for testing, if it is None,
        # create the transport worker
        if transport_worker is None:
            transport_worker = self._create_transport()

        transport_worker.setName(self.id)

        logging_service = self._create_junebug_logger_service()
        transport_worker.addService(logging_service)

        transport_worker.setServiceParent(service)
        self.transport_worker = transport_worker

    def _start_application(self, service):
        worker = self._create_application()
        worker.setName(self.application_id)

        worker.setServiceParent(service)
        self.application_worker = worker

    def _start_status_application(self, service):
        worker = self._create_status_application()
        worker.setName(self.status_application_id)
        worker.setServiceParent(service)
        self.status_application_worker = worker

    def _create_transport(self):
        return self._create_worker(
            self._transport_cls_name,
            self._transport_config)

    def _create_application(self):
        return self._create_worker(
            self.APPLICATION_CLS_NAME,
            self._application_config)

    def _create_status_application(self):
        return self._create_worker(
            self.STATUS_APPLICATION_CLS_NAME,
            self._status_application_config)

    def _create_junebug_logger_service(self):
        return self.JUNEBUG_LOGGING_SERVICE_CLS(
            self.id, self.config.logging_path, self.config.log_rotate_size,
            self.config.max_log_files)

    def _create_worker(self, cls_name, config):
        creator = WorkerCreator(self.options)
        worker = creator.create_worker(cls_name, config)
        return worker

    @inlineCallbacks
    def _stop_transport(self):
        if self.transport_worker is not None:
            yield self.transport_worker.disownServiceParent()
            self.transport_worker = None

    @inlineCallbacks
    def _stop_application(self):
        if self.application_worker is not None:
            yield self.application_worker.disownServiceParent()
            self.application_worker = None

    @inlineCallbacks
    def _stop_status_application(self):
        if self.status_application_worker is not None:
            yield self.status_application_worker.disownServiceParent()
            self.status_application_worker = None

    def _restore(self, service):
        self.transport_worker = service.getServiceNamed(self.id)
        self.application_worker = service.getServiceNamed(self.application_id)
        self.status_application_worker = service.getServiceNamed(
            self.status_application_id)

    def _check_character_limit(self, content):
        count = len(content)
        if (self.character_limit is not None and count > self.character_limit):
            raise MessageTooLong(
                'Message content %r is of length %d, which is greater than the'
                ' character limit of %d' % (
                    content, count, self.character_limit)
                )

    @inlineCallbacks
    def _send_message(self, sender, outbounds, event_url, msg,
                      event_auth_token=None):
        self._check_character_limit(msg['content'])

        if event_url is not None:
            yield outbounds.store_event_url(
                self.id, msg['message_id'], event_url)
            if event_auth_token is not None:
                yield outbounds.store_event_auth_token(
                    self.id, msg['message_id'], event_auth_token
                )

        queue = self.OUTBOUND_QUEUE % (self.id,)
        msg = yield sender.send_message(msg, routing_key=queue)
        returnValue(msg)
