"""Check package-local links, metadata and presets; no network or user files."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(root=ROOT):
    errors = []
    manifests = [json.loads((root / folder / 'plugin.json').read_text(encoding='utf-8'))
                 for folder in ('.codex-plugin', '.claude-plugin')]
    if len({m['version'] for m in manifests}) != 1 or any(m['name'] != 'findjob' for m in manifests):
        errors.append('Plugin name/version differs across hosts')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?', manifests[0]['version']):
        errors.append('Invalid semantic version')
    allowed = {'README.md', 'LICENSE', 'requirements-dev.txt', '.gitignore', '.gitattributes'}
    folders = {'skills', 'scripts', 'tests', 'docs', '.github', '.agents', '.codex-plugin', '.claude-plugin'}
    documents = [root / 'README.md', *(root / 'skills').rglob('*.md'), *(root / 'docs').rglob('*.md')]
    for path in documents:
        content = re.sub(r'```.*?```|~~~.*?~~~', '', path.read_text(encoding='utf-8'), flags=re.S)
        for raw in re.findall(r'\]\(([^)]+)\)', content):
            address = raw.strip().strip('<>')
            parts = urlsplit(address)
            if parts.scheme or parts.netloc or not parts.path:
                continue
            target = (path.parent / unquote(parts.path)).resolve()
            if not target.is_relative_to(root):
                errors.append(f'{path.relative_to(root)}: link leaves package: {raw}')
                continue
            relative = target.relative_to(root)
            if not target.exists() or (relative.parts[0] not in folders and relative.as_posix() not in allowed):
                errors.append(f'{path.relative_to(root)}: missing/non-package link: {raw}')
    profile = load_module('release_profiles', root / 'scripts/profile_data.py')
    profile.validate_profile(profile.load(root / 'skills/job-profile/references/example.md'))
    profile.validate_profile(profile.load(root / 'skills/job-search/references/presets/unity-non-game.json'))
    budget = load_module('release_budget', root / 'skills/job-search/scripts/search_budget.py')
    policy = json.loads((root / 'skills/job-search/references/presets/platform-extra.json').read_text(encoding='utf-8'))
    budget.validate({'platform_policy': policy, 'budget': {'queries': 60, 'enrichment_queries': 12}, 'searches': []})
    return {'version': manifests[0]['version'], 'markdown_files': len(documents), 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', action='store_true', help='Also require an explicit LICENSE for public release')
    args = parser.parse_args()
    try:
        result = check()
        if args.release and not (ROOT / 'LICENSE').is_file():
            result['errors'].append('Public release requires an author-selected LICENSE')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result['errors'] else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
