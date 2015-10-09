#!/usr/bin/env python
# -*- coding: utf-8 -*-
import unittest
from unittest import mock

import peewee
from playhouse import test_utils

from pircel import model


class TestModelUpdateValidity(unittest.TestCase):
    """ Testing that events from the protocol cannot put the model in an invalid state. """
    nick = 'percy'
    realname = 'Percy Wendel'
    username = 'pircel'

    def setUp(self):  # noqa
        self.database = peewee.SqliteDatabase(':memory:')
        self.db_context = test_utils.test_database(self.database, [model.IRCBufferMembershipRelation,
                                                                   model.IRCBufferModel,
                                                                   model.IRCLineModel,
                                                                   model.IRCServerModel,
                                                                   model.IRCUserModel,
                                                                   model.UserDetails,
                                                                   ])

    def get_interface(self):
        server_model = model.create_server('localhost', 6697, True, self.nick, self.realname, self.username)

        server_handler = mock.MagicMock()
        server_handler.identity.nick = self.nick
        server_handler.identity.realname = self.realname
        server_handler.identity.username = self.username

        interface = model.IRCServerInterface(server_model)
        interface.server_handler = server_handler
        return interface

    def test_multi_change_nick(self):
        """ When people change nick to the same name multiple times.

        Provided with feasible sequence of lines (join, part, nick, join, nick, part, nick, join, nick) for an actual
        IRC session.

        Testing for a bug in which multiple changes to the same nick would except and kill the connection.
        """
        with self.db_context:
            interface = self.get_interface()

            interface._handle_join(None, prefix='n!~u@h', args=['#c'])  # n joins
            interface._handle_part(None, prefix='n!~u@h', args=['#c'])  # n parts
            # n invisibly changes nick because they aren't in the channel, now m
            interface._handle_join(None, prefix='m!~u@h', args=['#c'])  # n joins, now called m
            interface._handle_nick(None, prefix='m!~u@h', args=['n'])  # n reclaims their nick
            interface._handle_part(None, prefix='n!~u@h', args=['#c'])  # n parts
            # n invisibly changes nick because they aren't in the channel, now m
            interface._handle_join(None, prefix='m!~u@h', args=['#c'])  # n joins, now called m
            interface._handle_nick(None, prefix='m!~u@h', args=['n'])  # n reclaims their nick


def main():
    unittest.main()

if __name__ == '__main__':
    main()
