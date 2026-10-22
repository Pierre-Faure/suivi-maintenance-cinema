# Suivi des affaires — Cinéma

Petite application web locale qui permet au responsable technique et bâtiment
d'un cinéma de suivre ses affaires (maintenances, rendez-vous avec les
entreprises, chantiers, vérifications) et ce qu'il doit relancer.

Outil personnel : un seul utilisateur, sur son PC. Objectif : savoir en moins
d'une minute où en est chaque affaire et ce qu'il y a à faire aujourd'hui.

**État :** MVP terminé : vue d'ensemble, affaires (entreprises, actions, journal,
documents liés ou importés), annuaire, historique et recherche, lanceur avec
sauvegarde et mises à jour. Conçu pour Windows.

Questions, idées, problèmes : ouvrez une [issue](https://github.com/Pierre-Faure/suivi-maintenance-cinema/issues).

## Installation sur un poste

Prérequis sous Windows, sans droits administrateur : [Git](https://git-scm.com/) et
[uv](https://docs.astral.sh/uv/). uv installe lui-même Python 3.14.

```powershell
git clone --branch prod https://github.com/Pierre-Faure/suivi-maintenance-cinema.git C:\suivi-affaires
cd C:\suivi-affaires
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

Puis créer sur le bureau un raccourci vers `lancer.cmd` (Propriétés → Exécuter :
« Réduite »), le lancer, et régler la racine des documents dans la page Réglages.
Choisir un dossier hors de OneDrive.

## Pile

Python 3.14 · Django 5.2 LTS · SQLite (WAL) · Waitress · WhiteNoise · Pico.css.
Aucune ressource externe à l'exécution : tout est livré avec l'application.

## Développement

Prérequis sous Windows (sans droits administrateur) : Git, [uv](https://docs.astral.sh/uv/), VS Code.

```powershell
git clone https://github.com/Pierre-Faure/suivi-maintenance-cinema.git
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
   - sauvegarde la base dans `data/sauvegardes/` (30 copies gardées), puis dans le
     dossier technique du partage si une racine des documents est réglée (page Réglages) ;
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

Le dépôt est public : les postes le clonent en HTTPS et se mettent à jour sans
identifiant. La branche `prod` est protégée contre les réécritures et la suppression.

## Données

Tout est dans un seul dossier, `data/` par défaut (modifiable avec `DJANGO_DATA_DIR`) :

- `db.sqlite3` : la base ;
- `cle_secrete.txt` : la clé de signature des sessions, recréée si elle est perdue
  (il suffit alors de se reconnecter) ;
- `sauvegardes/` : les copies de la base faites à chaque lancement ;
- `lanceur.log` : le journal des lancements.

Ce dossier n'est pas versionné : un `git pull` ne le touche pas. Sauvegarder
l'outil, c'est copier ce dossier.

## Documents

Les documents (devis, factures…) restent sur le partage réseau : l'outil n'en
garde que des liens, relatifs à la **racine des documents** réglée dans la page
Réglages (par exemple `Z:\Bâtiment`). Le dossier technique de cette racine
(`_Suivi des affaires` par défaut) reçoit une copie de chaque sauvegarde.

Sur la fiche d'une affaire, **Lier des fichiers** ouvre un explorateur intégré
qui part du dossier de l'entreprise. L'outil ne fait qu'ouvrir les fichiers liés
(dans leur application) ou montrer leur dossier dans l'Explorateur Windows ; il ne
modifie, ne déplace et ne supprime jamais rien sur le partage. Les programmes
(`.exe`, `.bat`, `.lnk`…) ne peuvent pas être liés ni ouverts. Un fichier renommé
ou déplacé apparaît « introuvable » : **Relier** permet de le retrouver.

**Importer des fichiers** (même fiche) : glisser-déposer ou « Parcourir », 50 Mo au
plus par fichier. Ils sont rangés dans `<dossier choisi>\<année>\` (dossier de
l'entreprise, ou un dossier libre comme « Autres » ou « Sinistres »), puis liés à
l'affaire. Rien n'est jamais écrasé : un nom déjà pris reçoit « (2) », et un fichier
identique déjà présent dans ce dossier (même empreinte SHA-256) est lié sans être
recopié. Seul le dossier de l'année peut être créé.

## Réglages

| Variable | Rôle | Défaut |
|---|---|---|
| `DJANGO_DEBUG` | `1` active le mode développement | `0` |
| `DJANGO_DATA_DIR` | Dossier des données | `data/` dans le projet |
| `DJANGO_SECRET_KEY` | Clé secrète imposée | lue ou créée dans le dossier de données |
| `DJANGO_ALLOWED_HOSTS` | Noms acceptés, séparés par des virgules | `127.0.0.1,localhost` |
| `DJANGO_LOG_LEVEL` | Niveau des journaux | `INFO` |

## Licence

[MIT](LICENSE) © 2026 Pierre Faure
