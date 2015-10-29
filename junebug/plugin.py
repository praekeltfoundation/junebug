class JunebugPlugin(object):
    '''Base class for all Junebug plugins'''

    def start_plugin(self, config):
        '''Can be overridden with any required startup code for the plugin.
        Can return a deferred.

        config - Config that Junebug was started with.'''
        pass

    def channel_started(self, channel):
        '''Called whenever a channel is started. Should be implemented by the
        plugin. Can return a deferred.

        channel - The channel that has been started.'''
        pass

    def channel_stopped(self, channel):
        '''Called whenever a channel is stopped. Should be implemented by the
        plugin. Can return a deferred.

        channel - The channel that has been stopped.'''
        pass
