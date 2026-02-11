Patch MeteoVoid

1) Fix imputation test
Le test tests/test_stream_imputation.py attend que l'imputation insère au moins un point quand un grand gap est détecté.
Le bug venait de dt_median_s calculé sur toutes les deltas, ce qui inclut le gros gap et gonfle la cadence attendue.
Correctif: calculer dt_expected_s sur les deltas "régulières" (<= gap_threshold) quand c'est possible.

2) Fix coverage
Ajout d'un test qui couvre le cas Redis keys en bytes dans api.latest_any.
Cela remonte la couverture au dessus de 85%.

3) Fix release.yml
Votre release.yml était invalide (erreurs "Unrecognized named-value: secrets").
Ce fichier remplace release.yml par une version propre basée sur Trusted Publisher OIDC.

Fichiers:
- src/meteovoid/stream.py
- tests/test_api_bytes_keys.py
- .github/workflows/release.yml
