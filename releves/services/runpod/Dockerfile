# Build only from the EXACT audited image used for the environment snapshot.
# Build context: services/runpod plus a private restore/ directory with manifest
# and the validated venv archives. Never include keys, models or client datasets.
ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS environments
ARG RUNTIME_IMAGE_TAG
ENV DOEMO_RUNTIME_IMAGE_TAG=${RUNTIME_IMAGE_TAG}
USER root
COPY environments.py /tmp/doemo-build/environments.py
COPY restore/ /tmp/doemo-build/restore/
RUN python3 /tmp/doemo-build/environments.py restore /tmp/doemo-build/restore/manifest.json

FROM ${BASE_IMAGE}
ARG RUNTIME_IMAGE_TAG
ENV DOEMO_RUNTIME_IMAGE_TAG=${RUNTIME_IMAGE_TAG} \
    DOEMO_PERSISTENT_ROOT=/workspace/doemo-studio \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_CACHE_DIR=/tmp/doemo-uv-cache \
    PIP_CACHE_DIR=/tmp/doemo-pip-cache
USER root
# Includes any /opt Python base interpreter recorded in the validated snapshot.
COPY --from=environments /opt/ /opt/
COPY *.py /opt/doemo-services/
EXPOSE 8000
CMD ["python3", "/opt/doemo-services/bootstrap.py"]
