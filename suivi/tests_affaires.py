from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comptes.models import Utilisateur

from .forms import EntrepriseForm
from .models import Action, Affaire, Contact, EntreeJournal, Entreprise, Intervenant


class Connecte(TestCase):
    def setUp(self):
        self.client.force_login(Utilisateur.objects.create_user("responsable"))
        self.affaire = Affaire.objects.create(titre="Fuite descente d'eau")
        self.otis = Entreprise.objects.create(nom="Otis")
        self.dupont = Contact.objects.create(entreprise=self.otis, nom="Dupont")

    def fiche(self):
        return reverse("affaire", args=[self.affaire.pk])


class AffaireEcransTests(Connecte):
    def test_accueil_liste_les_affaires_ouvertes(self):
        Affaire.objects.create(titre="Ancienne affaire", statut=Affaire.Statut.CLOS)
        reponse = self.client.get(reverse("accueil"))
        self.assertContains(reponse, "Fuite descente d&#x27;eau")
        self.assertNotContains(reponse, "Ancienne affaire")

    def test_creation(self):
        reponse = self.client.post(
            reverse("affaire_creer"),
            {"titre": "Revêtement des marches", "statut": "en_cours", "date_debut": "2026-08-01"},
        )
        affaire = Affaire.objects.get(titre="Revêtement des marches")
        self.assertRedirects(reponse, reverse("affaire", args=[affaire.pk]))
        self.assertEqual(affaire.date_debut, date(2026, 8, 1))

    def test_creation_sans_titre(self):
        reponse = self.client.post(reverse("affaire_creer"), {"statut": "en_cours"})
        self.assertContains(reponse, "Ce champ est obligatoire")

    def test_fiche(self):
        reponse = self.client.get(self.fiche())
        self.assertContains(reponse, "Fuite descente d&#x27;eau")
        self.assertContains(reponse, "Rien de prévu")

    def test_cloture_par_le_formulaire(self):
        self.client.post(
            reverse("affaire_modifier", args=[self.affaire.pk]),
            {"titre": self.affaire.titre, "statut": "clos"},
        )
        self.affaire.refresh_from_db()
        self.assertEqual(self.affaire.date_cloture, timezone.localdate())
        self.assertTrue(self.affaire.journal.filter(automatique=True).exists())

    def test_suppression(self):
        reponse = self.client.post(reverse("affaire_supprimer", args=[self.affaire.pk]))
        self.assertRedirects(reponse, reverse("accueil"))
        self.assertFalse(Affaire.objects.exists())


