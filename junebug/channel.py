import collections
from copy import deepcopy
import json
import uuid
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web import http
from vumi.message import TransportUserMessage
from vumi.service import WorkerCreator
from vumi.servicemaker import VumiOptions

from junebug.error import JunebugError


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
    def __init__(
            self, redis_manager, amqp_config, properties, id=None):
        '''Creates a new channel. ``redis_manager`` is the redis manager, from
        which a sub manager is created using the channel id. If the channel id
        is not supplied, a UUID one is generated. Call ``save`` to save the
        channel data. It can be started using the ``start`` function.'''
        self._properties, self.id, self.redis = (
            properties, id, redis_manager)
        if self.id is None:
            self.id = str(uuid.uuid4())

        self.options = deepcopy(VumiOptions.default_vumi_options)
        self.options.update(amqp_config)

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

    def start(self, service, transport_worker=None):
        '''Starts the relevant workers for the channel. ``service`` is the
        parent of under which the workers should be started.'''
        class_name = transports.get(self._properties.get('type'))
        if class_name is None:
            raise InvalidChannelType(
                'Invalid channel type %r, must be one of: %s' % (
                    self._properties.get('type'),
                    ', '.join(transports.keys())))

        # transport_worker parameter is for testing, if it isn't specified,
        # create the transport worker
        if transport_worker is None:
            workercreator = WorkerCreator(self.options)
            config = self._properties['config']
            config = self._convert_unicode(config)
            config['transport_name'] = self.id
            transport_worker = workercreator.create_worker(
                class_name, config)
        transport_worker.setName(self.id)
        transport_worker.setServiceParent(service)
        self.transport_worker = transport_worker

    @inlineCallbacks
    def stop(self):
        '''Stops the relevant workers for the channel'''
        if hasattr(self, 'transport_worker'):
            yield self.transport_worker.disownServiceParent()
            del self.transport_worker

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

        # Only restart if the channel config has changed
        if properties.get('config') is not None:
            service = self.transport_worker.parent
            yield self.stop()
            yield self.start(service)

        returnValue((yield self.status()))

    @inlineCallbacks
    def delete(self):
        '''Removes the channel data from redis'''
        channel_redis = yield self.redis.sub_manager(self.id)
        yield channel_redis.delete('properties')

    @classmethod
    @inlineCallbacks
    def from_id(cls, redis, amqp_config, id, parent):
        '''Creates a channel by loading the data from redis, given the
        channel's id, and the parent service of the channel'''
        channel_redis = yield redis.sub_manager(id)
        properties = yield channel_redis.get('properties')
        if properties is None:
            raise ChannelNotFound()
        properties = json.loads(properties)
        obj = cls(redis, amqp_config, properties, id)
        obj.transport_worker = parent.getServiceNamed(id)
        returnValue(obj)

    @classmethod
    @inlineCallbacks
    def get_all(cls, redis):
        '''Returns a set of keys of all of the channels'''
        channels = yield redis.smembers('channels')
        returnValue(channels)

    def status(self):
        '''Returns a dict with the configuration and status of the channel'''
        status = deepcopy(self._properties)
        status['id'] = self.id
        # TODO: Implement channel status
        status['status'] = {}
        return status

    def _api_from_message(self, msg):
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

    def _message_from_api(self, msg):
        ret = {}
        ret['to_addr'] = msg.get('to')
        ret['from_addr'] = msg['from']
        ret['content'] = msg['content']
        ret['transport_name'] = self.id
        channel_data = msg.get('channel_data', {})
        if channel_data.get('continue_session') is not None:
            ret['continue_session'] = channel_data.pop('continue_session')
        if channel_data.get('session_event') is not None:
            ret['session_event'] = channel_data.pop('session_event')
        ret['helper_metadata'] = channel_data
        return ret

    @inlineCallbacks
    def send_message(self, message_sender, msg):
        '''Sends a message. Takes a junebug.amqp.MessageSender instance to
        send a message.'''
        message = TransportUserMessage.send(
            **self._message_from_api(msg))
        queue = '%s.outbound' % self.id
        msg = yield message_sender.send_message(message, routing_key=queue)
        returnValue(self._api_from_message(msg))
