#!/usr/bin/python3

"""Script to perform a variety of maintenance operations on an
IMAP account as specified in a supplied configuration file."""

# ========================================================
# Copyright Jody M Sankey 2017-2026
# ========================================================
# AppliesTo: linux
# AppliesTo: server
# RemoveExtension: True
# PublicPermissions: True
# ========================================================

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
        description="Perform a variety of maintenance operations on IMAP accounts",
        epilog="Copyright Jody Sankey 2017",
    )
    parser.add_argument(
        "-d", "--dry_run", action="store_true", help="Don't make any actual changes on the server"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Don't output the usual summary of each operation",
    )
    group.add_argument("-v", "--verbose", action="store_true", help="List individual messages")
    parser.add_argument(
        "config_file",
        type=argparse.FileType("r"),
        nargs=1,
        help="Configuration file containing account and operation definitions",
    )
    return parser


class Logger:
    """Writes to terminal handling colors and quietness."""

    def fine(self, text):
        """Logs text at the FINE log level."""
        if not FLAGS.quiet:
            Logger._write_colored_line(34, text)  # Blue

    def info(self, text):
        """Logs text at the INFO log level."""
        if not FLAGS.quiet:
            Logger._write_colored_line(32, text)  # Green

    def warn(self, text):
        """Logs text at the WARN log level."""
        Logger._write_colored_line(33, text)  # Yellow

    def error(self, text):
        """Logs text at the ERROR log level."""
        Logger._write_colored_line(31, text)  # Red

    @staticmethod
    def _write_colored_line(color_number, text):
        if sys.stdout.isatty():
            print(f"\033[1;{color_number}m{text}\033[1;m")
        else:
            print(text)


FLAGS = create_parser().parse_args()
LOGGER = Logger()


class Account:
    """Encapsulates an IMAP account and operations against it."""

    def __init__(self, json_account):
        """Constructs a new account from the supplied json, validating input as required."""
        self.hostname = json_account["hostname"]
        self.port = int(json_account["port"])
        self.user = json_account["user"]
        with open(os.path.expanduser(json_account["password_file"]), encoding="utf-8") as f:
            self.password = f.readline().rstrip()
        self.operations = [Operation(op_json) for op_json in json_account["operations"]]
        self.connection = None

    def open(self):
        """Opens an IMAP connection to this specified account."""
        assert self.connection is None
        self.connection = imaplib.IMAP4_SSL(self.hostname, self.port)
        LOGGER.info(f"Opened connection to {self.hostname}:{self.port}")
        self.connection.login(self.user, self.password)
        if FLAGS.verbose:
            stat, resp = self.connection.list()
            mailbox_count = len(resp) if stat == "OK" else "N/K"
            print(f"authenticated as {self.user}, total {mailbox_count} mailboxes")

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
        LOGGER.info(f"Closed connection to {self.hostname}")