class IntervenantEcransTests(Connecte):
    def test_ajout_entreprise_seule(self):
        self.client.post(
            reverse("intervenant_ajouter", args=[self.affaire.pk]), {"qui": f"e{self.otis.pk}"}
        )
        intervenant = self.affaire.intervenants.get()
        self.assertEqual(intervenant.entreprise, self.otis)
        self.assertIsNone(intervenant.contact)

    def test_ajout_contact_met_a_jour_l_intervenant_existant(self):
        Intervenant.objects.create(affaire=self.affaire, entreprise=self.otis)
        self.client.post(
            reverse("intervenant_ajouter", args=[self.affaire.pk]), {"qui": f"c{self.dupont.pk}"}
        )
        self.assertEqual(self.affaire.intervenants.get().contact, self.dupont)

    def test_deux_contacts_de_la_meme_entreprise(self):
        martin = Contact.objects.create(entreprise=self.otis, nom="Martin")
        url = reverse("intervenant_ajouter", args=[self.affaire.pk])
        self.client.post(url, {"qui": f"c{self.dupont.pk}"})
        self.client.post(url, {"qui": f"c{martin.pk}"})
        self.assertEqual(self.affaire.intervenants.count(), 2)

    def test_meme_ligne_deux_fois(self):
        url = reverse("intervenant_ajouter", args=[self.affaire.pk])
        self.client.post(url, {"qui": f"c{self.dupont.pk}"})
        self.client.post(url, {"qui": f"c{self.dupont.pk}"})
        self.assertEqual(self.affaire.intervenants.count(), 1)

    def test_passer_sans_contact_garde_les_actions(self):
        intervenant = Intervenant.objects.create(
            affaire=self.affaire, entreprise=self.otis, contact=self.dupont
        )
        action = Action.objects.create(
            affaire=self.affaire, date=timezone.localdate(), quoi="Relancer", avec_qui=intervenant
        )
        reponse = self.client.post(reverse("intervenant_modifier", args=[intervenant.pk]), {"contact": ""})
        self.assertRedirects(reponse, self.fiche() + "#entreprises", fetch_redirect_response=False)
        intervenant.refresh_from_db()
        self.assertIsNone(intervenant.contact)
        action.refresh_from_db()
        self.assertEqual(action.avec_qui, intervenant)

    def test_modifier_vers_une_ligne_existante_refuse(self):
        Intervenant.objects.create(affaire=self.affaire, entreprise=self.otis)
        avec_contact = Intervenant.objects.create(
            affaire=self.affaire, entreprise=self.otis, contact=self.dupont
        )
        reponse = self.client.post(reverse("intervenant_modifier", args=[avec_contact.pk]), {"contact": ""})
        self.assertContains(reponse, "Cette ligne existe déjà sur l&#x27;affaire.")
        avec_contact.refresh_from_db()
        self.assertEqual(avec_contact.contact, self.dupont)

    def test_modifier_ne_propose_que_les_contacts_de_l_entreprise(self):
        schindler = Entreprise.objects.create(nom="Schindler")
        etranger = Contact.objects.create(entreprise=schindler, nom="Durand")
        intervenant = Intervenant.objects.create(affaire=self.affaire, entreprise=self.otis)
        self.client.post(reverse("intervenant_modifier", args=[intervenant.pk]), {"contact": etranger.pk})
        intervenant.refresh_from_db()
        self.assertIsNone(intervenant.contact)

    def test_choix_vide_refuse(self):
        reponse = self.client.post(reverse("intervenant_ajouter", args=[self.affaire.pk]), {"qui": ""})
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(self.affaire.intervenants.exists())

    def test_retrait_conserve_les_actions(self):
        intervenant = Intervenant.objects.create(affaire=self.affaire, entreprise=self.otis)
        action = Action.objects.create(
            affaire=self.affaire, date=timezone.localdate(), quoi="Relancer", avec_qui=intervenant
        )
        self.client.post(reverse("intervenant_retirer", args=[intervenant.pk]))
        action.refresh_from_db()
        self.assertIsNone(action.avec_qui)


class ActionEcransTests(Connecte):
    def test_ajout(self):
        reponse = self.client.post(
            reverse("action_ajouter", args=[self.affaire.pk]),
            {"type": "relance", "date": "2026-10-16", "quoi": "Relancer pour le devis"},
        )
        self.assertRedirects(reponse, self.fiche() + "#actions", fetch_redirect_response=False)
        self.assertEqual(self.affaire.actions.get().date, date(2026, 10, 16))

    def test_ajout_incomplet_reaffiche_la_fiche_avec_l_erreur(self):
        reponse = self.client.post(
            reverse("action_ajouter", args=[self.affaire.pk]), {"type": "relance", "date": "2026-10-16"}
        )
        self.assertContains(reponse, "Ce champ est obligatoire")
        self.assertFalse(Action.objects.exists())

    def test_date_proposee_dans_une_semaine(self):
        reponse = self.client.get(self.fiche())
        dans_une_semaine = timezone.localdate() + timedelta(days=7)
        self.assertContains(reponse, dans_une_semaine.isoformat())

    def test_avec_qui_limite_aux_intervenants_de_l_affaire(self):
        autre = Affaire.objects.create(titre="Autre")
        etranger = Intervenant.objects.create(affaire=autre, entreprise=self.otis)
        self.client.post(
            reverse("action_ajouter", args=[self.affaire.pk]),
            {"type": "relance", "date": "2026-10-16", "quoi": "x", "avec_qui": etranger.pk},
        )
        self.assertFalse(self.affaire.actions.exists())

    def test_cocher_puis_decocher(self):
        action = Action.objects.create(affaire=self.affaire, date=timezone.localdate(), quoi="Relancer")
        self.client.post(reverse("action_cocher", args=[action.pk]))
        action.refresh_from_db()
        self.assertIsNotNone(action.faite_le)
        self.assertEqual(self.affaire.journal.count(), 1)
        self.client.post(reverse("action_cocher", args=[action.pk]))
        action.refresh_from_db()
        self.assertIsNone(action.faite_le)
        self.assertEqual(self.affaire.journal.count(), 0)

    def test_ouvrir_l_adresse_de_cochage_ne_change_rien(self):
        action = Action.objects.create(affaire=self.affaire, date=timezone.localdate(), quoi="Relancer")
        reponse = self.client.get(reverse("action_cocher", args=[action.pk]))
        self.assertEqual(reponse.status_code, 302)
        action.refresh_from_db()
        self.assertIsNone(action.faite_le)

    def test_modification(self):
        action = Action.objects.create(affaire=self.affaire, date=timezone.localdate(), quoi="Relancer")
        self.client.post(
            reverse("action_modifier", args=[action.pk]),
            {"type": "passage", "date": "2026-10-20", "quoi": "Passage 9 h"},
        )
        action.refresh_from_db()
        self.assertEqual(action.quoi, "Passage 9 h")

    def test_suppression(self):
        action = Action.objects.create(affaire=self.affaire, date=timezone.localdate(), quoi="Relancer")
        self.client.post(reverse("action_supprimer", args=[action.pk]))
        self.assertFalse(Action.objects.exists())


