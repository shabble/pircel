#!/usr/bin/env python3
# -*- coding: utf8 -*-
"""
pircel.protocol
---------------

This module defines functions and objects for interacting with an IRC server including:
    - parsing IRC protocol messages received from the server
    - generating IRC protocol messages to be sent back to the server
    - a callback-based API for interacting with these that should be agnostic to the multiprocessing mechanism used
      (e.g. it'll work with both asyncio and tornado if you set them up right; though twisted won't work at the moment
      because it doesn't support python 3)
"""
import collections
import logging

import chardet

import pircel

logger = logging.getLogger(__name__)


class Error(pircel.Error):
    """ Root exception for protocol parsing errors. """


class UnknownNumericCommandError(Error):
    """ Exception thrown when a numeric command is given but no symbolic version can be found. """


class UnknownModeCommandError(Error):
    """ Exception thrown on unknown mode change command. """


def split_irc_line(s):
    """Breaks a message from an IRC server into its prefix, command, and arguments.

    Copied straight from twisted, license and copyright for this function follows:
    Copyright (c) 2001-2014
    Allen Short
    Andy Gayton
    Andrew Bennetts
    Antoine Pitrou
    Apple Computer, Inc.
    Ashwini Oruganti
    Benjamin Bruheim
    Bob Ippolito
    Canonical Limited
    Christopher Armstrong
    David Reid
    Donovan Preston
    Eric Mangold
    Eyal Lotem
    Google Inc.
    Hybrid Logic Ltd.
    Hynek Schlawack
    Itamar Turner-Trauring
    James Knight
    Jason A. Mobarak
    Jean-Paul Calderone
    Jessica McKellar
    Jonathan Jacobs
    Jonathan Lange
    Jonathan D. Simms
    Jürgen Hermann
    Julian Berman
    Kevin Horn
    Kevin Turner
    Laurens Van Houtven
    Mary Gardiner
    Matthew Lefkowitz
    Massachusetts Institute of Technology
    Moshe Zadka
    Paul Swartz
    Pavel Pergamenshchik
    Ralph Meijer
    Richard Wall
    Sean Riley
    Software Freedom Conservancy
    Travis B. Hartwell
    Thijs Triemstra
    Thomas Herve
    Timothy Allen
    Tom Prince

    Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
    documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
    rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
    permit persons to whom the Software is furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
    Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
    WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
    OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
    OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
    """
    prefix = ''
    trailing = []
    if not s:
        # Raise an exception of some kind
        pass
    if s[0] == ':':
        prefix, s = s[1:].split(' ', 1)
    if s.find(' :') != -1:
        s, trailing = s.split(' :', 1)
        args = s.split()
        args.append(trailing)
    else:
        args = s.split()
    command = args.pop(0)
    return prefix, command, args


def parse_identity(who):
    """ Extract the parts out of an IRC user identifier string. """
    nick, rest = who.split('!')
    username, host = rest.split('@')

    if username.startswith('~'):
        username = username[1:]

    return nick, username, host


def get_symbolic_command(command):
    """ Normalizes both numeric and symbolic commands into just symbolic commands. """
    if command.isdecimal():
        try:
            return numeric_to_symbolic[command]
        except KeyError as e:
            raise UnknownNumericCommandError("No numeric command found: '{}'".format(command)) from e
    else:
        return command


def decode(line):
    """ Attempts to decode the line with utf8 but falls back to chardet otherwise. """
    try:
        line = str(line, encoding='utf8')
    except UnicodeDecodeError:
        logger.debug('UTF8 decode failed, bytes: %s', line)
        encoding = chardet.detect(line)['encoding']
        logger.debug('Tried autodetecting and got %s, decoding now', encoding)
        line = str(line, encoding=encoding)
    except TypeError as e:
        if e.args[0] != 'decoding str is not supported':
            raise
    return line


def parse_line(line):
    """ Normalizes the line from the server and splits it into component parts. """
    line = decode(line)
    line = line.strip()
    return split_irc_line(line)


