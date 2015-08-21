import logging
import os.path
from twisted.trial.unittest import TestCase

from junebug.command_line import parse_arguments, logging_setup, start_server


class TestCommandLine(TestCase):
    def test_parse_arguments_interface(self):
        '''The interface command line argument can be specified by
        "--interface" and "-i" and has a default value of "localhost"'''
        args = parse_arguments([])
        self.assertEqual(args.interface, 'localhost')

        args = parse_arguments(['--interface', 'foobar'])
        self.assertEqual(args.interface, 'foobar')

        args = parse_arguments(['-i', 'foobar'])
        self.assertEqual(args.interface, 'foobar')

    def test_parse_arguments_port(self):
        '''The port command line argument can be specified by
        "--port" or "-p" and has a default value of 8080'''
        args = parse_arguments([])
        self.assertEqual(args.port, 8080)

        args = parse_arguments(['--port', '80'])
        self.assertEqual(args.port, 80)

        args = parse_arguments(['-p', '80'])
        self.assertEqual(args.port, 80)

    def test_parse_arguments_log_file(self):
        '''The log file command line argument can be specified by
        "--log-file" or "-l" and has a default value of None'''
        args = parse_arguments([])
        self.assertEqual(args.logfile, None)

        args = parse_arguments(['--log-file', 'foo.bar'])
        self.assertEqual(args.logfile, 'foo.bar')

        args = parse_arguments(['-l', 'foo.bar'])
        self.assertEqual(args.logfile, 'foo.bar')

    def test_parse_arguments_redis_host(self):
        '''The redis host command line argument can be specified by
        "--redis-host" or "-redish" and has a default value of "localhost"'''
        args = parse_arguments([])
        self.assertEqual(args.redis_host, 'localhost')

        args = parse_arguments(['--redis-host', 'foo.bar'])
        self.assertEqual(args.redis_host, 'foo.bar')

        args = parse_arguments(['-redish', 'foo.bar'])
        self.assertEqual(args.redis_host, 'foo.bar')

    def test_parse_arguments_redis_port(self):
        '''The redis port command line argument can be specified by
        "--redis-port" or "-redisp" and has a default value of 6379'''
        args = parse_arguments([])
        self.assertEqual(args.redis_port, 6379)

        args = parse_arguments(['--redis-port', '80'])
        self.assertEqual(args.redis_port, 80)

        args = parse_arguments(['-redisp', '80'])
        self.assertEqual(args.redis_port, 80)

    def test_parse_arguments_redis_database(self):
        '''The redis database command line argument can be specified by
        "--redis-db" or "-redisdb" and has a default value of 0'''
        args = parse_arguments([])
        self.assertEqual(args.redis_db, 0)

        args = parse_arguments(['--redis-db', '80'])
        self.assertEqual(args.redis_db, 80)

        args = parse_arguments(['-redisdb', '80'])
        self.assertEqual(args.redis_db, 80)

    def test_parse_arguments_redis_password(self):
        '''The redis password command line argument can be specified by
        "--redis-password" or "-redispass" and has a default value of None'''
        args = parse_arguments([])
        self.assertEqual(args.redis_pass, None)

        args = parse_arguments(['--redis-password', 'foo.bar'])
        self.assertEqual(args.redis_pass, 'foo.bar')

        args = parse_arguments(['-redispass', 'foo.bar'])
        self.assertEqual(args.redis_pass, 'foo.bar')

    def test_logging_setup(self):
        '''If filename is None, just a stdout logger is created, if filename
        is not None, both the stdout logger and a file logger is created'''
        logging_setup(None)
        [handler] = logging.getLogger().handlers
        self.assertEqual(handler.stream.name, '<stdout>')
        logging.getLogger().removeHandler(handler)

        filename = self.mktemp()
        logging_setup(filename)
        [handler1, handler2] = sorted(logging.getLogger().handlers)

        self.assertEqual(
            os.path.abspath(handler1.baseFilename),
            os.path.abspath(filename))
        self.assertEqual(handler2.stream.name, '<stdout>')

        logging.getLogger().removeHandler(handler1)
        logging.getLogger().removeHandler(handler2)

    def test_start_server(self):
        '''Starting the server should listen on the specified interface and
        port'''
        port = start_server('localhost', 0, {})
        host = port.getHost()
        self.assertEqual(host.host, '127.0.0.1')
        self.assertEqual(host.type, 'TCP')
        self.assertTrue(host.port > 0)
        port.stopListening()


