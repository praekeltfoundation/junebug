import json
import socket


def start_server(port=8002, response_port=8001):
    serversocket = socket.socket()
    serversocket.bind(('localhost', port))
    serversocket.listen(1)

    while True:
        connection, address = serversocket.accept()
        content = connection.recv(1024)
        connection.send("HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
        connection.close()
        send_response(content, response_port)


def send_response(content, port):
    content = json.loads(content.splitlines()[-1])
    reply = json.dumps({
        "reply_to": content.get('message_id'),
        #"from": content.get('to'),
        "content": "reply message",
        "channel_data": {
            "session_event": "close",
        },
    })

    s = socket.socket()
    s.connect(('localhost', 8080))
    channel_id = "45175bc5-6484-49c8-a276-c0164f900398"
    s.send(
        "POST /channels/%s/messages/ HTTP/1.1\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: %d\r\n"
        "\r\n%s\r\n\r\n" % (channel_id, len(reply), reply))
    #print s.recv(1024)
    s.close()


def main():
    start_server()


if __name__ == '__main__':
    main()
