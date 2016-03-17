from subprocess import Popen, PIPE
import httplib
import json
import os
import time
import re, math, sys


class Process(object):
    def get_command(self):
        '''Subclasses implement. Returns a list representing start command.'''
        return []

    def start(self, stdout=PIPE, extra_commands=[]):
        env = os.environ.copy()
        env['JUNEBUG_DISABLE_LOGGING'] = 'true'
        command = self.get_command()
        command.extend(extra_commands)
        self.process = Popen(
            command, env=env, stdout=stdout)
        self.post_start()

    def get_rss(self):
        if not sys.platform.startswith('linux'):
            return 0
        pid = self.process.pid
        with open("/proc/%d/status" % pid) as f:
            d = f.read()
            start = d.find('RSS')
            end = d.find('\n', start)
            m = re.search("(\d+)\s+([kKmM])B", d[start:end])
            if m.group(2) in 'kK':
                coef = 0.001
            else:
                coef = 1.0
            return int(math.ceil((float(m.group(1))) * coef))

    def post_start(self):
        '''Subclasses implement. What to do after starting process.'''
        pass

    def stop(self):
        self.process.terminate()


class Junebug(Process):
    def __init__(self):
        self.conn = httplib.HTTPConnection('localhost', port=8080)

    def get_command(self):
        return ['jb']

    def post_start(self):
        # This is horrible
        time.sleep(2)

    def create_ussd_channel(self):
        self.conn.request(
            "POST", '/channels/',
            json.dumps({
                'type': 'dmark',
                'config': {
                    'web_path': 'api',
                    'web_port': 8001,
                },
                'mo_url': 'http://localhost:8002',
            }),
            {'Content-Type': 'application/json'})
        r = self.conn.getresponse()
        assert r.status == 200
        channel = json.loads(r.read())['result']['id']
        self._wait_for_ussd_channel_start()
        return channel

    def _wait_for_ussd_channel_start(self):
        # This is horrible
        time.sleep(1)

    def delete_ussd_channel(self, channelid):
        self.conn.request(
            "DELETE", '/channels/%s' % channelid)
        r = self.conn.getresponse()
        assert r.status == 200


class FakeApplicationServer(Process):
    def get_command(self):
        return ['python', 'application_server.py']


class BenchmarkRunner(Process):
    def get_command(self):
        return ['python', 'submit_message.py']

    def print_results(self):
        for line in iter(self.process.stdout.readline, ''):
            print line.rstrip('\n')

def main():
    try:
        print 'Starting Junebug benchmark...'
        jb = Junebug()
        jb.start()

        app = FakeApplicationServer()
        app.start()

        ch = jb.create_ussd_channel()

        for concurrency in [2, 5, 10]:
            print 'Running benchmark with concurrency %d' % concurrency
            benchmark = BenchmarkRunner()
            max_rss = 0
            benchmark.start(
                stdout=None, extra_commands=[
                    '--concurrency=%d' % concurrency])
            while not benchmark.process.poll():
                try:
                    max_rss = max(max_rss, benchmark.get_rss())
                except (OSError, IOError):
                    pass # possible race condition?
                time.sleep(0.2)
            if sys.platform.startswith('linux'):
                print "Max memory: %d" % max_rss

        jb.delete_ussd_channel(ch)
    finally:
        jb.stop()
        app.stop()

if __name__ == '__main__':
    main()
