from copy import deepcopy
import json
import uuid
from twisted.internet.defer import inlineCallbacks, returnValue
from vumi.service import WorkerCreator
from vumi.servicemaker import VumiOptions
from vumi.persist.redis_manager import RedisManager


class ChannelNotFound(Exception):
    '''Raised when a channel's data cannot be found.'''


class InvalidChannelType(Exception):
    '''Raised when an invalid channel type is specified'''


transports = {
    'telnet': 'vumi.transport.telnet.TelnetServerTransport',
}


class Channel(object):
    def __init__(self, redis_config, properties, id=None):
        '''Creates a new channel. ``redis_config`` is the redis config, from
        which a sub manager is created using the channel id. If the channel id
        is not supplied, a UUID one is generated. Call ``save`` to save the
        channel data.'''
        self._properties, self.id = properties, id
        if self.id is None:
            self.id = str(uuid.uuid4())
        self._redis_base = RedisManager.from_config(redis_config)
        self._redis = self._redis_base.sub_manager(self.id)

    def start(self, service):
        '''Starts the relevant workers for the channel'''
        class_name = transports.get(self._properties['type'])
        if class_name is None:
            raise InvalidChannelType(
                'Invalid channel type %r, must be one of: %r' % (
                    self._properties['type'], transports.keys()))
        options = deepcopy(VumiOptions
        workercreator = WorkerCreator(VumiOptions.default_vumi_options)
        self.transport_worker = workercreator.create_worker(
            class_name, self._properties['config'])
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
    def from_id(cls, redis_config, id):
        '''Creates a channel by loading the data from redis, given the
        channel's id'''
        redis_base = RedisManager.from_config(redis_config)
        redis = redis_base.sub_manager(id)
        properties = yield redis.get('properties')
        if properties is None:
            raise ChannelNotFound()
        properties = json.loads(properties)
        returnValue(cls(redis_config, properties, id))

    @classmethod
    def get_all(cls, redis_config):
        '''Returns a set of keys of all of the channels'''
        redis = RedisManager.from_config(redis_config)
        return redis.smembers('channels')

    @property
    def status(self):
        '''Returns a dict with the configuration and status of the channel'''
        status = deepcopy(self._properties)
        status['id'] = self.id
        # TODO: Implement channel status
        status['status'] = {}
        return status
