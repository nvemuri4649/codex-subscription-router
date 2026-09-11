#!/usr/bin/env python3
"""Build the upstream Subscription Router for reviewed desktop build 8576."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import secrets
import shutil
import struct
import subprocess
import tempfile
import time

import patch_app as legacy
from patch_renderer_8576 import patch_renderer_8576
from patch_settings_8576 import patch_settings_8576

ROOT = Path(__file__).resolve().parent.parent
NAME = "Codex Subscription Router"
BUNDLE_ID = "app.cdxmux.multi"
STATE = Path.home() / "Library/Application Support/Codex Subscription Router"
VERSION = ("26.903.71938", "8576")
SOURCE_HASH = "58fef82480b9064e209b5b2fd934992e8d71515aea8084482369cfeaff1b8ee0"
PORT = 48123


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"{label}: expected one reviewed anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def one(root: Path, pattern: str) -> Path:
    found = list(root.glob(pattern))
    if len(found) != 1:
        raise RuntimeError(f"Expected one {pattern}, found {len(found)}")
    return found[0]


def patch_main(extracted: Path, state: Path, primary_home: Path) -> None:
    bootstrap = one(extracted / ".vite/build", "bootstrap-*.js")
    text = bootstrap.read_text()
    text = replace_once(text,
        "a.app.setPath(`userData`,w({appDataPath:a.app.getPath(`appData`),buildFlavor:Z,env:process.env}))",
        "a.app.setPath(`userData`," + json.dumps(str(state / "desktop")) + ")", "independent desktop state")
    text = replace_once(text, "try{await i.initialize();let{runMainAppStartup:e}",
        "try{let{runMainAppStartup:e}", "copied-app updater startup")
    bootstrap.write_text(text)
    # Environment is established before imported bootstrap modules can compute paths.
    early = extracted / ".vite/build/early-bootstrap.js"
    env = {"CODEX_HOME": str(primary_home), "CODEX_MUX_HOME": str(state / "router"),
           "CODEX_MUX_CONTROL_PORT": str(PORT), "CODEX_ELECTRON_USER_DATA_PATH": str(state / "desktop")}
    early.write_text("Object.assign(process.env," + json.dumps(env) + ");\n"
        + "process.env.CODEX_CLI_PATH=require('node:path').join(process.resourcesPath,'codex');\n"
        + early.read_text())
    # Disable all update entry points, including a later renderer feature sync.
    for path in (extracted / ".vite/build").glob("*.js"):
        text = path.read_text()
        if "async initializeUpdater(" in text:
            text, count = re.subn(r"async initializeUpdater\(([^)]*)\)\{", r"async initializeUpdater(\1){return;", text)
            path.write_text(text)


def state_import(state: Path, source_home: Path, import_state: Path | None = None, controller_account: str | None = None) -> dict | None:
    """Validate metadata before packaging; return None when existing state is kept."""
    path = state / 'router/state.json'
    if path.exists():
        if controller_account:
            existing = json.loads(path.read_text())
            current = next((a for a in existing['accounts'] if a.get('controller')), None)
            if not current or current['id'] != controller_account or not current.get('enabled'):
                raise RuntimeError('Existing router state has a different or disabled primary account; preserve it or explicitly change its controller before rebuilding')
        return None
    if import_state:
        old = json.loads(import_state.read_text())
        if old.get('version') != 1 or not old.get('accounts'):
            raise RuntimeError('Unsupported account metadata import')
        # No credential files are read or copied. Unknown experimental fields are dropped.
        data = {'version': 1, 'accounts': old['accounts'], 'threadOwner': old.get('threadOwner', {})}
    else:
        data = {'version': 1, 'accounts': [{'id': 'primary', 'label': 'Primary', 'codexHome': str(source_home),
            'enabled': True, 'controller': True, 'createdAt': int(time.time())}], 'threadOwner': {}}
    if controller_account:
        selected = next((a for a in data['accounts'] if a['id'] == controller_account), None)
        if not selected or not selected.get('enabled'):
            raise RuntimeError('Requested primary account must exist and be enabled')
        for account in data['accounts']:
            account['controller'] = account['id'] == controller_account
    return data


def seed_state(state: Path, source_home: Path, import_state: Path | None = None, controller_account: str | None = None) -> None:
    """Import routing metadata while keeping every existing credential home in place."""
    data = state_import(state, source_home, import_state, controller_account)
    if data is None:
        return
    path = state / 'router/state.json'
    with path.open('x') as stream:
        json.dump(data, stream, indent=2)
    path.chmod(0o600)


def asar_header_hash(path: Path) -> str:
    with path.open("rb") as stream:
        header = stream.read(16)
        length = struct.unpack("<4I", header)[3]
        return hashlib.sha256(stream.read(length)).hexdigest()


def build(args: argparse.Namespace) -> None:
    source, destination, state = args.source.expanduser().resolve(), args.destination.expanduser().resolve(), args.state.expanduser().resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise RuntimeError("Source and generated copy must be separate bundles")
    source_asar = source / "Contents/Resources/app.asar"
    info = plistlib.loads((source / "Contents/Info.plist").read_bytes())
    version = (info["CFBundleShortVersionString"], info["CFBundleVersion"])
    digest = hashlib.sha256(source_asar.read_bytes()).hexdigest()
    if version != VERSION or digest != SOURCE_HASH:
        raise RuntimeError(f"Unreviewed source build {version}; update compatibility anchors before building")
    if destination.exists() and not args.force:
        raise RuntimeError("Destination exists. Use --force to retain a backup and replace it.")
    state_import(state, args.codex_home.expanduser().resolve(),
        args.import_state.expanduser().resolve() if args.import_state else None, args.controller_account)
    if args.force and not args.check_only:
        legacy.ensure_components_are_stopped((destination,))
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    state.chmod(0o700)
    router = state / "router"
    router.mkdir(mode=0o700, exist_ok=True)
    token_path = router / "control-token"
    if not token_path.exists():
        token_path.write_text(secrets.token_hex(32))
    token_path.chmod(0o600)
    token = token_path.read_text().strip()
    if not re.fullmatch('[0-9a-f]{64}', token):
        raise RuntimeError('Invalid local control token')
    asar = legacy.ensure_asar_tool()
    identity = legacy.resolve_signing_identity(True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".subscription-router-build-", dir=destination.parent) as temporary:
        temp = Path(temporary)
        extracted = temp / "extracted"
        legacy.run([str(asar), "extract", str(source_asar), str(extracted)])
        before = {path: path.stat().st_mtime_ns for path in extracted.rglob('*.js')}
        patch_renderer_8576(extracted, token, PORT)
        patch_settings_8576(extracted, token, PORT)
        patch_main(extracted, state, args.codex_home.expanduser().resolve())
        for path in sorted(path for path in extracted.rglob('*.js') if path.stat().st_mtime_ns != before.get(path)):
            legacy.run(["node", "--check", str(path)])
        if args.check_only:
            print(f"Verified renderer and main-process patch anchors for {version[0]} ({version[1]})")
            return
        staged = temp / destination.name
        legacy.run(["ditto", str(source), str(staged)])
        launcher_source = (ROOT / 'native/launcher.c').read_text().replace('Codex Subscription Router', NAME)
        launcher_source = replace_once(launcher_source,
            '"--user-data-dir=%s/Library/Application Support/Codex Subscription Router",\n                 home',
            '"%s", ' + json.dumps('--user-data-dir=' + str(state / 'desktop')), 'independent launcher profile')
        launcher_c = temp / 'launcher.c'
        launcher_c.write_text(launcher_source)
        legacy.run(['xcrun','clang','-arch','arm64','-Os','-Wall','-Wextra','-o',
            str(staged/'Contents/MacOS/CodexSubscriptionRouterLauncher'),str(launcher_c)])
        resources = staged / "Contents/Resources"
        packed = temp / "app.asar"
        legacy.run([str(asar),"pack",str(extracted),str(packed),"--unpack-dir",legacy.ASAR_UNPACK_DIRECTORIES])
        shutil.copy2(packed,resources/'app.asar')
        shutil.rmtree(resources/'app.asar.unpacked')
        shutil.copytree(temp/'app.asar.unpacked',resources/'app.asar.unpacked')
        (resources/'codex').rename(resources/'codex.real')
        legacy.build_proxy(resources/'codex')
        info['CFBundleDisplayName']=info['CFBundleName']=NAME
        info['CFBundleIdentifier']=BUNDLE_ID
        info['CFBundleExecutable']='CodexSubscriptionRouterLauncher'
        info['CrProductDirName']=NAME
        info['CFBundleURLTypes']=[{'CFBundleURLName':NAME,'CFBundleURLSchemes':['codex-subscription-router']}]
        for key in list(info):
            if key.startswith('SU'): del info[key]
        info['SUEnableAutomaticChecks']=False
        info['ElectronAsarIntegrity']={'Resources/app.asar':{'algorithm':'SHA256','hash':asar_header_hash(resources/'app.asar')}}
        (staged/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        # Re-sign changed Electron bundles; embedded vendor services retain their
        # original signatures and authentication checks.
        legacy.sign_runtime_executable(resources/'codex',identity,runtime=False)
        legacy.sign_runtime_executable(staged/'Contents/MacOS/ChatGPT',identity,
            identifier=BUNDLE_ID+'.runtime',runtime=False)
        frameworks=staged/'Contents/Frameworks'
        bundles={p.resolve() for p in frameworks.rglob('*') if p.suffix in ('.app','.framework','.xpc') and p.is_dir()}
        for bundle in sorted(bundles,key=lambda p:len(p.parts),reverse=True):
            legacy.sign_runtime_bundle(bundle,identity,runtime=identity!='-')
        legacy.sign_runtime_bundle(staged,identity,identifier=BUNDLE_ID,runtime=False)
        legacy.run(['codesign','--verify','--deep','--strict',str(staged)])
        if destination.exists():
            backup=state/'backups'/time.strftime('%Y%m%d-%H%M%S')/destination.name
            backup.parent.mkdir(parents=True)
            destination.rename(backup)
        try:
            staged.rename(destination)
        except OSError:
            if not destination.exists() and 'backup' in locals() and backup.exists():
                backup.rename(destination)
            raise
    seed_state(state,args.codex_home.expanduser().resolve(),args.import_state.expanduser().resolve() if args.import_state else None,args.controller_account)
    report={'app':str(destination),'sourceVersion':version[0],'sourceBuild':version[1],'sourceAsarSha256':digest,'signing':'ad-hoc' if identity=='-' else 'certificate','state':str(state),'builtAt':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    (state/'build.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('/Applications/ChatGPT.app'))
    parser.add_argument('--destination',type=Path,default=Path.home()/'Applications'/f'{NAME}.app')
    parser.add_argument('--state',type=Path,default=STATE)
    parser.add_argument('--codex-home',type=Path,default=Path.home()/'.codex')
    parser.add_argument('--import-state',type=Path,help='Import existing account metadata without copying credentials')
    parser.add_argument('--controller-account',help='Existing account ID for normal ChatGPT chats; selected only on first import')
    parser.add_argument('--force',action='store_true')
    parser.add_argument('--check-only',action='store_true')
    build(parser.parse_args())
