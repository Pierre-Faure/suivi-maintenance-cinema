from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comptes.models import Utilisateur

from .models import Action, Affaire
from .vue_ensemble import vue_ensemble

UN_JOUR = timedelta(days=1)


class ProchaineActionTests(TestCase):
    """Ce que la vue d'ensemble affiche pour chaque affaire."""

    def test_prochaine_action_et_autres(self):
        jour = timezone.localdate()
        affaire = Affaire.objects.create(titre="Fuite hall")
        Action.objects.create(affaire=affaire, date=jour + 5 * UN_JOUR, quoi="Passage")
        premiere = Action.objects.create(affaire=affaire, date=jour - 3 * UN_JOUR, quoi="Relancer")
        Action.objects.create(affaire=affaire, date=jour + 9 * UN_JOUR, quoi="Fin")
        Action.objects.create(affaire=affaire, date=jour - 9 * UN_JOUR, quoi="Fait", faite_le=jour)

        affaire_vue = vue_ensemble().en_retard[0]

        self.assertEqual(affaire_vue.prochaine_action, premiere)
        self.assertEqual(affaire_vue.autres_actions, 2)  # l'action faite ne compte pas
        self.assertEqual(affaire_vue.jours_de_retard, 3)

    def test_rien_de_prevu(self):
        Affaire.objects.create(titre="Oubliée")
        affaire_vue = vue_ensemble().rien_de_prevu[0]
        self.assertIsNone(affaire_vue.prochaine_action)
        self.assertEqual(affaire_vue.autres_actions, 0)

    def test_vue_vide(self):
        Affaire.objects.create(titre="Close", statut=Affaire.Statut.CLOS)
        self.assertTrue(vue_ensemble().est_vide)


class AccueilTests(TestCase):
    def setUp(self):
        self.client.force_login(Utilisateur.objects.create_user("responsable"))
        jour = timezone.localdate()
        self.en_retard = Affaire.objects.create(titre="Affaire en retard")
        self.relance = Action.objects.create(
            affaire=self.en_retard, date=jour - 2 * UN_JOUR, quoi="Relancer pour le devis"
        )
        self.du_jour = Affaire.objects.create(titre="Affaire du jour")
        Action.objects.create(affaire=self.du_jour, date=jour, quoi="Passage 9 h")
        self.a_venir = Affaire.objects.create(titre="Affaire à venir")
        Action.objects.create(affaire=self.a_venir, date=jour + 4 * UN_JOUR, quoi="Visite")
        self.oubliee = Affaire.objects.create(titre="Affaire oubliée")

    def test_ordre_des_blocs(self):
        contenu = self.client.get(reverse("accueil")).content.decode()
        positions = [
            contenu.index(titre)
            for titre in ["En retard", "Aujourd&#x27;hui", "À venir", "Rien de prévu"]
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("il y a 2 j", contenu)

    def test_bloc_vide_masque(self):
        self.du_jour.delete()
        reponse = self.client.get(reverse("accueil"))
        self.assertNotContains(reponse, "Aujourd&#x27;hui")

    def test_aucune_affaire(self):
        Affaire.objects.all().delete()
        self.assertContains(self.client.get(reverse("accueil")), "Aucune affaire ouverte.")

    def test_cocher_depuis_la_vue_d_ensemble(self):
        reponse = self.client.post(
            reverse("action_cocher", args=[self.relance.pk]), {"next": reverse("accueil")}
        )
        self.assertRedirects(reponse, reverse("accueil"))
        self.relance.refresh_from_db()
        self.assertIsNotNone(self.relance.faite_le)
        # Plus d'action à faire : l'affaire passe dans « rien de prévu ».
        self.assertIn(self.en_retard, vue_ensemble().rien_de_prevu)

    def test_message_apres_cochage(self):
        reponse = self.client.post(
            reverse("action_cocher", args=[self.relance.pk]),
            {"next": reverse("accueil")},
            follow=True,
        )
        self.assertContains(reponse, "Fait : Relancer pour le devis")

    def test_lien_ajouter_une_action_ouvre_le_formulaire(self):
        url = reverse("affaire", args=[self.oubliee.pk]) + "?ajouter=action"
        self.assertContains(self.client.get(url), 'id="ajouter-action" open')

    def test_fiche_sans_parametre_formulaire_replie(self):
        url = reverse("affaire", args=[self.oubliee.pk])
        self.assertNotContains(self.client.get(url), 'id="ajouter-action" open')
