# Suivi des affaires — Cinéma

Petite application web locale qui permet au responsable technique et bâtiment
d'un cinéma de suivre ses affaires (maintenances, rendez-vous avec les
entreprises, chantiers, vérifications) et ce qu'il doit relancer.

Outil personnel : un seul utilisateur, sur son PC. Objectif : savoir en moins
d'une minute où en est chaque affaire et ce qu'il y a à faire aujourd'hui.

**État :** MVP en cours de réalisation. Socle technique en place, aucune
fonctionnalité métier pour l'instant.

## Pile

Python 3.14 · Django 5.2 LTS · SQLite (WAL) · Waitress · WhiteNoise · Pico.css.
Aucune ressource externe à l'exécution : tout est livré avec l'application.

## Développement

Prérequis sous Windows (sans droits administrateur) : Git, [uv](https://docs.astral.sh/uv/), VS Code.

```powershell
git clone https://github.com/<compte>/suivi-maintenance-cinema.git
cd suivi-maintenance-cinema
uv sync                                   # installe Python 3.14 et les dépendances
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver         # http://127.0.0.1:8000/
```

Le mode développement s'active avec `DJANGO_DEBUG=1`. Les terminaux de VS Code
le définissent automatiquement (`.vscode/settings.json`). Ailleurs, dans PowerShell :
`$env:DJANGO_DEBUG = "1"`.

Placer le projet hors d'un dossier synchronisé (OneDrive) : SQLite le supporte mal.

## Lancement en mode normal

```powershell
uv run waitress-serve --listen=127.0.0.1:8000 config.wsgi:application
```

L'application n'écoute que sur le poste lui-même. Aucune configuration n'est
nécessaire : la clé secrète est créée au premier lancement.

## Données

Tout est dans un seul dossier, `data/` par défaut (modifiable avec `DJANGO_DATA_DIR`) :

- `db.sqlite3` : la base ;
- `cle_secrete.txt` : la clé de signature des sessions, recréée si elle est perdue
  (il suffit alors de se reconnecter).

Ce dossier n'est pas versionné. Sauvegarder l'outil, c'est copier ce dossier.

## Réglages

| Variable | Rôle | Défaut |
|---|---|---|
| `DJANGO_DEBUG` | `1` active le mode développement | `0` |
| `DJANGO_DATA_DIR` | Dossier des données | `data/` dans le projet |
| `DJANGO_SECRET_KEY` | Clé secrète imposée | lue ou créée dans le dossier de données |
| `DJANGO_ALLOWED_HOSTS` | Noms acceptés, séparés par des virgules | `127.0.0.1,localhost` |
| `DJANGO_LOG_LEVEL` | Niveau des journaux | `INFO` |
