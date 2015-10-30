class JunebugPlugin(object):
    '''Base class for all Junebug plugins'''

    def start_plugin(self, config, junebug_config):
        '''
        Can be overridden with any required startup code for the plugin.
        Can return a deferred.

        :param config: The config specific to the plugin.
        :type config: dictionary
        :param junebug_config: The config that Junebug was started with.
        :type junebug_config: :class:`JunebugConfig`
        '''
        pass

    def stop_plugin(self):
        '''
        Can be overridden with any required shutdown code for the plugin.
        Can return a deferred.
        '''
        pass

    def channel_started(self, channel):
        '''
        Called whenever a channel is started. Should be implemented by the
        plugin. Can return a deferred.

        :param channel: The channel that has been started.
        :type channel: :class:`Channel`
        '''
        pass

    def channel_stopped(self, channel):
        '''
        Called whenever a channel is stopped. Should be implemented by the
        plugin. Can return a deferred.

        :param channel: The channel that has been stopped.
        :type channel: :class:`Channel`
        '''
        pass
