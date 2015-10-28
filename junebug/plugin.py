class JunebugPlugin(object):
    '''Base class for all Junebug plugins'''

    @classmethod
    def channel_started(cls, channel):
        '''Called whenever a channel is started. Should be implemented by the
        plugin.

        channel - The channel that has been started.'''
        raise NotImplementedError()

    @classmethod
    def channel_stopped(cls, channel):
        '''Called whenever a channel is stopped. Should be implemented by the
        plugin.

        channel - The channel that has been stopped.'''
        raise NotImplementedError()
