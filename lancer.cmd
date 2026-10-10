@echo off
rem Lanceur de l'outil de suivi des affaires : c'est ce fichier que vise l'icone du bureau.
rem 1. Met a jour le code depuis la branche suivie par ce poste (prod au cinema).
rem    Sans Internet ou en cas d'echec, l'outil demarre avec la version en place.
rem 2. Lance l'outil : sauvegarde, migrations, serveur, navigateur
rem    (voir suivi/management/commands/lancer.py).
rem Pas d'accents dans ce fichier : la console Windows les afficherait mal.

title Suivi des affaires - ne pas fermer cette fenetre
cd /d "%~dp0"

rem Jamais de question bloquante (identifiants, etc.) pendant la mise a jour.
set GIT_TERMINAL_PROMPT=0

echo Recherche de mises a jour...
git pull --ff-only --quiet
if errorlevel 1 echo Mise a jour impossible : l'outil demarre avec la version en place.

uv run python manage.py lancer
if errorlevel 1 (
    echo.
    echo L'outil s'est arrete sur une erreur. Le detail est dans data\lanceur.log.
    pause
)
