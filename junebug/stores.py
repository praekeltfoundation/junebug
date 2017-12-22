import json
from math import ceil
import time
from twisted.internet.defer import inlineCallbacks, returnValue, gatherResults

from vumi.message import (
    TransportEvent, TransportUserMessage, TransportStatus, to_json, from_json)


class BaseStore(object):
    '''
    Base class for store classes. Stores data in redis as a hash.

    :param redis: Redis manager
    :type redis: :class:`vumi.persist.redis_manager.RedisManager`
    :param ttl: Expiry time for keys in the store
    :type ttl: integer
    '''

    USE_DEFAULT_TTL = object()

    def __init__(self, redis, ttl=None):
        self.redis = redis
        self.ttl = ttl

    @inlineCallbacks
    def _redis_op(self, func, id, *args, **kwargs):
        ttl = kwargs.pop('ttl')
        if ttl is self.USE_DEFAULT_TTL:
            ttl = self.ttl
        val = yield func(id, *args, **kwargs)
        if ttl is not None:
            yield self.redis.expire(id, ttl)
        returnValue(val)

    def get_key(self, *args):
        '''Returns a key given strings'''
        return ':'.join(args)

    def store_all(self, id, properties, ttl=USE_DEFAULT_TTL):
        '''Stores all of the keys and values given in the dict `properties` as
        a hash at the key `id`'''
        return self._redis_op(self.redis.hmset, id, properties, ttl=ttl)

    def store_property(self, id, key, value, ttl=USE_DEFAULT_TTL):
        '''Stores a single key with a value as a hash at the key `id`'''
        return self._redis_op(self.redis.hset, id, key, value, ttl=ttl)

    def remove_property(self, id, key, ttl=USE_DEFAULT_TTL):
        '''Removes the property specified key from `id`'''
        return self._redis_op(self.redis.hdel, id, key, ttl=ttl)

    @inlineCallbacks
    def load_all(self, id, ttl=USE_DEFAULT_TTL):
        '''Retrieves all the keys and values stored as a hash at the key
        `id`'''
        returnValue((
            yield self._redis_op(self.redis.hgetall, id, ttl=ttl)) or {})

    def load_property(self, id, key, ttl=USE_DEFAULT_TTL):
        return self._redis_op(self.redis.hget, id, key, ttl=ttl)

    def increment_id(self, id, ttl=USE_DEFAULT_TTL):
        '''Increments the value stored at `id` by 1.'''
        return self._redis_op(self.redis.incr, id, 1, ttl=ttl)

    def get_id(self, id, ttl=USE_DEFAULT_TTL):
        '''Returns the value stored at `id`.'''
        return self._redis_op(self.redis.get, id, ttl=ttl)

    def get_set(self, id, ttl=USE_DEFAULT_TTL):
        '''Returns all elements of the set stored at `id`.'''
        return self._redis_op(self.redis.smembers, id, ttl=ttl)

    def add_set_item(self, id, value, ttl=USE_DEFAULT_TTL):
        '''Adds an item to a set'''
        return self._redis_op(self.redis.sadd, id, value, ttl=ttl)

    def remove_set_item(self, id, value, ttl=USE_DEFAULT_TTL):
        '''Removes the item `value` from the set at `id`'''
        return self._redis_op(self.redis.srem, id, value, ttl=ttl)

    def store_value(self, id, value, ttl=USE_DEFAULT_TTL):
        '''Stores `value` at `id`'''
        return self._redis_op(self.redis.set, id, value, ttl=ttl)

    def load_value(self, id, ttl=USE_DEFAULT_TTL):
        '''Gets the value stored at `id`'''
        return self._redis_op(self.redis.get, id, ttl=ttl)

    def remove_value(self, id, ttl=USE_DEFAULT_TTL):
        '''Deletes the value stored at `id`'''
        return self._redis_op(self.redis.delete, id, ttl=ttl)


