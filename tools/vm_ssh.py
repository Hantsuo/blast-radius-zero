"""One-off remote check/fix over SSH for the Vultr demo box.

Password comes from the environment (VULTR_ROOT_PW); it is never written to disk.

    $env:VULTR_ROOT_PW = ...
    python tools/vm_ssh.py "cloud-init status --long; tail -30 /var/log/cloud-init-output.log"
"""
from __future__ import annotations

import os
import sys

import paramiko

HOST = os.getenv("VULTR_HOST", "167.179.96.32")
USER = os.getenv("VULTR_USER", "root")


def main() -> int:
    password = os.getenv("VULTR_ROOT_PW")
    if not password:
        print("VULTR_ROOT_PW is not set", file=sys.stderr)
        return 2
    command = sys.argv[1] if len(sys.argv) > 1 else "uptime"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=password, timeout=20, banner_timeout=20, auth_timeout=20)
    stdin, stdout, stderr = client.exec_command(command, timeout=180)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    print(out)
    if err.strip():
        print("--- stderr ---")
        print(err)
    code = stdout.channel.recv_exit_status()
    client.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
