from twisted.internet.defer import inlineCallbacks
import uuid

from junebug.router import (
    Router, InvalidRouterConfig, InvalidRouterDestinationConfig)
from junebug.router.from_address import FromAddressRouter
from junebug.tests.helpers import JunebugTestBase


class TestRouter(JunebugTestBase):
    def setUp(self):
        return self.start_server()

    @inlineCallbacks
    def test_validate_router_config_invalid_channel_uuid(self):
        """
        If the provided channel UUID is not a valid UUID a config error should
        be raised
        """
        with self.assertRaises(InvalidRouterConfig) as e:
            yield FromAddressRouter.validate_router_config(
                self.api, {'channel': "bad-uuid"})

        self.assertEqual(
            e.exception.message,
            "Field 'channel' is not a valid UUID")

    @inlineCallbacks
    def test_validate_router_config_missing_channel(self):
        """
        If the provided channel UUID is not for an existing channel, a config
        error should be raised
        """
        channel_id = str(uuid.uuid4())

        with self.assertRaises(InvalidRouterConfig) as e:
            yield FromAddressRouter.validate_router_config(
                self.api, {'channel': channel_id})

        self.assertEqual(
            e.exception.message,
            "Channel {} does not exist".format(channel_id))

    @inlineCallbacks
    def test_validate_router_config_existing_destination(self):
        """
        If the specified channel already has a destination specified, then
        a config error should be raised
        """
        channel = yield self.create_channel(self.api.service, self.redis)

        with self.assertRaises(InvalidRouterConfig) as e:
            yield FromAddressRouter.validate_router_config(
                self.api, {'channel': channel.id})

        self.assertEqual(
            e.exception.message,
            "Channel {} already has a destination specified".format(
                channel.id))

    @inlineCallbacks
    def test_validate_router_config_existing_router(self):
        """
        If an existing router is already listening to the specified channel,
        then a config error should be raised
        """
        channel = yield self.create_channel(
            self.api.service, self.redis, properties={
                'type': 'telnet',
                'config': {
                    'twisted_endpoint': 'tcp:0',
                },
            })

        config = self.create_router_config(
            config={'test': 'pass', 'channel': channel.id})
        router = Router(self.api, config)
        yield router.save()
        router.start(self.api.service)

        with self.assertRaises(InvalidRouterConfig) as e:
            yield FromAddressRouter.validate_router_config(
                self.api, {'channel': channel.id})

        self.assertEqual(
            e.exception.message,
            "Router {} is already routing channel {}".format(
                router.id, channel.id))

    @inlineCallbacks
    def test_validate_router_destination_config_invalid_regex(self):
        """
        If invalid regex is passed into the regex field, a config error should
        be raised
        """
        with self.assertRaises(InvalidRouterDestinationConfig) as e:
            yield FromAddressRouter.validate_router_destination_config(
                self.api, {'regular_expression': "("})

        self.assertEqual(
            e.exception.message,
            "Field 'regular_expression' is not a valid regular expression: "
            "unbalanced parenthesis")

    @inlineCallbacks
    def test_validate_router_destination_config_missing_field(self):
        """
        regular_expression should be a required field
        """
        with self.assertRaises(InvalidRouterDestinationConfig) as e:
            yield FromAddressRouter.validate_router_destination_config(
                self.api, {})

        self.assertEqual(
            e.exception.message,
            "Missing required config field 'regular_expression'")
