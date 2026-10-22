import os
import tempfile
import time
from pathlib import Path
from unittest import mock

from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from comptes.models import Utilisateur

from .models import Affaire, Entreprise, Intervenant, Lien, Reglages
from .partage import est_executable, lister, trier_dossiers


class PartageFichiersTests(SimpleTestCase):
    def test_tri_des_dossiers(self):
        self.assertEqual(
            trier_dossiers(["Contrats", "2024", "archives", "2026", "2025"]),
            ["2026", "2025", "2024", "archives", "Contrats"],
        )

    def test_executables(self):
        for nom in ["setup.EXE", "script.ps1", "raccourci.lnk", "macro.vbs", "lancer.cmd"]:
            self.assertTrue(est_executable(nom), nom)
        for nom in ["devis.pdf", "rapport.docx", "mail.msg", "photo.JPG", "sans-extension"]:
            self.assertFalse(est_executable(nom), nom)

    def test_lister(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            (racine / "2025").mkdir()
            (racine / "2026").mkdir()
            ancien = racine / "ancien.pdf"
            ancien.write_text("a")
            os.utime(ancien, (time.time() - 3600, time.time() - 3600))
            (racine / "recent.pdf").write_text("bb")
            (racine / "~$verrou.docx").write_text("")  # verrou Office : caché
            dossiers, fichiers = lister(racine)
        self.assertEqual(dossiers, ["2026", "2025"])
        self.assertEqual([f["nom"] for f in fichiers], ["recent.pdf", "ancien.pdf"])
        self.assertEqual(fichiers[0]["taille"], 2)


class LienModeleTests(TestCase):
    def test_nom_et_dossier(self):
        lien = Lien(chemin="OTIS/2026/devis ascenseur.pdf")
        self.assertEqual(lien.nom, "devis ascenseur.pdf")
        self.assertEqual(lien.dossier, "OTIS › 2026")
        self.assertEqual(lien.dossier_relatif, "OTIS/2026")
        self.assertEqual(Lien(chemin="note.pdf").dossier_relatif, "")
        self.assertEqual(Lien(chemin="Dupont.SA/note.pdf").dossier_relatif, "Dupont.SA")

    def test_un_seul_lien_par_fichier_et_affaire(self):
        affaire = Affaire.objects.create(titre="Ascenseur")
        Lien.objects.create(affaire=affaire, chemin="OTIS/2026/devis.pdf")
        with self.assertRaises(IntegrityError):
            Lien.objects.create(affaire=affaire, chemin="OTIS/2026/devis.pdf")

    def test_supprimer_l_affaire_supprime_ses_liens(self):
        affaire = Affaire.objects.create(titre="Ascenseur")
        Lien.objects.create(affaire=affaire, chemin="OTIS/2026/devis.pdf")
        affaire.delete()
        self.assertFalse(Lien.objects.exists())


class Partage(TestCase):
    """Une racine temporaire : OTIS/2026 avec deux fichiers, un exécutable,
    Autres/ vide ; une affaire avec Otis rattachée à son dossier."""

    def setUp(self):
        self.client.force_login(Utilisateur.objects.create_user("responsable"))
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.racine = Path(temporaire.name) / "Batiment"
        (self.racine / "OTIS" / "2026").mkdir(parents=True)
        (self.racine / "OTIS" / "2025").mkdir()
        (self.racine / "Autres").mkdir()
        (self.racine / "OTIS" / "2026" / "devis.pdf").write_text("devis")
        (self.racine / "OTIS" / "2026" / "rapport.docx").write_text("rapport")
        (self.racine / "OTIS" / "2026" / "piege.exe").write_text("MZ")
        Reglages(racine=str(self.racine)).save()
        self.otis = Entreprise.objects.create(nom="Otis", dossier="OTIS")
        self.affaire = Affaire.objects.create(titre="Ascenseur bruyant")
        Intervenant.objects.create(affaire=self.affaire, entreprise=self.otis)

    def explorer(self, **params):
        return self.client.get(reverse("explorateur", args=[self.affaire.pk]), params)

    def lier(self, *chemins, **params):
        url = reverse("explorateur", args=[self.affaire.pk])
        return self.client.post(url, {"fichiers": list(chemins), **params})

    def fiche(self):
        return self.client.get(reverse("affaire", args=[self.affaire.pk]))


class ExplorateurTests(Partage):
    def test_part_du_dossier_de_l_entreprise(self):
        reponse = self.explorer()
        self.assertEqual(reponse.context["courant"], "OTIS")
        contenu = reponse.content.decode()
        self.assertLess(contenu.index(">2026<"), contenu.index(">2025<"))

    def test_plusieurs_entreprises_part_de_la_racine(self):
        autre = Entreprise.objects.create(nom="Autres", dossier="Autres")
        Intervenant.objects.create(affaire=self.affaire, entreprise=autre)
        reponse = self.explorer()
        self.assertEqual(reponse.context["courant"], "")
        self.assertContains(reponse, "Dossiers des entreprises de l'affaire")

    def test_liste_les_fichiers(self):
        reponse = self.explorer(d="OTIS/2026")
        self.assertContains(reponse, 'value="OTIS/2026/devis.pdf"')
        self.assertNotContains(reponse, 'value="OTIS/2026/piege.exe"')  # visible, pas sélectionnable
        self.assertContains(reponse, "piege.exe")

    def test_ne_remonte_pas_au_dessus_de_la_racine(self):
        reponse = self.explorer(d="../..")
        self.assertEqual(reponse.context["courant"], "")
        self.assertEqual(reponse.context["parent"], None)

    def test_dossier_introuvable(self):
        reponse = self.explorer(d="OTIS/2019")
        self.assertEqual(reponse.context["courant"], "")
        self.assertContains(reponse, "Dossier introuvable : OTIS/2019")

    def test_partage_indisponible(self):
        Reglages(racine=str(self.racine / "deconnecte")).save()
        reponse = self.explorer(follow=False)
        self.assertRedirects(reponse, reverse("affaire", args=[self.affaire.pk]) + "#documents", fetch_redirect_response=False)

    def test_sans_racine(self):
        Reglages(racine="").save()
        self.assertRedirects(self.explorer(), reverse("reglages"))


class LierTests(Partage):
    def test_lier_plusieurs_fichiers(self):
        reponse = self.lier("OTIS/2026/devis.pdf", "OTIS/2026/rapport.docx")
        self.assertRedirects(
            reponse, reverse("affaire", args=[self.affaire.pk]) + "#documents", fetch_redirect_response=False
        )
        self.assertEqual(
            sorted(self.affaire.liens.values_list("chemin", flat=True)),
            ["OTIS/2026/devis.pdf", "OTIS/2026/rapport.docx"],
        )

    def test_deja_lie_coche_et_grise(self):
        self.lier("OTIS/2026/devis.pdf")
        reponse = self.explorer(d="OTIS/2026")
        self.assertContains(reponse, "devis.pdf (déjà lié)")
        self.lier("OTIS/2026/devis.pdf")
        self.assertEqual(self.affaire.liens.count(), 1)

    def test_chemins_refuses(self):
        self.lier("OTIS/2026/piege.exe", "../secret.pdf", "OTIS/2026/absent.pdf", "C:\\Windows\\win.ini")
        self.assertFalse(self.affaire.liens.exists())

    def test_fiche_affiche_les_documents(self):
        self.lier("OTIS/2026/devis.pdf")
        reponse = self.fiche()
        self.assertContains(reponse, "devis.pdf")
        self.assertContains(reponse, "OTIS › 2026")
        self.assertContains(reponse, reverse("lien_ouvrir", args=[self.affaire.liens.get().pk]))

    def test_recherche_par_nom_de_fichier(self):
        self.lier("OTIS/2026/devis.pdf")
        reponse = self.client.get(reverse("historique"), {"q": "devis.pdf"})
        self.assertContains(reponse, "Ascenseur bruyant")


class OuvrirTests(Partage):
    def setUp(self):
        super().setUp()
        self.lien = Lien.objects.create(affaire=self.affaire, chemin="OTIS/2026/devis.pdf")

    def post(self, nom, lien=None):
        return self.client.post(reverse(nom, args=[(lien or self.lien).pk]), follow=True)

    def test_ouvrir(self):
        with mock.patch("suivi.views.ouvrir") as ouvrir:
            self.post("lien_ouvrir")
        ouvrir.assert_called_once_with(self.racine / "OTIS" / "2026" / "devis.pdf")

    def test_montrer_dans_le_dossier(self):
        with mock.patch("suivi.views.montrer") as montrer:
            self.post("lien_montrer")
        montrer.assert_called_once_with(self.racine / "OTIS" / "2026" / "devis.pdf")

    def test_ouvrir_exige_un_post(self):
        with mock.patch("suivi.views.ouvrir") as ouvrir:
            self.client.get(reverse("lien_ouvrir", args=[self.lien.pk]))
        ouvrir.assert_not_called()

    def test_executable_jamais_ouvert(self):
        # Même enregistré à la main en base, un exécutable n'est pas ouvert.
        piege = Lien.objects.create(affaire=self.affaire, chemin="OTIS/2026/piege.exe")
        with mock.patch("suivi.views.ouvrir") as ouvrir:
            reponse = self.post("lien_ouvrir", piege)
        ouvrir.assert_not_called()
        self.assertContains(reponse, "jamais ouvert par l&#x27;outil")

    def test_chemin_hors_racine_jamais_ouvert(self):
        piege = Lien.objects.create(affaire=self.affaire, chemin="../../Windows/win.ini")
        with mock.patch("suivi.views.ouvrir") as ouvrir:
            self.post("lien_ouvrir", piege)
        ouvrir.assert_not_called()

    def test_fichier_introuvable_puis_relier(self):
        (self.racine / "OTIS" / "2026" / "devis.pdf").rename(self.racine / "OTIS" / "2026" / "devis-v2.pdf")
        reponse = self.fiche()
        self.assertContains(reponse, "· introuvable")
        self.assertContains(reponse, f"?relier={self.lien.pk}")
        with mock.patch("suivi.views.ouvrir") as ouvrir:
            reponse = self.post("lien_ouvrir")
        ouvrir.assert_not_called()
        self.assertContains(reponse, "Fichier introuvable : devis.pdf")

        # « Relier » part de l'ancien dossier et propose un choix unique.
        reponse = self.explorer(relier=self.lien.pk)
        self.assertEqual(reponse.context["courant"], "OTIS/2026")
        self.assertContains(reponse, 'type="radio" name="fichiers" value="OTIS/2026/devis-v2.pdf"')
        self.lier("OTIS/2026/devis-v2.pdf", relier=self.lien.pk)
        self.lien.refresh_from_db()
        self.assertEqual(self.lien.chemin, "OTIS/2026/devis-v2.pdf")

    def test_relier_sans_choisir_reste_en_mode_relier(self):
        reponse = self.lier(relier=self.lien.pk)
        url = reverse("explorateur", args=[self.affaire.pk])
        self.assertRedirects(reponse, f"{url}?relier={self.lien.pk}", fetch_redirect_response=False)
        self.lien.refresh_from_db()
        self.assertEqual(self.lien.chemin, "OTIS/2026/devis.pdf")

    def test_relier_vers_un_fichier_deja_lie_garde_un_seul_lien(self):
        Lien.objects.create(affaire=self.affaire, chemin="OTIS/2026/rapport.docx")
        self.lier("OTIS/2026/rapport.docx", relier=self.lien.pk)
        self.assertEqual(list(self.affaire.liens.values_list("chemin", flat=True)), ["OTIS/2026/rapport.docx"])

    def test_partage_indisponible(self):
        Reglages(racine=str(self.racine / "deconnecte")).save()
        reponse = self.fiche()
        self.assertContains(reponse, "Partage indisponible")
        self.assertContains(reponse, "devis.pdf")  # le nom reste affiché
        self.assertNotContains(reponse, "· introuvable")  # on ne conclut pas à tort

    def test_retirer_ne_touche_pas_au_fichier(self):
        self.post("lien_retirer")
        self.assertFalse(Lien.objects.exists())
        self.assertTrue((self.racine / "OTIS" / "2026" / "devis.pdf").exists())
