import argparse
import time
import socket
import sys


def parse_arguments(args):
    parser = argparse.ArgumentParser(
        description=(
            'Creates and submits USSD messages via HTTP for benchmarking.'))
    parser.add_argument(
        '--port', dest='port', type=int, default=8003,
        help='Port to send USSD message requests to')
    parser.add_argument(
        '--start-id', dest='start_id', type=int, default=0,
        help='The integer to start with for request ids')
    parser.add_argument(
        '--end-id', dest='end_id', type=int, default=10000,
        help='The integer to start with for request ids')
    return parser.parse_args(args)


def main():
    config = parse_arguments(sys.argv[1:])
    create_requests(config.port, config.start_id, config.end_id)


def create_requests(port, start, end):
    print("Starting send.")
    start_time = time.time()
    avg = []
    t0 = time.time()
    batch = 100
    for i in xrange(start, end):
        s = socket.socket()
        s.connect(('localhost', port))
        s.send(
            "GET /api/?transactionId=%d&msisdn=0821234567"
            "&ussdServiceCode=1234&ussdRequestString=hello"
            "&transactionTime=0000&creationTime=0000&response=0000 HTTP/1.1\r\n"
            "Host: localhost:8001\r\n"
            "User-Agent: test\r\n"
            "\r\n\r\n" % i)
        s.recv(1024)
        s.close()
        if i % batch == 0 and i > 0:
            delta = time.time() - t0
            avg.append(batch/delta)
            print "Current avg:", batch/delta, "Total avg:", sum(avg)/len(avg)
            t0 = time.time()
    duration = time.time() - start_time
    print("Completed sending %d messages in %fs, for a speed of %fmsgs/s" % (
        end - start, duration, (end - start) / (duration)))


if __name__ == "__main__":
    main()
