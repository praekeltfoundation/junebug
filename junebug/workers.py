import json
import logging
from twisted.internet.defer import inlineCallbacks
import treq
from vumi.application.base import ApplicationConfig, ApplicationWorker
from vumi.config import ConfigDict, ConfigInt, ConfigText
from vumi.message import JSONMessageEncoder
from vumi.persist.txredis_manager import TxRedisManager

from junebug.channel import Channel
from junebug.stores import InboundMessageStore


class MessageForwardingConfig(ApplicationConfig):
    '''Config for MessageForwardingWorker application worker'''

    mo_message_url = ConfigText(
        'The URL to send HTTP POST requests to for MO messages',
        required=True, static=True)
    redis_manager = ConfigDict('Redis config.', required=True, static=True)
    ttl = ConfigInt(
        'Time to keep stored messages in redis for reply_to',
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
        message_redis = self.redis.sub_manager(
            '%s:incoming_messages' % self.config['transport_name'])
        self.message_store = InboundMessageStore(
            message_redis, self.config['ttl'])

    @inlineCallbacks
    def teardown_application(self):
        yield self.redis.close_manager()

    @inlineCallbacks
    def consume_user_message(self, message):
        '''Sends the vumi message as an HTTP request to the configured URL'''
        config = yield self.get_config(message)
        url = config.mo_message_url.encode('utf-8')
        headers = {
            'Content-Type': 'application/json',
        }
        msg = json.dumps(
            Channel.api_from_message(message), cls=JSONMessageEncoder)
        resp = yield treq.post(url, data=msg, headers=headers)
        if resp.code < 200 or resp.code >= 300:
            logging.exception(
                'Error sending message, received HTTP code %r with body %r. '
                'Message: %r' % (resp.code, (yield resp.content()), msg))
