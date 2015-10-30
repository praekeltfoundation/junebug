from copy import deepcopy
from twisted.internet.defer import inlineCallbacks

from junebug.channel import Channel
from junebug.tests.helpers import FakeJunebugPlugin, JunebugTestBase


class TestFakeJunebugPlugin(JunebugTestBase):
    @inlineCallbacks
    def test_plugin_start_plugin(self):
        '''Stores the name of the function call and arguments in calls'''
        plugin = FakeJunebugPlugin()
        config = yield self.create_channel_config()
        yield plugin.start_plugin({'test': 'plugin_config'}, config)

        [(name, [plugin_config, config_arg])] = plugin.calls
        self.assertEqual(name, 'start_plugin')
        self.assertEqual(config_arg, config)
        self.assertEqual(plugin_config, {'test': 'plugin_config'})

    @inlineCallbacks
    def test_plugin_stop_plugin(self):
        '''Stores the name of the function call and arguments in calls'''
        plugin = FakeJunebugPlugin()
        config = yield self.create_channel_config()
        yield plugin.start_plugin({'test': 'plugin_config'}, config)
        plugin.calls = []

        yield plugin.stop_plugin()

        [(name, [])] = plugin.calls
        self.assertEqual(name, 'stop_plugin')

    @inlineCallbacks
    def test_plugin_channel_started(self):
        '''Stores the name of the function call and arguments in calls'''
        plugin = FakeJunebugPlugin()
        config = yield self.create_channel_config()
        yield plugin.start_plugin({'test': 'pluginconfig'}, config)
        plugin.calls = []

        redis = yield self.get_redis()
        channel = Channel(
            redis, config, deepcopy(self.default_channel_properties))
        yield plugin.channel_started(channel)

        [(name, [channel_arg])] = plugin.calls
        self.assertEqual(name, 'channel_started')
        self.assertEqual(channel_arg, channel)

    @inlineCallbacks
    def test_plugin_channel_stopped(self):
        '''Stores the name of the function call and arguments in calls'''
        plugin = FakeJunebugPlugin()
        config = yield self.create_channel_config()
        yield plugin.start_plugin({'test': 'plugin_config'}, config)
        plugin.calls = []

        redis = yield self.get_redis()
        channel = Channel(
            redis, config, deepcopy(self.default_channel_properties))
        yield plugin.channel_stopped(channel)

        [(name, [channel_arg])] = plugin.calls
        self.assertEqual(name, 'channel_stopped')
        self.assertEqual(channel_arg, channel)
