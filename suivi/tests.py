from django.test import TestCase
from django.urls import reverse

from comptes.models import Utilisateur


class AccesTests(TestCase):
    """Toutes les pages exigent d'être connecté, sauf la page de connexion."""

    def test_accueil_redirige_vers_connexion(self):
        reponse = self.client.get(reverse("accueil"))
        self.assertRedirects(reponse, f"{reverse('connexion')}?next=/")

    def test_page_connexion_accessible(self):
        reponse = self.client.get(reverse("connexion"))
        self.assertEqual(reponse.status_code, 200)

    def test_accueil_apres_connexion(self):
        utilisateur = Utilisateur.objects.create_user("responsable", password="essai")
        self.client.force_login(utilisateur)
        reponse = self.client.get(reverse("accueil"))
        self.assertEqual(reponse.status_code, 200)

    def test_deconnexion(self):
        utilisateur = Utilisateur.objects.create_user("responsable", password="essai")
        self.client.force_login(utilisateur)
        reponse = self.client.post(reverse("deconnexion"))
        self.assertRedirects(reponse, reverse("connexion"))
        reponse = self.client.get(reverse("accueil"))
        self.assertEqual(reponse.status_code, 302)
