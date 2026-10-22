"""
Accès au partage réseau des documents (Z:\\Bâtiment au cinéma).

Règles communes :
- tout chemin enregistré dans l'outil est RELATIF à la racine réglée dans les
  Réglages ; on ne sort jamais de la racine ;
- un partage absent ou un dossier introuvable n'est jamais une erreur bloquante :
  les fonctions renvoient une valeur vide et l'écran le signale.
"""

import os
import re
import unicodedata
from pathlib import Path, PurePath


class HorsRacine(ValueError):
    """Chemin refusé : absolu, ou qui sort de la racine (« .. »)."""


def chemin_dans_racine(racine, relatif):
    """Chemin complet de `relatif` dans `racine`, après contrôle.

    Refuse les chemins absolus (« C:\\… », « \\\\serveur\\… ») et ceux qui
    remontent (« .. ») : c'est ce qui garantit qu'on reste dans la racine.
    """
    brut = str(relatif).strip()
    if (
        not brut
        or brut.startswith(("/", "\\"))  # « \\serveur\… » ou racine du disque
        or re.match(r"^[A-Za-z]:", brut)  # lettre de lecteur, testée sur tout système
    ):
        raise HorsRacine(brut)
    morceaux = PurePath(brut.replace("\\", "/").rstrip("/"))
    if morceaux.is_absolute() or ".." in morceaux.parts or not morceaux.parts:
        raise HorsRacine(brut)
    return Path(racine).joinpath(*morceaux.parts)


def accessible(dossier):
    """Vrai si le dossier existe et peut être lu (partage connecté)."""
    try:
        return bool(dossier) and Path(dossier).is_dir()
    except OSError:
        return False


def sous_dossiers(dossier):
    """Noms des sous-dossiers, triés ; liste vide si le dossier est inaccessible."""
    try:
        return sorted(
            (e.name for e in os.scandir(dossier) if e.is_dir() and not e.name.startswith(".")),
            key=str.casefold,
        )
    except OSError:
        return []


def normaliser(nom):
    """« Plomberie Martin & Fils » → « plomberiemartinfils » : sans casse,
    accents, espaces ni ponctuation, pour comparer des noms."""
    sans_accents = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sans_accents.casefold())


def proposer_dossier(nom_entreprise, dossiers):
    """Le dossier dont le nom ressemble le plus à celui de l'entreprise, ou None.

    1. même nom une fois normalisé (« OTIS » = « Otis ») ;
    2. sinon, un seul dossier qui contient le nom, ou dont le nom est contenu
       dans celui de l'entreprise (« Otis » ↔ « Otis Ascenseurs »).
    Si plusieurs dossiers correspondent, on ne devine pas : None.
    """
    cible = normaliser(nom_entreprise)
    if len(cible) < 3:
        return None
    normes = {dossier: normaliser(dossier) for dossier in dossiers}

    identiques = [d for d, n in normes.items() if n == cible]
    if len(identiques) == 1:
        return identiques[0]

    proches = [d for d, n in normes.items() if len(n) >= 3 and (cible in n or n in cible)]
    return proches[0] if len(proches) == 1 else None


def ouvrir(chemin):
    """Ouvre un dossier (ou un fichier) avec Windows, comme un double-clic.

    Possible parce que le serveur tourne sur le PC de l'utilisateur, sous sa
    session. Sur un autre système, lève une erreur explicite.
    """
    if not hasattr(os, "startfile"):
        raise OSError("L'ouverture dans l'Explorateur n'est possible que sous Windows.")
    os.startfile(chemin)  # noqa: S606 — chemin contrôlé par l'appelant
