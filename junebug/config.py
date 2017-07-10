from confmodel import Config
from confmodel.fields import (
    ConfigBool, ConfigText, ConfigInt, ConfigDict, ConfigList, ConfigFloat)


class JunebugConfig(Config):
    interface = ConfigText(
        "Interface to expose the API on",
        default='localhost')

    port = ConfigInt(
        "Port to expose the API on",
        default=8080)

    logfile = ConfigText(
        "File to log to or `None` for no logging",
        default=None)

    sentry_dsn = ConfigText(
        "DSN to send exceptions",
        default=None)

    redis = ConfigDict(
        "Config to use for redis connection",
        default={
            'host': 'localhost',
            'port': 6379,
            'db': 0,
            'password': None
        })

    amqp = ConfigDict(
        "Config to use for amqp connection",
        default={
            'hostname': '127.0.0.1',
            'vhost': '/',
            'port': 5672,
            'db': 0,
            'username': 'guest',
            'password': 'guest'
        })

    inbound_message_ttl = ConfigInt(
        "Maximum time (in seconds) allowed to reply to messages",
        default=60 * 10)

    outbound_message_ttl = ConfigInt(
        "Maximum time (in seconds) allowed for events to arrive for messages",
        default=60 * 60 * 24 * 2)

    channels = ConfigDict(
        "Mapping between channel types and python classes.",
        default={})

    replace_channels = ConfigBool(
        "If `True`, replaces the default channels with `channels`. If `False`,"
        " `channels` is added to the default channels.",
        default=False)

    plugins = ConfigList(
        "A list of dictionaries describing all of the enabled plugins. Each "
        "item should have a `type` key, with the full python class name of "
        "the plugin.", default=[])

    metric_window = ConfigFloat(
        "The size of the buckets (in seconds) used for metrics.", default=10.0)

    logging_path = ConfigText(
        "The path to place log files in.", default="logs/")

    log_rotate_size = ConfigInt(
        "The maximum size (in bytes) of a log file before it gets rotated.",
        default=1000000)

    max_log_files = ConfigInt(
        "The maximum amount of log files allowed before old files start to "
        "get deleted. 0 is unlimited.", default=5)

    max_logs = ConfigInt(
        "The maximum amount of logs that is allowed to be retrieved via the "
        "API.", default=100)
