import tempfile
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from .models import Entreprise, Lien, Reglages
from .partage import deposer, nom_sur
from .tests_liens import Partage


def envoi(nom, contenu=b"contenu"):
    return SimpleUploadedFile(nom, contenu)


class DeposerTests(SimpleTestCase):
    def setUp(self):
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.dossier = Path(temporaire.name) / "OTIS"
        self.dossier.mkdir()

    def test_nom_sur(self):
        self.assertEqual(nom_sur("devis.pdf"), "devis.pdf")
        self.assertEqual(nom_sur("..\\..\\Windows\\devis.pdf"), "devis.pdf")
        self.assertEqual(nom_sur("../../etc/passwd"), "passwd")
        self.assertEqual(nom_sur('devis:v2 "final"?.pdf'), "devis_v2 _final__.pdf")
        self.assertEqual(nom_sur("CON.pdf"), "_CON.pdf")
        self.assertEqual(nom_sur("..."), "document")

    def test_copie_dans_le_dossier_de_l_annee_cree_si_besoin(self):
        chemin, copie = deposer(envoi("devis.pdf"), self.dossier / "2026")
        self.assertTrue(copie)
        self.assertEqual(chemin, self.dossier / "2026" / "devis.pdf")
        self.assertEqual(chemin.read_bytes(), b"contenu")

    def test_ne_cree_pas_une_destination_absente(self):
        with self.assertRaises(FileNotFoundError):
            deposer(envoi("devis.pdf"), self.dossier.parent / "Inconnu" / "2026")

    def test_fichier_identique_deja_present_meme_sous_un_autre_nom(self):
        (self.dossier / "Devis OTIS.pdf").write_bytes(b"contenu")
        chemin, copie = deposer(envoi("devis.pdf"), self.dossier)
        self.assertFalse(copie)
        self.assertEqual(chemin.name, "Devis OTIS.pdf")
        self.assertEqual(len(list(self.dossier.iterdir())), 1)

    def test_meme_nom_contenu_different_suffixe(self):
        (self.dossier / "devis.pdf").write_bytes(b"ancien")
        (self.dossier / "devis (2).pdf").write_bytes(b"autre!")
        chemin, copie = deposer(envoi("devis.pdf", b"nouveau"), self.dossier)
        self.assertTrue(copie)
        self.assertEqual(chemin.name, "devis (3).pdf")
        self.assertEqual((self.dossier / "devis.pdf").read_bytes(), b"ancien")  # jamais écrasé

    def test_copie_interrompue_effacee(self):
        fichier = envoi("devis.pdf")
        with mock.patch.object(fichier, "chunks", side_effect=OSError("réseau coupé")):
            with self.assertRaises(OSError):
                deposer(fichier, self.dossier)
        self.assertEqual(list(self.dossier.iterdir()), [])


