import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from comptes.models import Utilisateur

from .models import Entreprise, Reglages
from .partage import HorsRacine, accessible, chemin_dans_racine, normaliser, proposer_dossier, sous_dossiers


class CheminDansRacineTests(SimpleTestCase):
    def test_chemin_relatif(self):
        self.assertEqual(chemin_dans_racine("/z/Batiment", "Otis"), Path("/z/Batiment/Otis"))
        self.assertEqual(chemin_dans_racine("/z/Batiment", "Otis\\2026\\devis.pdf"), Path("/z/Batiment/Otis/2026/devis.pdf"))

    def test_chemins_refuses(self):
        for chemin in ["", "  ", "..", "Otis/../../Exploitation", "/etc", "\\\\serveur\\partage", "C:\\Windows", "Z:Otis"]:
            with self.subTest(chemin=chemin), self.assertRaises(HorsRacine):
                chemin_dans_racine("/z/Batiment", chemin)


class ProposerDossierTests(SimpleTestCase):
    DOSSIERS = ["Autres", "OTIS", "Plomberie Martin & Fils", "Sinistres", "Desautel Sécurité", "Dupont Elec", "Dupont Plomberie"]

    def test_meme_nom_sans_casse_ni_accents(self):
        self.assertEqual(proposer_dossier("Otis", self.DOSSIERS), "OTIS")
        self.assertEqual(proposer_dossier("desautel securite", self.DOSSIERS), "Desautel Sécurité")

    def test_nom_contenu(self):
        self.assertEqual(proposer_dossier("Plomberie Martin", self.DOSSIERS), "Plomberie Martin & Fils")
        self.assertEqual(proposer_dossier("Desautel", self.DOSSIERS), "Desautel Sécurité")

    def test_ambigu_ou_absent(self):
        self.assertIsNone(proposer_dossier("Dupont", self.DOSSIERS))  # deux candidats
        self.assertIsNone(proposer_dossier("Schindler", self.DOSSIERS))
        self.assertIsNone(proposer_dossier("A", self.DOSSIERS))  # trop court pour deviner

    def test_normaliser(self):
        self.assertEqual(normaliser("Plomberie Martin & Fils"), "plomberiemartinfils")


class PartageTests(SimpleTestCase):
    def test_sous_dossiers_et_inaccessible(self):
        with tempfile.TemporaryDirectory() as racine:
            for nom in ["Otis", "autres", ".cache"]:
                (Path(racine) / nom).mkdir()
            (Path(racine) / "note.txt").write_text("")
            self.assertEqual(sous_dossiers(racine), ["autres", "Otis"])
            self.assertTrue(accessible(racine))
        self.assertEqual(sous_dossiers(racine), [])  # supprimé : comme un Z: déconnecté
        self.assertFalse(accessible(racine))
        self.assertFalse(accessible(None))


class ReglagesTests(TestCase):
    def test_une_seule_ligne(self):
        Reglages(racine="Z:\\Batiment").save()
        Reglages(racine="Y:\\Batiment").save()
        self.assertEqual(Reglages.objects.count(), 1)
        self.assertEqual(Reglages.actuels().racine, "Y:\\Batiment")

    def test_valeurs_par_defaut_sans_ecrire(self):
        reglages = Reglages.actuels()
        self.assertIsNone(reglages.chemin_racine)
        self.assertIsNone(reglages.chemin_sauvegardes)
        self.assertFalse(Reglages.objects.exists())

    def test_dossier_des_sauvegardes(self):
        reglages = Reglages(racine="/z/Batiment")
        self.assertEqual(reglages.chemin_sauvegardes, Path("/z/Batiment/_Suivi des affaires/sauvegardes"))


class Connecte(TestCase):
    """Une racine temporaire avec quelques dossiers, et un utilisateur connecté."""

    def setUp(self):
        self.client.force_login(Utilisateur.objects.create_user("responsable"))
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.racine = Path(temporaire.name)
        for nom in ["Autres", "OTIS", "Sinistres", "_Suivi des affaires"]:
            (self.racine / nom).mkdir()
        self.otis = Entreprise.objects.create(nom="Otis")

    def regler(self, racine=None):
        Reglages(racine=str(racine or self.racine)).save()

    def fiche(self):
        return self.client.get(reverse("entreprise", args=[self.otis.pk]))


