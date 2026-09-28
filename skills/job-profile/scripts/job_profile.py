#!/usr/bin/env python3
"""Draft, validate and save a profile in the user's workspace; no network calls."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys

_shared = Path(__file__).resolve().parents[3] / 'scripts'
_spec = importlib.util.spec_from_file_location('fingjob_profile_data', _shared / 'profile_data.py')
profile_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(profile_data)
_spec = importlib.util.spec_from_file_location('fingjob_file_store', _shared / 'file_store.py')
file_store = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(file_store)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    draft = commands.add_parser('draft', help='生成内部JSON草稿；不代表用户已确认')
    draft.add_argument('--role', action='append', required=True)
    draft.add_argument('--name')
    draft.add_argument('--output', required=True)
    create = commands.add_parser('create', help='将已确认画像保存为Markdown；同名自动编号')
    create.add_argument('--input', required=True)
    create.add_argument('--workspace', default=None)
    check = commands.add_parser('check', help='读取并检查Markdown或JSON画像')
    check.add_argument('--input', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'draft':
            profile = profile_data.defaults(args.role)
            if args.name:
                profile['name'] = args.name
            profile_data.validate_profile(profile)
            file_store.save(args.output, profile, replace=False)
            print(f'Draft: {Path(args.output).resolve()}')
            return 0
        profile = profile_data.load(args.input)
        profile_data.validate_profile(profile)
        if args.command == 'check':
            print(f'Valid profile: {profile["name"]}')
        else:
            workspace = Path(args.workspace) if args.workspace else Path.cwd()
            print(f'Profile: {profile_data.save_new(profile, workspace)}')
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
