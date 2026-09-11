#!/usr/bin/env python3
"""Build an independent Subscription Router from a reviewed official desktop bundle."""
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
REVIEWED_BUILDS = {
    VERSION: SOURCE_HASH,
    ("26.908.40834", "8881"): "bb40cd8811887363104a19291346af9595632e0e956316a1086b274fb8e3eafc",
}


def reviewed_source(source: Path) -> tuple[dict, tuple[str, str], str]:
    info = plistlib.loads((source / "Contents/Info.plist").read_bytes())
    version = (str(info["CFBundleShortVersionString"]), str(info["CFBundleVersion"]))
    if version not in REVIEWED_BUILDS:
        raise RuntimeError(f"Unsupported official build {version[0]} ({version[1]}); the working router is unchanged")
    digest = hashlib.sha256((source / "Contents/Resources/app.asar").read_bytes()).hexdigest()
    if digest != REVIEWED_BUILDS[version]:
        raise RuntimeError(f"Official build {version[1]} has an unreviewed ASAR hash; the working router is unchanged")
    return info, version, digest


def verify_official_source(source: Path) -> None:
    legacy.run(['codesign', '--verify', '--deep', '--strict', str(source)])
    signed = subprocess.run(['codesign', '-dv', '--verbose=4', str(source)],
                            check=True, capture_output=True, text=True).stderr
    if 'TeamIdentifier=2DC432GLL2' not in signed or 'Identifier=com.openai.codex\n' not in signed:
        raise RuntimeError('Build input must be the reviewed, signed official OpenAI desktop app')



def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"{label}: expected one reviewed anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def one(root: Path, pattern: str) -> Path:
    found = list(root.glob(pattern))
    if len(found) != 1:
        raise RuntimeError(f"Expected one {pattern}, found {len(found)}")
    return found[0]


def patch_main(extracted: Path, state: Path, primary_home: Path, source_build: str = "8576") -> None:
    build_root = extracted / ".vite/build"
    bootstrap = one(build_root, "bootstrap-*.js")
    updater_path = one(build_root, "window-all-closed-*.js")
    main_path = one(build_root, "main-*.js")
    text = bootstrap.read_text()
    text = replace_once(text,
        "a.app.setPath(`userData`,w({appDataPath:a.app.getPath(`appData`),buildFlavor:Z,env:process.env}))",
        "a.app.setPath(`userData`," + json.dumps(str(state / "desktop")) + ")", "independent desktop state")
    # Preserve the native updater and its feature-policy initialization.
    # Updates may replace the patch; monitoring reports that for manual repair.
    text = replace_once(text, "try{await i.initialize();let{runMainAppStartup:e}",
        "try{await i.initialize();let{runMainAppStartup:e}", "updater launch-policy initialization")
    bindings = {
        "8576": ("r", "S=a.i.shouldIncludeSparkle(c,process.platform,process.env),C=a.i.shouldIncludeUpdater(c,process.platform,process.env)", "S=!1,C=!1"),
        "8881": ("s", "C=a.i.shouldIncludeSparkle(u,process.platform,process.env),w=a.i.shouldIncludeUpdater(u,process.platform,process.env)", "C=!1,w=!1"),
    }
    updater_arg, flags, _ = bindings[source_build]
    updater = replace_once(updater_path.read_text(),
        f"enableUpdater:i.i.shouldIncludeUpdater({updater_arg},process.platform,process.env)",
        f"enableUpdater:i.i.shouldIncludeUpdater({updater_arg},process.platform,process.env)", "native updater capability")
    main = replace_once(main_path.read_text(),
        flags, flags, "native update menu capabilities")
    # Environment is established before imported bootstrap modules can compute paths.
    early = extracted / ".vite/build/early-bootstrap.js"
    env = {"CODEX_HOME": str(primary_home), "CODEX_MUX_HOME": str(state / "router"),
           "CODEX_MUX_CONTROL_PORT": str(PORT), "CODEX_ELECTRON_USER_DATA_PATH": str(state / "desktop")}
    early_text = "Object.assign(process.env," + json.dumps(env) + ");\n" \
        + "process.env.CODEX_CLI_PATH=require('node:path').join(process.resourcesPath,'codex');\n"
    early_text += early.read_text()
    # Validate all reviewed anchors before changing the extracted bundles.
    # The stock updater manager and menu capabilities are intentionally intact.
    bootstrap.write_text(text)
    updater_path.write_text(updater)
    main_path.write_text(main)
    early.write_text(early_text)


