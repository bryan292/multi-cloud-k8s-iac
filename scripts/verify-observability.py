#!/usr/bin/env python3
"""Verify private platform telemetry; --exercise tests and restores a dedicated Flux probe."""
import argparse
import base64
import contextlib
import json
import os
import re
import select
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

from operations import Operations
from target import cloud_environment, check_identity

ROOT = Path(__file__).resolve().parents[1]


class Observer:
    def __init__(self, config):
        self.operation = Operations(ROOT, config)
        self.env = cloud_environment(self.operation.config)
        self.env['KUBECONFIG'] = str(self.operation.target_dir / 'kubeconfig.yaml')
        self.provider = self.operation.provider

    def report(self, check, **details):
        print(json.dumps({'provider': self.provider, 'check': check, 'passed': True, **details}), flush=True)

    def kube(self, *args, value=None):
        result = subprocess.run(['kubectl', *args], input=json.dumps(value) if value else None,
                                capture_output=True, text=True, env=self.env, timeout=45)
        if result.returncode:
            raise ValueError('Kubernetes request failed; check access and the selected destination')
        return json.loads(result.stdout) if result.stdout.strip() else {}

    @contextlib.contextmanager
    def forward(self, service, port):
        process = subprocess.Popen(['kubectl', '-n', 'monitoring', 'port-forward', '--address=127.0.0.1',
                                    'service/' + service, f'0:{port}'], env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            output = b''
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                readable, _, _ = select.select([process.stdout], [], [], 1)
                if readable:
                    output += os.read(process.stdout.fileno(), 4096)
                    match = re.search(rb'Forwarding from 127\.0\.0\.1:(\d+) ->', output)
                    if match:
                        yield f'http://127.0.0.1:{int(match[1])}'
                        return
                if process.poll() is not None:
                    break
            raise ValueError('Private port-forward did not become ready')
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            process.stdout.close()

    @staticmethod
    def get(url, headers=None):
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(urllib.request.Request(url, headers=headers or {}), timeout=15) as response:
            return json.load(response)

    def query(self, prometheus, expression):
        response = self.get(prometheus + '/api/v1/query?' + urllib.parse.urlencode({'query': expression}))
        if response.get('status') != 'success':
            raise ValueError('Prometheus query failed')
        return response['data']['result']

    def until(self, check, predicate, timeout=360):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                self.report(check)
                return
            time.sleep(10)
        raise ValueError('Timed out waiting for ' + check)

    def exercise(self, prometheus, alertmanager):
        # Never send test notifications to an external receiver without explicit authorization.
        status = self.get(alertmanager + '/api/v2/status')
        config = yaml.safe_load(status['config']['original'])
        if any(any(key not in ('name', 'labels') and value for key, value in receiver.items()) for receiver in config.get('receivers', [])):
            raise ValueError('External Alertmanager receivers are configured; use read-only verification')
        name = 'observability-acceptance'
        manager = 'iac-observability-acceptance'
        existing = self.kube('-n', 'flux-system', 'get', 'kustomization', name, '--ignore-not-found', '-o', 'json')
        if existing and existing['metadata'].get('labels', {}).get('app.kubernetes.io/managed-by') != manager:
            raise ValueError('The acceptance probe belongs to another manager')
        manifest = {'apiVersion': 'kustomize.toolkit.fluxcd.io/v1', 'kind': 'Kustomization',
                    'metadata': {'name': name, 'namespace': 'flux-system', 'labels': {'app.kubernetes.io/managed-by': manager}},
                    'spec': {'interval': '1m', 'retryInterval': '30s', 'timeout': '1m', 'prune': False,
                             'sourceRef': {'kind': 'GitRepository', 'name': 'helm-umbrella-charts'},
                             'path': './acceptance-intentionally-missing-path'}}
        try:
            self.kube('apply', '-f', '-', '-o', 'json', value=manifest)
            self.until('controlled_failure_fires_in_prometheus', lambda: bool(self.query(prometheus,
                'ALERTS{alertname="FluxReconciliationFailure",name="observability-acceptance",alertstate="firing"}')))
            self.until('controlled_failure_reaches_alertmanager', lambda: any(
                a.get('labels', {}).get('alertname') == 'FluxReconciliationFailure' and a['labels'].get('name') == name
                for a in self.get(alertmanager + '/api/v2/alerts')))
        finally:
            # Restore to a known empty, healthy GitOps path; retain the probe resource.
            manifest['spec']['path'] = './applications/dev'
            manifest['metadata']['annotations'] = {'reconcile.fluxcd.io/requestedAt': str(time.time_ns())}
            self.kube('apply', '-f', '-', '-o', 'json', value=manifest)
        def probe_ready():
            probe = self.kube('-n', 'flux-system', 'get', 'kustomization', name, '-o', 'json')
            return any(c.get('type') == 'Ready' and c.get('status') == 'True' and
                       c.get('observedGeneration') == probe['metadata']['generation']
                       for c in probe.get('status', {}).get('conditions', []))
        self.until('probe_restored_ready', probe_ready)
        self.until('controlled_failure_resolves_in_prometheus', lambda: not self.query(prometheus,
            'ALERTS{alertname="FluxReconciliationFailure",name="observability-acceptance",alertstate="firing"}'))
        self.until('controlled_failure_resolves_in_alertmanager', lambda: not any(
            a.get('labels', {}).get('alertname') == 'FluxReconciliationFailure' and a['labels'].get('name') == name
            for a in self.get(alertmanager + '/api/v2/alerts')))
        self.report('probe_retained_healthy_no_external_notifications')

    def verify(self, exercise=False):
        check_identity(self.operation.config, self.env)
        services = self.kube('-n', 'monitoring', 'get', 'services', '-o', 'json')['items']
        assert services and all(s['spec'].get('type', 'ClusterIP') == 'ClusterIP' and not s['spec'].get('externalIPs') for s in services)
        assert not self.kube('-n', 'monitoring', 'get', 'ingresses', '-o', 'json')['items']
        self.report('administrative_services_private')
        with contextlib.ExitStack() as stack:
            prom = stack.enter_context(self.forward('monitoring-kube-prometheus-prometheus', 9090))
            loki = stack.enter_context(self.forward('loki', 3100))
            grafana = stack.enter_context(self.forward('monitoring-grafana', 80))
            am = stack.enter_context(self.forward('monitoring-kube-prometheus-alertmanager', 9093))
            self.until('flux_resource_metrics_present', lambda: len({
                v['metric'].get('kind') for v in self.query(prom, 'gotk_resource_info')
            } & {'Kustomization', 'HelmRelease', 'GitRepository'}) == 3)
            self.until('flux_controllers_scraped', lambda: len(self.query(prom, 'up{pod=~".*-controller-.*"} == 1')) >= 6)
            self.until('platform_reconciliation_healthy', lambda: bool(self.query(prom, 'platform:reconciliation_available:ratio == 1')))
            groups = self.get(prom + '/api/v1/rules')['data']['groups']
            rules = [r for g in groups if g['name'] == 'platform.reconciliation' for r in g['rules']]
            assert len(rules) == 6 and all(r.get('health') == 'ok' for r in rules)
            self.report('platform_rules_evaluate_successfully')
            self.until('node_cost_estimate_available', lambda: bool(self.query(prom, 'node_total_hourly_cost > 0')))
            self.until('flux_logs_queryable', lambda: bool(self.get(loki + '/loki/api/v1/query_range?' + urllib.parse.urlencode({
                'query': '{namespace="flux-system"}', 'limit': 1, 'since': '15m'
            }))['data']['result']))
            secret = self.kube('-n', 'monitoring', 'get', 'secret', 'monitoring-grafana', '-o', 'json')['data']
            credentials = base64.b64decode(secret['admin-user']) + b':' + base64.b64decode(secret['admin-password'])
            headers = {'Authorization': 'Basic ' + base64.b64encode(credentials).decode()}
            dashboard = self.get(grafana + '/api/dashboards/uid/multicloud-platform', headers)
            assert len(dashboard['dashboard']['panels']) == 10
            self.report('grafana_dashboard_provisioned')
            if exercise:
                self.exercise(prom, am)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config.yaml')
    parser.add_argument('--exercise', action='store_true', help='Create a dedicated failure probe, then retain it healthy')
    args = parser.parse_args()
    observer = Observer(args.config)
    with observer.operation.lock():
        observer.verify(args.exercise)


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        message = str(error) if type(error) is ValueError else 'Inspect the last passed check and cluster events; credentials and raw API responses are omitted.'
        print(json.dumps({'event': 'observability_verification_failed', 'message': message}), file=sys.stderr)
        raise SystemExit(1)
