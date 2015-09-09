import logging
import os.path
from twisted.internet.defer import inlineCallbacks

from junebug import JunebugApi
from junebug.command_line import parse_arguments, logging_setup, start_server
from junebug.tests.helpers import JunebugTestBase


class TestCommandLine(JunebugTestBase):
    def setUp(self):
        self.old_setup = JunebugApi.setup
        self.old_teardown = JunebugApi.teardown

        def do_nothing(self):
            pass

        JunebugApi.setup = do_nothing
        JunebugApi.teardown = do_nothing

    def tearDown(self):
        JunebugApi.setup = self.old_setup
        JunebugApi.teardown = self.old_teardown

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

    def test_parse_arguments_amqp_host(self):
        '''The amqp host command line argument can be specified by
        "--amqp-host" or "-amqph" and has a default value of "127.0.0.1"'''
        args = parse_arguments([])
        self.assertEqual(args.amqp_host, '127.0.0.1')

        args = parse_arguments(['--amqp-host', 'foo.bar'])
        self.assertEqual(args.amqp_host, 'foo.bar')

        args = parse_arguments(['-amqph', 'foo.bar'])
        self.assertEqual(args.amqp_host, 'foo.bar')

    def test_parse_arguments_amqp_port(self):
        '''The amqp port command line argument can be specified by
        "--amqp-port" or "-amqpp" and has a default value of 5672'''
        args = parse_arguments([])
        self.assertEqual(args.amqp_port, 5672)

        args = parse_arguments(['--amqp-port', '80'])
        self.assertEqual(args.amqp_port, 80)

        args = parse_arguments(['-amqpp', '80'])
        self.assertEqual(args.amqp_port, 80)

    def test_parse_arguments_amqp_username(self):
        '''The amqp username command line argument can be specified by
        "--amqp-user" or "-amqpu" and has a default value of "guest"'''
        args = parse_arguments([])
        self.assertEqual(args.amqp_user, 'guest')

        args = parse_arguments(['--amqp-user', 'test'])
        self.assertEqual(args.amqp_user, 'test')

        args = parse_arguments(['-amqpu', 'test'])
        self.assertEqual(args.amqp_user, 'test')

    def test_parse_arguments_amqp_password(self):
        '''The amqp password command line argument can be specified by
        "--amqp-password" or "-amqppass" and has a default value of "guest"'''
        args = parse_arguments([])
        self.assertEqual(args.amqp_pass, 'guest')

        args = parse_arguments(['--amqp-password', 'foo.bar'])
        self.assertEqual(args.amqp_pass, 'foo.bar')

        args = parse_arguments(['-amqppass', 'foo.bar'])
        self.assertEqual(args.amqp_pass, 'foo.bar')

    def test_parse_arguments_amqp_vhost(self):
        '''The amqp vhost command line argument can be specified by
        "--amqp-vhost" or "-amqpv" and has a default value of "/"'''
        args = parse_arguments([])
        self.assertEqual(args.amqp_vhost, '/')

        args = parse_arguments(['--amqp-vhost', 'foo.bar'])
        self.assertEqual(args.amqp_vhost, 'foo.bar')

        args = parse_arguments(['-amqpv', 'foo.bar'])
        self.assertEqual(args.amqp_vhost, 'foo.bar')

    def test_logging_setup(self):
        '''If filename is None, just a stdout logger is created, if filename
        is not None, both the stdout logger and a file logger is created'''
        logging_setup(None)
        [handler] = logging.getLogger().handlers
        self.assertEqual(handler.stream.name, '<stdout>')
        logging.getLogger().removeHandler(handler)

        filename = self.mktemp()
        logging_setup(filename)
        [handler1, handler2] = sorted(
            logging.getLogger().handlers,
            key=lambda h: hasattr(h, 'baseFilename'))

        self.assertEqual(
            os.path.abspath(handler2.baseFilename),
            os.path.abspath(filename))
        self.assertEqual(handler1.stream.name, '<stdout>')

        logging.getLogger().removeHandler(handler1)
        logging.getLogger().removeHandler(handler2)

    @inlineCallbacks
    def test_start_server(self):
        '''Starting the server should listen on the specified interface and
        port'''
        redis = yield self.get_redis()
        service = yield start_server('localhost', 0, redis._config, {
            'hostname': 'localhost',
            'port': 0,
            })
        port = service._port
        host = port.getHost()
        self.assertEqual(host.host, '127.0.0.1')
        self.assertEqual(host.type, 'TCP')
        self.assertTrue(host.port > 0)
        yield service.stopService()
