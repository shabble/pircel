#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
pircel.bot
----------

This module defines an example of using pircel with tornado to produce a "bot" that does basically nothing.

It can, however, be subclassed easily to do bot-like-things.
"""
import logging

import peewee
from tornado import ioloop

from pircel import model, protocol, tornado_adapter


logger = logging.getLogger(__name__)
loopinstance = ioloop.IOLoop.current()


class IRCBot:
    def __init__(self, args):
        user = model.UserDetails(nick=args.nick, username=args.username, realname=args.real_name)

        server_handler = protocol.IRCServerHandler(user)

        line_stream = tornado_adapter.LineStream()

        controller = None
        if args.storage_database is not None:
            db = peewee.SqliteDatabase(args.storage_database)
            model.database.initialize(db)
            model.create_tables()
            user.save()

            try:
                controller = model.IRCServerController.new(args.server, args.port, not args.insecure, user)
            except peewee.IntegrityError:
                controller = model.IRCServerController.get(args.server, args.port)

            controller.server_handler = server_handler
        self.controller = controller

        irc_client = tornado_adapter.IRCClient(line_stream, server_handler, controller)

        # Connect to server
        irc_client.connect(args.server, args.port, args.insecure, args.channel)

        self.args = args
        self.server = server_handler
        self.line_stream = line_stream
        self.user = user

    def main(self):
        loopinstance.start()

    @classmethod
    def from_default_args(cls, mutate_parser=None, **kwargs):
        args = get_parsed_args(mutate_parser)
        for key, value in kwargs.items():
            setattr(args, key, value)
        return cls(args)


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
    arg_parser.add_argument('-p', '--port', default=6697,
                            help='Port to use')
    arg_parser.add_argument('--insecure', action='store_true',
                            help="Don't use SSL/TLS for whatever reason")
    arg_parser.add_argument('-c', '--channel', action='append',
                            help='Channel to join on server')
    arg_parser.add_argument('-D', '--debug', action='store_true',
                            help='Enable debug logging')
    arg_parser.add_argument('--die-on-exception', action='store_true',
                            help='Exit program when an unhandled exception occurs, rather than trying to recover')
    arg_parser.add_argument('--debug-out-loud', action='store_true',
                            help='Print selected debug messages out over IRC')
    arg_parser.add_argument('--storage-database', default=None,
                            help='sqlite database, defaults to no storage')
    return arg_parser


def get_parsed_args(mutate_parser=None):
    arg_parser = get_arg_parser()
    if mutate_parser is not None:
        arg_parser = mutate_parser(arg_parser)

    args = arg_parser.parse_args()

    if not args.channel:
        args.channel = ['#possel-test']

    return args


def main():
    bot = IRCBot.from_default_args()

    # setup logging
    log_level = logging.DEBUG if bot.args.debug else logging.INFO
    log_date_format = "%Y-%m-%d %H:%M:%S"
    log_format = "%(asctime)s\t%(levelname)s\t%(module)s:%(funcName)s:%(lineno)d\t%(message)s"
    logging.basicConfig(level=log_level, format=log_format, datefmt=log_date_format)
    logging.captureWarnings(True)

    if bot.args.die_on_exception:
        loopinstance.handle_callback_exception = _exc_exit

    bot.main()


if __name__ == '__main__':
    main()
