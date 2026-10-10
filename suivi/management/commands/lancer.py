"""
Lance l'outil : la commande appelée par l'icône du bureau (via lancer.cmd).

    uv run python manage.py lancer

Étapes :
1. si l'outil tourne déjà, ouvre simplement le navigateur ;
2. sauvegarde la base (copie locale, puis partage réseau si configuré) ;
3. applique les migrations ;
4. démarre le serveur Waitress sur ce poste uniquement (127.0.0.1) ;
5. ouvre le navigateur dès que le serveur répond.

Une sauvegarde impossible n'empêche pas de démarrer : un avertissement est
affiché et noté dans data/lanceur.log. Seul un échec des migrations arrête tout.
"""

import logging
import socket
import threading
import time
import webbrowser
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.core.wsgi import get_wsgi_application
from waitress import serve

from suivi.sauvegarde import copier_vers, dossier_reseau, sauvegarder

journal = logging.getLogger("lanceur")


def port_occupe(port):
    """Vrai si quelque chose écoute déjà sur ce port (l'outil, en principe)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def ouvrir_quand_pret(url, port, delai=30):
    """Ouvre le navigateur dès que le serveur répond (au plus `delai` secondes)."""
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if port_occupe(port):
            webbrowser.open(url)
            return
        time.sleep(0.3)
    journal.warning("Le serveur n'a pas répondu à temps : ouvrez %s à la main.", url)


def fermer_journal():
    """Détache et ferme le fichier journal (sous Windows, un fichier ouvert
    ne peut pas être supprimé ni déplacé)."""
    for gestionnaire in list(journal.handlers):
        journal.removeHandler(gestionnaire)
        gestionnaire.close()


class Command(BaseCommand):
    help = "Lance l'outil : sauvegarde, migrations, serveur et navigateur."

    def add_arguments(self, parser):
        parser.add_argument("--port", type=int, default=8000)

    def dire(self, message, niveau=logging.INFO):
        """Affiche dans la fenêtre et note dans data/lanceur.log."""
        self.stdout.write(message)
        journal.log(niveau, message)

    def handle(self, *args, port, **options):
        data_dir = Path(settings.DATA_DIR)
        self.configurer_journal(data_dir / "lanceur.log")
        url = f"http://127.0.0.1:{port}/"

        if port_occupe(port):
            self.dire("L'outil tourne déjà : ouverture du navigateur.")
            webbrowser.open(url)
            return

        self.sauvegarder(Path(settings.DATABASES["default"]["NAME"]), data_dir)

        self.dire("Mise à jour de la base…")
        try:
            call_command("migrate", interactive=False, verbosity=0)
        except Exception as erreur:
            journal.exception("Échec des migrations")
            raise CommandError(
                f"La base n'a pas pu être mise à jour ({erreur}). "
                "L'outil ne démarre pas : signalez-le. "
                "Les sauvegardes sont dans data\\sauvegardes."
            ) from erreur

        threading.Thread(target=ouvrir_quand_pret, args=(url, port), daemon=True).start()
        self.dire(
            f"L'outil tourne sur {url}\n"
            "Ne fermez pas cette fenêtre : vous pouvez la réduire. La fermer arrête l'outil."
        )
        serve(get_wsgi_application(), host="127.0.0.1", port=port, threads=4)

    def sauvegarder(self, base, data_dir):
        if not base.exists():
            self.dire("Première utilisation : pas encore de base à sauvegarder.")
            return

        try:
            copie = sauvegarder(base, data_dir / "sauvegardes")
            self.dire(f"Sauvegarde : {copie.name}")
        except Exception:
            journal.exception("Échec de la sauvegarde locale")
            self.dire(
                "ATTENTION : sauvegarde impossible. L'outil démarre quand même ; "
                "signalez-le (détail dans data\\lanceur.log).",
                logging.WARNING,
            )
            return

        reseau = dossier_reseau(data_dir)
        if reseau is None:
            return
        try:
            copier_vers(copie, reseau)
            self.dire(f"Copie sur le partage : {reseau}")
        except Exception:
            journal.exception("Échec de la copie sur le partage %s", reseau)
            self.dire(
                f"ATTENTION : partage injoignable ({reseau}). "
                "La sauvegarde locale est faite ; l'outil démarre.",
                logging.WARNING,
            )

    def configurer_journal(self, chemin):
        """Note chaque lancement dans data/lanceur.log, pour le dépannage."""
        fermer_journal()
        gestionnaire = logging.FileHandler(chemin, encoding="utf-8")
        gestionnaire.setFormatter(logging.Formatter("{asctime} {levelname} : {message}", style="{"))
        journal.addHandler(gestionnaire)
        journal.setLevel(logging.INFO)
        journal.propagate = False  # la fenêtre affiche déjà les messages
