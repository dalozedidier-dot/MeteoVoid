Patch v1: ingestion multi-stations Europe (Open-Meteo)

Contenu
- config/stations_europe.yaml
- src/meteovoid/stations_config.py
- src/meteovoid/ingest_europe.py
- docs/INGEST_EUROPE.md
- docker-compose.yml: ajoute le service meteovoid-ingest-europe
- tools/generate_bulletin.py: fallback --stations-config si /stations n'existe pas

Important
- L'ingester n'est pas utilisé en CI Live Smoke (pour éviter la dépendance réseau).
- Le workflow Live Smoke reste déterministe via meteovoid-simulate.

Utilisation rapide
- docker compose up -d redis meteovoid-live meteovoid-api meteovoid-ingest-europe
- ouvrir http://localhost:8000/latest
- générer bulletin:
  python tools/generate_bulletin.py --api-url http://localhost:8000 --out-dir _ci_out/live_smoke --stations-config config/stations_europe.yaml --region belgium
