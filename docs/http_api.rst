.. Junebug HTTP API


HTTP API
========


HTTP API endpoints
------------------

Channels
^^^^^^^^

.. http:get:: /channels

   List all channels


.. http:post:: /channels

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


.. http:put:: /channels/(channel_id:str)

   Modify a channel's configuration.

   Accepts the same parameters as :http:put:`/channels`. Only the
   parameters provided are updated. Others retain their original
   values.


.. http:delete:: /channels/(channel_id:str)

   Delete a channel.


Messages
^^^^^^^^

.. http:post:: /channels/(channel_id:str)/messages

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
