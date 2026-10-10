# Suivi des affaires — Cinéma

Petite application web locale qui permet au responsable technique et bâtiment
d'un cinéma de suivre ses affaires (maintenances, rendez-vous avec les
entreprises, chantiers, vérifications) et ce qu'il doit relancer.

Outil personnel : un seul utilisateur, sur son PC. Objectif : savoir en moins
d'une minute où en est chaque affaire et ce qu'il y a à faire aujourd'hui.

**État :** MVP en cours de finalisation : vue d'ensemble, affaires (entreprises,
actions, journal), annuaire, historique et recherche, lanceur avec sauvegarde
et mises à jour.

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

## Lancement : `lancer.cmd`

C'est le fichier que vise l'icône du bureau (raccourci réglé sur « Exécuter : Réduite »). Il :

1. met à jour le code (`git pull` de la branche suivie par le poste) ; sans Internet,
   il continue avec la version en place ;
2. lance `uv run python manage.py lancer`, qui :
   - ouvre simplement le navigateur si l'outil tourne déjà ;
   - sauvegarde la base dans `data/sauvegardes/` (30 copies gardées), puis sur le
     partage réseau si `data/sauvegarde_reseau.txt` en donne le chemin ;
   - applique les migrations ;
   - démarre Waitress sur `127.0.0.1:8000` et ouvre le navigateur.

Fermer la fenêtre arrête l'outil. Chaque lancement est noté dans `data/lanceur.log`.
L'application n'écoute que sur le poste lui-même ; la clé secrète est créée au premier lancement.

## Versions et mise en production

- On développe et on pousse sur `main`.
- Les postes d'utilisation suivent la branche **`prod`** : seul ce qui y est poussé
  arrive chez l'utilisateur, au lancement suivant.

```powershell
git push origin main:prod      # mettre en production l'état actuel de main
```

Accès des postes au dépôt privé : une **clé de déploiement** en lecture seule par
poste (GitHub → Settings → Deploy keys), sans compte personnel. Une clé se révoque
d'un clic.

## Données

Tout est dans un seul dossier, `data/` par défaut (modifiable avec `DJANGO_DATA_DIR`) :

- `db.sqlite3` : la base ;
- `cle_secrete.txt` : la clé de signature des sessions, recréée si elle est perdue
  (il suffit alors de se reconnecter) ;
- `sauvegardes/` : les copies de la base faites à chaque lancement ;
- `sauvegarde_reseau.txt` (facultatif) : une ligne, le chemin du dossier de
  sauvegarde sur le partage réseau ;
- `lanceur.log` : le journal des lancements.

Ce dossier n'est pas versionné. Sauvegarder l'outil, c'est copier ce dossier.

## Réglages

| Variable | Rôle | Défaut |
|---|---|---|
| `DJANGO_DEBUG` | `1` active le mode développement | `0` |
| `DJANGO_DATA_DIR` | Dossier des données | `data/` dans le projet |
| `DJANGO_SECRET_KEY` | Clé secrète imposée | lue ou créée dans le dossier de données |
| `DJANGO_ALLOWED_HOSTS` | Noms acceptés, séparés par des virgules | `127.0.0.1,localhost` |
| `DJANGO_LOG_LEVEL` | Niveau des journaux | `INFO` |
