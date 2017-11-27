'''
Junebug is a system for managing text messaging transports via a RESTful HTTP
interface.
'''
import os

# Allows us to select which Twisted reactor to use. Must be done before any
# Twisted import calls.
r = os.environ.get('JUNEBUG_REACTOR', 'DEFAULT')
if r == "SELECT":
    from twisted.internet import selectreactor as r
elif r == "POLL":
    from twisted.internet import pollreactor as r
elif r == "KQUEUE":
    from twisted.internet import kqreactor as r
elif r == "WFMO":
    from twisted.internet import win32eventreactor as r
elif r == "IOCP":
    from twisted.internet import iocpreactor as r
elif r == "EPOLL":
    from twisted.internet import epollreactor as r
elif r == "DEFAULT":
    r = None
else:
    raise RuntimeError("Unsupported JUNEBUG_REACTOR setting %r" % (r,))
if r is not None:
    r.install()

from junebug.api import JunebugApi  # noqa

__all__ = ['JunebugApi']
__version__ = '0.1.27'
