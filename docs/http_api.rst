.. Junebug HTTP API


HTTP API
========

Junebug's HTTP API.

.. warning::

   Junebug's HTTP API doesn't exist yet. This document describes what
   its HTTP API might look like.


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
       URL to call on changes in channel status. May be null if not
       desired. Not supported by every channel type.
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
       Description of result (usually ``"channel created""``).
   :param dict result:
       The channel created.


.. http:get:: /channels/(channel_id:str)

   Return the channel configuration and a nested status object.

   Possible connection states are: ``up``, ``down``, ``unknown``.

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
            queue_length: 5,
            connection_state: "up",
            send_rate: 10,
            accept_rate: 12,
            reject_rate: 0
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
   :param str event_url:
       URL to call for status events (e.g. acknowledgements and
       delivery reports) related to this message.
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

Events POSTed to the ``event_url`` specified in
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

Events are posted to the message’s ``event_url`` after the message is
submitted to the provider, and when delivery reports are received.

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
