"""
Réglages du projet « Suivi maintenance & prestataires — Cinéma ».

Principes :
- Tout ce qui varie d'une machine à l'autre vient de variables d'environnement
  (préfixe DJANGO_), sans dépendance supplémentaire.
- Par défaut, le mode est sûr (DEBUG désactivé). Le développement l'active
  explicitement avec DJANGO_DEBUG=1.
- Les données (base SQLite, plus tard fichiers et sauvegardes) vivent dans un
  dossier unique, DJANGO_DATA_DIR, facile à monter en volume Docker et à sauvegarder.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(nom, defaut=None):
    """Lit une variable d'environnement ; chaîne vide = absente."""
    valeur = os.environ.get(nom, "").strip()
    return valeur or defaut


def env_liste(nom):
    """Lit une liste séparée par des virgules : "a, b" -> ["a", "b"]."""
    return [element.strip() for element in env(nom, "").split(",") if element.strip()]


# --- Mode et sécurité ---------------------------------------------------------

DEBUG = env("DJANGO_DEBUG", "0") == "1"

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-uniquement-cle-non-secrete"
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY est absente. Renseignez-la dans le fichier .env "
            "(une longue chaîne aléatoire), ou activez le mode développement "
            "avec DJANGO_DEBUG=1."
        )

# Noms ou adresses par lesquels l'outil est joint (ex. "suivi.cinema.lan,192.168.1.20").
# En DEBUG, Django accepte localhost même si la liste est vide.
ALLOWED_HOSTS = env_liste("DJANGO_ALLOWED_HOSTS")

# Origines autorisées pour les formulaires (ex. "http://suivi.cinema.lan").
CSRF_TRUSTED_ORIGINS = env_liste("DJANGO_CSRF_TRUSTED_ORIGINS")

# Note : l'outil sera servi sur le réseau local, a priori sans HTTPS.
# Les cookies « secure » ne sont donc pas activés ici ; à revoir si HTTPS est mis en place.


# --- Applications -------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Applications du projet
    "comptes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise sert les fichiers statiques (CSS, JS) sans serveur web séparé.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Pas de LocaleMiddleware : l'interface est en français quelle que soit
    # la langue du navigateur (LANGUAGE_CODE ci-dessous).
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- Données et base ----------------------------------------------------------

DATA_DIR = Path(env("DJANGO_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
        "OPTIONS": {
            # Attendre jusqu'à 20 s qu'un autre accès libère la base plutôt
            # que d'échouer immédiatement avec « database is locked ».
            "timeout": 20,
            # Les transactions réservent l'écriture dès leur début : évite les
            # blocages entre deux écritures simultanées.
            "transaction_mode": "IMMEDIATE",
            # WAL : lectures et écriture simultanées, plus robuste aux coupures.
            # synchronous=NORMAL : réglage recommandé avec WAL.
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Comptes ------------------------------------------------------------------

# Modèle d'utilisateur propre au projet, défini dès le départ :
# le changer après la première migration est très coûteux.
AUTH_USER_MODEL = "comptes.Utilisateur"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Langue, fuseau, formats --------------------------------------------------

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True  # stockage en UTC, affichage à l'heure de Paris


# --- Fichiers statiques -------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"  # rempli par collectstatic (image Docker)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Compression sans « manifest » : un fichier statique manquant ne peut pas
    # faire planter une page. En contrepartie, le navigateur garde les fichiers
    # en cache 60 s seulement, ce qui est sans importance sur un réseau local.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}


# --- Journaux -----------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{asctime} {levelname} {name} : {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "INFO")},
}
