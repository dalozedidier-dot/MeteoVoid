Patch Release v3

Problème corrigé
- GitHub Actions refusait le workflow car il utilisait "secrets.*" dans des expressions,
  ce qui provoquait "Unrecognized named-value: secrets".

Solution
- Le token PyPI est injecté uniquement via env: PYPI_API_TOKEN: ${{ secrets.PYPI_API_TOKEN }}
- Les conditions utilisent env.PYPI_API_TOKEN et steps.<id>.outcome, jamais secrets.*

Comportement
- Si PYPI_API_TOKEN est défini, publication via token.
- Sinon, tentative via Trusted Publisher OIDC.

Pour OIDC, il faut configurer le Trusted Publisher sur PyPI avec:
- repository: dalozedidier-dot/MeteoVoid
- workflow: .github/workflows/release.yml
- environment: pypi
