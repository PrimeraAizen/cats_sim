# syntax=docker/dockerfile:1
# Container image of the CATS simulator.
#
#   docker build -t cats-sim .
#   docker run --rm cats-sim                                   # smoke run (seconds)
#   docker run --rm -v "$PWD/results:/results" cats-sim run configs/quick.toml -o /results
#
# Two stages: uv installs the locked environment in a builder image, and the runtime
# image receives only the finished virtual environment and the configurations. Both
# stages must use the same Python version and Debian release (here 3.14 / trixie), so
# the venv's interpreter path stays valid. Image tags are literal so Dependabot can
# update them.

# ---------------------------------------------------------------- builder
FROM ghcr.io/astral-sh/uv:0.13.1-python3.14-trixie-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies first: this layer is reused until uv.lock or pyproject.toml changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --extra plot --no-install-project

# Then the project itself, installed as a regular (non-editable) wheel.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra plot --no-editable

# ---------------------------------------------------------------- runtime
FROM python:3.14-slim-trixie AS runtime

ARG VERSION=dev
ARG REVISION=unknown
LABEL org.opencontainers.image.title="cats-sim" \
      org.opencontainers.image.description="Simulator for tip selection algorithms on DAG-based distributed ledgers" \
      org.opencontainers.image.source="https://github.com/PrimeraAizen/cats_sim" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}"

RUN groupadd --system --gid 10001 cats \
    && useradd --system --uid 10001 --gid cats --no-create-home cats \
    && mkdir /results \
    && chown cats:cats /results

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY configs ./configs

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MPLCONFIGDIR=/tmp/matplotlib

USER 10001

ENTRYPOINT ["cats-sim"]
CMD ["run", "configs/smoke.toml", "--output-dir", "/results"]
