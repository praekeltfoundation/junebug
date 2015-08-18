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
        port = start_server('localhost', 0)
        host = port.getHost()
        self.assertEqual(host.host, '127.0.0.1')
        self.assertEqual(host.type, 'TCP')
        self.assertTrue(host.port > 0)
        port.stopListening()


