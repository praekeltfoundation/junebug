.. _getting-started:

Getting started
===============

This guides assumed you have already followed the :ref:`installation guide
<installation>`.

If you prefer a video tutorial, you can start by watching our `demo`_.

.. _demo: https://archive.org/details/Junebug010Demo

First, make sure you have `Redis`_ and `RabbitMQ`_ running. On a Debian-based system, one can run them with::

  $ service redis-server start
  $ service rabbitmq-server start

.. _redis: http://redis.io/
.. _rabbitmq: https://www.rabbitmq.com/

We can now launch Junebug::

  $ jb -p 8000

This starts the Junebug HTTP API running on port 8000. At the moment it won't
have any transports running, so let's create one using the API::

  $ curl -X POST \
         -d '{
          "type": "telnet",
          "label": "My First Channel",
          "mo_url": "http://requestb.in/pzvivfpz",
          "config": {"twisted_endpoint": "tcp:9001"}
          }' \
         http://localhost:8000/channels/

Here, we tell Junebug to send all mobile-originating messages received by this
channel to `mo_url`. We use a `requestb.in <requestbin>`_ url so that we can inspect the messages.

.. _requestbin: http://requestb.in/

This creates a simple telnet transport that listens on port 9001. You should
get a response like:

  .. code-block:: json

    {
      "status": 200,
      "code": "OK",
      "description": "channel created",
      "result": {
        "status": {},
        "mo_url": "http://www.example.com/first_channel/mo",
        "label": "My First Channel",
        "type": "telnet",
        "config": {"twisted_endpoint": "tcp:9001"},
        "id": "6a5c691e-140c-48b0-9f39-a53d4951d7fa"
      }
    }

With the telnet transport running, we can now connect to the telnet transport::

  $ telnet localhost 9001

If we take a look at the requestbin we gave as the `mo_url` when creating the
channel, we should see something like this:

  .. code-block:: json

      {
        "channel_data": {"session_event": "new"},
        "from": "127.0.0.1:53378",
        "channel_id": "bc5f2e63-7f53-4996-816d-4f89f45a5842",
        "timestamp": "2015-10-06 14:16:34.578820",
        "content": null,
        "to": "0.0.0.0:9001",
        "reply_to": null,
        "message_id": "35f3336d4a1a46c7b40cd172a41c510d"
      }

This message was sent to the channel when we connected to the telnet transport,
and is equivalent to starting a session for a session-based transport type like USSD.

Now, lets send a message to the telnet transport via junebug::

  $ curl -X POST \
      -d '{
        "to": "127.0.0.1:53378",
        "content": "hello"
      }' \
      localhost:8000/channels/bc5f2e63-7f53-4996-816d-4f89f45a5842/messages/

Here, we sent a message to the address `127.0.0.1:53378`. We should see a `hello` message appear in our telnet client.

Now, lets try receive a message via junebug by entering a message in our telnet
client::

   > Hi there

If we take a look at our requestbin url, we should see a new request:

  .. code-block:: json

    {
        channel_data: {session_event: "resume"},
        from: "127.0.0.1:53378",
        channel_id: "bc5f2e63-7f53-4996-816d-4f89f45a5842",
        timestamp: "2015-10-06 14:30:51.876897",
        content: "hi there",
        to: "0.0.0.0:9001",
        reply_to: null,
        message_id: "22c9cd74c5ff42d9b8e1a538e2a17175"
    }

Now, lets send a reply to this message by referencing its `message_id`::

  $ curl -X POST \
      -d '{
        "reply_to": "22c9cd74c5ff42d9b8e1a538e2a17175",
        "content": "hello again"
      }' \
      localhost:8000/channels/bc5f2e63-7f53-4996-816d-4f89f45a5842/messages/

We should see `hello again` appear in our telnet client.

Those are the basics for sending and receiving messages via junebug. Take a look at junebug's :ref:`HTTP API documentation <http-api>` to see how else one can interact with junebug, and junebug's :ref:`CLI <cli-reference>` and :ref:`config <config-reference>` references for more on how junebug can be configured.

Infrastructure Diagram
----------------------
This diagram is an example configuration of how all the parts of Junebug fit
together in a typical setup.

.. blockdiag::

    diagram {
        orientation = portrait;
        default_group_color = lightblue;
        edge_layout = flowchart;

        C1 [label="USSD Channel"];
        C2 [label="SMS Channel"];
        SMS [label="SMPP SMS line"];
        USSD [label="Dmark USSD line"];
        Status [label="Status monitoring app"];
        App1 [label="Survey app"];
        Bulk [label="Bulk message sending app"];

        USSD <-> C1 <-> App1;
                 C1 -> Status;
        SMS <-> C2 <- Bulk;
                C2 -> Status;

        group {
            label='Network provider';
            USSD;
            SMS;
        }

        group {
            label="Junebug";
            C1;
            C2;
        }

        group {
            label='User applications';
            App1;
            Status;
            Bulk;
        }

    }

This diagram details a simple application that uses Junebug. It has two
lines. The first line is a USSD line which the users will use to answer
survey questions. The second is an SMS line, which is used for bulk message
sending to prompt the users to dial the USSD line when a new survey is
available.

Each of these lines is connected to a Junebug channel.

The USSD channel sends all of its incoming messages to an application which
knows what to do with the messages, and can generate appropriate responses. In
this case, the application will store the user's answer, and send the user the
next question in the survey.

The SMS channel receives messages that it must send out on its messages
endpoint. These messages are generated by the bulk send application, which
notifies the users when a new survey is available.

Both of the channels send their status events to a status monitoring app,
which sends out emails to the correct people when there is something wrong
with either of the channels.
