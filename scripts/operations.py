"""Plan artifacts, isolated execution, and resumable operations (SPEC-002)."""
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

try:
    from .config import load_config
    from .target import (backend_config, cloud_environment, check_identity, check_backend,
                         check_bootstrap_state, pin_target, pre_plan, read_remote_state)
except ImportError:
    from config import load_config
    from target import (backend_config, cloud_environment, check_identity, check_backend,
                        check_bootstrap_state, pin_target, pre_plan, read_remote_state)


def stages(provider):
    if provider not in ('aws', 'azure'):
        raise ValueError('global.provider: expected aws or azure')
    return (['aws/network', 'aws/eks'] if provider == 'aws' else ['azure/aks']) + ['kubernetes', 'kube_resources']


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def source_digest(root):
    files = {}
    for name in ('scripts', 'schemas', 'infrastructure-modules', 'deployment-config', 'bootstrap'):
        for directory, children, names in os.walk(Path(root) / name):
            children[:] = sorted(child for child in children if not child.startswith('.'))
            for filename in sorted(names):
                path = Path(directory) / filename
                if path.suffix in ('.py', '.tf', '.hcl', '.tpl', '.json') and not filename.endswith(('.tfstate.json', '.tfvars.json')):
                    files[str(path.relative_to(root))] = file_digest(path)
    return digest(files)


def plan_summary(plan):
    result = {'create': 0, 'update': 0, 'delete': 0, 'read': 0}
    for change in plan.get('resource_changes', []):
        for action in change['change']['actions']:
            if action in result:
                result[action] += 1
    return result


def bootstrap_target(root, config):
    if config['global']['provider'] == 'aws':
        a = config['aws']
        return Path(root) / 'bootstrap', {'account_id': a['account_id'], 'region': a['state_region'], 'bucket_name': a['bucket_name']}
    a, state = config['azure'], config['azure']['state']
    return Path(root) / 'bootstrap/azure', {
        'subscription_id': a['subscription_id'], 'tenant_id': a['tenant_id'], 'location': a['location'],
        **state, 'tags': config['global']['common_tags'],
    }


class ToolFailure(ValueError):
    pass


class Runner:
    def run(self, args, cwd, env, log, capture=False, accepted=(0,)):
        fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, 'ab') as stream:
            result = subprocess.run(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE if capture else stream,
                                    stderr=stream if capture else subprocess.STDOUT)
        if result.returncode not in accepted:
            raise ToolFailure('tool execution failed; inspect the private stage log')
        if capture:
            try:
                return result.returncode, json.loads(result.stdout)
            except (ValueError, UnicodeError):
                raise ToolFailure('tool returned invalid JSON; inspect the private stage log') from None
        return result.returncode, None


