from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comptes.models import Utilisateur

from .models import Action, Affaire, Contact, EntreeJournal, Entreprise, Intervenant


class HistoriqueTests(TestCase):
    def setUp(self):
        self.client.force_login(Utilisateur.objects.create_user("responsable"))
        self.otis = Entreprise.objects.create(nom="Otis")
        self.dupont = Contact.objects.create(entreprise=self.otis, nom="Dupont")
        self.ouverte = Affaire.objects.create(titre="Ascenseur bruyant")
        self.close = Affaire.objects.create(
            titre="Fuite hall", statut=Affaire.Statut.CLOS, point_situation="Réparée"
        )
        Intervenant.objects.create(affaire=self.close, entreprise=self.otis)

    def get(self, **params):
        return self.client.get(reverse("historique"), params)

    def test_toutes_par_defaut(self):
        reponse = self.get()
        self.assertContains(reponse, "Ascenseur bruyant")
        self.assertContains(reponse, "Fuite hall")
        self.assertContains(reponse, "2 affaires")

    def test_filtre_closes(self):
        reponse = self.get(statut="closes")
        self.assertContains(reponse, "Fuite hall")
        self.assertNotContains(reponse, "Ascenseur bruyant")

    def test_filtre_ouvertes(self):
        reponse = self.get(statut="ouvertes")
        self.assertContains(reponse, "Ascenseur bruyant")
        self.assertNotContains(reponse, "Fuite hall")

    def test_filtre_inconnu_ignore(self):
        self.assertContains(self.get(statut="nimporte"), "2 affaires")

    def test_recherche_par_entreprise_trouve_une_affaire_close(self):
        reponse = self.get(q="otis")
        self.assertContains(reponse, "Fuite hall")
        self.assertNotContains(reponse, "Ascenseur bruyant")

    def test_recherche_par_contact(self):
        Intervenant.objects.create(affaire=self.ouverte, entreprise=self.otis, contact=self.dupont)
        reponse = self.get(q="dupont")
        self.assertContains(reponse, "Ascenseur bruyant")
        self.assertNotContains(reponse, "Fuite hall")

    def test_recherche_dans_le_journal_et_les_actions(self):
        EntreeJournal.objects.create(affaire=self.ouverte, texte="Câble de traction usé")
        Action.objects.create(affaire=self.close, date=timezone.localdate(), quoi="Rappeler le syndic")
        self.assertContains(self.get(q="traction"), "Ascenseur bruyant")
        self.assertContains(self.get(q="syndic"), "Fuite hall")

    def test_pas_de_doublon_quand_plusieurs_chemins_correspondent(self):
        Intervenant.objects.create(affaire=self.close, entreprise=self.otis, contact=self.dupont)
        EntreeJournal.objects.create(affaire=self.close, texte="Otis est passé")
        reponse = self.get(q="otis")
        self.assertContains(reponse, "1 affaire")
        # L'entreprise n'est listée qu'une fois, malgré ses deux lignes.
        self.assertContains(reponse, "<td>Otis</td>", html=False)

    def test_recherche_sans_resultat(self):
        self.assertContains(self.get(q="plomberie"), "Aucune affaire ne correspond.")

    def test_retour_depuis_une_affaire_close(self):
        reponse = self.client.get(reverse("affaire", args=[self.close.pk]))
        self.assertContains(reponse, "← Historique")
        reponse = self.client.get(reverse("affaire", args=[self.ouverte.pk]))
        self.assertContains(reponse, "← Vue d'ensemble")

    def test_lien_dans_le_menu(self):
        reponse = self.client.get(reverse("accueil"))
        self.assertContains(reponse, f'href="{reverse("historique")}"')


class FicheEntrepriseAffairesTests(TestCase):
    def setUp(self):
        self.client.force_login(Utilisateur.objects.create_user("responsable"))
        self.otis = Entreprise.objects.create(nom="Otis")

    def test_affaires_ouvertes_puis_closes(self):
        close = Affaire.objects.create(titre="Ancienne panne", statut=Affaire.Statut.CLOS)
        ouverte = Affaire.objects.create(titre="Panne en cours")
        Intervenant.objects.create(affaire=close, entreprise=self.otis)
        Intervenant.objects.create(affaire=ouverte, entreprise=self.otis)
        contenu = self.client.get(reverse("entreprise", args=[self.otis.pk])).content.decode()
        self.assertLess(contenu.index("Panne en cours"), contenu.index("Ancienne panne"))
        self.assertIn("Close le", contenu)

    def test_affaire_listee_une_fois_avec_deux_contacts(self):
        affaire = Affaire.objects.create(titre="Chantier marches")
        for nom in ["Maçon", "Plâtrier"]:
            contact = Contact.objects.create(entreprise=self.otis, nom=nom)
            Intervenant.objects.create(affaire=affaire, entreprise=self.otis, contact=contact)
        contenu = self.client.get(reverse("entreprise", args=[self.otis.pk])).content.decode()
        self.assertEqual(contenu.count("Chantier marches"), 1)

    def test_aucune_affaire(self):
        reponse = self.client.get(reverse("entreprise", args=[self.otis.pk]))
        self.assertContains(reponse, "Aucune affaire.")
