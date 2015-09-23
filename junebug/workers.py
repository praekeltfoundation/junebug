import json
import logging

import treq

from twisted.internet.defer import inlineCallbacks

from vumi.application.base import ApplicationConfig, ApplicationWorker
from vumi.config import ConfigDict, ConfigInt, ConfigText
from vumi.message import JSONMessageEncoder
from vumi.persist.txredis_manager import TxRedisManager

from junebug.utils import api_from_message, api_from_event
from junebug.stores import InboundMessageStore, OutboundMessageStore


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
    def forward_event(self, event):
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
        return self.forward_event(event)

    def consume_nack(self, event):
        return self.forward_event(event)

    def consume_delivery_report(self, event):
        return self.forward_event(event)

    def _get_event_url(self, event):
        msg_id = event['user_message_id']
        return self.outbounds.load_event_url(self.channel_id, msg_id)


def request_failed(resp):
    return resp.code < 200 or resp.code >= 300


def post(url, data):
    return treq.post(
        url.encode('utf-8'),
        data=json.dumps(data, cls=JSONMessageEncoder),
        headers={'Content-Type': 'application/json'})
