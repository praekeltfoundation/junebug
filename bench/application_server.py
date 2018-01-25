import json
import socket
import sys
import argparse


def start_server(port=8002, response_port=8001, router=None, destination=None):
    serversocket = socket.socket()
    serversocket.bind(('localhost', port))
    serversocket.listen(1)

    while True:
        connection, address = serversocket.accept()
        content = connection.recv(1024)
        connection.send("HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
        connection.close()
        send_response(content, response_port, router, destination)


def send_response(content, port, router=None, destination=None):
    content = json.loads(content.splitlines()[-1])
    reply = json.dumps({
        "reply_to": content.get('message_id'),
        "content": "reply message",
        "channel_data": {
            "session_event": "close",
        },
    })

    s = socket.socket()
    s.connect(('localhost', 8080))

    if (router and destination):
        s.send(
            "POST /routers/%s/destinations/%s/messages/ HTTP/1.1\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: %d\r\n"
            "\r\n%s\r\n\r\n" % (router, destination, len(reply) + 2, reply))
    else:
        channel_id = content['channel_id']
        s.send(
            "POST /channels/%s/messages/ HTTP/1.1\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: %d\r\n"
            "\r\n%s\r\n\r\n" % (channel_id, len(reply) + 2, reply))
    reply = s.recv(1024)
    try:
        assert (reply.splitlines()[0] == 'HTTP/1.1 200 OK' or
                reply.splitlines()[0] == 'HTTP/1.1 201 Created')
    finally:
        s.close()


def parse_arguments(args):
    parser = argparse.ArgumentParser(
        description=(
            'Fake Application to handle junebug messages.'))
    parser.add_argument(
        '--router', dest='router', type=str, default=None,
        help='Router that was created')
    parser.add_argument(
        '--destination', dest='destination', type=str, default=None,
        help='Destination that was created')

    return parser.parse_args(args)


def main():
    config = parse_arguments(sys.argv[1:])
    start_server(router=config.router, destination=config.destination)


if __name__ == '__main__':
    main()
