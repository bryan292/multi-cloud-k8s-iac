#!/usr/bin/env python3
"""Manage a job-local SSM tunnel without exposing session tokens or killing by stale PID."""
import os
import re
import signal
from pathlib import Path
import socket
import subprocess
import sys
import time


SUPERVISORS = {}

def wait_ready(process, port=8443, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ValueError('SSM tunnel exited before becoming ready; inspect the private tunnel log')
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                return
        except OSError:
            time.sleep(0.5)
    raise ValueError('SSM tunnel did not become ready')


def terminate_remote(log_path, region, required=False):
    identifiers = re.findall(r'Starting session with SessionId: ([A-Za-z0-9][A-Za-z0-9_-]+)', log_path.read_text())
    if not identifiers:
        if required:
            raise ValueError('could not identify the remote SSM session for cleanup')
        return
    result = subprocess.run(['aws', 'ssm', 'terminate-session', '--region', region,
                             '--session-id', identifiers[-1]], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=30)
    if result.returncode:
        raise ValueError('remote SSM session cleanup failed; inspect private session log and terminate it with the tunnel identity')


def serve(directory, instance, document, region):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    control = directory / 'control.sock'
    if control.exists():
        raise ValueError('tunnel control socket already exists')
    # Refuse a pre-existing listener: never accept an unrelated local service as the tunnel.
    probe = socket.socket()
    try:
        probe.bind(('127.0.0.1', 8443))
    finally:
        probe.close()
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(str(control))
    control.chmod(0o600)
    listener.listen(1)
    listener.settimeout(1)
    process = None
    def interrupted(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        with open(directory / 'session.log', 'wb') as log:
            process = subprocess.Popen(['aws', 'ssm', 'start-session', '--region', region,
                                        '--target', instance, '--document-name', document],
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       start_new_session=True)
            wait_ready(process)
            (directory / 'ready').touch(mode=0o600)
            deadline = time.monotonic() + 7200
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    connection, _ = listener.accept()
                except socket.timeout:
                    continue
                with connection:
                    if connection.recv(16) == b'stop':
                        return
    finally:
        cleanup_failed = False
        try:
            terminate_remote(directory / 'session.log', region, required=(directory / 'ready').exists())
        except (ValueError, OSError, subprocess.SubprocessError):
            cleanup_failed = True
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        listener.close()
        if cleanup_failed:
            (directory / 'cleanup_failed').write_text('Remote session cleanup needs attention; inspect session.log')
        control.unlink(missing_ok=True)
        (directory / 'ready').unlink(missing_ok=True)
        if cleanup_failed:
            raise ValueError('remote SSM session cleanup failed')


def start(directory, instance, document, region):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    if any((directory / name).exists() for name in ('control.sock', 'ready', 'cleanup_failed')):
        raise ValueError('a tunnel is already registered or a previous cleanup failure needs attention')
    with open(directory / 'supervisor.log', 'ab') as log:
        child = subprocess.Popen([sys.executable, __file__, 'serve', str(directory), instance, document, region],
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    SUPERVISORS[str(directory)] = child
    deadline = time.monotonic() + 65
    while time.monotonic() < deadline:
        if child.poll() is not None:
            SUPERVISORS.pop(str(directory), None)
            child.wait()
            raise ValueError('tunnel setup failed; inspect private supervisor/session logs')
        if (directory / 'ready').exists():
            return
        time.sleep(0.5)
    stop(directory)
    raise ValueError('tunnel setup timed out')


def stop(directory):
    control = directory / 'control.sock'
    if not control.exists():
        if (directory / 'cleanup_failed').exists():
            raise ValueError('remote SSM session cleanup failed; inspect private session log')
        child = SUPERVISORS.pop(str(directory), None)
        if child:
            child.wait(timeout=15)
        return
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(5)
        try:
            client.connect(str(control))
            client.sendall(b'stop')
        except (ConnectionRefusedError, FileNotFoundError):
            return
    deadline = time.monotonic() + 45
    while control.exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    if control.exists():
        raise ValueError('tunnel supervisor did not finish cleanup')
    child = SUPERVISORS.pop(str(directory), None)
    if child:
        child.wait(timeout=15)
    if (directory / 'cleanup_failed').exists():
        raise ValueError('remote SSM session cleanup failed; inspect private session log')


if __name__ == '__main__':
    os.umask(0o077)
    try:
        command, directory, *values = sys.argv[1:]
        {'start': start, 'serve': serve, 'stop': stop}[command](Path(directory), *values)
    except (ValueError, KeyError, OSError) as exc:
        print(str(exc) if isinstance(exc, ValueError) else 'tunnel operation failed', file=sys.stderr)
        raise SystemExit(1)
