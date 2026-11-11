#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export KUBECONFIG="${KUBECONFIG:-$PWD/kubeconfig.yaml}"
export AWS_DEFAULT_REGION="$(python3 -c 'import yaml; print(yaml.safe_load(open("config.yaml"))["global"]["region"])')"
namespace="iac-storage-smoke-$(date +%s)"
volume_id=""
cleanup() {
  pv=$(kubectl get pvc smoke -n "$namespace" -o jsonpath='{.spec.volumeName}' 2>/dev/null || true)
  if [[ -n "$pv" ]]; then
    volume_id=$(kubectl get pv "$pv" -o jsonpath='{.spec.csi.volumeHandle}' 2>/dev/null || true)
  fi
  kubectl delete namespace "$namespace" --wait=true --timeout=120s || return
  if [[ -n "$volume_id" ]]; then
    kubectl delete pv "$pv" --wait=true --timeout=60s
    aws ec2 wait volume-available --volume-ids "$volume_id"
    aws ec2 delete-volume --volume-id "$volume_id"
  fi
}
trap cleanup EXIT
kubectl create namespace "$namespace"
kubectl apply -n "$namespace" -f - <<'YAML'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: smoke
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: gp3
  resources:
    requests:
      storage: 1Gi
YAML
create_pod() {
  kubectl apply -n "$namespace" -f - <<'YAML'
apiVersion: v1
kind: Pod
metadata:
  name: smoke
spec:
  terminationGracePeriodSeconds: 1
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: smoke
      image: public.ecr.aws/docker/library/busybox:1.37.0
      command: [sh, -c, 'sleep 3600']
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: [ALL]
      resources:
        requests: {cpu: 10m, memory: 16Mi}
        limits: {cpu: 100m, memory: 32Mi}
      volumeMounts:
        - {name: data, mountPath: /data}
  volumes:
    - name: data
      persistentVolumeClaim: {claimName: smoke}
YAML
  kubectl wait -n "$namespace" pod/smoke --for=condition=Ready --timeout=300s
}
create_pod
pv=$(kubectl get pvc smoke -n "$namespace" -o jsonpath='{.spec.volumeName}')
volume_id=$(kubectl get pv "$pv" -o jsonpath='{.spec.csi.volumeHandle}')
kubectl exec -n "$namespace" smoke -- sh -c 'echo persistence-ok > /data/proof; sync'
kubectl delete pod smoke -n "$namespace" --wait=true
create_pod
[[ "$(kubectl exec -n "$namespace" smoke -- cat /data/proof)" == "persistence-ok" ]]
[[ "$(aws ec2 describe-volumes --volume-ids "$volume_id" --query 'Volumes[0].Encrypted' --output text)" == "True" ]]
echo "PASS encrypted EBS volume survived pod recreation"

if [[ "${TEST_BACKUP:-0}" == "1" ]]; then
  python3 scripts/smoke-backup.py "$namespace" "$volume_id"
fi
