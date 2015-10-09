#!/usr/bin/env python
# -*- coding: utf-8 -*-
import datetime
import logging
import ssl

from tornado import gen, ioloop, tcpclient

from pircel import protocol


logger = logging.getLogger(__name__)
loopinstance = ioloop.IOLoop.current()


class LineStream:
    def __init__(self):
        self.tcp_client_factory = tcpclient.TCPClient()
        self.line_callback = None
        self.connect_callback = None

    @gen.coroutine
    def connect(self, host, port, secure):
        logger.debug('Connecting to server %s:%s', host, port)

        if secure:
            ssl_options = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        else:
            ssl_options = None

        self.connection = yield self.tcp_client_factory.connect(host, port, ssl_options=ssl_options)
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

    def start(self):
        loopinstance.start()


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

    @classmethod
    def from_interface(cls, interface):
        line_stream = LineStream()
        server_handler = protocol.IRCServerHandler(interface.identity)
        return cls(line_stream, server_handler, interface)


def main():
    pass

if __name__ == '__main__':
    main()
