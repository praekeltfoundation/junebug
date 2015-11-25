.. _design:

Design
======

An HTTP API for managing text-based messaging channels such as SMS,
USSD, XMPP, Twitter, IRC.


Features
--------

Junebug is a system for managing text messaging transports via a RESTful HTTP interface that supports:

* Creating, introspecting, updating and deleting transports
* Sending and receiving text messages
* Receiving status updates on text messages sent
* Monitoring transport health and performance
* Retrieving recent transport logs for debugging transport issues.


Design principles
-----------------

Junebug aims to satisfy the following broad criteria:

* Avoid replication of work to integrate with aggregators and MNOs
  (and to maintain these connections).
* Maximum simplicity (narrow scope, minimal useful feature set).
* Provide a common interface to diverse connection protocols.
* Handle buffering of messages and events in both inbound and outbound
  directions.
* Minimum dependencies.
* Easy to install.


Design goals
------------

Outbound message sending
^^^^^^^^^^^^^^^^^^^^^^^^

* Simple universal HTTP API for sending.
* Each channel is independent and cannot block or cause others to
  fail.
* Does not handle routing. Channel to send to is specified when making
  the HTTP API request.
* Configurable rate-limiting on each connection.
* Queues for each connection.
* Multiple priority levels supported for each connection. We need at
  least two priority levels: "bulk" and "realtime".

Delivery and status reports for outbound messages
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* Can specify an HTTP URL with each outgoing request, as the callback
  for delivery status reports for that message.
* Callback URL supports template variables (like Kannel does).

Channel creation and management
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* CRUD operations on channels.
* Possible to list channels.
* Possible to query the queue length.
* Possible to query the message sending, delivery and failure rates.
* Possible to cancel the sending of all queued messages.

Inbound messages
^^^^^^^^^^^^^^^^

* Able to specify a URL, per channel, that is called with configurable
  (substituted) parameters.
* Retries delivery on failures (not for version 1.0).


Logging
^^^^^^^

Accessing detailed log messages is a vital requirement for debugging
issues with connections to third parties.

* Be able to access PDUs or similar detailed channel message logs for recent messages.
* Logs should be retrieval by associated message or channel id.


Relevant prior works
--------------------

Other systems that have acted as inspirations or components of
Junebug:

* `Vumi`_ and `Vumi Go`_
* `Kannel`_
* `CloudHopper`_

.. _Vumi: https://github.com/praekelt/vumi
.. _Vumi Go: https://github.com/praekelt/vumi-go
.. _Kannel: http://kannel.org/
.. _CloudHopper: https://github.com/twitter/cloudhopper-smpp


Glossary
--------

:channel:
    a single connection to a provider
:channel type:
    connections are instances of channel types. Example: Twilio, SMPP 3.4, etc.


System Architecture
-------------------
.. blockdiag::

    diagram {
        Junebug <-> Redis, RabbitMQ, Files;
    }

Junebug relies on Redis for temporary storage, RabbitMQ for message queueing,
and files on disc for logs. This setup was chosen so that Junebug would be
easy to setup and start using, and not require a large, complicated,
multi-system setup.

There are downsides to this approach, however, Junebug is currently restricted
to a single threaded process.
