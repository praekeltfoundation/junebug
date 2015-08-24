from twisted.web import http


class JunebugError(Exception):
    '''Generic error from which all other junebug errors inherit from'''
    name = 'JunebugError'
    description = 'Generic Junebug Error'
    code = http.INTERNAL_SERVER_ERROR
