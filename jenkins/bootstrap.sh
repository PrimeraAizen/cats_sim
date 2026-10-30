#!/usr/bin/env bash
# One-command setup of the local CI/CD environment. Safe to re-run.
#   1. checks that Minikube is running and that jenkins/.env is filled in;
#   2. creates the cats-sim namespace and the jenkins-deployer ServiceAccount;
#   3. writes the Jenkins secrets: admin password, Docker Hub token, and a kubeconfig
#      that holds only the ServiceAccount's token;
#   4. builds and starts Jenkins with Docker Compose and waits until it answers.
# Prerequisites: Docker Desktop, `brew install minikube`,
#                `minikube start --driver=docker --cpus=2 --memory=2g`.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(dirname "$here")"
secrets="$here/secrets"
kube=(kubectl --context minikube --namespace cats-sim)

die() {
    echo "error: $*" >&2
    exit 1
}

command -v minikube >/dev/null || die "minikube is not installed (brew install minikube)"
minikube status >/dev/null || die "Minikube is not running (minikube start --driver=docker --cpus=2 --memory=2g)"

[[ -f "$here/.env" ]] || die "copy jenkins/.env.example to jenkins/.env and fill it in"
set -a
# shellcheck source=/dev/null
source "$here/.env"
set +a
for var in JENKINS_ADMIN_PASSWORD DOCKERHUB_USERNAME DOCKERHUB_TOKEN; do
    [[ -n "${!var:-}" ]] || die "$var is empty in jenkins/.env"
done

echo "==> Kubernetes: namespace and the jenkins-deployer ServiceAccount"
kubectl --context minikube apply -f "$repo/k8s/namespace.yaml" -f "$repo/k8s/jenkins-rbac.yaml"
token=""
for _ in $(seq 30); do
    token="$("${kube[@]}" get secret jenkins-deployer-token -o jsonpath='{.data.token}' 2>/dev/null || true)"
    [[ -n "$token" ]] && break
    sleep 1
done
[[ -n "$token" ]] || die "the cluster did not fill in the jenkins-deployer token"
ca="$("${kube[@]}" get secret jenkins-deployer-token -o jsonpath='{.data.ca\.crt}')"
# Jenkins joins the "minikube" Docker network and talks to the node directly; the node
# IP is in the API server certificate, 127.0.0.1:<forwarded port> would not be reachable.
server="https://$(minikube ip):8443"

echo "==> Jenkins secrets in jenkins/secrets/"
mkdir -p "$secrets"
umask 077
printf '%s' "$JENKINS_ADMIN_PASSWORD" >"$secrets/jenkins_admin_password"
printf '%s' "$DOCKERHUB_USERNAME" >"$secrets/dockerhub_username"
printf '%s' "$DOCKERHUB_TOKEN" >"$secrets/dockerhub_token"
cat >"$secrets/kubeconfig" <<EOF
apiVersion: v1
kind: Config
clusters:
  - name: minikube
    cluster:
      server: $server
      certificate-authority-data: $ca
users:
  - name: jenkins-deployer
    user:
      token: $(printf '%s' "$token" | base64 --decode)
contexts:
  - name: jenkins-deployer@minikube
    context:
      cluster: minikube
      user: jenkins-deployer
      namespace: cats-sim
current-context: jenkins-deployer@minikube
EOF

echo "==> Jenkins: build and start"
# GID that owns the Docker socket as seen from inside a container.
DOCKER_GID="$(docker run --rm -v /var/run/docker.sock:/var/run/docker.sock alpine:3.22 \
    stat -c %g /var/run/docker.sock)"
export DOCKER_GID
docker compose --file "$here/docker-compose.yml" up --detach --build

printf 'Waiting for Jenkins'
for _ in $(seq 90); do
    if curl -fsS -o /dev/null http://localhost:8080/login; then
        echo
        echo "Jenkins is up: http://localhost:8080 (user: admin, password from jenkins/.env)"
        echo "The 'CATS simulator' job scans the repository every minute."
        exit 0
    fi
    printf '.'
    sleep 2
done
echo
die "Jenkins did not answer within 3 minutes; see: docker compose -f jenkins/docker-compose.yml logs"
