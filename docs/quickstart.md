# AWS and Azure quickstart

Use the pinned versions in the repository Dockerfile or install the corresponding host
tools. Azure deployments additionally require Azure CLI and kubelogin on the host.
Install Python dependencies with `python3 -m pip install -r requirements.txt`.

## 1. Select and validate configuration

Copy `config.aws.yaml_example` or `config.azure.yaml_example` into a private file.
Keep `schema_version: 1`; fill the selected provider's identity, state destination,
network and cluster values. Replace administrative CIDRs with your trusted network and
pin a published umbrella commit. Follow the migration section of the README for old YAML.

The following examples validate their structure without cloud credentials:

```sh offline
python3 scripts/preflight.py --offline --config config.aws.yaml_example
python3 scripts/preflight.py --offline --config config.azure.yaml_example
python3 scripts/iac.py --help
python3 scripts/iac.py deploy --help
python3 scripts/iac.py destroy --help
```

## 2. Authenticate

AWS: use the named profile in `aws.profile` and verify it with `aws sts get-caller-identity
--profile YOUR_PROFILE`. Azure: run `az login`, then `az account set --subscription
YOUR_SUBSCRIPTION`. The orchestrator verifies account/tenant and state ownership before
planning. Never paste access tokens into the configuration.

## 3. Create state storage

```sh
python3 scripts/iac.py --config YOUR_CONFIG bootstrap --plan-only
python3 scripts/iac.py --config YOUR_CONFIG bootstrap --plan-dir RUN_DIR --plan-digest SHA256
```

Review the private bootstrap log and use the emitted path/digest. Existing deployments
reuse their backend; do not substitute a new empty destination. Securely back up the local
bootstrap state; cluster state is stored in the configured remote backend.

## 4. Deploy

```sh
python3 scripts/iac.py --config YOUR_CONFIG deploy
python3 scripts/iac.py --config YOUR_CONFIG verify
python3 scripts/iac.py --config YOUR_CONFIG diagnose
```

The deploy command authorizes sequential plan/apply. To require a separate review, follow
[the stage-by-stage plan workflow](operations.md#plan-and-apply). AWS starts with
`aws/network` then `aws/eks`; Azure starts with `azure/aks`. Both finish with `kubernetes`
and `kube_resources`. A failed operation retains all resources for inspection and recovery.

## 5. Connect and check idempotency

Select the kubeconfig under `.iac/targets/<destination-hash>/` for the chosen destination.
Import this file into Lens or set `KUBECONFIG` to its absolute path. AWS exec authentication
requires the configured profile; Azure requires `kubelogin` and the matching Azure CLI login
in the environment used by Lens.

```sh
kubectl get nodes
kubectl -n flux-system get gitrepositories,kustomizations,helmreleases
python3 scripts/iac.py --config YOUR_CONFIG plan
```

A stable deployment should report zero planned changes for every stage. Inspect any drift
before applying. See [runbooks](runbooks.md) for operations, storage and recovery limits.
Destroy only on explicit owner authorization using the exact confirmation in
[the teardown procedure](operations.md#explicit-teardown).
