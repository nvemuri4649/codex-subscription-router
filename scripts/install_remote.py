#!/usr/bin/env python3
"""Install an opt-in router beside the official remote Codex executable.

No auth files are copied. The patched app discovers this path automatically;
other Codex clients continue to use the existing official remote executable.
"""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALL_RELATIVE = ".local/share/codex-personal-work"


def ssh(host, script, data=None):
    if host.startswith("-"):
        raise ValueError("SSH host must not start with a dash")
    return subprocess.run(
        ["ssh", "-T", "-o", "BatchMode=yes", host, script],
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def wrapper_script(binary, real_codex, state_root, primary_home, host_id):
    values = {
        "CODEX_MUX_REAL_CODEX": real_codex,
        "CODEX_MUX_HOME": state_root,
        "CODEX_HOME": primary_home,
        "CODEX_MUX_HOST_ID": host_id,
        "CODEX_MUX_REMOTE": "1",
        "CODEX_MUX_NO_CONTROL": "1",
    }
    return "#!/bin/sh\nset -eu\n" + "".join(
        f"export {key}={shlex.quote(value)}\n" for key, value in values.items()
    ) + f"exec {shlex.quote(binary)} \"$@\"\n"


def install_file(host, destination, data, mode):
    temporary = destination + ".new"
    script = (
        "set -eu; umask 077; "
        f"cat > {shlex.quote(temporary)}; "
        f"chmod {mode} {shlex.quote(temporary)}; "
        f"mv -f {shlex.quote(temporary)} {shlex.quote(destination)}"
    )
    ssh(host, script, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="existing SSH alias or user@host")
    parser.add_argument("--host-id", required=True, help="exact native Codex host ID, for example remote-ssh-discovered:crusoe")
    parser.add_argument("--primary-role", choices=["personal", "work"], default="work", help="role of the login already on this remote host")
    parser.add_argument("--default-mode", choices=["casual", "intensive"], default="intensive")
    parser.add_argument("--real-codex", help="absolute existing official Codex executable if not on remote PATH")
    parser.add_argument("--go", default="go", help="local Go executable for cross compilation")
    parser.add_argument("--dry-run", action="store_true", help="read remote platform and print proposed paths without installing")
    args = parser.parse_args()
    if args.host_id == "local" or not args.host_id.strip():
        parser.error("--host-id must identify this remote host, not local")
    probe = ssh(args.host, "uname -s; uname -m; printf '%s\\n' \"$HOME\" \"${CODEX_HOME:-$HOME/.codex}\"; command -v codex || true").decode().splitlines()
    if len(probe) < 4:
        raise RuntimeError("remote platform probe was incomplete")
    system, machine, remote_home, primary_home = probe[:4]
    goos = {"Linux": "linux", "Darwin": "darwin"}.get(system)
    goarch = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64", "amd64": "amd64"}.get(machine)
    if not goos or not goarch:
        raise RuntimeError(f"unsupported remote platform {system}/{machine}")
    real_codex = args.real_codex or (probe[4] if len(probe) > 4 else "")
    if not real_codex.startswith("/"):
        parser.error("official remote codex was not found; pass --real-codex with its absolute path")
    if not remote_home.startswith("/") or not primary_home.startswith("/"):
        raise RuntimeError("remote home paths must be absolute")
    install_root = f"{remote_home}/{INSTALL_RELATIVE}"
    state_root = f"{remote_home}/.codex-pw"
    wrapper = f"{install_root}/codex"
    binary = f"{install_root}/codex-mux"
    if real_codex in (wrapper, binary):
        raise RuntimeError("--real-codex must refer to the official CLI, not this wrapper")
    plan = {"hostId": args.host_id, "platform": f"{goos}/{goarch}", "wrapper": wrapper, "stateRoot": state_root, "officialCodex": real_codex, "existingAccountRole": args.primary_role, "defaultMode": args.default_mode}
    print(json.dumps(plan, indent=2))
    if args.dry_run:
        return
    already_configured = ssh(args.host, f"if test -f {shlex.quote(state_root + '/state.json')}; then printf yes; fi") == b"yes"
    ssh(args.host, f"set -eu; test -x {shlex.quote(real_codex)}; umask 077; mkdir -p {shlex.quote(install_root)} {shlex.quote(state_root)}; chmod 700 {shlex.quote(install_root)} {shlex.quote(state_root)}")
    with tempfile.TemporaryDirectory(prefix="codex-pw-build-") as temporary:
        output = Path(temporary) / "codex-mux"
        environment = {**os.environ, "GOOS": goos, "GOARCH": goarch, "CGO_ENABLED": "0"}
        subprocess.run([args.go, "build", "-trimpath", "-o", str(output), "./cmd/codex-mux"], cwd=PROJECT_ROOT, env=environment, check=True)
        install_file(args.host, binary, output.read_bytes(), "700")
    install_file(args.host, wrapper, wrapper_script(binary, real_codex, state_root, primary_home, args.host_id).encode(), "700")
    if already_configured:
        print("Preserved existing account roles and workflow preferences.")
    else:
        setup = [wrapper, "personal-work", "setup", "--role", args.primary_role, "--default-mode", args.default_mode]
        print(ssh(args.host, shlex.join(setup)).decode(), end="")
    print("Installed. Reconnect this host in Codex Personal & Work.")
    print("To add a separate personal login on this remote host, run:")
    print(shlex.join(["ssh", "-t", args.host, shlex.join([wrapper, "personal-work", "login", "--role", "personal", "--label", "Personal"])]))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode(errors="replace").strip() if isinstance(error.stderr, bytes) else error.stderr
        raise SystemExit(detail or f"Command failed with exit status {error.returncode}") from error