class ReglagesEcranTests(Connecte):
    def test_enregistrement(self):
        reponse = self.client.post(
            reverse("reglages"), {"racine": f'"{self.racine}\\"', "dossier_technique": "_Suivi des affaires"}
        )
        self.assertRedirects(reponse, reverse("reglages"))
        self.assertEqual(Reglages.actuels().racine, str(self.racine))  # guillemets et \\ final retirés
        self.assertContains(self.client.get(reverse("reglages")), "Racine accessible : 4 dossiers")

    def test_racine_introuvable_enregistree_avec_avertissement(self):
        reponse = self.client.post(
            reverse("reglages"), {"racine": str(self.racine / "absent"), "dossier_technique": "_Suivi des affaires"},
            follow=True,
        )
        self.assertContains(reponse, "est introuvable ou le partage n&#x27;est pas connecté")
        self.assertTrue(Reglages.actuels().racine.endswith("absent"))

    def test_dossier_technique_hors_racine_refuse(self):
        reponse = self.client.post(reverse("reglages"), {"racine": str(self.racine), "dossier_technique": "..\\ailleurs"})
        self.assertContains(reponse, "Indiquez un nom de dossier dans la racine")

    def test_lien_dans_le_menu(self):
        self.assertContains(self.client.get(reverse("accueil")), f'href="{reverse("reglages")}"')


class DossierEntrepriseTests(Connecte):
    def test_sans_racine(self):
        self.assertContains(self.fiche(), "La racine des documents n'est pas réglée")

    def test_proposition_puis_rattachement(self):
        self.regler()
        self.assertContains(self.fiche(), "Dossier proposé : <code>OTIS</code>", html=False)
        reponse = self.client.post(reverse("entreprise_dossier", args=[self.otis.pk]), {"dossier": "OTIS"})
        self.assertRedirects(reponse, reverse("entreprise", args=[self.otis.pk]))
        self.otis.refresh_from_db()
        self.assertEqual(self.otis.dossier, "OTIS")
        self.assertContains(self.fiche(), "Ouvrir le dossier")

    def test_choix_limite_aux_dossiers_libres(self):
        self.regler()
        Entreprise.objects.create(nom="Assureur", dossier="Sinistres")
        reponse = self.client.get(reverse("entreprise_dossier", args=[self.otis.pk]))
        self.assertContains(reponse, '<option value="Autres">')
        self.assertNotContains(reponse, '<option value="Sinistres">')  # déjà pris
        self.assertNotContains(reponse, '<option value="_Suivi des affaires">')  # dossier technique
        # Un dossier qui n'est pas dans la liste est refusé.
        self.client.post(reverse("entreprise_dossier", args=[self.otis.pk]), {"dossier": "../Exploitation"})
        self.otis.refresh_from_db()
        self.assertEqual(self.otis.dossier, "")

    def test_detacher(self):
        self.regler()
        self.otis.dossier = "OTIS"
        self.otis.save()
        self.client.post(reverse("entreprise_dossier", args=[self.otis.pk]), {"dossier": ""})
        self.otis.refresh_from_db()
        self.assertEqual(self.otis.dossier, "")

    def test_dossier_introuvable(self):
        self.regler()
        self.otis.dossier = "Otis Ascenseurs"  # renommé depuis sur le partage
        self.otis.save()
        self.assertContains(self.fiche(), "introuvable : renommé ou déplacé ?")
        reponse = self.client.get(reverse("entreprise_dossier", args=[self.otis.pk]))
        self.assertContains(reponse, "Otis Ascenseurs (introuvable)")

    def test_partage_indisponible(self):
        self.regler(self.racine / "deconnecte")
        self.otis.dossier = "OTIS"
        self.otis.save()
        self.assertContains(self.fiche(), "Partage indisponible")
        reponse = self.client.get(reverse("entreprise_dossier", args=[self.otis.pk]), follow=True)
        self.assertContains(reponse, "Le partage est indisponible")

    def test_ouvrir_le_dossier(self):
        self.regler()
        self.otis.dossier = "OTIS"
        self.otis.save()
        with mock.patch("suivi.views.ouvrir") as ouvrir:
            self.client.post(reverse("entreprise_ouvrir_dossier", args=[self.otis.pk]))
        ouvrir.assert_called_once_with(self.racine / "OTIS")

    def test_ouvrir_refuse_un_dossier_hors_racine(self):
        self.regler()
        Entreprise.objects.filter(pk=self.otis.pk).update(dossier="../..")  # base modifiée à la main
        with mock.patch("suivi.views.ouvrir") as ouvrir:
            reponse = self.client.post(reverse("entreprise_ouvrir_dossier", args=[self.otis.pk]), follow=True)
        ouvrir.assert_not_called()
        self.assertContains(reponse, "Dossier introuvable")

    def test_ouvrir_exige_un_post(self):
        self.regler()
        self.otis.dossier = "OTIS"
        self.otis.save()
        with mock.patch("suivi.views.ouvrir") as ouvrir:
            self.client.get(reverse("entreprise_ouvrir_dossier", args=[self.otis.pk]))
        ouvrir.assert_not_called()