class IRCServerHandler:
    def __init__(self, identity):
        """ Protocol parser (and response generator) for an IRC server.

        Args:
            identity (User object): "Our" nick and user name etc.
        """
        self._write = None
        self.identity = identity

        # Default values
        self.motd = ''

        self.callbacks = collections.defaultdict(set)

    # =========================================================================
    # Parsing and "reading"
    # ---------------------
    #
    # Methods that result from a new input from the IRC server.
    # =========================================================================
    def handle_line(self, line):
        # Parse the line
        prefix, command, args = parse_line(line)

        try:
            symbolic_command = get_symbolic_command(command)
        except UnknownNumericCommandError:
            self.log_unhandled(command, prefix, args)
            return

        # local callbacks maintain the state of the model and deal with the protocol stuff
        try:
            handler_name = 'on_{}'.format(symbolic_command.lower())
            handler = getattr(self, handler_name)
        except AttributeError:
            self.log_unhandled(symbolic_command, prefix, args)
        else:
            handler(prefix, *args)

        # user callbacks do whatever they want them to do
        for callback in set(self.callbacks[symbolic_command.lower()]):
            callback(self, prefix, *args)

    def log_unhandled(self, command, prefix, args):
        """ Called when we encounter a command we either don't know or don't have a handler for. """
        logger.warning('Unhandled Command received: %s with args (%s) from prefix %s', command, args, prefix)
    # =========================================================================

    # =========================================================================
    # Generating and "writing"
    # ------------------------
    #
    # Methods that ultimately call self._write or are used in other methods in
    # this section.
    #
    # TODO: Should public API functions like `who` and `connect` be in here? Is
    #       this an appropriate description for this section?
    # =========================================================================
    @property
    def write_function(self):
        return self._write

    @write_function.setter
    def write_function(self, new_write_function):
        self._write = new_write_function

    def pong(self, value):
        self._write('PONG :{}'.format(value))

    def connect(self):
        self._write('NICK {}'.format(self.identity.nick))
        self._write('USER {} 0 * :{}'.format(self.identity.username, self.identity.real_name))

    def who(self, mask):
        self._write('WHO {}'.format(mask))

    def join(self, channel, password=None):
        logger.debug('Joining %s', channel)
        if password:
            self._write('JOIN {} {}'.format(channel, password))
        else:
            self._write('JOIN {}'.format(channel))

    def _split_line_channel_command(self, command, channel, message):
        if not isinstance(message, (str, bytes)):
            message = str(message)
        for line in message.split('\n'):
            self._write('{} {} :{}'.format(command, channel, line))

    def send_message(self, channel, message):
        self._split_line_channel_command('PRIVMSG', channel, message)

    def send_notice(self, channel, message):
        self._split_line_channel_command('NOTICE', channel, message)
    # =========================================================================

    # =========================================================================
    # Callback API
    # ------------
    #
    # The primary intended mechanism for interacting with this module, a user
    # will instantiate this class then add callbacks where they want.
    #
    # A callback is any old callable, details in the docstring for
    # `add_callback`.
    # =========================================================================
    def add_callback(self, signal, callback):
        """ Attach a function to be called on an IRC command (specified symbolically).

        The function will be called with the following args:
            * The calling IRCServerHandler object
            * The prefix of the command (usually who it's from?)
            * The remaining arguments from the command

        For example the `join` signal will be called with `(self, who, channel)`.
        """
        self.callbacks[signal].add(callback)

    def remove_callback(self, signal, callback):
        self.callbacks[signal].remove(callback)

    def clear_callbacks(self, signal):
        self.callbacks[signal] = set()
    # =========================================================================

    # =========================================================================
    # Default handlers
    # ----------------
    #
    # So far just ping responding. In future might handle protocol negotiation
    # bits like character encoding and the like.
    # =========================================================================
    def on_ping(self, prefix, token, *args):
        logger.debug('Ping received: %s, %s', prefix, token)
        self.pong(token)
    # =========================================================================

