Patch Release v4

Objectif
- Empêcher le workflow Release de passer en échec quand PyPI Trusted Publisher n'est pas encore configuré.

Changement
- Si PYPI_API_TOKEN est défini (secret GitHub), publication PyPI via token (échec = vrai problème -> job rouge).
- Si PYPI_API_TOKEN est vide, tentative OIDC (Trusted Publisher) en continue-on-error.
  - En cas de "invalid-publisher", le job reste vert et affiche un message expliquant la config PyPI.

Résultat
- Le workflow Release peut rester vert (et créer la GitHub Release + attacher les dist),
  même si PyPI n'est pas prêt.
