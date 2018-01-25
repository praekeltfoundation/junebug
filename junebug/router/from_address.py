from confmodel import Config
from confmodel.config import ConfigField
from confmodel.errors import ConfigError
from confmodel.fields import ConfigBool
import re
from twisted.internet.defer import (
    gatherResults, inlineCallbacks, returnValue, succeed)
from uuid import UUID
from vumi.persist.txredis_manager import TxRedisManager

from junebug.channel import Channel, ChannelNotFound
from junebug.router import (
    BaseRouterWorker, InvalidRouterConfig, InvalidRouterDestinationConfig)
from junebug.stores import OutboundMessageStore
from junebug.utils import api_from_message


class ConfigUUID(ConfigField):
    """
    Field for validating UUIDs
    """
    field_type = 'uuid'

    def clean(self, value):
        try:
            return UUID(value)
        except (ValueError, AttributeError, TypeError):
            self.raise_config_error('is not a valid UUID')


class ConfigRegularExpression(ConfigField):
    """
    Field for validation regular expressions
    """
    field_type = 'regex'

    def clean(self, value):
        try:
            return re.compile(value)
        except (ValueError, TypeError, re.error) as e:
            self.raise_config_error(
                'is not a valid regular expression: {}'.format(e.message))


class FromAddressRouterConfig(Config):
    """
    Config for the FromAddressRouter.
    """
    channel = ConfigUUID(
        "The UUID of the channel to route messages for. This channel may not "
        "have an ``amqp_queue`` or ``mo_url`` parameter specified.",
        required=True, static=True)


class FromAddressRouterDestinationConfig(Config):
    """
    Config for each destination of the FromAddressRouter.
    """
    regular_expression = ConfigRegularExpression(
        "The regular expression to match the from address on for this "
        "destination. Any inbound messages with a from address that matches "
        "this regular expression will be sent to this destination.",
        required=True, static=True)
    default = ConfigBool(
        "Whether or not this destination is a default destination. Any "
        "messages that don't match any the destination regular expressions "
        "will be sent to the default destination(s).",
        required=False, default=False, static=True)


class FromAddressRouterWorkerConfig(
        FromAddressRouterConfig, BaseRouterWorker.CONFIG_CLASS):
    pass


class FromAddressRouter(BaseRouterWorker):
    """
    A router that routes inbound messages based on the from address of the
    message
    """
    CONFIG_CLASS = FromAddressRouterWorkerConfig

    @classmethod
    @inlineCallbacks
    def validate_router_config(cls, api, config, router_id=None):
        try:
            config = FromAddressRouterConfig(config)
        except ConfigError as e:
            raise InvalidRouterConfig(e.message)

        channel_id = str(config.channel)
        try:
            channel = yield Channel.from_id(
                api.redis, api.config, channel_id, api.service, api.plugins)
        except ChannelNotFound:
            raise InvalidRouterConfig(
                "Channel {} does not exist".format(channel_id))
        if channel.has_destination:
            raise InvalidRouterConfig(
                "Channel {} already has a destination specified".format(
                    channel_id))

        # Check that no other routers are listening to this channel
        def check_router_channel(router):
            channel = router.get('config', {}).get('channel', None)
            if channel == channel_id and router_id != router['id']:
                raise InvalidRouterConfig(
                    "Router {} is already routing channel {}".format(
                        router['id'], channel_id))

        routers = yield api.router_store.get_router_list()
        routers = yield gatherResults([
            api.router_store.get_router_config(r) for r in routers])
        for router in routers:
            check_router_channel(router)

    @classmethod
    def validate_destination_config(cls, api, config):
        try:
            FromAddressRouterDestinationConfig(config)
        except ConfigError as e:
            raise InvalidRouterDestinationConfig(e.message)

    @inlineCallbacks
    def setup_router(self):
        config = self.get_static_config()
        self.redis = yield TxRedisManager.from_config(
            self.config['redis_manager'])
        self.outbounds = OutboundMessageStore(
            self.redis, self.config['outbound_ttl'])
        yield self.consume_channel(
            str(config.channel),
            self.handle_inbound_message,
            self.handle_inbound_event)
        for destination in config.destinations:
            self.consume_destination(
                destination['id'], self.handle_outbound_message)

    def get_destination_channel(self, destination_id, message_body):
        config = self.get_static_config()
        return succeed(str(config.channel))

    def handle_outbound_message(self, destinationid, message):
        config = self.get_static_config()
        channel_id = str(config.channel)
        d1 = self.outbounds.store_message(
            channel_id, api_from_message(message))
        d2 = self.send_outbound_to_channel(channel_id, message)
        return gatherResults([d1, d2])

    def handle_inbound_message(self, channelid, message):
        to_addr = message['to_addr']
        if to_addr is None:
            self.log.error(
                'Message has no to address, cannot route message: {}'.format(
                    message.to_json()))
            return

        d = []
        for destination in self.get_static_config().destinations:
            result = re.search(
                destination['config']['regular_expression'], to_addr)
            if result is not None:
                d.append(self.send_inbound_to_destination(
                    destination['id'], message))
        return gatherResults(d)

    @inlineCallbacks
    def handle_inbound_event(self, channelid, event):
        message = yield self.outbounds.load_message(
            channelid, event['user_message_id'])
        if message is None:
            self.log.error(
                'Cannot find message {} for event, not routing event: {}'
                .format(event['user_message_id'], event.to_json()))
            returnValue(None)

        from_addr = message.get('from', None)
        if from_addr is None:
            self.log.error(
                'Message has no from address, cannot route event: {}'.format(
                    event.to_json()))
            returnValue(None)

        d = []
        for destination in self.get_static_config().destinations:
            result = re.search(
                destination['config']['regular_expression'], from_addr)
            if result is not None:
                d.append(self.send_event_to_destination(
                    destination['id'], event))
        yield gatherResults(d)

    def teardown_router(self):
        return self.redis.close_manager()