symbolic_to_numeric = {
    "RPL_WELCOME": '001',
    "RPL_YOURHOST": '002',
    "RPL_CREATED": '003',
    "RPL_MYINFO": '004',
    "RPL_ISUPPORT": '005',
    "RPL_BOUNCE": '010',
    "RPL_STATSCONN": '250',
    "RPL_LOCALUSERS": '265',
    "RPL_GLOBALUSERS": '266',
    "RPL_USERHOST": '302',
    "RPL_ISON": '303',
    "RPL_AWAY": '301',
    "RPL_UNAWAY": '305',
    "RPL_NOWAWAY": '306',
    "RPL_WHOISUSER": '311',
    "RPL_WHOISSERVER": '312',
    "RPL_WHOISOPERATOR": '313',
    "RPL_WHOISIDLE": '317',
    "RPL_ENDOFWHOIS": '318',
    "RPL_WHOISCHANNELS": '319',
    "RPL_WHOWASUSER": '314',
    "RPL_ENDOFWHOWAS": '369',
    "RPL_LISTSTART": '321',
    "RPL_LIST": '322',
    "RPL_LISTEND": '323',
    "RPL_UNIQOPIS": '325',
    "RPL_CHANNELMODEIS": '324',
    "RPL_NOTOPIC": '331',
    "RPL_TOPIC": '332',
    "RPL_INVITING": '341',
    "RPL_SUMMONING": '342',
    "RPL_INVITELIST": '346',
    "RPL_ENDOFINVITELIST": '347',
    "RPL_EXCEPTLIST": '348',
    "RPL_ENDOFEXCEPTLIST": '349',
    "RPL_VERSION": '351',
    "RPL_WHOREPLY": '352',
    "RPL_ENDOFWHO": '315',
    "RPL_NAMREPLY": '353',
    "RPL_ENDOFNAMES": '366',
    "RPL_LINKS": '364',
    "RPL_ENDOFLINKS": '365',
    "RPL_BANLIST": '367',
    "RPL_ENDOFBANLIST": '368',
    "RPL_INFO": '371',
    "RPL_ENDOFINFO": '374',
    "RPL_MOTDSTART": '375',
    "RPL_MOTD": '372',
    "RPL_ENDOFMOTD": '376',
    "RPL_YOUREOPER": '381',
    "RPL_REHASHING": '382',
    "RPL_YOURESERVICE": '383',
    "RPL_TIME": '391',
    "RPL_USERSSTART": '392',
    "RPL_USERS": '393',
    "RPL_ENDOFUSERS": '394',
    "RPL_NOUSERS": '395',
    "RPL_TRACELINK": '200',
    "RPL_TRACECONNECTING": '201',
    "RPL_TRACEHANDSHAKE": '202',
    "RPL_TRACEUNKNOWN": '203',
    "RPL_TRACEOPERATOR": '204',
    "RPL_TRACEUSER": '205',
    "RPL_TRACESERVER": '206',
    "RPL_TRACESERVICE": '207',
    "RPL_TRACENEWTYPE": '208',
    "RPL_TRACECLASS": '209',
    "RPL_TRACERECONNECT": '210',
    "RPL_TRACELOG": '261',
    "RPL_TRACEEND": '262',
    "RPL_STATSLINKINFO": '211',
    "RPL_STATSCOMMANDS": '212',
    "RPL_ENDOFSTATS": '219',
    "RPL_STATSUPTIME": '242',
    "RPL_STATSOLINE": '243',
    "RPL_UMODEIS": '221',
    "RPL_SERVLIST": '234',
    "RPL_SERVLISTEND": '235',
    "RPL_LUSERCLIENT": '251',
    "RPL_LUSEROP": '252',
    "RPL_LUSERUNKNOWN": '253',
    "RPL_LUSERCHANNELS": '254',
    "RPL_LUSERME": '255',
    "RPL_ADMINME": '256',
    "RPL_ADMINLOC": '257',
    "RPL_ADMINLOC": '258',
    "RPL_ADMINEMAIL": '259',
    "RPL_TRYAGAIN": '263',
    "ERR_NOSUCHNICK": '401',
    "ERR_NOSUCHSERVER": '402',
    "ERR_NOSUCHCHANNEL": '403',
    "ERR_CANNOTSENDTOCHAN": '404',
    "ERR_TOOMANYCHANNELS": '405',
    "ERR_WASNOSUCHNICK": '406',
    "ERR_TOOMANYTARGETS": '407',
    "ERR_NOSUCHSERVICE": '408',
    "ERR_NOORIGIN": '409',
    "ERR_NORECIPIENT": '411',
    "ERR_NOTEXTTOSEND": '412',
    "ERR_NOTOPLEVEL": '413',
    "ERR_WILDTOPLEVEL": '414',
    "ERR_BADMASK": '415',
    "ERR_UNKNOWNCOMMAND": '421',
    "ERR_NOMOTD": '422',
    "ERR_NOADMININFO": '423',
    "ERR_FILEERROR": '424',
    "ERR_NONICKNAMEGIVEN": '431',
    "ERR_ERRONEUSNICKNAME": '432',
    "ERR_NICKNAMEINUSE": '433',
    "ERR_NICKCOLLISION": '436',
    "ERR_UNAVAILRESOURCE": '437',
    "ERR_USERNOTINCHANNEL": '441',
    "ERR_NOTONCHANNEL": '442',
    "ERR_USERONCHANNEL": '443',
    "ERR_NOLOGIN": '444',
    "ERR_SUMMONDISABLED": '445',
    "ERR_USERSDISABLED": '446',
    "ERR_NOTREGISTERED": '451',
    "ERR_NEEDMOREPARAMS": '461',
    "ERR_ALREADYREGISTRED": '462',
    "ERR_NOPERMFORHOST": '463',
    "ERR_PASSWDMISMATCH": '464',
    "ERR_YOUREBANNEDCREEP": '465',
    "ERR_YOUWILLBEBANNED": '466',
    "ERR_KEYSET": '467',
    "ERR_CHANNELISFULL": '471',
    "ERR_UNKNOWNMODE": '472',
    "ERR_INVITEONLYCHAN": '473',
    "ERR_BANNEDFROMCHAN": '474',
    "ERR_BADCHANNELKEY": '475',
    "ERR_BADCHANMASK": '476',
    "ERR_NOCHANMODES": '477',
    "ERR_BANLISTFULL": '478',
    "ERR_NOPRIVILEGES": '481',
    "ERR_CHANOPRIVSNEEDED": '482',
    "ERR_CANTKILLSERVER": '483',
    "ERR_RESTRICTED": '484',
    "ERR_UNIQOPPRIVSNEEDED": '485',
    "ERR_NOOPERHOST": '491',
    "ERR_NOSERVICEHOST": '492',
    "ERR_UMODEUNKNOWNFLAG": '501',
    "ERR_USERSDONTMATCH": '502',
}
numeric_to_symbolic = {v: k for k, v in symbolic_to_numeric.items()}
