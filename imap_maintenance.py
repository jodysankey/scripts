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

from abc import ABC, abstractmethod
import argparse
from datetime import date, datetime, timedelta
import email.mime.text
import email.parser
import imaplib
import json
import re
import os
import smtplib
import sys
from typing import Any, Optional


def create_parser() -> argparse.ArgumentParser:
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

    def fine(self, text: str) -> None:
        """Logs text at the FINE log level."""
        if FLAGS.verbose:
            Logger._write_colored_line(34, text)  # Blue

    def info(self, text: str) -> None:
        """Logs text at the INFO log level."""
        if not FLAGS.quiet:
            Logger._write_colored_line(32, text)  # Green

    def warn(self, text: str) -> None:
        """Logs text at the WARN log level."""
        Logger._write_colored_line(33, text)  # Yellow

    def error(self, text: str) -> None:
        """Logs text at the ERROR log level."""
        Logger._write_colored_line(31, text)  # Red

    @staticmethod
    def _write_colored_line(color_number: int, text: str) -> None:
        if sys.stdout.isatty():
            print(f"\033[1;{color_number}m{text}\033[1;m")
        else:
            print(text)


FLAGS = create_parser().parse_args()
LOGGER = Logger()


class SmtpSender:
    """Encapsulates sending using a particular email account."""

    def __init__(self, user: str, password: str, hostname: str, port: int) -> None:
        self.user = user
        self.password = password
        self.hostname = hostname
        self.port = port

    def send(self, to_address: str, subject: str, text: str) -> None:
        """Sends an email via SMTP."""
        smtp = smtplib.SMTP(self.hostname, self.port)
        try:
            smtp.starttls()
            smtp.login(self.user, self.password)
            msg = email.mime.text.MIMEText(text)
            msg["From"] = self.user
            msg["To"] = to_address
            msg["Subject"] = subject
            smtp.sendmail(self.user, to_address, msg.as_string())
        except smtplib.SMTPException as e:
            LOGGER.warn(f"Failed to send email to {to_address}: {e}")
        finally:
            smtp.quit()


class Account:
    """Encapsulates an IMAP account and operations against it."""

    def __init__(self, json_account: dict[str, Any]) -> None:
        """Constructs a new account from the supplied json, validating input as required."""
        self.hostname = json_account["hostname"]
        self.port = int(json_account["port"])
        self.user = json_account["user"]
        with open(os.path.expanduser(json_account["password_file"]), encoding="utf-8") as f:
            self.password = f.readline().rstrip()
        self.sender = SmtpSender(
            self.user,
            self.password,
            json_account["smtp_hostname"],
            int(json_account["smtp_port"]),
        )
        self.alert_address = json_account.get("alert_address")
        self.operations = [Operation(op_json) for op_json in json_account["operations"]]
        self.connection: Optional[imaplib.IMAP4_SSL] = None

    def open(self) -> None:
        """Opens an IMAP connection to this specified account."""
        assert self.connection is None
        self.connection = imaplib.IMAP4_SSL(self.hostname, self.port)
        LOGGER.fine(f"Opened connection to {self.hostname}:{self.port}")
        self.connection.login(self.user, self.password)
        if FLAGS.verbose:
            stat, resp = self.connection.list()
            mailbox_count = len(resp) if stat == "OK" else "N/K"
            print(f"authenticated as {self.user}, total {mailbox_count} mailboxes")

    def execute(self) -> None:
        """Performs all operations, respecting dry run and verbose."""
        assert self.connection is not None
        for operation in self.operations:
            operation.execute(self.connection)

    def close(self) -> None:
        """Cleanly closes an IMAP connection to this specified account."""
        assert self.connection is not None
        self.connection.logout()
        self.connection = None
        LOGGER.fine(f"Closed connection to {self.hostname}")


def _send_alert(connection: imaplib.IMAP4_SSL, uids: list[str], account: Account) -> None:
    """Sends an alert email for each matched message via SMTP."""
    email_parser = email.parser.BytesParser()
    alerts = []
    for uid in uids:
        stat, resp = connection.uid("FETCH", uid, "(RFC822.HEADER)")
        if stat == "OK":
            msg = email_parser.parsebytes(resp[0][1])
            alerts.append((msg["From"], msg["Subject"]))
        else:
            LOGGER.warn(f"Error fetching headers for UID {uid}")
    smtp = smtplib.SMTP(account.smtp_hostname, account.smtp_port)
    try:
        smtp.starttls()
        smtp.login(account.user, account.password)
        for from_addr, subject in alerts:
            alert = email.mime.text.MIMEText(subject or "")
            alert["From"] = account.user
            alert["To"] = account.alert_address
            alert["Subject"] = f"Email from: {from_addr}"
            try:
                smtp.sendmail(account.user, account.alert_address, alert.as_string())
            except smtplib.SMTPException as e:
                LOGGER.warn(f"Failed to send alert for message from {from_addr}: {e}")
    finally:
        smtp.quit()


