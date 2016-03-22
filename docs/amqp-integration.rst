.. _amqp-integration:

AMQP integration
================

Should you choose to use the AMQP queues to handle messaging with Junebug, when
you specify the ``amqp_queue`` parameter when you configure the
:ref:`channel <channels>`, the usage is as follows:

* Inbound *(mobile originated)* messages are sent to the **routing key** of
  ``{amqp_queue}.inbound``
* Events are sent to the **routing key** of ``{amqp_queue}.event``
* Outbound *(mobile terminated)* messages will be fetched from **queue**
  ``{amqp_queue}.outbound``

Remember to bind the **routing key** to your desired **queue**, and that the Exchange
name defaults to ``vumi``, else it you will not recieve the messages. Please
have a look at https://www.rabbitmq.com/tutorials/amqp-concepts.html for more
information.

The data sent over AMQP is the standard Vumi data format.

An example of the data format is:

.. code:: json

    {
        "transport_name": "2427d857-688d-4cee-88d9-8e0e32dfdc13",
        "from_addr_type": null,
        "group": null,
        "from_addr": "127.0.0.1:46419",
        "timestamp": "2016-03-18 11:49:36.830534",
        "in_reply_to": null,
        "provider": null,
        "to_addr": "0.0.0.0:9001",
        "routing_metadata": {},
        "message_id": "a5d2800751f54b55a622e3965e1b71ec",
        "content": "a",
        "to_addr_type": null,
        "message_version": "20110921",
        "transport_type": "telnet",
        "helper_metadata": {
            "session_event": "resume"
        },
        "transport_metadata": {},
        "session_event": "resume",
        "message_type": "user_message"
    }
