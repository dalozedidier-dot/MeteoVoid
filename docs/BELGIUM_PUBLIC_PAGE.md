# MeteoVoid Belgique — page publique GitHub Pages

Cette page publie une interface HTML plus lisible à partir du dernier run MeteoVoid Belgique.

Elle ne remplace pas les alertes officielles de l’IRM/KMI. Elle sert de vitrine technique et de tableau de bord expérimental : score national, niveau opérationnel, transition convective, cartes météo avancées et exports auditables.

## Workflow

Le workflow dédié est :

```text
.github/workflows/belgium_pages.yml
```

Il peut être lancé manuellement ou automatiquement toutes les trois heures. Il génère les artefacts MeteoVoid dans `_ci_out/belgium_alert`, construit une page statique dans `_site`, puis la déploie via GitHub Pages.

## URL en ligne

Après le premier déploiement, l’URL apparaît dans le résumé du workflow GitHub Actions, étape `Deploy to GitHub Pages`.

Selon la configuration GitHub Pages du dépôt, l’URL suit généralement cette forme :

```text
https://<utilisateur>.github.io/<repo>/
```

## Lecture recommandée

La page principale `index.html` évite de tout afficher en même temps. Elle propose une navigation par vues : synthèse, transition convective, carte risque, cartes avancées, radar, humidité, point de rosée, formation orageuse et provinces.

Les cartes spécialisées restent disponibles dans :

```text
reports/latest/
```

## Données et prudence

Les cartes radar et fonds de carte peuvent dépendre de services externes chargés côté navigateur. Les cartes d’humidité, de point de rosée et de formation orageuse sont des interpolations légères à partir des sorties MeteoVoid ; elles doivent être lues comme des aides visuelles, pas comme des champs officiels.

## GitHub Pages

Le workflow `Belgium Public Dashboard` active GitHub Pages via `actions/configure-pages` avec `enablement: true`, puis publie le dossier `_site`. Si la publication échoue encore, vérifier dans `Settings > Pages` que la source est bien **GitHub Actions**.

