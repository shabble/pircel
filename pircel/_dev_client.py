#!/usr/bin/env python3
# -*- coding: utf8 -*-
import logging

from tornado import gen, ioloop, tcpclient

from pircel import protocol

CHANNEL_JOIN_DELAY = 30

logger = logging.getLogger(__name__)
loopinstance = ioloop.IOLoop.instance()


class LineStream:
    def __init__(self):
        self.tcp_client_factory = tcpclient.TCPClient()
        self.line_callback = None
        self.connect_callback = None

    @gen.coroutine
    def connect(self, host, port):
        logger.debug('Connecting to server %s:%s', host, port)
        self.connection = yield self.tcp_client_factory.connect(host, port)
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
        return self.connection.write(line.encode('utf8'))


def connect(args, server_handler):
    line_stream = LineStream()

    # Attach instances
    server_handler.write_function = line_stream.write_function
    line_stream.connect_callback = server_handler.pre_line
    line_stream.line_callback = server_handler.handle_line

    if args.die_on_exception:
        loopinstance.handle_callback_exception = _exc_exit

    # Connect to server
    line_stream.connect(args.server, 6667)

    connected_rpl = 'rpl_welcome'

    def _join_channel(channel):
        def inner_func(*args):
            server_handler.channels[channel].join()
            server_handler.remove_callback(connected_rpl, inner_func)
        return inner_func

    # Join channels
    for channel in args.channel:
        server_handler.add_callback(connected_rpl, _join_channel(channel))


def main_loop():
    loopinstance.start()


def _exc_exit(unused_callback):
    import sys
    import traceback
    traceback.print_exc()
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
    arg_parser.add_argument('-c', '--channel', action='append',
                            help='Channel to join on server')
    arg_parser.add_argument('-D', '--debug', action='store_true',
                            help='Enable debug logging')
    arg_parser.add_argument('--die-on-exception', action='store_true',
                            help='Exit program when an unhandled exception occurs, rather than trying to recover')
    arg_parser.add_argument('--debug-out-loud', action='store_true',
                            help='Print selected debug messages out over IRC')
    return arg_parser


def get_parsed_args():
    arg_parser = get_arg_parser()
    args = arg_parser.parse_args()

    if not args.channel:
        args.channel = ['#possel-test']

    return args


def main():
    args = get_parsed_args()

    # setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    log_date_format = "%Y-%m-%d %H:%M:%S"
    log_format = "%(asctime)s\t%(levelname)s\t%(module)s:%(funcName)s:%(lineno)d\t%(message)s"
    logging.basicConfig(level=log_level, format=log_format, datefmt=log_date_format)
    logging.captureWarnings(True)

    user = protocol.User(args.nick, args.username, args.real_name)
    server_handler = protocol.IRCServerHandler(user, args.debug_out_loud)

    connect(args, server_handler)

    main_loop()


if __name__ == '__main__':
    main()
