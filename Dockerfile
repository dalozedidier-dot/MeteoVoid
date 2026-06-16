FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE /app/
COPY src/ /app/src/

RUN python -m pip install -U pip \
    && python -m pip install -e ".[live]" \
    && groupadd --system meteovoid \
    && useradd --system --gid meteovoid --home-dir /app --shell /usr/sbin/nologin meteovoid \
    && chown -R meteovoid:meteovoid /app

USER meteovoid

LABEL org.opencontainers.image.title="MeteoVoid" \
      org.opencontainers.image.description="Experimental non-official weather anomaly and convective watch toolkit" \
      org.opencontainers.image.licenses="MIT"

ENTRYPOINT ["meteovoid"]
CMD ["--help"]
