#!/usr/bin/env bash
set -euo pipefail

docker compose --profile demo up --build redis postgres meteovoid-simulate meteovoid-live meteovoid-api