class ImportTests(Partage):
    """Racine : OTIS/2026, OTIS/2025, Autres ; Otis sur l'affaire."""

    def setUp(self):
        super().setUp()
        (self.racine / "Sinistres").mkdir()
        (self.racine / "Desautel").mkdir()
        Entreprise.objects.create(nom="Desautel", dossier="Desautel")  # pas sur l'affaire
        self.annee = str(timezone.localdate().year)

    def importer(self, *fichiers, destination="OTIS", annee="2026", follow=False):
        url = reverse("importer", args=[self.affaire.pk])
        donnees = {"fichiers": list(fichiers), "destination": destination, "annee": annee}
        return self.client.post(url, donnees, follow=follow)

    def test_formulaire_sur_la_fiche(self):
        reponse = self.fiche()
        form = reponse.context["form_import"]
        groupes = dict(form.fields["destination"].choices)
        self.assertEqual(groupes["Entreprises de l'affaire"], [("OTIS", "Otis")])
        self.assertEqual(groupes["Autres dossiers"], [("Autres", "Autres"), ("Sinistres", "Sinistres")])
        self.assertEqual(form.initial["destination"], "OTIS")
        annees = [a for a, _ in form.fields["annee"].choices]
        self.assertIn("2025", annees)
        self.assertEqual(annees, sorted(annees, reverse=True))
        self.assertEqual(form.initial["annee"], self.annee)
        self.assertContains(reponse, 'enctype="multipart/form-data"')

    def test_sans_entreprise_autres_par_defaut(self):
        self.affaire.intervenants.all().delete()
        form = self.fiche().context["form_import"]
        self.assertEqual(form.initial["destination"], "Autres")

    def test_import_et_lien(self):
        reponse = self.importer(envoi("devis poulie.pdf"), envoi("photo.jpg", b"jpg"), follow=True)
        self.assertTrue((self.racine / "OTIS" / "2026" / "devis poulie.pdf").is_file())
        self.assertEqual(
            sorted(self.affaire.liens.values_list("chemin", flat=True)),
            ["OTIS/2026/devis poulie.pdf", "OTIS/2026/photo.jpg"],
        )
        self.assertContains(reponse, "2 fichiers importés dans OTIS › 2026")

    def test_dossier_transverse_et_annee_creee(self):
        self.importer(envoi("constat.pdf"), destination="Sinistres", annee=self.annee)
        self.assertTrue((self.racine / "Sinistres" / self.annee / "constat.pdf").is_file())
        self.assertTrue(Lien.objects.filter(chemin=f"Sinistres/{self.annee}/constat.pdf").exists())

    def test_doublon_lie_sans_copie(self):
        # OTIS/2026/devis.pdf (« devis ») existe déjà : voir Partage.
        reponse = self.importer(envoi("Devis-recu.pdf", b"devis"), follow=True)
        self.assertFalse((self.racine / "OTIS" / "2026" / "Devis-recu.pdf").exists())
        self.assertEqual(list(self.affaire.liens.values_list("chemin", flat=True)), ["OTIS/2026/devis.pdf"])
        self.assertContains(reponse, "lié sans copie : devis.pdf")

    def test_programme_refuse(self):
        reponse = self.importer(envoi("outil.exe", b"MZ"), envoi("ok.pdf"), follow=True)
        self.assertFalse((self.racine / "OTIS" / "2026" / "outil.exe").exists())
        self.assertTrue((self.racine / "OTIS" / "2026" / "ok.pdf").exists())
        self.assertContains(reponse, "outil.exe (programme)")

    def test_trop_volumineux(self):
        with mock.patch("suivi.views.TAILLE_MAX", 3):
            self.importer(envoi("gros.pdf", b"1234"))
        self.assertFalse((self.racine / "OTIS" / "2026" / "gros.pdf").exists())
        self.assertFalse(Lien.objects.exists())

    def test_destination_hors_liste_refusee(self):
        for destination in ["Desautel", "../..", "OTIS/2026/../../.."]:
            reponse = self.importer(envoi("x.pdf"), destination=destination)
            self.assertEqual(reponse.status_code, 200)  # fiche réaffichée avec l'erreur
        self.assertFalse(list((self.racine / "Desautel").iterdir()))
        self.assertFalse(Lien.objects.exists())

    def test_annee_hors_liste_refusee(self):
        self.importer(envoi("x.pdf"), annee="../..")
        self.importer(envoi("x.pdf"), annee="1990")
        self.assertFalse(Lien.objects.exists())

    def test_sans_fichier(self):
        reponse = self.importer()
        self.assertContains(reponse, "Choisissez ou déposez au moins un fichier.")
        self.assertContains(reponse, '<details id="importer" open>')

    def test_partage_indisponible(self):
        Reglages(racine=str(self.racine / "deconnecte")).save()
        self.assertIsNone(self.fiche().context["form_import"])
        reponse = self.importer(envoi("x.pdf"))
        self.assertRedirects(
            reponse, reverse("affaire", args=[self.affaire.pk]) + "#documents", fetch_redirect_response=False
        )
