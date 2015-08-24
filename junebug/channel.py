import collections
from copy import deepcopy
import json
import uuid
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web import http
from vumi.service import WorkerCreator
from vumi.servicemaker import VumiOptions
from vumi.persist.redis_manager import RedisManager

from junebug.error import JunebugError


class ChannelNotFound(JunebugError):
    '''Raised when a channel's data cannot be found.'''
    name = 'ChannelNotFound'
    description = 'channel not found',
    code = http.NOT_FOUND


class InvalidChannelType(JunebugError):
    '''Raised when an invalid channel type is specified'''
    name = 'InvalidChannelType',
    description = 'invalid channel type',
    code = http.BAD_REQUEST


transports = {
    'telnet': 'vumi.transports.telnet.TelnetServerTransport',
    'xmpp': 'vumi.transports.xmpp.XMPPTransport',
}


class Channel(object):
    def __init__(self, redis_config, properties, id=None, parent=None):
        '''Creates a new channel. ``redis_config`` is the redis config, from
        which a sub manager is created using the channel id. If the channel id
        is not supplied, a UUID one is generated. Call ``save`` to save the
        channel data. If ``parent`` is supplied, the channel is automatically
        started as a child of parent, else it is not started, and can be
        started using the ``start`` function.'''
        self._properties, self.id = properties, id
        if self.id is None:
            self.id = str(uuid.uuid4())
        self._redis_base = RedisManager.from_config(redis_config)
        self._redis = self._redis_base.sub_manager(self.id)
        if parent is not None:
            self.start(parent)

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

    def start(self, service):
        '''Starts the relevant workers for the channel. ``service`` is the
        parent of under which the workers should be started.'''
        class_name = transports.get(self._properties.get('type'))
        if class_name is None:
            raise InvalidChannelType(
                'Invalid channel type %r, must be one of: %s' % (
                    self._properties.get('type'),
                    ', '.join(transports.keys())))
        workercreator = WorkerCreator(VumiOptions.default_vumi_options)
        config = self._convert_unicode(self._properties['config'])
        self.transport_worker = workercreator.create_worker(
            class_name, config)
        self.transport_worker.setName(self.id)
        if service is not None:
            self.transport_worker.setServiceParent(service)

    @inlineCallbacks
    def stop(self):
        '''Stops the relevant workers for the channel'''
        yield self.transport_worker.stopService()

    @inlineCallbacks
    def save(self):
        '''Saves the channel data into redis.'''
        properties = json.dumps(self._properties)
        yield self._redis.set('properties', properties)
        yield self._redis_base.sadd('channels', self.id)

    @inlineCallbacks
    def delete(self):
        '''Removes the channel data from redis'''
        yield self._redis.delete('properties')

    @classmethod
    @inlineCallbacks
    def from_id(cls, redis_config, id, parent):
        '''Creates a channel by loading the data from redis, given the
        channel's id, and the parent service of the channel'''
        redis_base = RedisManager.from_config(redis_config)
        redis = redis_base.sub_manager(id)
        properties = yield redis.get('properties')
        if properties is None:
            raise ChannelNotFound()
        properties = json.loads(properties)
        obj = cls(redis_config, properties, id)
        obj.transport_worker = parent.getServiceNamed(id)
        returnValue(obj)

    @classmethod
    def get_all(cls, redis_config):
        '''Returns a set of keys of all of the channels'''
        redis = RedisManager.from_config(redis_config)
        return redis.smembers('channels')

    def status(self):
        '''Returns a dict with the configuration and status of the channel'''
        status = deepcopy(self._properties)
        status['id'] = self.id
        # TODO: Implement channel status
        status['status'] = {}
        return status
