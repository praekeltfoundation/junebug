.. _http-api:


HTTP API
========

Junebug's HTTP API.

.. warning::

   Junebug is still in alpha, and some of the HTTP API endpoints documented
   here are yet to be completed.


HTTP API endpoints
------------------

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
      component's status is ``minor`` and the ``amqp`` component's status is
      ``major``, this field's value will will be `major`.

   :param dict components:
      An object showing the most recent status event for each component.

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
             status: 'good',
             components: {
                smpp: {
                   component: 'smpp',
                   channel_id: "channel-uuid-1234",
                   status: 'good',
                   reasons: [],
                   details: {}
                },
                component: {
                   component: 'amqp',
                   channel_id: "channel-uuid-1234",
                   status: 'good',
                   reasons: [],
                   details: {}
                }
            }
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
   :param list reasons:
       An array of human-readable strings associated with this status event.
   :param dict details:
       Details specific to this event intended to be used for debugging
       purposes. For example, if the event was related to a component
       establishing a connection, the host and port are possible fields.


**Request Example**:

.. sourcecode:: json

   {
      component: 'smpp',
      channel_id: "channel-uuid-5678",
      status: 'good',
      reasons: [],
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

  - ``good``: The component is operational.
  - ``minor``: The component is operational, but there is an issue which may
    affect the operation of the component. For example, the component may be
    throttled.
  - ``major``: The component is not operational as a result of the issue
    described by the event.
