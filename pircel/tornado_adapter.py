#!/usr/bin/env python
# -*- coding: utf-8 -*-
import datetime
import logging
import ssl
import random
from bdb import BdbQuit

from tornado import gen, ioloop, tcpclient
from tornado.ioloop import IOLoop

from pircel import protocol

class Registry:
    fwd_reg = {}
    reg = {}

    @classmethod
    def register(cls, *args):
        def decorator(fn):
            cls.fwd_reg[fn.__name__] = args
            for x in args:
                cls.reg.setdefault(x, []).append((fn.__name__, fn.__qualname__))

            return fn
        return decorator

class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

class Identity(AttrDict):
    pass


logger = logging.getLogger(__name__)




class LineStream:
    def __init__(self):
        self.tcp_client_factory = tcpclient.TCPClient()
        self.line_callback = None
        self.connect_callback = None
        self.connection = None

    @gen.coroutine
    def connect(self, host, port, secure):
        logger.debug('Connecting to server %s:%s', host, port)

        if secure:
            ssl_options = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        else:
            ssl_options = None

        self.connection = yield self.tcp_client_factory.connect(host, port,
                                                                ssl_options=ssl_options)
        logger.debug('Connected.')
        if self.connect_callback is not None:
            self.connect_callback()
            logger.debug('Called post-connection callback')
        self._schedule_line()

    def handle_line(self, line):
        if self.line_callback is not None:
            self.line_callback(line)

        self._schedule_line()

    def _schedule_line(self):
        self.connection.read_until(b'\n', self.handle_line)

    def write_function(self, line):
        if line[-1] != '\n':
            line += '\n'
        logger.debug('sending >>{}<<'.format(line.encode('unicode-escape')))
        return self.connection.write(line.encode('utf8'))

class IRCClient:
    def __init__(self, line_stream, server_handler, interface=None):
        if interface is not None:
            interface.server_handler = server_handler
        # Attach instances
        server_handler.write_function = line_stream.write_function
        line_stream.connect_callback = self.connect_callback
        line_stream.line_callback = server_handler.handle_line

        self.line_stream = line_stream
        self.server_handler = server_handler
        self.interface = interface

    def connect_callback(self):
        self.server_handler.connect()

    def _ping(self):
        self.server_handler.send_ping(datetime.datetime.utcnow().timestamp())

    def connect(self, server=None, port=None, insecure=None, channels=None):
        # If we have a interface we ignore the above inputs
        if self.interface is not None:
            server, port, secure = self.interface.connection_details
            insecure = not secure
            channels = (channel.name for channel in self.interface.channels if channel.current)

        self.ping_callback = ioloop.PeriodicCallback(self._ping, 60000)
        self.ping_callback.start()

        # Connect to server
        self.line_stream.connect(server, port, not insecure)

        # Channel autojoin stuff
        connected_rpl = 'rpl_welcome'

        def _join_channel(channel):
            def inner_func(*args, **kwargs):
                logger.debug('Joining channel: %s', channel)
                self.server_handler.join(channel)
                self.server_handler.remove_callback(connected_rpl, inner_func)
            return inner_func

        # Join channels
        for channel in channels:
            self.server_handler.add_callback(connected_rpl, _join_channel(channel), weak=False)

    def start(self):
        if IOLoop.instance()._running:
           IOLoop.instance().stop()

        IOLoop.instance().start()
        logger.warning('IOLoop start completed')

    def stop(self):
        logger.debug('closing linestream connection')
        line_stream = self.line_stream
        if line_stream.connection is not None:
            line_stream.connection.close()
        logger.debug('cancelling pinger task')
        self.ping_callback.stop()

        logger.debug('stopping ioloop')
        IOLoop.instance().stop()



    @classmethod
    def from_interface(cls, interface):
        line_stream = LineStream()
        server_handler = protocol.IRCServerHandler(interface.identity)
        return cls(line_stream, server_handler, interface)

