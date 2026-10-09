"""
Réglages du projet « Suivi des affaires — Cinéma ».

Principes :
- Tout ce qui varie d'une machine à l'autre vient de variables d'environnement
  (préfixe DJANGO_), sans dépendance supplémentaire.
- Par défaut, le mode est sûr (DEBUG désactivé). Le développement l'active
  explicitement avec DJANGO_DEBUG=1.
- Les données (base SQLite, clé secrète, plus tard les fichiers) vivent dans un
  dossier unique, DJANGO_DATA_DIR, facile à sauvegarder et à déplacer.
- L'outil n'est servi que sur le poste où il tourne (127.0.0.1).
"""

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(nom, defaut=None):
    """Lit une variable d'environnement ; chaîne vide = absente."""
    valeur = os.environ.get(nom, "").strip()
    return valeur or defaut


def env_liste(nom):
    """Lit une liste séparée par des virgules : "a, b" -> ["a", "b"]."""
    return [element.strip() for element in env(nom, "").split(",") if element.strip()]


# --- Dossier de données -------------------------------------------------------

DATA_DIR = Path(env("DJANGO_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


# --- Mode et sécurité ---------------------------------------------------------

DEBUG = env("DJANGO_DEBUG", "0") == "1"


def lire_ou_creer_cle_secrete(chemin):
    """Lit la clé secrète dans un fichier ; la crée au premier lancement.

    Rien à configurer à l'installation. Si le fichier est perdu, une nouvelle
    clé est créée : la seule conséquence est qu'il faut se reconnecter.
    """
    if not chemin.exists():
        chemin.write_text(secrets.token_urlsafe(50), encoding="utf-8")
    return chemin.read_text(encoding="utf-8").strip()


SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-uniquement-cle-non-secrete"
    else:
        SECRET_KEY = lire_ou_creer_cle_secrete(DATA_DIR / "cle_secrete.txt")

# L'outil n'écoute que sur ce PC : localhost suffit par défaut.
ALLOWED_HOSTS = env_liste("DJANGO_ALLOWED_HOSTS") or ["127.0.0.1", "localhost"]

# Servi uniquement en local (127.0.0.1), sans HTTPS : pas de cookies « secure ».


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
    "suivi",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise sert les fichiers statiques (CSS) sans serveur web séparé.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Pas de LocaleMiddleware : l'interface est en français quelle que soit
    # la langue du navigateur (LANGUAGE_CODE ci-dessous).
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Toutes les pages exigent d'être connecté, sauf celles marquées
    # explicitement (la page de connexion l'est déjà par Django).
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
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
                "django.contrib.messages.context_processors.messages",
                "suivi.context_processors.theme",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- Base de données ----------------------------------------------------------

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

LOGIN_URL = "connexion"
LOGIN_REDIRECT_URL = "accueil"
LOGOUT_REDIRECT_URL = "connexion"

# PC physiquement partagé : on se reconnecte à chaque ouverture de l'outil.
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
# Filet de sécurité : certains navigateurs restaurent les sessions au
# redémarrage (« reprendre là où je m'étais arrêté »). Côté serveur, la session
# expire quoi qu'il arrive au bout de 12 h.
SESSION_COOKIE_AGE = 12 * 60 * 60

# --- Langue, fuseau, formats --------------------------------------------------

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True  # stockage en UTC, affichage à l'heure de Paris


# --- Fichiers statiques -------------------------------------------------------

STATIC_URL = "static/"

# WhiteNoise sert les fichiers directement depuis les dossiers « static » des
# applications : pas de collectstatic, une étape de moins à la livraison.
# Pour un seul utilisateur en local, l'absence de compression est sans effet.
WHITENOISE_USE_FINDERS = True


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
