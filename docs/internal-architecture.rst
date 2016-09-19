Internal Architecture
=====================

Internal Junebug is structured as a set of services that live within a
single process.

Each Junebug channel creates three services -- a transport, a message
forwarder and a status receiver.

*Transports* are Vumi transport workers that send and receive SMSes, USSD
requests or other text messages from external service providers such as MNOs (
mobile network operators) or aggregators (re-sellers of connections to multiple
MNOs).

*Message Forwarders* receive inbound (MO, mobile originated) messages from
transports and relay to applications either via HTTP or AMQP depending on the
channel configuration.

*Channel Status Processors* receive status events from transports and store
them in redis and forward them on via HTTP to interested applications.

Junebug uses Redis to store configuration and temporary state such as
channel status. Services that use Redis are marked with an "R" in the
diagram below. Some types of transports will also make use of Redis.

.. blockdiag::

    diagram {
      group junebug {
        label = "";
        shape = "box";
        color = "#8080A0";

        group junebug_api {
          color = "#D0A0A0";
          JunebugApi [label = "Junebug API", numbered="R"];
        }

        group channel_1 {
          color = "#A0D0A0";
          label = "Channel 1";
          Transport1 [label = "Transport 1", numbered="R"];
          MessageForwarder1 [label = "Message\nForwarder 1", numbered="R"];
          ChannelStatus1 [label = "Channel Status\nProcessor 1", numbered="R"];
          Transport1 -> MessageForwarder1;
          Transport1 -> ChannelStatus1;
        }

        group channel_2 {
          color = "#A0D0A0";
          label = "Channel 2";
          Transport2 [label = "Transport 2"];
          MessageForwarder2 [label = "Message\nForwarder 2", numbered="R"];
          ChannelStatus2 [label = "Channel Status\nProcessor 2", numbered="R"];
          Transport2 -> MessageForwarder2;
          Transport2 -> ChannelStatus2;
        }

        group channel_3 {
          color = "#A0D0A0";
          label = "Channel 3";
          Transport3 [label = "Transport 3", numbered="R"];
          MessageForwarder3 [label = "Message\nForwarder 3", numbered="R"];
          ChannelStatus3 [label = "Channel Status\nProcessor 3", numbered="R"];
          Transport3 -> MessageForwarder3;
          Transport3 -> ChannelStatus3;
        }
      }

      App1 [label = "Application 1"];
      MessageForwarder1 -> App1 [style = 'dotted'];

      App2 [label = "Application 2"];
      MessageForwarder2 -> App2 [style = 'solid'];

      App3 [label = "Application 3"];
      MessageForwarder3 -> App3 [style = 'dotted'];
      ChannelStatus3 -> App3 [style = 'dotted'];

      Nginx [label = "Nginx"];
      Nginx -> JunebugApi [style = 'dotted'];
      Nginx -> Transport1 [style = 'dotted'];
      Nginx -> Transport2 [style = 'dotted'];
    }
