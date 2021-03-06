#!/usr/bin/python3

"""Script to perform a variety of maintenance operations on an
IMAP account as specified in a supplied configuration file."""

#========================================================
# Copyright Jody M Sankey 2017
#========================================================
# AppliesTo: linux
# AppliesTo: server
# RemoveExtension: True
# PublicPermissions: True
#========================================================

import argparse
from datetime import date, datetime, timedelta
import email.parser
import imaplib
import itertools
import json
import re
import os
import sys


def create_parser():
    """Creates the definition of the expected command line flags."""
    parser = argparse.ArgumentParser(
        description='Perform a variety of maintenance operations on IMAP accounts',
        epilog='Copyright Jody Sankey 2017')
    parser.add_argument('-d', '--dry_run', action='store_true',
                        help="Don't make any actual changes on the server")
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-q', '--quiet', action='store_true',
                       help="Don't output the usual summary of each operation")
    group.add_argument('-v', '--verbose', action='store_true',
                       help="List individual messages")
    parser.add_argument('config_file', type=argparse.FileType('r'), nargs=1,
                        help="Configuration file containing account and operation definitions")
    return parser


class Logger:
    """Writes to terminal handling colors and quietness."""

    def fine(self, text):
        """Logs text at the FINE log level."""
        if not FLAGS.quiet: Logger._write_colored_line(36, text)

    def info(self, text):
        """Logs text at the INFO log level."""
        if not FLAGS.quiet: Logger._write_colored_line(32, text)

    def warn(self, text):
        """Logs text at the WARN log level."""
        Logger._write_colored_line(33, text)

    def error(self, text):
        """Logs text at the ERROR log level."""
        Logger._write_colored_line(31, text)

    @staticmethod
    def _write_colored_line(color_number, text):
        if sys.stdout.isatty():
            print('\033[1;{}m{}\033[1;m'.format(color_number, text))
        else:
            print(text)


FLAGS = create_parser().parse_args()
LOGGER = Logger()


class Account:
    """Encapsulates an IMAP account and operations against it."""

    def __init__(self, json_account):
        """Constructs a new account from the supplied json, validating input as required."""
        self.hostname = json_account['hostname']
        self.port = int(json_account['port'])
        self.user = json_account['user']
        with open(os.path.expanduser(json_account['password_file'])) as f:
            self.password = f.readline().rstrip()
        self.operations = [Operation(op_json) for op_json in json_account['operations']]
        self.connection = None

    def open(self):
        """Opens an IMAP connection to this specified account."""
        assert self.connection is None
        self.connection = imaplib.IMAP4_SSL(self.hostname, self.port)
        LOGGER.info('opened connection to {}:{}'.format(self.hostname, self.port))
        self.connection.login(self.user, self.password)
        if FLAGS.verbose:
            stat, resp = self.connection.list()
            mailbox_count = len(resp) if stat == 'OK' else 'N/K'
            print('authenticated as {}, total {} mailboxes'.format(self.user, mailbox_count))

    def execute(self):
        """Performs all operations, respecting dry run and verbose."""
        assert self.connection is not None
        for operation in self.operations:
            operation.execute(self.connection)

    def close(self):
        """Cleanly closes an IMAP connection to this specified account."""
        assert self.connection is not None
        self.connection.logout()
        self.connection = None
        LOGGER.info('closed connection to {}'.format(self.hostname))


