FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE /app/
COPY src/ /app/src/

RUN python -m pip install -U pip \
  && python -m pip install -e ".[live]"

ENTRYPOINT ["meteovoid"]
CMD ["--help"]
