'''
Junebug is a system for managing text messaging transports via a RESTful HTTP
interface.
'''
import os

r = os.environ.get('JUNEBUG_REACTOR')
if r == "SELECT":
    from twisted.internet import selectreactor
    selectreactor.install()
elif r == "POLL":
    from twisted.internet import pollreactor
    pollreactor.install()
elif r == "KQUEUE":
    from twisted.internet import kqreactor
    kqreactor.install()
elif r == "WFMO":
    from twisted.internet import win32eventreactor
    win32eventreactor.install()
elif r == "IOCP":
    from twisted.internet import iocpreactor
    iocpreactor.install()
elif r == "EPOLL":
    from twisted.internet import epollreactor
    epollreactor.install()

from junebug.api import JunebugApi

__all__ = ['JunebugApi']
__version__ = '0.1.2a'