class Operation:
    """Encapsulates an operation on an IMAP account."""

    # Trailing commas are important to keep everything tuples
    _ACTIONS = {
        "MOVE": (
            (
                imaplib.IMAP4_SSL.uid,
                "COPY",
                "<UID>",
                "<DEST>",
            ),
            (
                imaplib.IMAP4_SSL.uid,
                "STORE",
                "<UID>",
                "+FLAGS.SILENT",
                r"(\Deleted)",
            ),
            (imaplib.IMAP4_SSL.expunge,),
        ),
        "MOVE_MARK_READ": (
            (
                imaplib.IMAP4_SSL.uid,
                "STORE",
                "<UID>",
                "+FLAGS.SILENT",
                r"(\Seen)",
            ),
            (
                imaplib.IMAP4_SSL.uid,
                "COPY",
                "<UID>",
                "<DEST>",
            ),
            (
                imaplib.IMAP4_SSL.uid,
                "STORE",
                "<UID>",
                "+FLAGS.SILENT",
                r"(\Deleted)",
            ),
            (imaplib.IMAP4_SSL.expunge,),
        ),
        "DELETE": (
            (
                imaplib.IMAP4_SSL.uid,
                "STORE",
                "<UID>",
                "+FLAGS.SILENT",
                r"(\Deleted)",
            ),
            (imaplib.IMAP4_SSL.expunge,),
        ),
        "MARK_READ": (
            (
                imaplib.IMAP4_SSL.uid,
                "STORE",
                "<UID>",
                "+FLAGS.SILENT",
                r"(\Seen)",
            ),
        ),
    }

    def __init__(self, json_op):
        """Constructs a new operation from the supplied json, validating input as required."""
        if json_op["action"] not in Operation._ACTIONS:
            raise KeyError(
                f'Unknown action {json_op["action"]}. Options are {",".join(Operation._ACTIONS)}'
            )
        self.action = json_op["action"]
        self.commands = Operation._ACTIONS[json_op["action"]]
        if "<DEST>" in itertools.chain.from_iterable(self.commands):
            self.dest = json_op["dest"]
            self.path = self.source = json_op["source"]
        else:
            self.dest = None
            self.path = json_op["path"]
        self.query = Operation._query(json_op)

    def execute(self, connection):
        """Performs this operation using a supplied IMAP4 connection, respecting dry run and
        verbose flags."""
        resp = connection.select(self.path)
        if resp[0] != "OK":
            LOGGER.warn(resp[1].decode("utf-8"))
            return

        try:
            stat, resp = connection.uid("SEARCH", self.query)
            if stat != "OK":
                LOGGER.warn(f"Error with SEARCH {self}: {resp.decode('utf-8')}")
                return
            uids = resp[0].decode("utf-8").split()

            if len(uids) == 0:
                LOGGER.fine(f"{self} did not match any messages")
            elif FLAGS.dry_run:
                LOGGER.fine(f"{self} would have impacted {len(uids)} messages")
                if FLAGS.verbose:
                    Operation._print_messages(connection, uids)
            else:
                if FLAGS.verbose:
                    print(f"{self} matched {len(uids)} messages:")
                    Operation._print_messages(connection, uids)
                subs = {"<UID>": ",".join(uids), "<DEST>": self.dest}
                for command in self.commands:
                    args = [(subs[a] if a in subs else a) for a in command[1:]]
                    stat, resp = command[0](connection, *args)
                    if stat != "OK":
                        LOGGER.warn(f"Error executing {self}: {resp}")
                        return
                LOGGER.fine(f"{self} impacted {len(uids)} messages")
        finally:
            connection.close()

    def __str__(self):
        dest = f"->{self.dest}" if self.dest else ""
        return f"({self.action} {self.path}{dest} WHERE {self.query})"

    @staticmethod
    def _query(json_op):
        """Returns an IMAP query string to find messages targeted by an json operation object."""
        components = []
        if "subject" in json_op:
            components.append(f'SUBJECT "{json_op["subject"]}"')
        if "from" in json_op:
            components.append(f'FROM "{json_op["from"]}"')
        if "to" in json_op:
            components.append(f'TO "{json_op["to"]}"')
        if "age_days" in json_op:
            limit_date = date.today() - timedelta(int(json_op["age_days"]))
            components.append("BEFORE " + limit_date.strftime("%d-%b-%Y"))
        if "is_read" in json_op:
            components.append("SEEN" if not bool(json_op["is_read"]) else "UNSEEN")
        return " ".join(components) if components else "ALL"

    @staticmethod
    def _print_messages(connection, uids):
        """Prints a short summary of each message in a set of UIDs."""
        email_parser = email.parser.BytesParser()
        for uid in uids:
            stat, resp = connection.uid("FETCH", uid, "(RFC822.HEADER)")
            if stat != "OK":
                print(f"  Error fetching UID {uid}")
            else:
                e = email_parser.parsebytes(resp[0][1])
                print(f'  {e["Delivery-date"][:16]}   {e["From"]} --> {e["To"]}   "{e["Subject"]}"')


def main():
    """Runs the script using the supplied command line arguments."""
    comment_line = re.compile(r"^\s*#")
    config_lines = (l for l in FLAGS.config_file[0].readlines() if not comment_line.match(l))

    LOGGER.fine("Starting IMAP maintenance at " + datetime.now().strftime("%c"))
    try:
        config_json = json.loads("".join(config_lines))
        accounts = [Account(account) for account in config_json]
    except (KeyError, json.decoder.JSONDecodeError) as e:
        LOGGER.error(f"{type(e).__name__}: {e}")
        sys.exit(1)

    for account in accounts:
        account.open()
        try:
            account.execute()
        except imaplib.IMAP4.error as e:
            LOGGER.error(str(e))
        finally:
            account.close()


if __name__ == "__main__":
    main()
