.. _http-api:


HTTP API
========

Junebug's HTTP API.


HTTP API endpoints
------------------

.. _channels:

Channels
^^^^^^^^

.. http:get:: /channels/

   List all channels


.. http:post:: /channels/

   Create a channel.

   :param str type: channel type (e.g. ``smpp``, ``twitter``, ``xmpp``)
   :param str label: user-defined label
   :param dict config:
       channel connection settings (a blob to pass to the channel type
       implementor)
   :param dict metadata:
       user-defined data blob (used to record user-specified
       information about the channel, e.g. the channel owner)
   :param str status_url:
       URL that junebug should send :ref:`status events <status-events>`
       to. May be ``null`` if not desired. Not supported by every channel.
   :param str mo_url:
       URL to call on incoming messages (mobile originated) from this channel.
       One or both of mo_url or amqp_queue must be specified. If both are
       specified, messages will be sent to both.
   :param str amqp_queue:
       AMQP queue to repost messages onto for mobile originated messages. One
       or both of mo_url or amqp_queue must be specified. If both are
       specified, messages are sent to both. See :ref:`amqp-integration` for
       more details.
   :param int rate_limit_count:
       Number of incoming messages to allow in a given time window.
       See ``rate_limit_window``.
   :param int rate_limit_window:
       Size of throttling window in seconds.
   :param int character_limit:
       Maximum number of characters allowed per message.

   Returns:

   :param int status:
       HTTP status code (usually 201 on success).
   :param str code:
       HTTP status string.
   :param str description:
       Description of result (usually ``"channel created"``).
   :param dict result:
       The channel created.


.. http:get:: /channels/(channel_id:str)

   Return the channel configuration and a nested :ref:`status <status-events>`
   object.

   The status object takes the following form:

   :param str status:
      The worst case of each :ref:`component's <status-components>`
      :ref:`status level <status-levels>`. For example if the ``redis``
      component's status is ``degraded`` and the ``amqp`` component's status is
      ``down``, this field's value will will be `down`.

   :param dict components:
      An object showing the most recent status event for each component.

   :param float inbound_message_rate:
      The inbound messages per second for the channel.

   :param float outbound_message_rate:
      The outbound messages per second for the channel.

   :param float submitted_event_rate:
      The submitted events per second for the channel.

   :param float rejected_event_rate:
      The rejected events per second for the channel.

   :param float delivery_succeeded_rate:
      The delivery succeeded events per second for the channel.

   :param float delivery_failed_rate:
      The delivery failed events per second for the channel.

   :param float delivery_pending_rate:
      The delivery pending events per second for the channel.

   **Example response**:

   .. sourcecode:: json

      {
        status: 200,
        code: "OK",
        description: "channel status",
        result: {
          id: "uuid-1234",
          type: "smpp",
          label: "An SMPP Transport",
          config: {
            system_id: "secret_id",
            password: "secret_password"
          },
          metadata: {
            owned_by: "user-5",
          },
          status_url: "http://example.com/user-5/status",
          mo_url: "http://example.com/user-5/mo",
          rate_limit_count: 500,
          rate_limit_window: 10,
          character_limit: null,
          status: {
             status: 'ok',
             components: {
                smpp: {
                   component: 'smpp',
                   channel_id: "channel-uuid-1234",
                   status: 'ok',
                   reasons: [],
                   details: {}
                },
                amqp: {
                   component: 'amqp',
                   channel_id: "channel-uuid-1234",
                   status: 'ok',
                   reasons: [],
                   details: {}
                }
            },
            inbound_message_rate: 1.75,
            outbound_message_rate: 7.11,
            submitted_event_rate: 6.2,
            rejected_event_rate: 2.13,
            delivery_succeeded_rate: 5.44,
            delivery_failed_rate: 1.27,
            delivery_pending_rate: 4.32
          }
        }
      }


.. http:post:: /channels/(channel_id:str)

   Modify a channel's configuration.

   Accepts the same parameters as :http:post:`/channels/`. Only the
   parameters provided are updated. Others retain their original
   values.


.. http:delete:: /channels/(channel_id:str)

   Delete a channel.


.. http:post:: /channels/(channel_id:str)/restart

   Restart a channel.


Logs
^^^^

.. http:get:: /channels/(channel_id:str)/logs

   Get the most recent logs for a specific channel.

   :query int n:
       Optional. The number of logs to fetch. If not supplied, then the
       configured maximum number of logs are returned. If this number is
       greater than the configured maximum logs value, then only the
       configured maximum number of logs will be returned.

   The response is a list of logs, with each log taking the following form:

   :param str logger: The logger that created the log, usually the channel id.
   :param int level:
       The level of the logs. Corresponds to the levels found in the python
       module :py:mod:`logging`.
   :param float timestamp: Timestamp, in the format of seconds since the epoch.
   :param str message: The message of the log.

   In the case of an exception, there will be an exception object, with the
   following parameters:

   :param str class: The class of the exception.
   :param str instance: The specific instance of the exception.
   :param list stack:
       A list of strings representing the traceback of the error.

   **Example Request**:

   .. sourcecode:: http

       GET /channels/123-456-7a90/logs?n=2 HTTP/1.1
       Host: example.com
       Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: json

      {
        status: 200,
        code: "OK",
        description: "Logs retrieved",
        result: [
            {
                logger: "123-456-7a90",
                level: 40,
                timestamp: 987654321.0,
                message: "Last log for the channel"
                exception: {
                    class: "ValueError",
                    instance: "ValueError("Bad value",)",
                    stack: [
                        ...
                    ]
                }
            },
            {
                logger: "123-456-7a90",
                level: 20,
                timestamp: 987654320.0,
                message: "Second last log for the channel"
            }
        ]
      }


