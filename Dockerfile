FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1
WORKDIR /build

COPY pyproject.toml README.md LICENSE /build/
COPY src/ /build/src/

RUN python -m pip install -U pip build \
    && python -m build --wheel --outdir /wheels \
    && python -m pip wheel --no-cache-dir --wheel-dir /wheels ".[live]"

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY config/ /app/config/

RUN python -m pip install -U pip \
    && python -m pip install --no-cache-dir /wheels/*.whl \
    && rm -rf /wheels \
    && groupadd --system meteovoid \
    && useradd --system --gid meteovoid --home-dir /app --shell /usr/sbin/nologin meteovoid \
    && chown -R meteovoid:meteovoid /app

USER meteovoid

LABEL org.opencontainers.image.title="MeteoVoid" \
      org.opencontainers.image.description="Experimental non-official weather anomaly and convective watch toolkit" \
      org.opencontainers.image.licenses="MIT"

ENTRYPOINT ["meteovoid"]
CMD ["--help"]