class IRCBot:
    def __init__(self, args):
        self.args = args
        line_stream = LineStream()
        IOLoop.instance().handle_callback_exception = _exc_exit

        rand_nick = 'pircel_{}'.format(random.randint(128, 256))
        ident = Identity(nick=rand_nick, username='upircel', realname='timmy')
        server_handler = protocol.IRCServerHandler(ident)
        self.client = IRCClient(line_stream, server_handler)


    def main(self):
        args = self.args
        self.register_callbacks()
        self.client.connect(args.server, args.port, insecure=True, channels=args.channels)
        self.client.start()

    def register_callbacks(self):
        cb_reg = Registry.reg
        for cb, cb_handlers in cb_reg.items():
            cb_funcs = [getattr(self, c[0]) for c in cb_handlers]
            for cb_func in cb_funcs:
                logger.info('registered {} to {}'.format(cb, cb_func))
                self.client.server_handler.add_callback(cb, cb_func, weak=False)

                #import ipdb; ipdb.set_trace()

    @Registry.register('privmsg')
    def _on_privmsg(self, *args, **kwargs):
        logger.info('got privmsg {a!r}, **{kw!r}'.format(a=args, kw=kwargs))

    @Registry.register('notice')
    def _on_notice(self, *args, **kwargs):
        logger.info('got notice {a!r}, **{kw!r}'.format(a=args, kw=kwargs))

    @classmethod
    def from_default_args(cls, mutate_parser=None, **kwargs):
        args = get_parsed_args(mutate_parser)
        for key, value in kwargs.items():
            setattr(args, key, value)
        return cls(args)

def _exc_exit( unused_callback):
    import sys
    import traceback
    ex = sys.exc_info
    print("EXCEPTION HANDLER", file=sys.stderr, flush=True)
    traceback.print_exc()
#    SHUTDOWN_EVERYTHING()


def SHUTDOWN_EVERYTHING():
    IOLoop.instance().stop()
    #IOLoop.instance().clear_instance()
    #IOLoop.instance().clear_current()
    import sys
    sys.exit(1)

def get_arg_parser():
    import argparse
    arg_parser = argparse.ArgumentParser(description='Pircel IRC Library Test client')
    arg_parser.add_argument('-n', '--nick', default='pircel',
                            help='Nick to use on the server.')
    arg_parser.add_argument('-u', '--username', default='pircel',
                            help='Username to use on the server')
    arg_parser.add_argument('-r', '--real-name', default='pircel IRC',
                            help='Real name to use on the server')
    arg_parser.add_argument('-s', '--server', default='irc.imaginarynet.org.uk',
                            help='IRC Server to connect to')
    arg_parser.add_argument('-p', '--port', default=6667,
                            help='IRC Port to connect to')

    arg_parser.add_argument('-c', '--channels', action='append',
                            help='Channel to join on server')
    arg_parser.add_argument('-D', '--debug', action='store_true',
                            help='Enable debug logging')
    arg_parser.add_argument('--die-on-exception', action='store_true',
                            help='Exit program when an unhandled exception occurs, rather than trying to recover')
    arg_parser.add_argument('--debug-out-loud', action='store_true',
                            help='Print selected debug messages out over IRC')
    return arg_parser


def get_parsed_args(mutate_parser=None):
    arg_parser = get_arg_parser()
    if mutate_parser is not None:
        arg_parser = mutate_parser(arg_parser)

    args = arg_parser.parse_args()

    if not args.channels:
        args.channels = ['#mhntest']

    return args


def handle_sigint(*args, **kwargs):
    logging.error('caught sigint. Going idb')
    client = kwargs['client']
    import ipdb
    ipdb.set_trace()
    logger.warning('continuing?')

    #loopinstance.stop()

def main():
    #import signal
    loopinstance = IOLoop.instance()

    bot = IRCBot.from_default_args()
    log_level = logging.DEBUG if bot.args.debug else logging.INFO
    log_date_format = "%Y-%m-%d %H:%M:%S"
    log_format = "%(asctime)s\t%(levelname)s\t%(module)s:%(funcName)s:%(lineno)d\t%(message)s"
    logging.basicConfig(level=log_level, format=log_format, datefmt=log_date_format)
    logging.captureWarnings(True)
    # signal.signal(signal.SIGINT,
    #               lambda sig, frame: loopinstance.add_callback_from_signal(
    #                   handle_sigint, bot=bot, client=bot.client))

    try:
        bot.main()
    except KeyboardInterrupt:
        print("maybe stopping")
        bot.client.stop()
        SHUTDOWN_EVERYTHING()
        print("hopefully stopped")
        # import os
        # os.exit(1)


from importlib import reload
def _do_reload():
    import pircel
    import pircel.tornado_adapter
    import pircel.protocol
    import pircel.signals
    for x in [pircel, pircel.tornado_adapter, pircel.protocol, pircel.signals]:
        reload(x)
    print("reloaded?")

if __name__ == '__main__':
    main()
