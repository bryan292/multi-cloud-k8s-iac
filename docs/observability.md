# Platform observability acceptance

The platform GitOps repository owns monitoring, Loki, Alloy, OpenCost, dashboards and
Prometheus rules. The shared AWS/Azure implementation is in the isolated
[`codex/spec008-observability` branch](https://github.com/bryan292/helm-umbrella-charts/tree/codex/spec008-observability).
Deployment uses the full reviewed commit in `platform.commit`, never a mutable branch ref.
Keep this branch, or another durable reference containing the commit, while clusters use it.
See its [operational guide](https://github.com/bryan292/helm-umbrella-charts/blob/codex/spec008-observability/docs/observability.md)
for SLI definitions, retention, cost-estimate limitations, access and rollback.

After a reviewed `kube_resources` apply and Flux reconciliation, run the read-only checks:

```sh
python3 scripts/verify-observability.py --config config.yaml
```

It verifies private services, Flux resource/controller metrics, evaluated rules, node cost
estimates, Loki queries and Grafana dashboard provisioning. It uses the isolated target's
kubeconfig and checks the cloud account; all HTTP access goes through loopback-only Kubernetes
port-forwards. Grafana credentials are read from the existing Secret in memory and are never
printed. The script closes its own port-forwards on success or failure.

To additionally test alert firing and recovery:

```sh
python3 scripts/verify-observability.py --config config.yaml --exercise
```

This explicitly creates a dedicated `observability-acceptance` Flux Kustomization with a
missing source path. After the real alert reaches Prometheus and Alertmanager, it restores
the empty `applications/dev` path and waits for resolution. It refuses a probe owned by
another manager or an Alertmanager with external receivers, and restores the probe path
in a `finally` block if the exercise fails. The healthy probe remains; no infrastructure,
PVC, namespace or user workload is deleted.

The availability target is platform reconciliation at 99.9% over 30 days. New/size-truncated
history is partial; a healthy instantaneous check does not establish 30 days of SLO
compliance. OpenCost reports estimates, not invoices. Logs use single-instance dev storage
with bounded retention; production HA and recovery remain separate work. The current null
Alertmanager receiver provides API/UI visibility without notifying a person; external
notification delivery requires a destination selected by the owner.

Acceptance passed in the retained EKS and AKS clusters using commit
`e6771d2569a313e53b259e043ff028c965464313`: all telemetry checks, real alert firing,
Alertmanager reception, probe restoration and resolution passed. Seven subsequent
deployment-stage plans returned zero changes. Both healthy probes and all storage remain.
