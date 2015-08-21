import argparse
import logging
import logging.handlers
import sys

from twisted.internet import reactor
from twisted.python import log

from junebug.service import JunebugService


def parse_arguments(args):
    '''Parse and return the command line arguments'''

    parser = argparse.ArgumentParser(
        description=(
            'Junebug. A system for managing text messaging transports via a '
            'RESTful HTTP interface'))

    parser.add_argument(
        '--interface', '-i', dest='interface', default='localhost', type=str,
        help='The interface to expose the API on. Defaults to "localhost"')
    parser.add_argument(
        '--port', '-p', dest='port', default=8080, type=int,
        help='The port to expose the API on, defaults to "8080"')
    parser.add_argument(
        '--log-file', '-l', dest='logfile', default=None, type=str,
        help='The file to log to. Defaults to not logging to a file')
    parser.add_argument(
        '--redis-host', '-redish', dest='redis_host', default='localhost',
        type=str,
        help='The hostname of the redis instance. Defaults to "localhost"')
    parser.add_argument(
        '--redis-port', '-redisp', dest='redis_port', default=6379,
        type=int,
        help='The port of the redis instance. Defaults to "6379"')
    parser.add_argument(
        '--redis-db', '-redisdb', dest='redis_db', default=0,
        type=int,
        help='The database to use for the redis instance. Defaults to "0"')
    parser.add_argument(
        '--redis-password', '-redispass', dest='redis_pass', default=None,
        type=str,
        help='The password to use for the redis instance. Defaults to "None"')

    return parser.parse_args(args)


def logging_setup(filename):
    '''Sets up the logging system to output to stdout and filename,
    if filename is not None'''

    LOGGING_FORMAT = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'

    # Send Twisted Logs to python logger
    log.PythonLoggingObserver().start()

    # Set up stdout logger
    logging.basicConfig(
        level=logging.INFO, format=LOGGING_FORMAT, stream=sys.stdout)

    # Set up file logger
    if filename:
        handler = logging.handlers.RotatingFileHandler(
            filename, maxBytes=1024*1024, backupCount=5)
        handler.setFormatter(logging.Formatter(LOGGING_FORMAT))
        logging.getLogger().addHandler(handler)


def start_server(interface, port, redis_config):
    '''Starts a new Junebug HTTP API server on the specified resource and
    port'''
    service = JunebugService(interface, port, redis_config)
    return service.startService()


def main():
    args = parse_arguments(sys.argv[1:])
    logging_setup(args.logfile)
    redis_config = {
        'host': args.redis_host,
        'port': args.redis_port,
        'db': args.redis_db,
        'password': args.redis_pass,
    }
    start_server(args.interface, args.port, redis_config)
    reactor.run()


if __name__ == '__main__':
    main()
