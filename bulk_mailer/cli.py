#!/usr/bin/env python

import argparse
import sys
import traceback

from . import __version__ as bulk_mailer_version
from .bulk_mailer import BulkMailer
from .log import Log

# raise error when running with Python2
if not sys.version_info[:2] >= (3, 0):
    raise SystemExit("ERROR: Templer requires a Python3 runtime! Your current Python version is: {}".format("".join(
        sys.version.splitlines())))


def main():
    # parse arguments
    parser = argparse.ArgumentParser(
        prog="docker-compose-templer",
        description="Render Docker Compose file templates with the power of Jinja2",
        add_help=False,
    )

    parser.add_argument(
        "--help",
        action="help",
        help="Show this help message and exit",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"Bulk Mailer v{bulk_mailer_version}",
        help="Print the program version and quit",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="count",
        default=0,
        help="Enable verbose mode",
    )
    parser.add_argument(
        "recipients_list",
        nargs='+',
        default=[],
        help=
        "Filename of the report(s). More infos in the example section below. Example: '${Y}-${M}-${D}_${site_name}.csv'"
    )

    smtp_parser = parser.add_argument_group(title="connection arguments")
    smtp_parser.add_argument(
        "-h",
        "--smtp-host",
        dest="smtp_host",
        type=str,
        help="",
    )
    smtp_parser.add_argument(
        "-o",
        "--smtp-port",
        dest="smtp_port",
        type=int,
        default=465,
        help="",
    )
    smtp_parser.add_argument(
        "-u",
        "--smtp-username",
        dest="smtp_username",
        type=str,
        help="",
    )
    smtp_parser.add_argument(
        "-p",
        "--smtp-password",
        dest="smtp_password",
        type=str,
        help="",
    )
    smtp_parser.add_argument(
        "--smtp-nossl",
        dest="smtp_nossl",
        action="store_true",
        default=False,
        help="",
    )
    smtp_parser.add_argument(
        "--smtp-starttls",
        dest="smtp_starttls",
        action="store_true",
        default=False,
        help="",
    )

    sender_parser = parser.add_argument_group(title="mail arguments")
    sender_parser.add_argument(
        "-e",
        "--sender",
        dest="sender",
        type=str,
        help="",
    )
    sender_parser.add_argument(
        "-s",
        "--subject",
        dest="subject",
        type=str,
        help="",
    )
    sender_parser.add_argument(
        "-l",
        "--html-template",
        dest="html_template",
        type=str,
        help="",
    )
    sender_parser.add_argument(
        "-m",
        "--markdown-template",
        dest="markdown_template",
        type=str,
        help="",
    )
    sender_parser.add_argument(
        "--plaintext-template",
        dest="plaintext_template",
        type=str,
        help="",
    )
    sender_parser.add_argument(
        "--csv-skip-rows",
        dest="csv_skip_rows",
        type=int,
        default=0,
        help="",
    )
    sender_parser.add_argument(
        "--csv-delimiter",
        dest="csv_delimiter",
        type=str,
        default=";",
        help="",
    )
    sender_parser.add_argument(
        "--send-delay",
        dest="delay",
        type=int,
        default=0,
        help="",
    )

    encryption_signature_parser = parser.add_argument_group(title="encryption and signature arguments")
    encryption_signature_parser.add_argument(
        "--gpg-encrypt",
        dest="gpg_encrypt",
        action="store_true",
        default=False,
        help="",
    )
    encryption_signature_parser.add_argument(
        "--gpg-sign",
        dest="gpg_sign",
        action="store_true",
        default=False,
        help="",
    )
    encryption_signature_parser.add_argument(
        "--gpg-key",
        dest="gpg_key",
        type=str,
        help="",
    )
    encryption_signature_parser.add_argument(
        "--gpg-password",
        dest="gpg_password",
        type=str,
        help="",
    )

    test_parser = parser.add_argument_group(title="test arguments")
    test_parser.add_argument(
        "--test-email",
        dest="test_email",
        type=str,
        help="",
    )
    test_parser.add_argument(
        "--test-count",
        dest="test_count",
        type=int,
        default=1,
        help="",
    )
    test_parser.add_argument(
        "-n",
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=False,
        help="",
    )

    args = parser.parse_args(sys.argv[1:])

    # initialize dumb logger
    levels = [Log.ERROR, Log.INFO, Log.DEBUG]
    Log.level = levels[min(len(levels) - 1, args.verbose + 1)]
    if args.dry_run:
        Log.prefix = "(DRY RUN) "

    try:
        # get missing arguments
        if not args.dry_run:
            if args.smtp_host is None:
                args.smtp_host = input("SMTP Host: ")
            if args.smtp_username is None:
                args.smtp_username = input("SMTP Username: ")
            if args.smtp_password is None:
                from getpass import getpass
                args.smtp_password = getpass("SMTP Password (input is hidden): ")

        bulk_mailer = BulkMailer()

        # input and template settings
        for rl in args.recipients_list:
            bulk_mailer.csv_input(rl, args.csv_delimiter, args.csv_skip_rows)
        if args.plaintext_template:
            bulk_mailer.plaintext_template(path=args.plaintext_template)
        if args.markdown_template:
            bulk_mailer.markdown_template(path=args.markdown_template)
        if args.html_template:
            bulk_mailer.html_template(path=args.html_template)

        # SMTP settings
        bulk_mailer.smtp(
            args.smtp_host,
            args.smtp_port,
            args.smtp_username,
            args.smtp_password,
            None if args.smtp_nossl else "starttls" if args.smtp_starttls else "tls",
        )

        # mail settings
        if args.sender:
            bulk_mailer.sender(args.sender)
        if args.subject:
            bulk_mailer.subject(args.subject)

        # GPG settings
        if args.gpg_sign:
            bulk_mailer.gpg_sign(True, args.gpg_key, args.gpg_password)
        if args.gpg_encrypt:
            bulk_mailer.gpg_encrypt(True)

        # test settings
        if args.test_email:
            bulk_mailer.test_mail(args.test_email, args.test_count)
        bulk_mailer.dry_run(args.dry_run)

        # send the mails
        bulk_mailer.send(args.delay)

    except Exception as e:
        # catch errors and print to stderr
        if args.verbose >= 2:
            Log.error(traceback.format_exc())
        else:
            Log.error(str(e))
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