class InboundMessageStore(BaseStore):
    '''Stores the entire inbound message, in order to later construct
    replies'''

    def get_key(self, channel_id, message_id):
        return super(InboundMessageStore, self).get_key(
            channel_id, 'inbound_messages', message_id)

    def store_vumi_message(self, channel_id, message):
        '''Stores the given vumi message'''
        key = self.get_key(channel_id, message.get('message_id'))
        return self.store_property(key, 'message', message.to_json())

    @inlineCallbacks
    def load_vumi_message(self, channel_id, message_id):
        '''Retrieves the stored vumi message, given its unique id'''
        key = self.get_key(channel_id, message_id)
        msg_json = yield self.load_property(key, 'message')
        if msg_json is None:
            returnValue(None)
        returnValue(TransportUserMessage.from_json(msg_json))


class OutboundMessageStore(BaseStore):
    '''Stores the event url, in order to look it up when deciding where events
    should go'''
    PROPERTY_KEYS = ['message']

    def get_key(self, channel_id, message_id):
        return super(OutboundMessageStore, self).get_key(
            channel_id, 'outbound_messages', message_id)

    def load_event_url(self, channel_id, message_id):
        '''Retrieves a stored event url, given the channel and message ids'''
        key = self.get_key(channel_id, message_id)
        d = self.load_property(key, 'message')
        d.addCallback(from_json)
        d.addErrback(lambda _: {})
        d.addCallback(lambda m: m.get('event_url', None))
        return d

    def load_event_auth_token(self, channel_id, message_id):
        '''Retrieves a stored event auth token, given the channel and message
        ids'''
        key = self.get_key(channel_id, message_id)
        d = self.load_property(key, 'message')
        d.addCallback(from_json)
        d.addErrback(lambda _: {})
        d.addCallback(lambda m: m.get('event_auth_token', None))
        return d

    def store_message(self, channel_id, message):
        '''Stores an outbound message'''
        key = self.get_key(channel_id, message['message_id'])
        return self.store_property(key, 'message', to_json(message))

    def store_event(self, channel_id, message_id, event):
        '''Stores an event for a message'''
        key = self.get_key(channel_id, message_id)
        event_id = event['event_id']
        return self.store_property(key, event_id, event.to_json())

    def load_message(self, channel_id, message_id):
        key = self.get_key(channel_id, message_id)
        d = self.load_property(key, 'message')
        d.addCallback(from_json)
        d.addErrback(lambda _: None)
        return d

    @inlineCallbacks
    def load_event(self, channel_id, message_id, event_id):
        '''Loads the event with id event_id'''
        key = self.get_key(channel_id, message_id)
        event_json = yield self.load_property(key, event_id)
        if event_json is None:
            returnValue(None)
        returnValue(TransportEvent.from_json(event_json))

    @inlineCallbacks
    def load_all_events(self, channel_id, message_id):
        '''Returns a list of all the stored events'''
        key = self.get_key(channel_id, message_id)
        events_json = yield self.load_all(key)
        self._remove_property_keys(events_json)
        returnValue([
            TransportEvent.from_json(e) for e in events_json.values()])

    def _remove_property_keys(self, dct):
        '''If we remove all other property keys, we will be left with just the
        events.'''
        for k in self.PROPERTY_KEYS:
            dct.pop(k, None)


class StatusStore(BaseStore):
    '''Stores the most recent status message for each status component.'''

    def get_key(self, channel_id):
        return '%s:status' % channel_id

    def store_status(self, channel_id, status):
        '''Stores a single status. Overrides any previous status with the same
        component.'''
        key = self.get_key(channel_id)
        return self.store_property(key, status['component'], status.to_json())

    @inlineCallbacks
    def get_statuses(self, channel_id):
        '''Returns the latest status message for each component in a
        dictionary'''
        key = self.get_key(channel_id)
        statuses = yield self.load_all(key)
        returnValue(dict(
            (k, TransportStatus.from_json(v))
            for k, v in statuses.iteritems()
        ))


