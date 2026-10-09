from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from .models import Action, Affaire, Contact, EntreeJournal, Entreprise, Intervenant
from .vue_ensemble import vue_ensemble

UN_JOUR = timedelta(days=1)


class AffaireTests(TestCase):
    def test_cloture_remplit_la_date_et_trace_au_journal(self):
        affaire = Affaire.objects.create(titre="Fuite hall")
        affaire.statut = Affaire.Statut.CLOS
        affaire.save()
        self.assertEqual(affaire.date_cloture, timezone.localdate())
        entree = affaire.journal.get()
        self.assertTrue(entree.automatique)
        self.assertEqual(entree.texte, "Statut : En cours → Clos")

    def test_reouverture_vide_la_date_de_cloture(self):
        affaire = Affaire.objects.create(titre="Fuite hall", statut=Affaire.Statut.CLOS)
        affaire.statut = Affaire.Statut.EN_COURS
        affaire.save()
        self.assertIsNone(affaire.date_cloture)
        self.assertEqual(affaire.journal.count(), 1)

    def test_creation_directement_close_sans_trace(self):
        affaire = Affaire.objects.create(titre="Ampoule", statut=Affaire.Statut.CLOS)
        self.assertEqual(affaire.date_cloture, timezone.localdate())
        self.assertFalse(affaire.journal.exists())

    def test_date_de_cloture_saisie_conservee(self):
        affaire = Affaire.objects.create(
            titre="Ampoule", statut=Affaire.Statut.CLOS, date_cloture=date(2026, 8, 15)
        )
        self.assertEqual(affaire.date_cloture, date(2026, 8, 15))

    def test_modification_sans_changement_de_statut(self):
        affaire = Affaire.objects.create(titre="Fuite hall")
        affaire.point_situation = "Devis demandé"
        affaire.save()
        self.assertFalse(affaire.journal.exists())

    def test_suppression_emporte_actions_intervenants_et_journal(self):
        affaire = Affaire.objects.create(titre="Fuite hall")
        otis = Entreprise.objects.create(nom="Otis")
        Intervenant.objects.create(affaire=affaire, entreprise=otis)
        Action.objects.create(affaire=affaire, date=timezone.localdate(), quoi="Relancer")
        EntreeJournal.objects.create(affaire=affaire, texte="Note")
        affaire.delete()
        self.assertFalse(Intervenant.objects.exists())
        self.assertFalse(Action.objects.exists())
        self.assertFalse(EntreeJournal.objects.exists())
        self.assertTrue(Entreprise.objects.exists())


class ActionTests(TestCase):
    def setUp(self):
        self.affaire = Affaire.objects.create(titre="Fuite hall")
        self.action = Action.objects.create(
            affaire=self.affaire, date=timezone.localdate(), quoi="Relancer pour le devis"
        )

    def test_cocher(self):
        self.action.cocher()
        self.action.refresh_from_db()
        self.assertEqual(self.action.faite_le, timezone.localdate())
        entree = self.affaire.journal.get()
        self.assertTrue(entree.automatique)
        self.assertEqual(entree.action, self.action)
        self.assertEqual(entree.texte, "Fait : relance — Relancer pour le devis")

    def test_cocher_deux_fois_ne_trace_qu_une_fois(self):
        self.action.cocher()
        self.action.cocher()
        self.assertEqual(self.affaire.journal.count(), 1)

    def test_decocher_retire_la_trace(self):
        self.action.cocher()
        self.action.decocher()
        self.action.refresh_from_db()
        self.assertIsNone(self.action.faite_le)
        self.assertFalse(self.affaire.journal.exists())

    def test_decocher_conserve_les_notes(self):
        EntreeJournal.objects.create(affaire=self.affaire, texte="Note manuelle")
        self.action.cocher()
        self.action.decocher()
        self.assertEqual(self.affaire.journal.get().texte, "Note manuelle")

    def test_supprimer_une_action_retire_sa_trace(self):
        self.action.cocher()
        self.action.delete()
        self.assertFalse(self.affaire.journal.exists())

    def test_en_retard(self):
        hier = Action(affaire=self.affaire, date=timezone.localdate() - UN_JOUR, quoi="x")
        self.assertTrue(hier.en_retard)
        self.assertFalse(self.action.en_retard)  # prévue aujourd'hui
        hier.faite_le = timezone.localdate()
        self.assertFalse(hier.en_retard)

    def test_avec_qui_doit_intervenir_sur_l_affaire(self):
        autre = Affaire.objects.create(titre="Autre affaire")
        otis = Entreprise.objects.create(nom="Otis")
        self.action.avec_qui = Intervenant.objects.create(affaire=autre, entreprise=otis)
        with self.assertRaises(ValidationError):
            self.action.full_clean()


