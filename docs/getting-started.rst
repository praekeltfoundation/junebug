.. Getting started

Getting started
===============

This guides assumed you have already followed the `installation guide`_.

.. _installation guide: installation

First you'll need to launch Junebug::

  $ jb -p 8000

This starts the Junebug HTTP API running on port 8000. At the moment it won't
have any transports running, so let's create one using the API::

  $ curl -X POST \
         -d '{"type": "telnet", "label": "My First Channel", "mo_url": "http://www.example.com/first_channel/mo", "config": {"transport_name": "my_first_transport", "twisted_endpoint": "tcp:9001"}}' \
         http://localhost:8000/channels

This creates a simple telnet transport that listens on port 9001. You should
get a response like::

  {
    "status": 200,
    "code": "OK",
    "description": "channel created",
    "result": {
      "status": {},
      "mo_url": "http://www.example.com/first_channel/mo",
      "label": "My First Channel",
      "type": "telnet",
      "config": {
        "transport_name": "my_first_transport",
        "twisted_endpoint": "tcp:9001"
      },
      "id": "6a5c691e-140c-48b0-9f39-a53d4951d7fa"
    }
  }
