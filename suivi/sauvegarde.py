"""
Sauvegarde de la base, appelée par le lanceur à chaque démarrage.

Deux niveaux :
- une copie locale dans `data/sauvegardes/`, toujours ;
- une copie sur le partage réseau, dans le dossier technique réglé dans
  l'outil (page Réglages), si une racine des documents est réglée.

On garde les N copies les plus récentes de chaque côté.
"""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

GARDER = 30
PREFIXE = "db-"
SUFFIXE = ".sqlite3"


def sauvegarder(base, dossier, garder=GARDER, maintenant=None):
    """Copie la base dans `dossier` et renvoie le chemin de la copie.

    Utilise la sauvegarde intégrée à SQLite : la copie est cohérente même si
    la base est ouverte ou en mode WAL (une simple copie de fichier ne l'est pas).
    """
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    maintenant = maintenant or datetime.now()
    cible = dossier / f"{PREFIXE}{maintenant:%Y-%m-%d_%H%M%S}{SUFFIXE}"

    source = sqlite3.connect(base)
    copie = sqlite3.connect(cible)
    try:
        source.backup(copie)
    finally:
        copie.close()
        source.close()

    nettoyer(dossier, garder)
    return cible


def copier_vers(copie, dossier, garder=GARDER):
    """Recopie une sauvegarde dans un autre dossier (le partage réseau)."""
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / Path(copie).name
    shutil.copy2(copie, cible)
    nettoyer(dossier, garder)
    return cible


def nettoyer(dossier, garder=GARDER):
    """Supprime les copies les plus anciennes au-delà de `garder`.

    Le nom contient la date (AAAA-MM-JJ_HHMMSS) : l'ordre alphabétique est
    l'ordre chronologique. Seuls nos propres fichiers sont concernés.
    """
    copies = sorted(Path(dossier).glob(f"{PREFIXE}*{SUFFIXE}"))
    for ancienne in copies[:-garder] if garder else copies:
        ancienne.unlink()
