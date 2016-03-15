import argparse
import time
import socket
import sys
from threading import Thread
from Queue import Queue

def parse_arguments(args):
    parser = argparse.ArgumentParser(
        description=(
            'Creates and submits USSD messages via HTTP for benchmarking.'))
    parser.add_argument(
        '--port', dest='port', type=int, default=8001,
        help='Port to send USSD message requests to')
    parser.add_argument(
        '--start-id', dest='start_id', type=int, default=0,
        help='The integer to start with for request ids')
    parser.add_argument(
        '--end-id', dest='end_id', type=int, default=10000,
        help='The integer to start with for request ids')
    parser.add_argument(
        '--concurrency', dest='concurrency', type=int, default=10,
        help='The integer to start with for request ids')
    return parser.parse_args(args)


def main():
    config = parse_arguments(sys.argv[1:])
    create_requests(config.port, config.start_id, config.end_id, config.concurrency)

def sync_worker(port, item):
    start, end = item
    l = []
    t0 = time.time()
    for k in range(start, end):
        s = socket.socket()
        s.connect(('localhost', port))
        s.send(
            "GET /api/?transactionId=%d&msisdn=0821234567"
            "&ussdServiceCode=1234&ussdRequestString=hello"
            "&transactionTime=0000&creationTime=0000&response=0000 HTTP/1.1\r\n"
            "Host: localhost:8001\r\n"
            "User-Agent: test\r\n"
            "\r\n\r\n" % k)
        s.recv(1024)
        s.close()
    return time.time() - t0

def worker(port, in_q, out_q):
    while True:
        item = in_q.get()
        if item is None:
            break
        out_q.put(sync_worker(port, item))

def create_requests(port, start, end, concurrency):
    batch = 20
    if concurrency > 1:
        in_q = Queue()
        out_q = Queue()
        all_threads = []
        for i in range(concurrency):
            t = Thread(target=worker, args=(port, in_q, out_q))
            t.start()
            all_threads.append(t)
        for i in range(start, end, batch):
            in_q.put((i, i+batch))
        for i in range(start, end, batch):
            print out_q.get()
        for k in range(concurrency):
            in_q.put(None)
        for t in all_threads:
            t.join()
    else:
        # run it directly
        l = []
        for i in range(start, end, batch):
            l.append(sync_worker(port, (i, i+batch)))
        print l

if __name__ == "__main__":
    main()