class MessageRateStore(BaseStore):
    '''Gets called everytime a message should be counted, and can return the
    current messages per second.'''

    def get_seconds(self):
        return time.time()

    def get_key(self, channel_id, label, bucket):
        return super(MessageRateStore, self).get_key(
            channel_id, label, str(bucket))

    def _get_current_key(self, channel_id, label, bucket_size):
        bucket = int(self.get_seconds() / bucket_size)
        return self.get_key(channel_id, label, bucket)

    def _get_last_key(self, channel_id, label, bucket_size):
        bucket = int(self.get_seconds() / bucket_size) - 1
        return self.get_key(channel_id, label, bucket)

    def increment(self, channel_id, label, bucket_size):
        '''Increments the correct counter. Should be called whenever a message
        that should be counted is received.

        Note: bucket_size should be kept constant for each channel_id and label
        combination. Changing bucket sizes results in undefined behaviour.'''
        key = self._get_current_key(channel_id, label, bucket_size)
        return self.increment_id(key, ttl=int(ceil(bucket_size * 2)))

    @inlineCallbacks
    def get_messages_per_second(self, channel_id, label, bucket_size):
        '''Gets the current message rate in messages per second.

        Note: bucket_size should be kept constant for each channel_id and label
        combination. Changing bucket sizes results in undefined behaviour.'''
        key = self._get_last_key(channel_id, label, bucket_size)
        rate = yield self.get_id(key, ttl=None)
        if rate is None:
            returnValue(0)
        returnValue(float(rate) / bucket_size)


class RouterStore(BaseStore):
    '''Stores all configuration for routers'''

    def get_router_set_key(self):
        """Gets the key for the set of routers"""
        return self.get_key('routers')

    def get_router_key(self, router_id):
        """Gets the key for a router with id ``router_id``"""
        return self.get_key('routers', router_id)

    def get_router_destination_set_key(self, router_id):
        """Gets the key for the set of destinations for the router"""
        return self.get_key('routers', router_id, 'destinations')

    def get_router_destination_key(self, router_id, destination_id):
        """Gets the key for the destination with ID ``destination_id`` for the
        router with ID ``router_id``"""
        return self.get_key(
            'routers', router_id, 'destinations', destination_id)

    def get_router_list(self):
        '''Returns a list of UUIDs for all the current router configurations'''
        d = self.get_set(self.get_router_set_key())
        d.addCallback(sorted)
        return d

    def save_router(self, config):
        '''Saves the configuration of a router'''
        d1 = self.store_value(
            self.get_router_key(config['id']), json.dumps(config))
        d2 = self.add_set_item(self.get_router_set_key(), config['id'])
        return gatherResults([d1, d2])

    def _handle_read_router_error(self, err):
        if err.type == TypeError:
            # Trying to decode ``None`` means missing router. Return None
            return None
        raise err

    def get_router_config(self, router_id):
        """Gets the configuration of a router with the id ``router_id``"""
        d = self.load_value(self.get_router_key(router_id))
        d.addCallback(json.loads)
        d.addErrback(self._handle_read_router_error)
        return d

    def delete_router(self, router_id):
        """Removes the configuration of the router with id ``router_id``"""
        d1 = self.remove_value(self.get_router_key(router_id))
        d2 = self.remove_set_item(self.get_router_set_key(), router_id)
        return gatherResults([d1, d2])

    def save_router_destination(self, router_id, destination_config):
        """Saves the configuration of a destination of a router"""
        destination_id = destination_config['id']
        d1 = self.store_value(
            self.get_router_destination_key(router_id, destination_id),
            json.dumps(destination_config)
        )
        d2 = self.add_set_item(
            self.get_router_destination_set_key(router_id), destination_id)
        return gatherResults([d1, d2])

    def get_router_destination_list(self, router_id):
        """Returns the list of destinations for a router"""
        d = self.get_set(self.get_router_destination_set_key(router_id))
        d.addCallback(sorted)
        return d

    def _handle_read_router_destination_error(self, err):
        if err.type == TypeError:
            # Trying to decode ``None`` means missing router. Return None
            return None
        raise err

    def get_router_destination_config(self, router_id, destination_id):
        """Returns the stored configuration of a router's destination"""
        d = self.load_value(
            self.get_router_destination_key(router_id, destination_id))
        d.addCallback(json.loads)
        d.addErrback(self._handle_read_router_destination_error)
        return d

    def delete_router_destination(self, router_id, destination_id):
        d1 = self.remove_value(
            self.get_router_destination_key(router_id, destination_id))
        d2 = self.remove_set_item(
            self.get_router_destination_set_key(router_id), destination_id)
        return gatherResults([d1, d2])
