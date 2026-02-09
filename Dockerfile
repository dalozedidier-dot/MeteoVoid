FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE /app/
COPY src/ /app/src/

RUN python -m pip install -U pip \
  && pip install -e .

ENTRYPOINT ["meteovoid"]
CMD ["--help"]
