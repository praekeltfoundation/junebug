import json
import logging

import treq

from twisted.internet.defer import inlineCallbacks

from vumi.application.base import ApplicationConfig, ApplicationWorker
from vumi.config import ConfigDict, ConfigInt, ConfigText
from vumi.message import JSONMessageEncoder
from vumi.persist.txredis_manager import TxRedisManager
from vumi.worker import BaseConfig, BaseWorker

from junebug.utils import api_from_message, api_from_event, api_from_status
from junebug.stores import (
    InboundMessageStore, OutboundMessageStore, StatusStore)


class MessageForwardingConfig(ApplicationConfig):
    '''Config for MessageForwardingWorker application worker'''

    mo_message_url = ConfigText(
        "The URL to send HTTP POST requests to for MO messages",
        required=True, static=True)

    redis_manager = ConfigDict(
        "Redis config.",
        required=True, static=True)

    inbound_ttl = ConfigInt(
        "Maximum time (in seconds) allowed to reply to messages",
        required=True, static=True)

    outbound_ttl = ConfigInt(
        "Maximum time (in seconds) allowed for events to arrive for messages",
        required=True, static=True)


class MessageForwardingWorker(ApplicationWorker):
    '''This application worker consumes vumi messages placed on a configured
    amqp queue, and sends them as HTTP requests with a JSON body to a
    configured URL'''
    CONFIG_CLASS = MessageForwardingConfig

    @inlineCallbacks
    def setup_application(self):
        self.redis = yield TxRedisManager.from_config(
            self.config['redis_manager'])

        self.inbounds = InboundMessageStore(
            self.redis, self.config['inbound_ttl'])

        self.outbounds = OutboundMessageStore(
            self.redis, self.config['outbound_ttl'])

    @inlineCallbacks
    def teardown_application(self):
        yield self.redis.close_manager()

    @property
    def channel_id(self):
        return self.config['transport_name']

    @inlineCallbacks
    def consume_user_message(self, message):
        '''Sends the vumi message as an HTTP request to the configured URL'''
        yield self.inbounds.store_vumi_message(self.channel_id, message)

        msg = api_from_message(message)
        resp = yield post(self.config['mo_message_url'], msg)

        if request_failed(resp):
            logging.exception(
                'Error sending message, received HTTP code %r with body %r. '
                'Message: %r' % (resp.code, (yield resp.content()), msg))

    @inlineCallbacks
    def store_and_forward_event(self, event):
        '''Store the event in the message store, POST it to the correct
        URL.'''
        yield self._store_event(event)
        yield self._forward_event(event)

    def _store_event(self, event):
        '''Stores the event in the message store'''
        message_id = event['user_message_id']
        return self.outbounds.store_event(self.channel_id, message_id, event)

    @inlineCallbacks
    def _forward_event(self, event):
        '''POST the event to the correct URL'''
        url = yield self._get_event_url(event)

        if url is None:
            return

        msg = api_from_event(self.channel_id, event)

        if msg['event_type'] is None:
            logging.exception("Discarding unrecognised event %r" % (event,))
            return

        resp = yield post(url, msg)

        if request_failed(resp):
            logging.exception(
                'Error sending event, received HTTP code %r with body %r. '
                'Event: %r' % (resp.code, (yield resp.content()), event))

    def consume_ack(self, event):
        return self.store_and_forward_event(event)

    def consume_nack(self, event):
        return self.store_and_forward_event(event)

    def consume_delivery_report(self, event):
        return self.store_and_forward_event(event)

    def _get_event_url(self, event):
        msg_id = event['user_message_id']
        return self.outbounds.load_event_url(self.channel_id, msg_id)


class ChannelStatusConfig(BaseConfig):
    '''Config for the ChannelStatusWorker'''
    redis_manager = ConfigDict(
        "Redis config.",
        required=True, static=True)

    channel_id = ConfigText(
        "The channel id which this worker is consuming statuses for",
        required=True, static=True)

    status_url = ConfigText(
        "Optional url to POST status events to",
        default=None, static=True)


class ChannelStatusWorker(BaseWorker):
    '''This worker consumes status messages for the transport, and stores them
    in redis. Statuses with the same component are overwritten. It can also
    optionally forward the statuses to a URL'''
    CONFIG_CLASS = ChannelStatusConfig

    @inlineCallbacks
    def setup_connectors(self):
        connector = yield self.setup_receive_status_connector(
            self.config['channel_id'])
        connector.set_status_handler(self.consume_status)

    @inlineCallbacks
    def setup_worker(self):
        redis = yield TxRedisManager.from_config(self.config['redis_manager'])
        self.store = StatusStore(redis, ttl=None)

    def teardown_worker(self):
        pass

    @inlineCallbacks
    def consume_status(self, status):
        '''Store the status in redis under the correct component'''
        yield self.store.store_status(self.config['channel_id'], status)

        if self.config.get('status_url') is not None:
            yield self.send_status(status)

    @inlineCallbacks
    def send_status(self, status):
        data = api_from_status(self.config['channel_id'], status)
        resp = yield post(self.config['status_url'], data)

        if request_failed(resp):
            logging.exception(
                'Error sending status event, received HTTP code %r with '
                'body %r. Status event: %r'
                % (resp.code, (yield resp.content()), status))


def request_failed(resp):
    return resp.code < 200 or resp.code >= 300


def post(url, data):
    return treq.post(
        url.encode('utf-8'),
        data=json.dumps(data, cls=JSONMessageEncoder),
        headers={'Content-Type': 'application/json'})
