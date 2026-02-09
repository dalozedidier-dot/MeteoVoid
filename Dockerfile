FROM python:3.12-slim

# Empêche Python de bufferiser stdout/stderr
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dépendances système minimales
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# Copier les fichiers nécessaires à l’installation
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# Installer le package
RUN python -m pip install --upgrade pip \
 && python -m pip install .

# Point d’entrée : CLI MeteoVoid
ENTRYPOINT ["meteovoid"]
CMD ["--help"]