def enable_native_updates(info: dict) -> None:
    """Keep publisher verification and the official payload's supported name."""
    if not isinstance(info.get('SUPublicEDKey'), str) or not info['SUPublicEDKey'].strip():
        raise RuntimeError('Official Sparkle public update key is required')
    # SUBundleName is Sparkle's documented host name override. Its installer
    # uses this to find ChatGPT.app in the official signed archive.
    info['SUBundleName'] = 'ChatGPT'
    info['SUEnableAutomaticChecks'] = True


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


def build(args: argparse.Namespace) -> dict | None:
    if args.destination.expanduser().is_symlink():
        raise RuntimeError('Destination must not be a symlink')
    source, destination, state = args.source.expanduser().resolve(), args.destination.expanduser().resolve(), args.state.expanduser().resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise RuntimeError("Source and generated copy must be separate bundles")
    info, version, digest = reviewed_source(source)
    verify_official_source(source)
    if destination.exists() and not args.check_only:
        raise RuntimeError('Existing app bundles are updated through scripts/update_router.py; they are never overwritten by the builder')
    record_build = getattr(args, 'record_build', True)
    if record_build:
        state_import(state, args.codex_home.expanduser().resolve(),
            args.import_state.expanduser().resolve() if args.import_state else None, args.controller_account)
    elif not (state / 'router/state.json').is_file():
        raise RuntimeError('Prepare requires an existing router installation; use install for first setup')
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
        # Patch a verified snapshot; an official update during this build must
        # never mix files from two desktop releases.
        snapshot = temp / "official-source.app"
        legacy.run(['ditto', str(source), str(snapshot)])
        snapshot_info, snapshot_version, snapshot_digest = reviewed_source(snapshot)
        verify_official_source(snapshot)
        if (snapshot_version, snapshot_digest) != (version, digest):
            raise RuntimeError('Official source changed during snapshot; retry without replacing the working app')
        source, info = snapshot, snapshot_info
        source_asar = snapshot / "Contents/Resources/app.asar"
        extracted = temp / "extracted"
        legacy.run([str(asar), "extract", str(source_asar), str(extracted)])
        before = {path: path.stat().st_mtime_ns for path in extracted.rglob('*.js')}
        if version[1] == '8576':
            patch_renderer_8576(extracted, token, PORT)
            patch_settings_8576(extracted, token, PORT)
        else:
            from patch_renderer_8881 import patch_renderer_8881
            from patch_settings_8881 import patch_settings_8881
            patch_renderer_8881(extracted, token, PORT)
            patch_settings_8881(extracted, token, PORT)
        patch_main(extracted, state, args.codex_home.expanduser().resolve(), version[1])
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
        enable_native_updates(info)
        info['ElectronAsarIntegrity']={'Resources/app.asar':{'algorithm':'SHA256','hash':asar_header_hash(resources/'app.asar')}}
        (staged/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        # Re-sign changed Electron bundles; embedded vendor services retain their
        # original signatures and authentication checks.
        legacy.sign_runtime_executable(resources/'codex',identity,runtime=False)
        legacy.sign_runtime_executable(staged/'Contents/MacOS/ChatGPT',identity,
            identifier=BUNDLE_ID+'.runtime',runtime=False)
        frameworks=staged/'Contents/Frameworks'
        # Sparkle's standalone installer is not a nested bundle and must be
        # signed explicitly before its enclosing framework.
        legacy.sign_runtime_executable(frameworks/'Sparkle.framework/Versions/B/Autoupdate',identity,runtime=True)
        bundles={p.resolve() for p in frameworks.rglob('*') if p.suffix in ('.app','.framework','.xpc') and p.is_dir()}
        for bundle in sorted(bundles,key=lambda p:len(p.parts),reverse=True):
            legacy.sign_runtime_bundle(bundle,identity,runtime=identity!='-' or 'Sparkle.framework' in bundle.parts)
        legacy.sign_runtime_bundle(staged,identity,identifier=BUNDLE_ID,runtime=False)
        legacy.run(['codesign','--verify','--deep','--strict',str(staged)])
        # A candidate is immutable once built. The activation manager handles
        # replacing a previous app only after checking that it has stopped.
        if destination.exists():
            raise RuntimeError('Candidate destination appeared during build; refusing replacement')
        staged.rename(destination)
    report={'app':str(destination),'sourceVersion':version[0],'sourceBuild':version[1],
        'sourceAsarSha256':digest,'signing':'ad-hoc' if identity=='-' else 'certificate',
        'state':str(state),'codexHome':str(args.codex_home.expanduser().resolve()),
        'routerVersion':(ROOT/'VERSION').read_text().strip(),'updatePolicy':'native-updates-notify-only',
        'builtAt':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    if record_build:
        seed_state(state,args.codex_home.expanduser().resolve(),args.import_state.expanduser().resolve() if args.import_state else None,args.controller_account)
        (state/'build.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return report


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
