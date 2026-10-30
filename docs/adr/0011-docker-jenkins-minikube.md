# 11. Docker image, Jenkins pipeline and deployment to Minikube

Status: Accepted (2026-10-24). Amends [0008](0008-ci-cd-github-actions.md)

## Context

ADR 0008 put CI/CD on GitHub Actions and set Jenkins aside, because the code is on
GitHub. Three needs have since appeared:

- The simulator should run the same way on any machine, cluster or CI runner,
  independent of the host's Python. A lock file pins packages, but not the
  interpreter or the operating system.
- The course assignment requires a self-hosted Jenkins pipeline that runs the unit
  tests on every commit and builds a Docker image. Pushing the image and deploying it
  to Kubernetes (Minikube) are optional.
- Research groups often run CI on their own servers, next to their data and compute.
  The project should show that it does not depend on one hosted CI service.

## Decision

**Container image** (`Dockerfile`, `.dockerignore`):

- Multi-stage build. uv installs the locked environment (`uv sync --locked --no-dev
  --extra plot --no-editable`) in `ghcr.io/astral-sh/uv:…-python3.14-trixie-slim`. The
  runtime stage `python:3.14-slim-trixie` receives only `.venv` and `configs/`. Both
  stages share Python and Debian, so the venv's interpreter path stays valid.
- Dependencies are installed in their own layer before the source is copied, with
  BuildKit cache mounts, so a code change rebuilds in seconds.
- The image runs as non-root user 10001 and also works with a read-only root file
  system. Its entrypoint is `cats-sim`, and the default command is the smoke run.
- OCI labels record the version and the git commit. The build context is an
  allow-list, so tests, docs and secrets never enter the image.

**Jenkins** (`jenkins/`), started with one script (`jenkins/bootstrap.sh`):

- A custom image built on a pinned Jenkins LTS. It adds the docker CLI, kubectl
  (checksum-verified), uv and a pre-installed Python 3.14.
- Jenkins Configuration as Code (`casc.yaml`) defines the admin user, the
  credentials and the job. The job is a Job DSL multibranch pipeline that checks the
  repository every minute, because a laptop Jenkins cannot receive GitHub webhooks.
- Docker-outside-of-Docker: the host's Docker socket is mounted, so builds use the
  host engine and its layer cache.
- Secrets are files in `jenkins/secrets/` (git-ignored) mounted at `/run/secrets`, not
  environment variables, so a pipeline step that prints its environment cannot leak
  them.

**Pipeline** (`Jenkinsfile`):

- Every branch runs: set up → (lint ‖ type-check ‖ hadolint) → unit tests with JUnit
  and coverage reports → build image → smoke-run the image under the same restrictions
  as on Kubernetes.
- `main` additionally runs: push `<user>/cats-sim:<commit>` and `:latest` to Docker
  Hub → create a Kubernetes Job on Minikube from `k8s/job.yaml` and fail the build
  unless it completes.

**Kubernetes** (`k8s/`):

- The `cats-sim` namespace enforces the *restricted* Pod Security Standard.
- Jenkins deploys as the `jenkins-deployer` ServiceAccount, which can manage Jobs and
  read pods and logs in that namespace only.
- The simulator is a batch program, so it is deployed as a **Job**, not a long-running
  Deployment. A completed Job is proof that the published image works on a cluster.

GitHub Actions stays the primary CI for pull requests. Its new `docker` job builds and
smoke-runs the image on every PR. Dependabot now also updates the Docker base images.

## Alternatives considered

- **Replacing GitHub Actions with Jenkins:** this would lose PR checks when the
  laptop is off. The two systems complement each other.
- **Docker-in-Docker sidecar** (the Jenkins handbook setup): this gives better
  isolation, but it needs TLS certificates and a second daemon, and loses the host's
  layer cache. Mounting the socket is acceptable on a single-user machine, but it gives
  Jenkins root-equivalent access to the host's Docker. On a shared server, use DinD or
  rootless BuildKit instead.
- **Running the tests inside `docker build`:** this gives one environment for tests
  and image. However, Jenkins could not show JUnit and coverage trends, and every test
  change would invalidate the image cache.
- **Webhooks through a tunnel (ngrok, smee.io):** these give instant builds, but they
  expose the local Jenkins to the internet. Polling every minute is enough here.
- **Deploying with minikube's admin kubeconfig:** this is simpler, but it gives Jenkins
  cluster-admin rights. A namespaced ServiceAccount follows least privilege.
- **Deploying from a local image (`minikube image load`):** this would skip Docker Hub,
  but then the cluster would not test the artifact that was actually published.

## Consequences

- Any machine with Docker reproduces the experiments without installing Python:
  `docker run --rm -v "$PWD/results:/results" <user>/cats-sim run configs/paper.toml -o /results`.
- Each image tag equals a git commit, and the Job's annotations link back to the
  Jenkins build, so a figure can be traced to a commit, an image and a build.
- The images are built for the build machine's architecture (arm64 on Apple
  silicon). Use `docker buildx build --platform linux/amd64,linux/arm64` if x86
  servers must pull them.
- Jenkins runs builds on the controller (two executors). This is fine for one
  repository; a shared installation should move builds to agents.
