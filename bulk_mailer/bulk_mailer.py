import csv
import re
import smtplib
import time
from pathlib import Path
from time import sleep
from typing import Any, List, Set, Union

import frontmatter
import html2text
import jinja2
import mistune
from envelope import Envelope
from envelope.utils import Address, assure_list

from bulk_mailer import jinja_filter
from bulk_mailer.utils import check_file, merge_dicts, read_file

from .email import EMailGenerator
from .log import Log


class BulkMailer:

    #TODO: implement function __str__
    def __str__(self):
        raise NotImplementedError()

    #TODO: implement function __repr__
    def __repr__(self):
        """Print basic representation of the object."""
        raise NotImplementedError()

    def __init__(self):
        self._sender = None
        self._subject = None
        self._smtp = None

        self._csv_input = None
        self._html_template = ""
        self._plaintext_template = ""
        self._markdown_template = ""

        self._gpg_encrypt = False
        self._gpg_key = None
        self._gpg_passphrase = None
        self._gpg_sign = False

        self._test_count = None
        self._test_email_set = None
        self._dry_run = False

    def smtp(self, host="localhost", port=25, user=None, password=None, security=None):
        assert (isinstance(host, str))
        assert (isinstance(port, int) and 0 < port and port < 65535)
        assert (isinstance(user, (str, type(None))))
        assert (isinstance(password, (str, type(None))))
        assert (security is None or (isinstance(security, str) and security in ["tls", "starttls"]))

        self._smtp = dict(host=host, port=port, user=user, password=password, security=security)
        return self

    def sender(self, email=None) -> Union["BulkMailer", Address]:
        assert (isinstance(email, (str, type(None))))

        if email is None:
            return self._sender
        self._sender = Address.parse(email, single=True, allow_false=True)
        return self

    def from_(self, email=None):
        """Alias for `sender`."""
        return self.sender(email)

    def subject(self, subject=None) -> Union["BulkMailer", str]:
        assert (isinstance(subject, (str, type(None))))

        if subject is None:
            return self._subject
        self._subject = subject
        return self

    def csv_input(self, path=None, delimiter=";", skip_rows=0, clear=False):
        assert (isinstance(path, (str, Path, type(None))))
        assert (isinstance(delimiter, str))
        assert (isinstance(skip_rows, int) and skip_rows >= 0)
        assert (isinstance(clear, bool))

        if not self._csv_input or clear:
            self._csv_input = []

        if path is None:
            return self._csv_input
        elif isinstance(path, str):
            path = Path(path)

        csv_cfg = dict(path=path, delimiter=delimiter, skip_rows=skip_rows)
        self._csv_input.append(csv_cfg)
        return self

    def plaintext_template(self, content=None, path=None):
        assert (isinstance(content, (str, type(None))))
        assert (isinstance(path, (str, Path, type(None))))
        assert (not (content is None and path is None))

        if content:
            self._plaintext_template = content
        elif path:
            if isinstance(path, str):
                path = Path(path)
            self._plaintext_template = read_file(path)
        else:
            return self._plaintext_template
        return self

    def markdown_template(self, content=None, path=None):
        assert (isinstance(content, (str, type(None))))
        assert (isinstance(path, (str, Path, type(None))))
        assert (not (content is None and path is None))

        if content:
            self._markdown_template = content
        elif path:
            if isinstance(path, str):
                path = Path(path)
            self._markdown_template = read_file(path)
        else:
            return self._markdown_template
        return self

    def html_template(self, content=None, path=None):
        assert (isinstance(content, (str, type(None))))
        assert (isinstance(path, (str, Path, type(None))))
        assert (not (content is None and path is None))

        if content:
            self._html_template = content
        elif path:
            if isinstance(path, str):
                path = Path(path)
            self._html_template = read_file(path)
        else:
            return self._html_template
        return self

    def gpg_sign(self, sign=True, key=None, passphrase=None):
        assert (isinstance(sign, bool))
        assert (isinstance(key, (str, type(None))))
        assert (isinstance(passphrase, (str, type(None))))

        self._gpg_sign = sign
        self._gpg_key = key
        self._gpg_passphrase = passphrase
        return self

    def gpg_encrypt(self, encrypt=True):
        assert (isinstance(encrypt, bool))

        self._gpg_encrypt = encrypt
        return self

    def dry_run(self, dry_run=True):
        assert (isinstance(dry_run, bool))

        self._dry_run = dry_run
        return self

    def test_mail(self, email=None, count=1, clear=False):
        assert (isinstance(email, (str, list, type(None))))
        assert (isinstance(count, int) and count >= 0)
        assert (isinstance(clear, bool))

        if clear:
            self._email = None

        if email is None:
            return self._test_email_set

        self._test_email_set = self._parse_addresses(email)
        self._test_count = count
        return self

    def send(self, delay=0):
        contexts = self._create_context()

        for i, context in enumerate(contexts):
            envelope = EMailGenerator.generate(
                self._plaintext_template,
                self._markdown_template,
                self._html_template,
                context,
            )
            if self._test_email_set:
                if i < self._test_count:
                    envelope.recipients(clear=True).to(list(self._test_email_set))
                else:
                    return
            self._send_mail(envelope)
            time.sleep(delay)

    @staticmethod
    def _parse_addresses(email_or_list):
        email_set = {a for a in assure_list(email_or_list) if a}
        address_set = set(Address.parse(list(email_set)))
        return address_set

    def _create_context(self) -> dict:
        context = []
        for csv_cfg in self._csv_input:
            check_file(csv_cfg["path"])

            with csv_cfg["path"].open("r") as csv_file:
                csv_reader = csv.reader(csv_file, delimiter=csv_cfg["delimiter"])
                csv_iter = iter(csv_reader)

                try:
                    # skip rows
                    for i in range(csv_cfg["skip_rows"]):
                        next(csv_iter)

                    # parse header
                    header_row = next(csv_iter)
                    header = []
                    for hr in header_row:
                        hr = hr.lower()
                        # create valid identifier by removing invalid combinations
                        hr = re.sub('[^0-9a-zA-Z_]', '_', hr)
                        hr = re.sub('^[^a-zA-Z_]+', '', hr)
                        header.append(hr)

                        if not hr:
                            raise NameError(
                                f"CSV file '{csv_cfg['path']}' is missing a proper header. Make sure none of the headers is empty."
                            )

                    for var_name in ["mail", "e_mail", "email", "to"]:
                        if var_name in header:
                            recipient_email_column = header.index(var_name)
                            break
                    else:
                        raise NameError(f"CSV file '{csv_cfg['path']}' is missing an email column.")

                    # read data rows
                    for csv_row in csv_iter:
                        data = {header[i]: val for i, val in enumerate(csv_row)}
                        if self._sender:
                            data["from"] = str(self._sender)
                            data["sender"] = str(self._sender)
                        if self._subject:
                            data["subject"] = str(self._subject)
                        data["recipient"] = csv_row[recipient_email_column]
                        data["to"] = csv_row[recipient_email_column]

                        context.append(data)

                except StopIteration:
                    pass

        return context

    def _send_mail(self, envelope: Envelope) -> None:
        recipients = self._test_email_set if self._test_email_set else envelope.recipients

        Log.info("Sending email from {} to {}", envelope.from_(), ", ".join(list(envelope.recipients())))
        if Log.level >= Log.DEBUG:
            formatted_mail = "\n".join(["    > " + l for l in envelope.preview().splitlines()])
            Log.debug("Message content:\n" + formatted_mail)

        if not self._dry_run:
            # tls settings
            envelope.smtp(
                host=self._smtp["host"],
                port=self._smtp["port"],
                user=self._smtp["user"],
                password=self._smtp["password"],
                security=self._smtp["security"],
            )

            # sign the email
            if self._gpg_sign:
                envelope.signature(key=self._gpg_key if self._gpg_key else True, passphrase=self._gpg_passphrase)

            # encrypt the email
            if self._gpg_encrypt:
                envelope.encryption()

            # send the email
            try:
                envelope.send()
            except smtplib.SMTPAuthenticationError as err:
                raise Exception(f"Authentication failed: {err.self._error.decode('utf-8')}")
            except smtplib.SMTPServerDisconnected as err:
                raise Exception(f"Server disconnected: {err.self._error.decode('utf-8')}")
            except Exception as e:
                raise e