class AnnuaireTests(TestCase):
    def setUp(self):
        self.affaire = Affaire.objects.create(titre="Ascenseur")
        self.otis = Entreprise.objects.create(nom="Otis")
        self.dupont = Contact.objects.create(entreprise=self.otis, nom="M. Dupont")

    def test_contact_doit_appartenir_a_l_entreprise(self):
        schindler = Entreprise.objects.create(nom="Schindler")
        intervenant = Intervenant(affaire=self.affaire, entreprise=schindler, contact=self.dupont)
        with self.assertRaises(ValidationError):
            intervenant.full_clean()

    def test_une_entreprise_une_fois_par_affaire(self):
        Intervenant.objects.create(affaire=self.affaire, entreprise=self.otis)
        doublon = Intervenant(affaire=self.affaire, entreprise=self.otis)
        with self.assertRaises(ValidationError):
            doublon.full_clean()

    def test_entreprise_utilisee_non_supprimable(self):
        Intervenant.objects.create(affaire=self.affaire, entreprise=self.otis)
        with self.assertRaises(ProtectedError):
            self.otis.delete()

    def test_contact_utilise_non_supprimable(self):
        Intervenant.objects.create(
            affaire=self.affaire, entreprise=self.otis, contact=self.dupont
        )
        with self.assertRaises(ProtectedError):
            self.dupont.delete()

    def test_entreprise_inutilisee_supprimee_avec_ses_contacts(self):
        self.otis.delete()
        self.assertFalse(Contact.objects.exists())


class VueEnsembleTests(TestCase):
    JOUR = date(2026, 10, 9)

    def creer(self, titre, *dates, statut=Affaire.Statut.EN_COURS, faites=()):
        """Crée une affaire avec des actions à faire (dates) et des actions faites."""
        affaire = Affaire.objects.create(titre=titre, statut=statut)
        for jour in dates:
            Action.objects.create(affaire=affaire, date=jour, quoi="À faire")
        for jour in faites:
            Action.objects.create(affaire=affaire, date=jour, quoi="Fait", faite_le=jour)
        return affaire

    def test_classement(self):
        j = self.JOUR
        retard_ancien = self.creer("Retard ancien", j - 5 * UN_JOUR, j + 3 * UN_JOUR)
        retard_recent = self.creer("Retard récent", j - UN_JOUR)
        du_jour = self.creer("Du jour", j)
        rien = self.creer("Rien de prévu")
        tout_fait = self.creer("Tout fait", faites=[j - 2 * UN_JOUR])
        en_attente = self.creer("En attente sans action", statut=Affaire.Statut.EN_ATTENTE)
        plus_tard = self.creer("Plus tard", j + 10 * UN_JOUR)
        bientot = self.creer("Bientôt", j + 2 * UN_JOUR)
        self.creer("Close", j - 3 * UN_JOUR, statut=Affaire.Statut.CLOS)

        vue = vue_ensemble(aujourdhui=j)

        self.assertEqual(vue.en_retard, [retard_ancien, retard_recent])
        self.assertEqual(vue.aujourdhui, [du_jour])
        self.assertCountEqual(vue.rien_de_prevu, [rien, tout_fait, en_attente])
        self.assertEqual(vue.a_venir, [bientot, plus_tard])

    def test_prochaine_date_ignore_les_actions_faites(self):
        self.creer("Affaire", self.JOUR + 5 * UN_JOUR, faites=[self.JOUR - 3 * UN_JOUR])
        vue = vue_ensemble(aujourdhui=self.JOUR)
        self.assertEqual(vue.a_venir[0].prochaine_date, self.JOUR + 5 * UN_JOUR)
