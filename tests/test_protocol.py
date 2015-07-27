#!/usr/bin/env python
# -*- coding: utf-8 -*-
import unittest

from pircel import protocol


class TestInitialConnection(unittest.TestCase):
    nick = 'test'
    user = 'test'
    realname = 'test'

    def setUp(self):
        self.output = []
        identity = protocol.User(self.nick, self.user, self.realname)
        self.server_handler = protocol.IRCServerHandler(identity)

        self.server_handler.write_function = self.output.append

    def test_connect(self):
        self.server_handler.connect()

        expected = ['NICK {}'.format(self.nick), 'USER {} 0 * :{}'.format(self.user, self.realname)]

        self.assertListEqual(self.output, expected)

    def test_pint(self):
        self.server_handler.connect()
        ping_value = 'stuff'
        self.server_handler.handle_line('PING :{}'.format(ping_value))
        self.assertEqual(self.output[-1], 'PONG :{}'.format(ping_value))


def main():
    unittest.main()

if __name__ == '__main__':
    main()
