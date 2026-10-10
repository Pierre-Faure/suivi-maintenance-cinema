from django.test import TestCase
from django.urls import reverse

from comptes.models import Utilisateur

from .models import Affaire, Contact, Entreprise, Intervenant


class AnnuaireEcransTests(TestCase):
    def setUp(self):
        self.client.force_login(Utilisateur.objects.create_user("responsable"))
        self.otis = Entreprise.objects.create(nom="Otis", notes="Astreinte 24/24")
        self.dupont = Contact.objects.create(entreprise=self.otis, nom="Dupont")
        Entreprise.objects.create(nom="Schindler")

    # --- Liste et recherche ---

    def test_liste(self):
        reponse = self.client.get(reverse("annuaire"))
        self.assertContains(reponse, "Otis")
        self.assertContains(reponse, "Schindler")

    def test_recherche_par_nom_de_contact(self):
        reponse = self.client.get(reverse("annuaire"), {"q": "dupont"})
        self.assertContains(reponse, "Otis")
        self.assertNotContains(reponse, "Schindler")

    def test_recherche_dans_les_notes(self):
        reponse = self.client.get(reverse("annuaire"), {"q": "astreinte"})
        self.assertContains(reponse, "Otis")
        self.assertNotContains(reponse, "Schindler")

    def test_recherche_sans_resultat(self):
        reponse = self.client.get(reverse("annuaire"), {"q": "plombier"})
        self.assertContains(reponse, "Aucune entreprise ne correspond")

    # --- Entreprises ---

    def test_fiche(self):
        reponse = self.client.get(reverse("entreprise", args=[self.otis.pk]))
        self.assertContains(reponse, "Astreinte 24/24")
        self.assertContains(reponse, "Dupont")

    def test_creation(self):
        reponse = self.client.post(
            reverse("entreprise_creer"), {"nom": "Desautel", "telephone": "01 02 03 04 05"}
        )
        desautel = Entreprise.objects.get(nom="Desautel")
        self.assertRedirects(reponse, reverse("entreprise", args=[desautel.pk]))

    def test_creation_refuse_un_doublon(self):
        reponse = self.client.post(reverse("entreprise_creer"), {"nom": "OTIS"})
        self.assertContains(reponse, "Une entreprise porte déjà ce nom")
        self.assertEqual(Entreprise.objects.filter(nom__iexact="otis").count(), 1)

    def test_modification_garde_son_propre_nom(self):
        reponse = self.client.post(
            reverse("entreprise_modifier", args=[self.otis.pk]),
            {"nom": "Otis", "telephone": "09 00 00 00 00"},
        )
        self.assertRedirects(reponse, reverse("entreprise", args=[self.otis.pk]))
        self.otis.refresh_from_db()
        self.assertEqual(self.otis.telephone, "09 00 00 00 00")

    def test_suppression_entreprise_inutilisee(self):
        reponse = self.client.post(reverse("entreprise_supprimer", args=[self.otis.pk]))
        self.assertRedirects(reponse, reverse("annuaire"))
        self.assertFalse(Entreprise.objects.filter(nom="Otis").exists())
        self.assertFalse(Contact.objects.exists())

    def test_suppression_entreprise_utilisee_impossible(self):
        affaire = Affaire.objects.create(titre="Ascenseur")
        Intervenant.objects.create(affaire=affaire, entreprise=self.otis)
        reponse = self.client.get(reverse("entreprise_supprimer", args=[self.otis.pk]))
        self.assertContains(reponse, "Elle intervient sur 1 affaire, listée sur sa fiche.")
        self.client.post(reverse("entreprise_supprimer", args=[self.otis.pk]))
        self.assertTrue(Entreprise.objects.filter(pk=self.otis.pk).exists())

    def test_entreprise_inexistante(self):
        reponse = self.client.get(reverse("entreprise", args=[9999]))
        self.assertEqual(reponse.status_code, 404)

    # --- Contacts ---

    def test_ajout_contact(self):
        reponse = self.client.post(
            reverse("contact_creer", args=[self.otis.pk]), {"nom": "Martin", "fonction": "Technicien"}
        )
        self.assertRedirects(reponse, reverse("entreprise", args=[self.otis.pk]))
        self.assertTrue(self.otis.contacts.filter(nom="Martin").exists())

    def test_modification_contact(self):
        self.client.post(
            reverse("contact_modifier", args=[self.dupont.pk]), {"nom": "Dupont", "telephone": "06"}
        )
        self.dupont.refresh_from_db()
        self.assertEqual(self.dupont.telephone, "06")

    def test_suppression_contact_utilise_impossible(self):
        affaire = Affaire.objects.create(titre="Ascenseur")
        Intervenant.objects.create(affaire=affaire, entreprise=self.otis, contact=self.dupont)
        self.client.post(reverse("contact_supprimer", args=[self.dupont.pk]))
        self.assertTrue(Contact.objects.filter(pk=self.dupont.pk).exists())

    def test_suppression_contact_inutilise(self):
        reponse = self.client.post(reverse("contact_supprimer", args=[self.dupont.pk]))
        self.assertRedirects(reponse, reverse("entreprise", args=[self.otis.pk]))
        self.assertFalse(Contact.objects.exists())

    def test_annuaire_exige_d_etre_connecte(self):
        self.client.logout()
        reponse = self.client.get(reverse("annuaire"))
        self.assertEqual(reponse.status_code, 302)
