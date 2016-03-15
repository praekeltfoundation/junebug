'''
Junebug is a system for managing text messaging transports via a RESTful HTTP
interface.
'''
from twisted.internet import kqreactor
kqreactor.install()
from junebug.api import JunebugApi

__all__ = ['JunebugApi']
__version__ = '0.1.2a'
