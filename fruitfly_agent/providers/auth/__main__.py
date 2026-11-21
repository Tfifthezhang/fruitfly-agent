"""Explicit account operations for local and headless hosts."""
from __future__ import annotations

import argparse
import getpass
import json
import sys

from fruitfly_agent.core.errors import FatalError

from .stores import configured_store, select_store
from .transfer import deploy, receive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Manage FruitFlyAgent account authorization')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status', help='List registration metadata without renewing credentials')
    storage = commands.add_parser('storage', help='Explicitly select a credential backend')
    storage.add_argument('backend', choices=('file', 'keyring'))
    login = commands.add_parser('login', help='Authorize using a browser on another machine')
    login.add_argument('integration')
    login.add_argument('--account', default='')
    upload = commands.add_parser('deploy', help='Send only the selected account over SSH stdin')
    upload.add_argument('account')
    upload.add_argument('host')
    upload.add_argument('--python', default='python3', help='Remote installed Python executable')
    upload.add_argument('--replace', action='store_true')
    incoming = commands.add_parser('receive', help='Receive a selected registration on stdin')
    incoming.add_argument('--replace', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'storage':
            select_store(args.backend)
        elif args.command == 'status':
            print(json.dumps(configured_store().list()))
        elif args.command == 'deploy':
            deploy(configured_store(), args.account, args.host, python=args.python, replace=args.replace)
            print('Selected account deployed.')
        elif args.command == 'receive':
            from ..connections.registry import builtin_connections
            receive(sys.stdin.buffer, configured_store(),
                    integrations=tuple(item.id for item in builtin_connections().definitions()),
                    replace=args.replace)
        elif args.command == 'login':
            from ..connections.service import ConnectionService
            service = ConnectionService()
            attempt, url, record = service.begin_login(args.integration, args.account)
            try:
                print('Open this URL in your browser. After authorization, paste the complete callback URL here.')
                print(url, flush=True)
                attempt.accept(getpass.getpass('Callback URL (hidden): '))
                service.complete_login(attempt, record)
                print('Account authorization stored.')
            finally:
                attempt.close()
        return 0
    except (ValueError, OSError, RuntimeError, EOFError, FatalError):
        print('Account operation failed. Check the selected account, private storage and SSH access.', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