class Operations:
    def __init__(self, root, config_path, emit=None, runner=None):
        self.root = Path(root).resolve()
        self.config_path = Path(config_path).resolve()
        self.config = load_config(self.config_path)
        self.provider = self.config['global']['provider']
        self.all_stages = stages(self.provider)
        self.config_hash = digest(self.config)
        self.source_hash = source_digest(self.root)
        self.target_hash = digest({stage: backend_config(self.config, stage) for stage in self.all_stages})
        self.base = self.root / '.iac'
        self.base.mkdir(mode=0o700, exist_ok=True)
        os.chmod(self.base, 0o700)
        (self.base / 'targets').mkdir(mode=0o700, exist_ok=True)
        (self.base / 'runs').mkdir(mode=0o700, exist_ok=True)
        self.target_dir = self.base / 'targets' / self.target_hash
        self.target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.emit = emit or (lambda **event: None)
        self.runner = runner or Runner()
        self.run_dir = None
        self.env = None
        self.manifest = None

    @contextlib.contextmanager
    def lock(self):
        fd = os.open(self.target_dir / 'operation.lock', os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(fd, 'w') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('another operation is running for this destination') from None
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def selected(self, requested=None, destroy=False):
        ordered = list(reversed(self.all_stages)) if destroy else self.all_stages
        if not requested:
            return ordered
        if len(set(requested)) != len(requested) or any(stage not in ordered for stage in requested):
            raise ValueError('stage: choose unique stages belonging to the selected provider')
        return [stage for stage in ordered if stage in requested]

    def stable(self):
        if digest(load_config(self.config_path)) != self.config_hash or source_digest(self.root) != self.source_hash:
            raise ValueError('configuration or sources changed; generate a new reviewed plan')
        if self.run_dir and digest(load_config(self.run_dir / 'config.json')) != self.config_hash:
            raise ValueError('configuration snapshot changed; generate a new reviewed plan')

    def prepare(self, bootstrap=False):
        self.stable()
        if bootstrap:
            self.env = cloud_environment(self.config)
            directory, _ = bootstrap_target(self.root, self.config)
            existing = check_bootstrap_state(self.config, directory)
            check_identity(self.config, self.env)
            if existing:
                check_backend(self.config, self.env)
            pin_target(self.config, self.root, ['bootstrap'])
        else:
            self.env = dict(pre_plan(self.config, self.root, self.all_stages))
        self.env.update(IAC_CONFIG=str(self.run_dir / 'config.json'),
                        IAC_KUBECONFIG=str(self.target_dir / 'kubeconfig.yaml'),
                        KUBECONFIG=str(self.target_dir / 'kubeconfig.yaml'),
                        TG_DOWNLOAD_DIR=str(self.target_dir / 'cache'), TF_IN_AUTOMATION='1')

    def start(self, action, selected):
        identifier = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
        self.run_dir = self.base / 'runs' / identifier
        self.run_dir.mkdir(parents=True, mode=0o700)
        atomic_json(self.run_dir / 'config.json', self.config)
        self.manifest = {'version': 1, 'run_id': identifier, 'action': action, 'target': self.target_hash,
                         'config': self.config_hash, 'sources': self.source_hash,
                         'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                         'order': selected, 'stages': {}, 'status': 'running'}
        self.save()
        self.emit(event='run_started', run_id=identifier, action=action, provider=self.provider)

    def save(self):
        atomic_json(self.run_dir / 'manifest.json', self.manifest)

    def load(self, directory, expected_digest=None):
        self.run_dir = Path(directory).resolve()
        path = self.run_dir / 'manifest.json'
        if expected_digest is not None and file_digest(path) != expected_digest:
            raise ValueError('plan digest does not match the reviewed manifest')
        try:
            manifest = json.loads(path.read_text())
            if (not isinstance(manifest, dict) or
                    not isinstance(manifest.get('order'), list) or not manifest['order'] or
                    not all(isinstance(stage, str) for stage in manifest['order']) or
                    not isinstance(manifest.get('stages'), dict) or
                    not all(isinstance(record, dict) for record in manifest['stages'].values())):
                raise ValueError()
            if (manifest['version'] != 1 or manifest['target'] != self.target_hash or
                    manifest['config'] != self.config_hash or manifest['sources'] != self.source_hash):
                raise ValueError()
            action = manifest['action']
            valid = ['bootstrap'] if action == 'bootstrap' else self.selected(manifest['order'], action == 'destroy')
            if action not in ('deploy', 'destroy', 'bootstrap') or valid != manifest['order']:
                raise ValueError()
            if set(manifest['stages']) - set(valid):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise ValueError('manifest is invalid or belongs to another configuration/source/destination') from None
        self.manifest = manifest
        self.stable()

    def call(self, stage, args, capture=False, accepted=(0,)):
        log = self.run_dir / (stage.replace('/', '-') + '.log')
        env = dict(self.env)
        if stage == 'bootstrap':
            directory, values = bootstrap_target(self.root, self.config)
            env.update({f'TF_VAR_{key}': json.dumps(value) if isinstance(value, dict) else str(value) for key, value in values.items()})
            env['TF_DATA_DIR'] = str(self.target_dir / 'bootstrap-data')
            executable = 'terraform'
        else:
            directory = self.root / 'deployment-config' / stage
            executable = 'terragrunt'
        return self.runner.run([executable, *args], directory, env, log, capture=capture, accepted=accepted)

    def dependencies(self, stage):
        if stage in ('bootstrap', 'aws/network', 'azure/aks'):
            return {}
        names = ['aws/network'] if stage == 'aws/eks' else ['aws/eks' if self.provider == 'aws' else 'azure/aks']
        if stage == 'kube_resources':
            names.append('kubernetes')
        return {name: digest(self.call(name, ['output', '-json'], capture=True)[1]) for name in names}

    def make_plan(self, stage, destroy=False):
        self.stable()
        plan_path = self.run_dir / (stage.replace('/', '-') + '.tfplan')
        if stage == 'bootstrap':
            self.call(stage, ['init', '-input=false', '-lockfile=readonly'])
        dependencies = self.dependencies(stage)
        code, _ = self.call(stage, ['plan', '-input=false', '-detailed-exitcode',
                                   *(['-destroy'] if destroy else []), f'-out={plan_path}'], accepted=(0, 2))
        os.chmod(plan_path, 0o600)
        _, plan = self.call(stage, ['show', '-json', str(plan_path)], capture=True)
        record = {'status': 'planned', 'plan': plan_path.name, 'sha256': file_digest(plan_path),
                  'dependencies': dependencies, 'summary': plan_summary(plan), 'exit_code': code}
        self.manifest['stages'][stage] = record
        self.save()
        self.emit(event='planned', stage=stage, changes=record['summary'], exit_code=code)
        return record

    def apply(self, stage):
        self.stable()
        record = self.manifest['stages'][stage]
        expected_name = stage.replace('/', '-') + '.tfplan'
        if record['status'] != 'planned' or record['plan'] != expected_name:
            raise ValueError('plan is not in an applicable state; generate a new plan')
        plan_path = self.run_dir / expected_name
        if plan_path.is_symlink() or file_digest(plan_path) != record['sha256']:
            raise ValueError('saved plan changed; generate a new reviewed plan')
        if self.dependencies(stage) != record['dependencies']:
            raise ValueError('upstream outputs changed; re-plan this stage before applying')
        if stage == 'bootstrap':
            self.call(stage, ['init', '-input=false', '-lockfile=readonly'])
        record['status'] = 'applying'
        self.save()
        self.emit(event='applying', stage=stage)
        self.call(stage, ['apply', '-input=false', str(plan_path)])
        record['status'] = 'completed'
        self.save()
        self.emit(event='completed', stage=stage)

    def execute(self, action, requested=None, plan_only=False, plan_dir=None, plan_digest=None, resume=None, confirm=None):
        if action not in ('deploy', 'destroy', 'bootstrap'):
            raise ValueError('unsupported operation action')
        if plan_digest and not plan_dir:
            raise ValueError('--plan-digest requires --plan-dir; no operation was started')
        if action == 'destroy':
            g = self.config['global']
            expected = f"{self.provider}/{g['environment']}/{g['cluster_name']}"
            if confirm != expected:
                raise ValueError('destroy requires --confirm-destroy provider/environment/cluster_name matching the configuration')
        if plan_dir and (resume or not plan_digest):
            raise ValueError('saved plans require --plan-digest and cannot be combined with --resume')
        if plan_only and (plan_dir or resume):
            raise ValueError('plan-only cannot apply or resume a previous run')
        selected = ['bootstrap'] if action == 'bootstrap' else self.selected(requested, action == 'destroy')
        with self.lock():
            try:
                if plan_dir or resume:
                    self.load(plan_dir or resume, plan_digest if plan_dir else None)
                    if self.manifest['action'] != action or (requested and self.manifest['order'] != selected):
                        raise ValueError('saved operation action/stages differ from this request')
                    selected = self.manifest['order']
                    if plan_dir and any(self.manifest['stages'].get(stage, {}).get('status') != 'planned' for stage in selected):
                        raise ValueError('the reviewed bundle does not contain applicable plans for every stage')
                else:
                    self.start(action, selected)
                self.prepare(action == 'bootstrap')
                for stage in selected:
                    if resume and self.manifest['stages'].get(stage, {}).get('status') == 'completed':
                        if action == 'destroy':
                            state = read_remote_state(self.config, stage, self.env)
                            code = 2 if state.get('resources') or state.get('outputs') else 0
                        else:
                            code, _ = self.call(stage, ['plan', '-input=false', '-detailed-exitcode'], accepted=(0, 2))
                        if code != 0:
                            raise ValueError('completed stage has drift; start a new operation after review')
                        self.emit(event='resume_verified', stage=stage)
                        continue
                    if not plan_dir:
                        self.make_plan(stage, action == 'destroy')
                    if not plan_only:
                        self.apply(stage)
                self.manifest['status'] = 'planned' if plan_only else 'completed'
                self.save()
                self.emit(event='run_completed', status=self.manifest['status'], run_dir=str(self.run_dir),
                          plan_digest=file_digest(self.run_dir / 'manifest.json'))
                return self.run_dir
            except (Exception, KeyboardInterrupt):
                if self.manifest and self.run_dir:
                    self.manifest['status'] = 'failed'
                    self.save()
                raise