Messages
^^^^^^^^

.. http:post:: /channels/(channel_id:str)/messages/

   Send an outbound (mobile terminated) message.

   :param str to:
       the address (e.g. MSISDN) to send the message too. Should be omitted
       if ``reply_to`` is specified.
   :param str from:
       the address the message is from. May be ``null`` if the channel
       only supports a single from address.
   :param str reply_to:
       the uuid of the message being replied to if this is a response to a
       previous message. Important for session-based transports like USSD.
       Optional. Only one of ``to`` or ``reply_to`` may be specified.
       The default settings allow 10 minutes to reply to a message, after which
       an error will be returned.
   :param str event_url:
       URL to call for status events (e.g. acknowledgements and
       delivery reports) related to this message. The default settings allow
       2 days for events to arrive, after which they will no longer be
       forwarded.
   :param int priority:
       Delivery priority from 1 to 5. Higher priority messages are delivered first.
       If omitted, priority is 1.
   :param dict channel_data:
       Additional data that is passed to the channel to interpret. E.g.
       ``continue_session`` for USSD, ``direct_message`` or ``tweet`` for
       Twitter.

   **Example request**:

   .. sourcecode:: json

      {
        to: "+26612345678",
        from: "8110",
        reply_to: "uuid-1234",
        event_url: "http://example.com/events/msg-1234",
        content: "Hello world!",
        priority: 1,
        channel_data: {
          continue_session: true,
        }
      }

   **Example response**:

   .. sourcecode:: json

      {
        status: 201,
        code: "created",
        description: "message submitted",
        result: {
          id: "message-uuid-1234"
        }
      }


.. http:get:: /channels/(channel_id:str)/messages/(msg_id:str)

   Retrieve a message's status.

   **Example response**:

   .. sourcecode:: json

      {
        status: 200,
        code: "OK",
        description: "message status",
        result: {
          id: "msg-uuid-1234",
          last_event_type: "ack",
          last_event_timestamp: "2015-06-15 13:00:00",
          events: [
              /* array of all events; formatted like events */
          ]
        }
      }


Events
------

Events ``POST``\ed to the ``event_url`` specified in
:http:post:`/channels/(channel_id:str)/messages/` have the following
format:

.. http:post:: /event/url

   :param str event_type:
       The type of the event. See the list of event types below.
   :param str message_id:
       The UUID of the message the event is for.
   :param str channel_id:
       The UUID of the channel the event occurred for.
   :param str timestamp:
       The timestamp at which the event occurred.
   :param dict event_details:
       Details specific to the event type.

Events are posted to the message's ``event_url`` after the message is
submitted to the provider, and when delivery reports are received.
The default settings allow events to arrive for up to 2 days; any further
events will not be forwarded.

**Request example**:

.. sourcecode:: json

   {
     event_type: "submitted",
     message_id: "msg-uuid-1234",
     channel_id: "channel-uuid-5678",
     timestamp: "2015-06-15 13:00:00",
     event_details: {
        /* detail specific to the channel implementation. */
     }
   }

Event types
^^^^^^^^^^^

Sent when the message is submitted to the provider:

* ``submitted``: message successfully sent to the provider.
* ``rejected``: message rejected by the channel.

Sent later when (or if) delivery reports are received:

* ``delivery_succeeded``: provider confirmed that the message was delivered.
* ``delivery_failed``: provider declared that message delivery failed.
* ``delivery_pending``: provider is still attempting to deliver the message.


.. _status-events:

Status events
-------------

Status events ``POST``\ed to the ``status_url`` specified in :http:post:`/channels/` have the following format:

.. http:post:: /status/url

   :param str component:
       The :ref:`component <status-components>`  relevant to this status event.
   :param str channel_id:
       The UUID of the channel the status event occurred for.
   :param str status:
       The :ref:`status level <status-levels>` this event was categorised under.
   :param str type:
       A programmatically usable string value describing the reason for the
       status event.
   :param str message:
       A human-readable string value describing the reason for the status
       event.
   :param dict details:
       Details specific to this event intended to be used for debugging
       purposes. For example, if the event was related to a component
       establishing a connection, the host and port are possible fields.


**Request Example**:

.. sourcecode:: json

   {
      status: "down",
      component: "smpp",
      channel_id: "channel-uuid-5678",
      type: "connection_lost",
      message: "Connection lost",
      details: {}
   }


.. _status-components:

Components
^^^^^^^^^^

Each status event published by a channel describes a component used as part of
the channel's operation. For example, an smpp channel type will have a
``redis`` component describing its redis connection, an ``amqp`` component
describing its amqp connection and an ``smpp`` component describing events
specific to the SMPP protocol (for example, connections, binds, throttling).

.. _status-levels:

Status levels
^^^^^^^^^^^^^

A status event can be categorised under one of the following levels:

  - ``ok``: The component is operational.
  - ``degraded``: The component is operational, but there is an issue which may
    affect the operation of the component. For example, the component may be
    throttled.
  - ``down``: The component is not operational as a result of the issue
    described by the event.
