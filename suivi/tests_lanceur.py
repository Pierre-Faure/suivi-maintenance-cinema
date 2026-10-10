import sqlite3
import tempfile
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from .management.commands.lancer import Command, fermer_journal
from .sauvegarde import copier_vers, dossier_reseau, nettoyer, sauvegarder

COMMANDE = "suivi.management.commands.lancer"


class Dossier(SimpleTestCase):
    """Chaque test travaille dans un dossier temporaire, supprimé ensuite."""

    def setUp(self):
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.dossier = Path(temporaire.name)

    def creer_base(self, valeur="contenu"):
        base = self.dossier / "db.sqlite3"
        with sqlite3.connect(base) as connexion:
            connexion.execute("CREATE TABLE t (x TEXT)")
            connexion.execute("INSERT INTO t VALUES (?)", (valeur,))
        connexion.close()
        return base


class SauvegardeTests(Dossier):
    def test_copie_lisible_et_complete(self):
        base = self.creer_base("Fuite hall")
        copie = sauvegarder(base, self.dossier / "sauvegardes")
        connexion = sqlite3.connect(copie)
        self.assertEqual(connexion.execute("SELECT x FROM t").fetchone(), ("Fuite hall",))
        connexion.close()

    def test_base_en_mode_wal(self):
        base = self.creer_base()
        ouverte = sqlite3.connect(base)
        ouverte.execute("PRAGMA journal_mode=WAL")
        ouverte.execute("INSERT INTO t VALUES ('écrit en WAL')")
        ouverte.commit()  # la ligne n'est encore que dans le fichier -wal
        copie = sauvegarder(base, self.dossier / "sauvegardes")
        ouverte.close()
        connexion = sqlite3.connect(copie)
        self.assertEqual(connexion.execute("SELECT COUNT(*) FROM t").fetchone(), (2,))
        connexion.close()

    def test_rotation(self):
        base = self.creer_base()
        dossier = self.dossier / "sauvegardes"
        debut = datetime(2026, 10, 1, 8, 0, 0)
        for i in range(5):
            sauvegarder(base, dossier, garder=3, maintenant=debut + timedelta(days=i))
        restantes = sorted(p.name for p in dossier.iterdir())
        self.assertEqual(
            restantes,
            ["db-2026-10-03_080000.sqlite3", "db-2026-10-04_080000.sqlite3", "db-2026-10-05_080000.sqlite3"],
        )

    def test_nettoyer_ne_touche_pas_aux_autres_fichiers(self):
        (self.dossier / "note.txt").write_text("à garder")
        (self.dossier / "db-2026-01-01_000000.sqlite3").write_text("")
        nettoyer(self.dossier, garder=0)
        self.assertEqual([p.name for p in self.dossier.iterdir()], ["note.txt"])

    def test_copie_vers_le_partage(self):
        base = self.creer_base()
        copie = sauvegarder(base, self.dossier / "local")
        cible = copier_vers(copie, self.dossier / "partage" / "Suivi")
        self.assertTrue(cible.exists())
        self.assertEqual(cible.name, copie.name)


class DossierReseauTests(Dossier):
    def ecrire(self, contenu):
        (self.dossier / "sauvegarde_reseau.txt").write_text(contenu, encoding="utf-8")

    def test_absent(self):
        self.assertIsNone(dossier_reseau(self.dossier))

    def test_vide_ou_commentaires(self):
        self.ecrire("\n# chemin du partage\n\n")
        self.assertIsNone(dossier_reseau(self.dossier))

    def test_chemin(self):
        self.ecrire('# partage du cinéma\n"\\\\serveur\\partage\\Suivi"\n')
        self.assertEqual(dossier_reseau(self.dossier), Path("\\\\serveur\\partage\\Suivi"))

    def test_fichier_enregistre_par_le_bloc_notes(self):
        # Le Bloc-notes peut ajouter une marque d'encodage (BOM) en début de fichier.
        (self.dossier / "sauvegarde_reseau.txt").write_bytes("\ufeffD:\\Sauvegardes\n".encode("utf-8"))
        self.assertEqual(dossier_reseau(self.dossier), Path("D:\\Sauvegardes"))


class CommandeLancerTests(TestCase):
    """La commande, sans démarrer de vrai serveur ni de navigateur."""

    def setUp(self):
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.data = Path(temporaire.name)
        reglages = override_settings(DATA_DIR=self.data)
        reglages.enable()
        self.addCleanup(reglages.disable)
        # Fermé avant la suppression du dossier temporaire (ordre inverse des ajouts).
        self.addCleanup(fermer_journal)

    def lancer(self, port_deja_pris=False):
        sortie = StringIO()
        with (
            mock.patch(f"{COMMANDE}.port_occupe", return_value=port_deja_pris),
            mock.patch(f"{COMMANDE}.serve") as serve,
            mock.patch(f"{COMMANDE}.ouvrir_quand_pret"),
            mock.patch(f"{COMMANDE}.webbrowser.open") as ouvrir,
            mock.patch(f"{COMMANDE}.call_command") as migrate,
        ):
            call_command("lancer", stdout=sortie)
        return sortie.getvalue(), serve, ouvrir, migrate

    def test_lancement_normal(self):
        sortie, serve, ouvrir, migrate = self.lancer()
        migrate.assert_called_once_with("migrate", interactive=False, verbosity=0)
        serve.assert_called_once()
        self.assertEqual(serve.call_args.kwargs["host"], "127.0.0.1")
        self.assertIn("Ne fermez pas cette fenêtre", sortie)
        self.assertTrue((self.data / "lanceur.log").exists())

    def test_outil_deja_lance(self):
        sortie, serve, ouvrir, migrate = self.lancer(port_deja_pris=True)
        ouvrir.assert_called_once_with("http://127.0.0.1:8000/")
        serve.assert_not_called()
        migrate.assert_not_called()

    def test_echec_des_migrations(self):
        with (
            mock.patch(f"{COMMANDE}.port_occupe", return_value=False),
            mock.patch(f"{COMMANDE}.serve") as serve,
            mock.patch(f"{COMMANDE}.call_command", side_effect=RuntimeError("table verrouillée")),
        ):
            with self.assertRaises(CommandError):
                call_command("lancer", stdout=StringIO())
        serve.assert_not_called()

    def test_sauvegarde_puis_partage_injoignable(self):
        base = self.data / "db.sqlite3"
        sqlite3.connect(base).close()
        (self.data / "sauvegarde_reseau.txt").write_text(str(self.data / "fichier" / "pas-un-dossier"))
        (self.data / "fichier").write_text("")  # un fichier là où on attend un dossier
        commande = Command(stdout=StringIO())
        commande.configurer_journal(self.data / "lanceur.log")
        commande.sauvegarder(base, self.data)
        sortie = commande.stdout.getvalue()
        self.assertEqual(len(list((self.data / "sauvegardes").iterdir())), 1)
        self.assertIn("ATTENTION : partage injoignable", sortie)
