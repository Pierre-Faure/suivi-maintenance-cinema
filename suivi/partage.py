"""
Accès au partage réseau des documents (Z:\\Bâtiment au cinéma).

Règles communes :
- tout chemin enregistré dans l'outil est RELATIF à la racine réglée dans les
  Réglages ; on ne sort jamais de la racine ;
- un partage absent ou un dossier introuvable n'est jamais une erreur bloquante :
  les fonctions renvoient une valeur vide et l'écran le signale.
"""

import hashlib
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


# --- Fichiers -----------------------------------------------------------------

# Jamais ouverts ni liés : ils lanceraient un programme au lieu d'afficher un document.
EXECUTABLES = {
    ".exe", ".com", ".scr", ".pif", ".msi", ".msp", ".bat", ".cmd", ".ps1", ".psm1",
    ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".hta", ".cpl", ".jar", ".reg",
    ".lnk", ".url", ".scf", ".application", ".appref-ms",
}


def est_executable(nom):
    return Path(str(nom)).suffix.casefold() in EXECUTABLES


def relatif(racine, chemin):
    """Chemin de `chemin` dans `racine`, avec des « / » : « OTIS/2026/devis.pdf »."""
    return Path(chemin).relative_to(racine).as_posix()


def trier_dossiers(noms):
    """Dossiers d'années d'abord, la plus récente en tête, puis les autres
    par ordre alphabétique : « 2026, 2025, Archives, Contrats »."""
    annees = sorted((n for n in noms if re.fullmatch(r"\d{4}", n)), reverse=True)
    autres = sorted((n for n in noms if not re.fullmatch(r"\d{4}", n)), key=str.casefold)
    return annees + autres


def lister(dossier):
    """Contenu d'un dossier : (noms des sous-dossiers, fichiers).

    Chaque fichier est un dictionnaire : nom, taille, modifie (horodatage).
    Fichiers du plus récent au plus ancien. Lève OSError si le dossier est
    inaccessible.
    """
    dossiers, fichiers = [], []
    with os.scandir(dossier) as entrees:
        for entree in entrees:
            if entree.name.startswith((".", "~$")):  # cachés, verrous Office
                continue
            try:
                if entree.is_dir():
                    dossiers.append(entree.name)
                elif entree.is_file():
                    info = entree.stat()
                    fichiers.append({"nom": entree.name, "taille": info.st_size, "modifie": info.st_mtime})
            except OSError:
                continue  # un fichier illisible ne doit pas empêcher d'afficher les autres
    fichiers.sort(key=lambda f: f["modifie"], reverse=True)
    return trier_dossiers(dossiers), fichiers


def montrer(chemin):
    """Ouvre l'Explorateur Windows sur le dossier, avec le fichier sélectionné."""
    if not hasattr(os, "startfile"):
        raise OSError("L'ouverture dans l'Explorateur n'est possible que sous Windows.")
    import subprocess

    # Syntaxe propre à l'Explorateur : /select,"chemin" (un nom de fichier
    # Windows ne peut pas contenir de guillemet).
    subprocess.Popen(f'explorer /select,"{chemin}"')  # noqa: S602


# --- Import -------------------------------------------------------------------

TAILLE_MAX = 50 * 1024 * 1024  # 50 Mo par fichier importé

# Caractères interdits dans un nom de fichier Windows, et noms réservés.
INTERDITS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def nom_sur(nom):
    """Nom de fichier utilisable sous Windows, sans aucun chemin :
    « ..\\..\\devis:v2.pdf » → « devis_v2.pdf »."""
    nom = str(nom).replace("\\", "/").rsplit("/", 1)[-1]
    nom = INTERDITS.sub("_", nom).strip().rstrip(". ")
    if not nom:
        return "document"
    if nom.split(".", 1)[0].upper() in RESERVES:
        nom = f"_{nom}"
    return nom


def empreinte(morceaux):
    """Empreinte SHA-256 d'un contenu lu par morceaux."""
    calcul = hashlib.sha256()
    for morceau in morceaux:
        calcul.update(morceau)
    return calcul.hexdigest()


def morceaux_du_fichier(chemin, taille=1024 * 1024):
    with open(chemin, "rb") as fichier:
        while morceau := fichier.read(taille):
            yield morceau


def deposer(envoi, dossier):
    """Range un fichier envoyé par le navigateur dans `dossier` (créé s'il
    manque ; son parent doit exister). Renvoie (chemin, copie).

    - Si un fichier identique (même taille, même empreinte) est déjà dans le
      dossier, rien n'est copié : on renvoie ce fichier et copie=False.
    - Si le nom est pris par un autre fichier, on ajoute « (2) », « (3) »…
    - Un fichier existant n'est jamais écrasé ; une copie interrompue est effacée.
    """
    dossier = Path(dossier)
    dossier.mkdir(exist_ok=True)

    signature = None
    for entree in os.scandir(dossier):
        try:
            meme_taille = entree.is_file() and entree.stat().st_size == envoi.size
        except OSError:
            continue
        if meme_taille:
            signature = signature or empreinte(envoi.chunks())
            if empreinte(morceaux_du_fichier(entree.path)) == signature:
                return Path(entree.path), False

    nom = Path(nom_sur(envoi.name))
    cible, numero = dossier / nom.name, 2
    while True:
        try:
            sortie = open(cible, "xb")  # « x » : échoue si le fichier existe
            break
        except FileExistsError:
            cible = dossier / f"{nom.stem} ({numero}){nom.suffix}"
            numero += 1
    try:
        with sortie:
            for morceau in envoi.chunks():
                sortie.write(morceau)
    except BaseException:
        cible.unlink(missing_ok=True)
        raise
    return cible, True