class JournalEcransTests(Connecte):
    def test_ajout_note(self):
        self.client.post(reverse("note_ajouter", args=[self.affaire.pk]), {"texte": "Constat fait"})
        note = self.affaire.journal.get()
        self.assertFalse(note.automatique)

    def test_note_vide_refusee(self):
        reponse = self.client.post(reverse("note_ajouter", args=[self.affaire.pk]), {"texte": ""})
        self.assertContains(reponse, "Ce champ est obligatoire")

    def test_modification_avec_date(self):
        note = EntreeJournal.objects.create(affaire=self.affaire, texte="Note")
        self.client.post(
            reverse("note_modifier", args=[note.pk]),
            {"texte": "Note corrigée", "horodatage": "2026-08-12T14:30"},
        )
        note.refresh_from_db()
        self.assertEqual(note.texte, "Note corrigée")
        self.assertEqual(timezone.localtime(note.horodatage).date(), date(2026, 8, 12))

    def test_suppression(self):
        note = EntreeJournal.objects.create(affaire=self.affaire, texte="Note")
        self.client.post(reverse("note_supprimer", args=[note.pk]))
        self.assertFalse(EntreeJournal.objects.exists())

    def test_entree_automatique_intouchable(self):
        auto = EntreeJournal.objects.create(affaire=self.affaire, texte="Statut", automatique=True)
        self.assertEqual(self.client.get(reverse("note_modifier", args=[auto.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("note_supprimer", args=[auto.pk])).status_code, 404)


class EntrepriseDepuisAffaireTests(Connecte):
    def test_creation_revient_a_l_affaire(self):
        reponse = self.client.post(
            reverse("entreprise_creer") + f"?next={self.fiche()}", {"nom": "Desautel"}
        )
        self.assertRedirects(reponse, self.fiche())

    def test_retour_externe_ignore(self):
        reponse = self.client.post(
            reverse("entreprise_creer") + "?next=https://exemple.com/", {"nom": "Desautel"}
        )
        entreprise = Entreprise.objects.get(nom="Desautel")
        self.assertRedirects(reponse, reverse("entreprise", args=[entreprise.pk]))


class EmailSoupleTests(TestCase):
    def test_adresse_copiee_depuis_outlook(self):
        form = EntrepriseForm({"nom": "Otis", "email": "Jean Dupont <jean.dupont@otis.fr>"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["email"], "jean.dupont@otis.fr")

    def test_adresse_invalide_message_en_francais(self):
        form = EntrepriseForm({"nom": "Otis", "email": "jean.dupont"})
        self.assertFalse(form.is_valid())
        self.assertIn("Saisissez une adresse de courriel valide.", form.errors["email"])


class ThemeTests(Connecte):
    def test_cycle_systeme_clair_sombre(self):
        self.client.post(reverse("theme"), {"next": "/annuaire/"})
        self.assertEqual(self.client.cookies["theme"].value, "light")
        self.assertContains(self.client.get(reverse("accueil")), 'data-theme="light"')
        self.client.post(reverse("theme"))
        self.assertEqual(self.client.cookies["theme"].value, "dark")
        self.client.post(reverse("theme"))
        self.assertEqual(self.client.cookies["theme"].value, "")
        self.assertNotContains(self.client.get(reverse("accueil")), "data-theme")

    def test_retour_a_la_page_courante(self):
        reponse = self.client.post(reverse("theme"), {"next": "/annuaire/"})
        self.assertRedirects(reponse, "/annuaire/")