class Operation:
    """Encapsulates an operation on an IMAP account."""

    # Trailing commas are important to keep everything tuples
    _ACTIONS = {
        'MOVE': (
            (imaplib.IMAP4_SSL.uid, 'COPY', '<UID>', '<DEST>', ),
            (imaplib.IMAP4_SSL.uid, 'STORE', '<UID>', '+FLAGS.SILENT', r'(\Deleted)', ),
            (imaplib.IMAP4_SSL.expunge, ),
        ),
        'MOVE_MARK_READ': (
            (imaplib.IMAP4_SSL.uid, 'STORE', '<UID>', '+FLAGS.SILENT', r'(\Seen)', ),
            (imaplib.IMAP4_SSL.uid, 'COPY', '<UID>', '<DEST>', ),
            (imaplib.IMAP4_SSL.uid, 'STORE', '<UID>', '+FLAGS.SILENT', r'(\Deleted)', ),
            (imaplib.IMAP4_SSL.expunge, ),
        ),
        'DELETE': (
            (imaplib.IMAP4_SSL.uid, 'STORE', '<UID>', '+FLAGS.SILENT', r'(\Deleted)', ),
            (imaplib.IMAP4_SSL.expunge, ),
        ),
        'MARK_READ': (
            (imaplib.IMAP4_SSL.uid, 'STORE', '<UID>', '+FLAGS.SILENT', r'(\Seen)', ),
        ),
    }

    def __init__(self, json_op):
        """Constructs a new operation from the supplied json, validating input as required."""
        if json_op['action'] not in Operation._ACTIONS.keys():
            raise KeyError('Unknown action {}. Options are {}'.format(
                json_op['action'], ','.join(Operation._ACTIONS.keys())))
        self.action = json_op['action']
        self.commands = Operation._ACTIONS[json_op['action']]
        if '<DEST>' in itertools.chain.from_iterable(self.commands):
            self.dest = json_op['dest']
            self.path = self.source = json_op['source']
        else:
            self.dest = None
            self.path = json_op['path']
        self.query = Operation._query(json_op)


    def execute(self, connection):
        """Performs this operation using a supplied IMAP4 connection, respecting dry run and
        verbose flags."""
        resp = connection.select(self.path)
        if resp[0] != 'OK':
            LOGGER.warn(resp[1].decode('utf-8'))
            return

        try:
            stat, resp = connection.uid('SEARCH', self.query)
            if stat != 'OK':
                LOGGER.warn('Error with SEARCH {}: {}'.format(self, resp.decode('utf-8')))
                return
            uids = resp[0].decode('utf-8').split()

            if len(uids) == 0:
                LOGGER.fine('{} did not match any messages'.format(self))
            elif FLAGS.dry_run:
                LOGGER.fine('{} would have impacted {} messages'.format(self, len(uids)))
                if FLAGS.verbose:
                    Operation._print_messages(connection, uids)
            else:
                if FLAGS.verbose:
                    print('{} matched {} messages:'.format(self, len(uids)))
                    Operation._print_messages(connection, uids)
                subs = {'<UID>': ','.join(uids), '<DEST>': self.dest}
                for command in self.commands:
                    args = [(subs[a] if a in subs else a) for a in command[1:]]
                    stat, resp = command[0](connection, *args)
                    if stat != 'OK':
                        LOGGER.warn('Error executing {}: {}'.format(self, resp))
                        return
                LOGGER.fine('{} impacted {} messages'.format(self, len(uids)))
        finally:
            connection.close()

    def __str__(self):
        return '({} {} WHERE {})'.format(
            self.action, self.path + ('->' + self.dest if self.dest else ''), self.query)

    @staticmethod
    def _query(json_op):
        """Returns an IMAP query string to find messages targeted by an json operation object."""
        components = []
        if 'subject' in json_op:
            components.append('SUBJECT "{}"'.format(json_op['subject']))
        if 'from' in json_op:
            components.append('FROM "{}"'.format(json_op['from']))
        if 'to' in json_op:
            components.append('TO "{}"'.format(json_op['to']))
        if 'age_days' in json_op:
            limit_date = date.today() - timedelta(int(json_op['age_days']))
            components.append('BEFORE ' + limit_date.strftime('%d-%b-%Y'))
        if 'is_read' in json_op:
            components.append('SEEN' if not bool(json_op['is_read']) else "UNSEEN")
        return ' '.join(components) if components else 'ALL'

    @staticmethod
    def _print_messages(connection, uids):
        """Prints a short summary of each message in a set of UIDs."""
        email_parser = email.parser.BytesParser()
        for uid in uids:
            stat, resp = connection.uid('FETCH', uid, '(RFC822.HEADER)')
            if stat != 'OK':
                print('  Error fetching UID {}'.format(uid))
            else:
                e = email_parser.parsebytes(resp[0][1])
                print('  {}   {} --> {}   "{}"'.format(
                    e['Delivery-date'][:16], e['From'], e['To'], e['Subject']))



def main():
    """Runs the script using the supplied command line arguments."""
    comment_line = re.compile(r"^\s*#")
    config_lines = (l for l in FLAGS.config_file[0].readlines() if not comment_line.match(l))

    LOGGER.fine('Starting IMAP maintenance at ' + datetime.now().strftime('%c'))
    try:
        config_json = json.loads(''.join(config_lines))
        accounts = [Account(account) for account in config_json]
    except (KeyError, json.decoder.JSONDecodeError) as e:
        LOGGER.error('{}: {}'.format(type(e).__name__, str(e)))
        sys.exit(1)

    for account in accounts:
        account.open()
        try:
            account.execute()
        except imaplib.IMAP4.error as e:
            LOGGER.error(str(e))
        finally:
            account.close()


if __name__ == '__main__':
    main()
