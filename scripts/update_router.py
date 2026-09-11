#!/usr/bin/env python3
"""Prepare reviewed router updates separately; activate only when the app is stopped."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

import build_current as builder


def read_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.is_file() else {}


def save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def installation(args: argparse.Namespace) -> tuple[Path, Path, dict]:
    state = args.state.expanduser().resolve()
    current = read_json(state / 'build.json')
    destination = args.destination or Path(current.get('app', str(Path.home() / 'Applications' / f'{builder.NAME}.app')))
    # Do not resolve a destination symlink: the lifecycle deliberately rejects it.
    destination = destination.expanduser().absolute()
    return state, destination, current


def prepare(args: argparse.Namespace) -> dict:
    state, destination, current = installation(args)
    source = args.source.expanduser().resolve()
    _, version, _ = builder.reviewed_source(source)
    if current and int(version[1]) < int(current['sourceBuild']):
        raise RuntimeError('The source app is older than the installed router. Use a newer reviewed source; rollback is a separate guarded operation.')
    if not current or not destination.is_dir():
        raise RuntimeError('No installed router found; use install for first setup')
    pending_path = state / 'updates/pending.json'
    if pending_path.exists():
        pending = read_json(pending_path)
        raise RuntimeError(f"An update is already prepared at {pending.get('candidate')}; activate it or preserve/remove that pending entry before preparing another")
    candidate = state / 'updates/staging' / uuid.uuid4().hex / destination.name
    report = builder.build(argparse.Namespace(
        source=source, destination=candidate, state=state,
        codex_home=Path(current.get('codexHome', str(args.codex_home.expanduser()))),
        import_state=None, controller_account=None, force=False,
        check_only=False, record_build=False,
    ))
    # This invokes only CLI version output, never an app-server or user task.
    cli_version = subprocess.check_output([str(candidate / 'Contents/Resources/codex'), '--version'], text=True).strip()
    report['codexVersion'] = cli_version
    pending = {'version': 1, 'candidate': str(candidate), 'destination': str(destination), 'report': report}
    save_json(pending_path, pending)
    print(f'Update prepared and verified: {candidate}\nRunning apps and account state were left untouched.')
    return pending


def activate(args: argparse.Namespace) -> dict:
    from update_lifecycle import activate_candidate
    state, destination, _ = installation(args)
    pending_path = state / 'updates/pending.json'
    pending = read_json(pending_path)
    if pending.get('version') != 1:
        raise RuntimeError('No prepared update found; run prepare first')
    if Path(pending['destination']) != destination:
        raise RuntimeError('Prepared update targets a different installation')
    candidate = Path(pending['candidate'])
    expected_root = state / 'updates/staging'
    if candidate.is_symlink() or expected_root not in candidate.resolve().parents:
        raise RuntimeError('Prepared candidate is outside the router staging directory')
    result = activate_candidate(candidate, destination, state, pending['report'])
    pending_path.unlink()
    print(f'Activated: {destination}\nThe previous app is retained for guarded rollback.')
    if args.launch:
        subprocess.run(['open', str(destination)], check=True)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'prepare', 'activate', 'install', 'rollback'])
    parser.add_argument('--source', type=Path, default=Path('/Applications/ChatGPT.app'))
    parser.add_argument('--state', type=Path, default=builder.STATE)
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--codex-home', type=Path, default=Path.home() / '.codex')
    parser.add_argument('--launch', action='store_true', help='Launch after successful activation; never stop a running app')
    args = parser.parse_args(argv)
    try:
        state, destination, current = installation(args)
        if args.action == 'status':
            try:
                _, available, _ = builder.reviewed_source(args.source.expanduser().resolve())
                source_status = {'version': available[0], 'build': available[1], 'supported': True}
            except (RuntimeError, OSError, KeyError, ValueError) as error:
                source_status = {'supported': False, 'reason': str(error)}
            print(json.dumps({'installed': current, 'source': source_status,
                'pending': read_json(state / 'updates/pending.json'),
                'policy': 'Native app updates are allowed. This CLI is only for explicit router rebuilds and repairs.',
                'installedUpdatePolicy': current.get('updatePolicy', 'legacy native updater')}, indent=2))
        elif args.action == 'prepare':
            prepare(args)
        elif args.action == 'activate':
            activate(args)
        elif args.action == 'rollback':
            from update_lifecycle import rollback_last
            rollback_last(destination, state)
            print('Restored the previous app. Account state and history were not reverted.')
            if args.launch:
                subprocess.run(['open', str(destination)], check=True)
        elif not destination.exists():
            if current:
                raise RuntimeError('An installation is recorded but its app is missing; recover it before starting a new install')
            builder.build(argparse.Namespace(source=args.source, destination=destination, state=state,
                codex_home=args.codex_home, import_state=None, controller_account=None,
                force=False, check_only=False, record_build=True))
            if args.launch:
                subprocess.run(['open', str(destination)], check=True)
        else:
            if not (state / 'updates/pending.json').exists():
                prepare(args)
            activate(args)
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f'Router update: {error}', file=sys.stderr)
        print('The updater does not terminate tasks. A prepared update can be activated after quitting the app.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
