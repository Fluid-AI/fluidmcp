#!/usr/bin/env python3
"""Run the checkout's CLI with a disposable echo server and retain test evidence."""
import json
from importlib.metadata import distributions
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[3]
PORT = int(os.environ.get('PORT', '8099'))
STATE = Path(os.environ.get('TMPDIR', '/tmp')) / f'fluidmcp-local-server-{PORT}'
POINTER = STATE / 'current_run'


def stop():
    if not POINTER.exists():
        print('No recorded run.')
        return
    run_dir = Path(POINTER.read_text().strip())
    run = json.loads((run_dir / 'run.json').read_text())
    try:
        process = psutil.Process(run['pid'])
        # PID alone can refer to an unrelated process after a restart.
        if process.create_time() != run['process_created']:
            raise RuntimeError('Recorded PID was reused; refusing to stop it')
        children = process.children(recursive=True)
        process.terminate()
        _, alive = psutil.wait_procs([process], timeout=10)
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        _, remaining = psutil.wait_procs(alive + children, timeout=5)
        for child in remaining:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(remaining, timeout=5)
    except psutil.NoSuchProcess:
        pass
    (STATE / 'server.pid').unlink(missing_ok=True)
    (STATE / 'token').unlink(missing_ok=True)
    print(f'Stopped. Evidence retained: {run_dir}')


def start():
    # The CLI loads these files with override=True. Refuse hidden overrides of
    # the isolated test environment rather than silently testing another setup.
    for path in (ROOT / '.env', ROOT / 'fluidmcp/cli/.env'):
        if path.exists():
            raise RuntimeError(f'{path} would override test configuration; use a clean worktree')
    with socket.socket() as sock:
        sock.bind(('0.0.0.0', PORT))
    if (STATE / 'server.pid').exists():
        raise RuntimeError('A run is recorded on this port; stop it first')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()
    commit = git('rev-parse', 'HEAD')
    run_dir = STATE / 'runs' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    (run_dir / 'calls').mkdir(parents=True)
    name = 'skill-echo-' + uuid.uuid4().hex[:8]
    config = {'mcpServers': {name: {
        'command': sys.executable,
        'args': [str(ROOT / 'tests_e2e/fake_mcp_server.py'), '--transport', 'http', '--artifacts', str(run_dir)],
        'transport': 'http', 'max_concurrent_requests': 100,
    }}}
    config_path = run_dir / 'config.json'
    config_path.write_text(json.dumps(config, indent=2))
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'SYSTEMROOT') if key in os.environ}
    env.update(PYTHONPATH=str(ROOT), PYTHONUNBUFFERED='1',
               MCP_CLIENT_SERVER_ALL_PORT=str(PORT), MCP_INSTALLATION_DIR=str(run_dir / 'packages'),
               FMCP_SECURE_MODE='false', FMCP_HTTP_PROXY_TIMEOUT='30', FMCP_HTTP_POOL_MAX_CONNECTIONS='200')
    command = [sys.executable, '-c', 'from fluidmcp.cli.cli import main; main()',
               'run', str(config_path), '--file', '--start-server']
    # Like tests_e2e, invoke the source entry function to avoid an installed
    # wheel or the source-layout __main__ import selecting different code.
    with (run_dir / 'server.log').open('w') as log:
        process = subprocess.Popen(command, cwd=run_dir, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
    metadata = dict(branch=git('rev-parse', '--abbrev-ref', 'HEAD'), commit=commit,
                    uncommitted_changes=bool(git('status', '--porcelain')), port=PORT,
                    pid=process.pid, process_created=psutil.Process(process.pid).create_time(),
                    python=sys.executable, dependencies='Explicit interpreter; see dependencies.txt',
                    started_at=datetime.now(timezone.utc).isoformat(), server_name=name)
    (run_dir / 'run.json').write_text(json.dumps(metadata, indent=2))
    POINTER.write_text(str(run_dir))
    (STATE / 'server.pid').write_text(str(process.pid))
    (STATE / 'token').unlink(missing_ok=True)
    try:
        installed = sorted(f'{dist.metadata["Name"]}=={dist.version}' for dist in distributions())
        (run_dir / 'dependencies.txt').write_text('\n'.join(installed) + '\n')
        with httpx.Client(timeout=2, trust_env=False) as client:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f'Gateway exited; see {run_dir}/server.log')
                try:
                    response = client.get(f'http://127.0.0.1:{PORT}/health')
                    if response.status_code == 200 and response.json().get('running_servers') == 1:
                        print(f'BASE_URL=http://127.0.0.1:{PORT}\nRUN_DIR={run_dir}\nSERVER_NAME={name}')
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(.2)
        raise RuntimeError(f'Gateway not ready after 90 seconds; see {run_dir}/server.log')
    except BaseException:
        stop()
        raise


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in ('start', 'stop'):
        sys.exit('Usage: local_server.py start|stop')
    {'start': start, 'stop': stop}[sys.argv[1]]()
