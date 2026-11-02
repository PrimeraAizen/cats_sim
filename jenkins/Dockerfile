# syntax=docker/dockerfile:1
# Jenkins controller for the CATS pipeline: Jenkins LTS, the plugins in plugins.txt, the
# configuration in casc.yaml, and the command-line tools the Jenkinsfile calls
# (docker CLI, kubectl, uv with a pre-installed Python). Started by docker-compose.yml.
# Image tags are literal so Dependabot can update them.

FROM docker:29.9.2-cli AS docker-cli
FROM ghcr.io/astral-sh/uv:0.13.6 AS uv

FROM jenkins/jenkins:2.580.1-lts-jdk21

ARG TARGETARCH
ARG KUBECTL_VERSION=v1.37.1
ARG PYTHON_VERSION=3.14

USER 0
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# The docker CLI talks to the host's Docker Engine through the mounted socket.
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-buildx \
     /usr/local/libexec/docker/cli-plugins/docker-buildx
COPY --from=uv /uv /uvx /usr/local/bin/

RUN curl -fsSLo /usr/local/bin/kubectl \
        "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
    && echo "$(curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl.sha256")  /usr/local/bin/kubectl" \
       | sha256sum --check \
    && chmod 0755 /usr/local/bin/kubectl

# Python for the pipeline's `uv sync`, installed once here instead of in every build.
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python
RUN uv python install --no-bin "${PYTHON_VERSION}" \
    && chown -R jenkins:jenkins /opt/uv

# uid 1000 is the image's jenkins user.
USER 1000

COPY --chown=jenkins:jenkins plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

# Everything else (users, credentials, the pipeline job) comes from casc.yaml.
COPY --chown=jenkins:jenkins casc.yaml /usr/share/jenkins/casc.yaml
ENV CASC_JENKINS_CONFIG=/usr/share/jenkins/casc.yaml \
    JAVA_OPTS="-Djenkins.install.runSetupWizard=false"
