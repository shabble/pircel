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

    def test_change_nick_id(self):
        """ Tests that getting a user by nick after their nick changes returns the same id. """
        with self.db_context:
            interface = self.get_interface()

            model.create_user('n', interface.server_model)  # has id 1
            user1_m = model.create_user('m', interface.server_model)

            interface._handle_nick(None, prefix='m!~u@h', args=['n'])  # m reclaims their nick

            user1_n = model.get_user('n', interface.server_model)

            self.assertEqual(user1_m.id, user1_n.id)

    def test_multi_change_nick(self):
        """ Tests that no exception is raised when a user changes to a nick we think is still active. """
        with self.db_context:
            interface = self.get_interface()

            buffer = model.create_buffer('#c', interface.server_model)
            model.create_user(self.nick, interface.server_model)

            current_user = model.create_user('m', interface.server_model)
            model.create_user('n', interface.server_model, current=False)

            model.create_membership(buffer, current_user)

            interface._handle_nick(None, prefix='m!~u@h', args=['n'])  # n reclaims their nick


def main():
    unittest.main()

if __name__ == '__main__':
    main()
