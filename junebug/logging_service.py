import json
import logging
import os
import time

from twisted.python import log
from twisted.python.log import ILogObserver
from twisted.python.logfile import LogFile
from twisted.application.service import Service

from zope.interface import implements

DEFAULT_LOG_CONTEXT_SENTINEL = "_JUNEBUG_CONTEXT_"


class JunebugLogObserver(object):
    """Twisted log observer that logs to a rotated log file."""
    implements(ILogObserver)

    DEFAULT_ERROR_LEVEL = logging.ERROR
    DEFAULT_LOG_LEVEL = logging.INFO
    LOG_LEVEL_THRESHOLD = logging.INFO
    LOG_ENTRY = '%[(timestamp)s] '

    def __init__(self, logfile, worker_id, log_context_sentinel=None):
        '''
        Create a new JunebugLogObserver.

        :param logfile: File to write logs to.
        :type logfile: :class:`twisted.python.logfile.LogFile`
        :param str worker_id: ID of the worker that the log is for.
        '''
        if log_context_sentinel is None:
            log_context_sentinel = DEFAULT_LOG_CONTEXT_SENTINEL
        self.worker_id = worker_id
        self.log_context_sentinel = log_context_sentinel
        self.log_context = {self.log_context_sentinel: True}
        self.logfile = logfile

    def level_for_event(self, event):
        '''Get the associated log level for an event.'''
        level = event.get('logLevel')
        if level is not None:
            return level
        if event.get('isError'):
            return self.DEFAULT_ERROR_LEVEL
        return self.DEFAULT_LOG_LEVEL

    def logger_for_event(self, event):
        '''Get the name of the logger for an event.'''
        system = event.get('system')
        logger = ".".join(system.split(','))
        return logger.lower()

    def _log_to_file(self, event):
        '''Logs the specified event to the log file.'''
        level = self.level_for_event(event)
        if level < self.LOG_LEVEL_THRESHOLD:
            return

        data = {
            "logger": self.logger_for_event(event),
            "level": level,
            "timestamp": time.time(),
            "message": log.textFromEventDict(event),
        }

        failure = event.get('failure')
        if failure:
            data['class'] = repr(failure.type)
            data['instance'] = repr(failure.value)
            data['stack'] = failure.stack

        self.logfile.write(json.dumps(data) + '\n')

    def __call__(self, event):
        if self.log_context_sentinel in event:
            return
        if self.worker_id not in event.get('system', '').split(','):
            return
        log.callWithContext(self.log_context, self._log_to_file, event)


class JunebugLoggerService(Service):
    '''Service for :class:`junebug.logging.JunebugLogObserver`'''
    log_observer = None

    def __init__(self, worker_id, path, rotate, max_files, logger=None):
        '''
        Create the service for the Junebug Log Observer.

        :param str worker_id: ID of the worker to observe logs for.
        :param str path: Path to place the log files.
        :param int rotate: Size (in bytes) before rotating log file.
        :param int max_files:
            Maximum amount of log files before old log files
            start to get deleted.
        :param logger:
            logger to add observer to. Defaults to
            twisted.python.log.theLogPublisher
        :type logger: :class:`twisted.python.log.LogPublisher`
        '''
        self.setName('Junebug Worker Logger')
        self.logger = logger if logger is not None else log.theLogPublisher
        self.worker_id = worker_id
        self.path = path
        self.rotate = rotate
        self.max_files = max_files

    def startService(self):
        self.logfile = LogFile(
            self.worker_id, self.path, rotateLength=self.rotate,
            maxRotatedFiles=self.max_files)
        self.log_observer = JunebugLogObserver(self.logfile, self.worker_id)
        self.logger.addObserver(self.log_observer)
        return super(JunebugLoggerService, self).startService()

    def stopService(self):
        if self.running:
            self.logger.removeObserver(self.log_observer)
            self.logfile.close()
        return super(JunebugLoggerService, self).stopService()

    def registered(self):
        return self.log_observer in self.logger.observers


def reverse_read(filename, buf):
    '''
    Read the non-blank lines from a file in reverse order.

    :param str filename: The path of the file to be read.
    :param int buf: The size of the read buffer.

    :returns:
        A generator that yields each line from the file in reverse order as a
        string.
    '''
    with open(filename) as f:
        f.seek(0, os.SEEK_END)
        total_size = remaining_size = f.tell()
        offset = 0
        incomplete_line = None
        while remaining_size > 0:
            offset = min(total_size, offset + buf)
            f.seek(-offset, os.SEEK_END)
            data = f.read(min(remaining_size, buf))
            remaining_size -= buf
            lines = data.split('\n')
            if incomplete_line:
                lines[-1] += incomplete_line
            incomplete_line = lines.pop(0)
            for l in lines[::-1]:
                if l is not '':
                    yield l
        if incomplete_line:
            yield incomplete_line


def read_logs(logfile, lines, buf=4096):
    '''
    Reads log files to fetch the last N logs.

    :param logfile: The LogFile to read from.
    :type logfile: :class:`twisted.python.logfile.LogFile`
    :param int lines: Maximum number of lines to read.
    :param int buf: The size of the read buffer.

    :returns: list -- Each item is a dictionary representing a log entry.
    '''
    logs = []

    # Read the current log file
    for line in reverse_read(logfile.path, buf):
        logs.append(json.loads(line))
        if len(logs) == lines:
            return logs
    # Read the rotated log files
    for file_num in logfile.listLogs():
        for line in reverse_read('%s.%d' % (logfile.path, file_num), buf):
            logs.append(json.loads(line))
            if len(logs) == lines:
                return logs
    return logs
