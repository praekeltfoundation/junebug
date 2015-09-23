import collections
from copy import deepcopy
import json
import uuid
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web import http
from vumi.message import TransportUserMessage
from vumi.service import WorkerCreator
from vumi.servicemaker import VumiOptions

from junebug.utils import api_from_message, message_from_api
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


transports = {
    'telnet': 'vumi.transports.telnet.TelnetServerTransport',
    'xmpp': 'vumi.transports.xmpp.XMPPTransport',
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
    APPLICATION_CLS_NAME = 'junebug.workers.MessageForwardingWorker'

    def __init__(self, redis_manager, config, properties, id=None):
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

    @property
    def application_id(self):
        return self.APPLICATION_ID % (self.id,)

    def start(self, service, transport_worker=None):
        '''Starts the relevant workers for the channel. ``service`` is the
        parent of under which the workers should be started.'''
        self._start_transport(service, transport_worker)
        self._start_application(service)

    @inlineCallbacks
    def stop(self):
        '''Stops the relevant workers for the channel'''
        yield self._stop_application()
        yield self._stop_transport()

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

        if 'mo_url' in properties:
            yield self._stop_application()
            yield self._start_application(service)

        returnValue((yield self.status()))

    @inlineCallbacks
    def delete(self):
        '''Removes the channel data from redis'''
        channel_redis = yield self.redis.sub_manager(self.id)
        yield channel_redis.delete('properties')
        yield self.redis.srem('channels', self.id)

    def status(self):
        '''Returns a dict with the configuration and status of the channel'''
        status = deepcopy(self._properties)
        status['id'] = self.id
        # TODO: Implement channel status
        status['status'] = {}
        return status

    @classmethod
    @inlineCallbacks
    def from_id(cls, redis, config, id, parent):
        '''Creates a channel by loading the data from redis, given the
        channel's id, and the parent service of the channel'''
        channel_redis = yield redis.sub_manager(id)
        properties = yield channel_redis.get('properties')
        if properties is None:
            raise ChannelNotFound()
        properties = json.loads(properties)

        obj = cls(redis, config, properties, id)
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
    def send_message(cls, id, sender, outbounds, msg):
        '''Sends a message.'''
        event_url = msg.get('event_url')
        msg = message_from_api(id, msg)
        msg = TransportUserMessage.send(**msg)
        msg = yield cls._send_message(id, sender, outbounds, event_url, msg)
        returnValue(api_from_message(msg))

    @classmethod
    @inlineCallbacks
    def send_reply_message(cls, id, sender, outbounds, inbounds, msg):
        '''Sends a reply message.'''
        in_msg = yield inbounds.load_vumi_message(id, msg['reply_to'])

        if in_msg is None:
            raise MessageNotFound(
                "Inbound message with id %s not found" % (msg['reply_to'],))

        event_url = msg.get('event_url')
        msg = message_from_api(id, msg)
        msg = in_msg.reply(**msg)
        msg = yield cls._send_message(id, sender, outbounds, event_url, msg)
        returnValue(api_from_message(msg))

    @property
    def _transport_config(self):
        config = self._properties['config']
        config = self._convert_unicode(config)
        config['transport_name'] = self.id
        return config

    @property
    def _application_config(self):
        return {
            'transport_name': self.id,
            'mo_message_url': self._properties['mo_url'],
            'redis_manager': self.config.redis,
            'inbound_ttl': self.config.inbound_message_ttl,
            'outbound_ttl': self.config.outbound_message_ttl,
        }

    @property
    def _transport_cls_name(self):
        cls_name = transports.get(self._properties.get('type'))

        if cls_name is None:
            raise InvalidChannelType(
                'Invalid channel type %r, must be one of: %s' % (
                    self._properties.get('type'),
                    ', '.join(transports.keys())))

        return cls_name

    def _start_transport(self, service, transport_worker=None):
        # transport_worker parameter is for testing, if it is None,
        # create the transport worker
        if transport_worker is None:
            transport_worker = self._create_transport()

        transport_worker.setName(self.id)
        transport_worker.setServiceParent(service)
        self.transport_worker = transport_worker

    def _start_application(self, service):
        worker = self._create_application()
        worker.setName(self.application_id)
        worker.setServiceParent(service)
        self.application_worker = worker

    def _create_transport(self):
        return self._create_worker(
            self._transport_cls_name,
            self._transport_config)

    def _create_application(self):
        return self._create_worker(
            self.APPLICATION_CLS_NAME,
            self._application_config)

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

    def _restore(self, service):
        self.transport_worker = service.getServiceNamed(self.id)
        self.application_worker = service.getServiceNamed(self.application_id)

    def _convert_unicode(self, data):
        # Twisted doesn't like it when we give unicode in for config things
        if isinstance(data, basestring):
            return str(data)
        elif isinstance(data, collections.Mapping):
            return dict(map(self._convert_unicode, data.iteritems()))
        elif isinstance(data, collections.Iterable):
            return type(data)(map(self._convert_unicode, data))
        else:
            return data

    @classmethod
    @inlineCallbacks
    def _send_message(cls, id, sender, outbounds, event_url, msg):
        if event_url is not None:
            yield outbounds.store_event_url(id, msg['message_id'], event_url)

        queue = cls.OUTBOUND_QUEUE % (id,)
        msg = yield sender.send_message(msg, routing_key=queue)
        returnValue(msg)
