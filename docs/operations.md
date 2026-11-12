# Unified operations

Install `requirements.txt`, authenticate to the selected cloud, and use `scripts/iac.py`.
Global options precede the subcommand: `--config PATH` selects a versioned configuration;
`--json` emits one JSON event per line. `--plan-digest` must always accompany `--plan-dir`; it cannot authorize a newly generated plan. Raw Terraform output stays in private stage logs.

```sh
python3 scripts/iac.py --help
python3 scripts/iac.py --config config.aws.yaml_example --json diagnose --offline
python3 scripts/iac.py --config config.azure.yaml_example --json diagnose --offline
```

Examples contain placeholders: replace identities, administrative CIDRs and the published
umbrella commit before contacting a cloud. Offline diagnostics check configuration and
installed tools; online diagnostics also check identity, backend, cluster identity, API, nodes, Flux, metrics, CSI,
DNS components, certificates, ingress and Kubernetes quotas. See [diagnostics](diagnostics.md)
for read-only guarantees, warnings and the limits of each check.

## Plan and apply

```sh
python3 scripts/iac.py --config config.yaml bootstrap --plan-only
python3 scripts/iac.py --config config.yaml bootstrap --plan-dir RUN_DIR --plan-digest SHA256
python3 scripts/iac.py --config config.yaml deploy
python3 scripts/iac.py --config config.yaml verify
python3 scripts/iac.py --config config.yaml diagnose
```

Copy `RUN_DIR` and `SHA256` from the final planning event after reviewing the private
stage logs. `bootstrap` retains the existing local bootstrap state. Back it up securely.
`deploy` plans and applies each stage sequentially, allowing downstream stages to consume
new upstream outputs. It does not wait for interactive approval: invoking it authorizes
those applies. Use `plan` or `deploy --plan-only` when approval is needed first.

```sh
python3 scripts/iac.py --config config.yaml plan --stage aws/network
python3 scripts/iac.py --config config.yaml deploy --plan-dir RUN_DIR --plan-digest SHA256
```

For Azure's first stage use `--stage azure/aks`. A first deployment cannot plan every
stage before its dependencies exist. Review and apply the foundation, then plan dependent
stages in order. On an established deployment, a multi-stage bundle is possible; if an
upstream apply changes outputs, the old downstream plan is rejected and must be regenerated.

Artifacts bind configuration, source files, upstream output hashes and the binary plan.
Terraform also rejects stale state. Keep the same checkout, absolute run path and installed
tooling when applying a saved plan. A local digest detects accidental changes; it is not a
signature against an attacker able to replace both the plan and its approval digest.

## Isolation and recovery

`.iac/runs/<run-id>/` contains a configuration snapshot, manifest, binary plans and logs.
`.iac/targets/<hash>/` contains a separate cache, kubeconfig and operation lock for each
backend destination. Remote state keys remain unchanged. These directories are ignored by
Git, use private permissions, and may contain sensitive Terraform values. Do not publish
raw plans, snapshots or logs as public CI artifacts.

```sh
python3 scripts/iac.py --config config.yaml deploy --resume RUN_DIR
```

Resume requires unchanged source and configuration, checks completed stages for drift,
and regenerates the plan for any interrupted stage before applying it. Inspect the private
log and cloud state first. A failed apply can have created resources. A failed or interrupted
operation never automatically destroys infrastructure. If completed stages have drift or
source/configuration changed, review a new operation instead of editing the journal.

Export the selected `.iac/targets/<hash>/kubeconfig.yaml` as `KUBECONFIG` for kubectl,
Lens and standalone smoke tests. Also set `IAC_CONFIG` to the absolute selected configuration path for standalone smoke tests. Those tests manage their own temporary test resources;
they are separate from cluster retention.

## Explicit teardown

Only run teardown when the owner authorizes removal. The exact confirmation string is
`global.provider/global.environment/global.cluster_name` from the selected configuration.

```sh
python3 scripts/iac.py --config config.yaml destroy --plan-only --confirm-destroy PROVIDER/ENVIRONMENT/CLUSTER
python3 scripts/iac.py --config config.yaml destroy --plan-dir RUN_DIR --plan-digest SHA256 --confirm-destroy PROVIDER/ENVIRONMENT/CLUSTER
```

Stages run in reverse dependency order; state storage is retained. Remove workload-created
Ingress/LoadBalancer objects while their controllers are still available and inspect retained
disks, snapshots and DNS records. Destroy resume checks emptied remote states for completed
stages, so it does not need to contact a cluster that was already removed.