class OpCmd(ABC):
    """Encapsulates one part of an operation on an IMAP account."""

    @abstractmethod
    def execute(self, connection: imaplib.IMAP4_SSL, uids: list[str], target: str) -> Optional[str]:
        """Runs this command on the supplied UIDs, returning None on success."""
        pass


class StoreOpCmd(OpCmd):
    """Store operation using IMAP4_SSL."""

    def __init__(self, *args: str) -> None:
        self.args = args

    def execute(self, connection: imaplib.IMAP4_SSL, uids: list[str], target: str) -> Optional[str]:
        stat, resp = imaplib.IMAP4_SSL.uid(connection, "STORE", ",".join(uids), *self.args)
        return None if stat == "OK" else resp


class CopyOpCmd(OpCmd):
    """Copy to the target folder using IMAP4_SSL."""

    def execute(self, connection: imaplib.IMAP4_SSL, uids: list[str], target: str) -> Optional[str]:
        stat, resp = imaplib.IMAP4_SSL.uid(connection, "COPY", ",".join(uids), target)
        return None if stat == "OK" else resp


class ExpungeOpCmd(OpCmd):
    """Copy to expunge using IMAP4_SSL."""

    def execute(self, connection: imaplib.IMAP4_SSL, uids: list[str], target: str) -> Optional[str]:
        stat, resp = imaplib.IMAP4_SSL.expunge(connection)
        return None if stat == "OK" else resp


class Operation:
    """Encapsulates an operation on an IMAP account."""

    _ACTIONS: dict[str, tuple[OpCmd, ...]] = {
        "MOVE": (
            CopyOpCmd(),
            StoreOpCmd("+FLAGS.SILENT", r"(\Deleted)"),
            ExpungeOpCmd(),
        ),
        "MOVE_MARK_READ": (
            StoreOpCmd("+FLAGS.SILENT", r"(\Seen)"),
            CopyOpCmd(),
            StoreOpCmd("+FLAGS.SILENT", r"(\Deleted)"),
            ExpungeOpCmd(),
        ),
        "DELETE": (
            StoreOpCmd("+FLAGS.SILENT", r"(\Deleted)"),
            ExpungeOpCmd(),
        ),
        "MARK_READ": (StoreOpCmd("+FLAGS.SILENT", r"(\Seen)"),),
    }

    def __init__(self, json_op: dict[str, Any]) -> None:
        """Constructs a new operation from the supplied json, validating input as required."""
        if json_op["action"] not in Operation._ACTIONS:
            raise KeyError(
                f'Unknown action {json_op["action"]}. Options are {",".join(Operation._ACTIONS)}'
            )
        self.action = json_op["action"]
        self.commands = Operation._ACTIONS[json_op["action"]]
        if any(isinstance(cmd, CopyOpCmd) for cmd in self.commands):
            self.dest: Optional[str] = json_op["dest"]
            self.path = json_op["source"]
        else:
            self.dest = None
            self.path = json_op["path"]
        self.query = Operation._query(json_op)

    def execute(self, connection: imaplib.IMAP4_SSL) -> None:
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
                LOGGER.info(f"{self} would have impacted {len(uids)} messages")
                if FLAGS.verbose:
                    Operation._print_messages(connection, uids)
            else:
                if FLAGS.verbose:
                    print(f"{self} matched {len(uids)} messages:")
                    Operation._print_messages(connection, uids)
                for command in self.commands:
                    err = command.execute(connection, uids, self.dest)
                    if err is not None:
                        LOGGER.warn(f"Error executing {self}: {err}")
                        return
                LOGGER.info(f"{self} impacted {len(uids)} messages")
        finally:
            connection.close()

    def __str__(self) -> str:
        dest = f"->{self.dest}" if self.dest else ""
        return f"({self.action} {self.path}{dest} WHERE {self.query})"

    @staticmethod
    def _query(json_op: dict[str, Any]) -> str:
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
    def _print_messages(connection: imaplib.IMAP4_SSL, uids: list[str]) -> None:
        """Prints a short summary of each message in a set of UIDs."""
        email_parser = email.parser.BytesParser()
        for uid in uids:
            stat, resp = connection.uid("FETCH", uid, "(RFC822.HEADER)")
            if stat != "OK":
                print(f"  Error fetching UID {uid}")
            else:
                e = email_parser.parsebytes(resp[0][1])
                print(f'  {e["Delivery-date"][:16]}   {e["From"]} --> {e["To"]}   "{e["Subject"]}"')


def main() -> None:
    """Runs the script using the supplied command line arguments."""
    comment_line = re.compile(r"^\s*#")
    config_lines = (l for l in FLAGS.config_file[0].readlines() if not comment_line.match(l))

    LOGGER.info("Starting IMAP maintenance at " + datetime.now().isoformat(timespec="seconds"))
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
