# Image de l'application. La même image sert en développement et en production :
# seuls la commande lancée et les variables d'environnement changent.

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_DATA_DIR=/data

# Utilisateur sans privilèges. UID/GID 1000 = premier utilisateur sous WSL et
# sous la plupart des Linux : les fichiers créés dans les dossiers montés
# t'appartiennent, pas à root.
ARG UID=1000
ARG GID=1000
RUN groupadd --gid ${GID} app \
    && useradd --uid ${UID} --gid ${GID} --create-home app

WORKDIR /app

# Dépendances d'abord : cette couche n'est reconstruite que si requirements.txt change.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=app:app . .

# Fichiers statiques rassemblés dans l'image. DJANGO_DEBUG=1 uniquement pour
# cette commande, afin de ne pas exiger de clé secrète à la construction.
RUN DJANGO_DEBUG=1 python manage.py collectstatic --noinput \
    && mkdir -p /data \
    && chown app:app /data

USER app
EXPOSE 8000

# Production : Gunicorn, 2 processus (largement suffisant ; SQLite n'aime pas
# les écritures très concurrentes). Journaux d'accès sur la sortie standard.
# Les migrations ne sont PAS lancées ici : elles passent par la commande de
# mise à jour, après une sauvegarde (étape 9).
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-"]
