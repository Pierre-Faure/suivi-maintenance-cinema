"""Formulaires de l'outil."""

from datetime import timedelta
from email.utils import parseaddr

from django import forms
from django.utils import timezone

from .models import Action, Affaire, Contact, EntreeJournal, Entreprise, Intervenant, Reglages
from .partage import HorsRacine, chemin_dans_racine


def champ_date():
    """Calendrier du navigateur ; la valeur envoyée est au format AAAA-MM-JJ."""
    return forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class EmailSouple(forms.EmailField):
    """Champ email qui accepte aussi une adresse copiée depuis Outlook.

    « Jean Dupont <jean.dupont@otis.fr> » devient « jean.dupont@otis.fr ».
    """

    def to_python(self, value):
        value = super().to_python(value)
        if "<" in value:
            adresse = parseaddr(value)[1]
            if adresse:
                return adresse
        return value


# --- Annuaire -----------------------------------------------------------------


class EntrepriseForm(forms.ModelForm):
    class Meta:
        model = Entreprise
        fields = ["nom", "telephone", "email", "notes"]
        field_classes = {"email": EmailSouple}
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}

    def clean_nom(self):
        """Évite les doublons : « Otis » et « OTIS » sont la même entreprise."""
        nom = self.cleaned_data["nom"].strip()
        doublons = Entreprise.objects.filter(nom__iexact=nom).exclude(pk=self.instance.pk)
        if doublons.exists():
            raise forms.ValidationError(
                "Une entreprise porte déjà ce nom dans l'annuaire."
            )
        return nom


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ["nom", "fonction", "telephone", "email"]
        field_classes = {"email": EmailSouple}


# --- Affaires -----------------------------------------------------------------


class AffaireForm(forms.ModelForm):
    class Meta:
        model = Affaire
        fields = ["titre", "statut", "point_situation", "date_debut"]
        widgets = {"date_debut": champ_date()}


class ActionForm(forms.ModelForm):
    """Action d'une affaire : « avec qui » ne propose que ses intervenants."""

    class Meta:
        model = Action
        fields = ["type", "date", "quoi", "avec_qui"]
        widgets = {"date": champ_date()}

    def __init__(self, *args, affaire, **kwargs):
        super().__init__(*args, **kwargs)
        # Rattachée avant validation : Action.clean() vérifie « avec qui ».
        self.instance.affaire = affaire
        self.fields["avec_qui"].queryset = affaire.intervenants.select_related(
            "entreprise", "contact"
        )
        self.fields["avec_qui"].empty_label = "—"
        # Nouvelle action : relance dans une semaine par défaut, modifiable.
        if self.instance.pk is None and not self.is_bound:
            self.initial.setdefault("date", timezone.localdate() + timedelta(days=7))


class NoteForm(forms.ModelForm):
    """Ajout rapide d'une note : le texte seul, datée de maintenant."""

    class Meta:
        model = EntreeJournal
        fields = ["texte"]
        widgets = {"texte": forms.Textarea(attrs={"rows": 2})}
        labels = {"texte": "Nouvelle note"}


class NoteModifierForm(forms.ModelForm):
    """Modification d'une note : texte et date (pour dater une note après coup)."""

    class Meta:
        model = EntreeJournal
        fields = ["texte", "horodatage"]
        widgets = {
            "texte": forms.Textarea(attrs={"rows": 4}),
            "horodatage": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }


class IntervenantContactForm(forms.ModelForm):
    """Change le contact d'une ligne, ou la passe « sans contact particulier »."""

    class Meta:
        model = Intervenant
        fields = ["contact"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contact"].queryset = self.instance.entreprise.contacts.all()
        self.fields["contact"].empty_label = "Sans contact particulier"
        self.fields["contact"].label_from_instance = lambda contact: contact.nom

    def clean_contact(self):
        # L'affaire et l'entreprise ne font pas partie du formulaire : Django ne
        # vérifie donc pas les doublons tout seul. On le fait ici.
        contact = self.cleaned_data["contact"]
        doublon = Intervenant.objects.filter(
            affaire_id=self.instance.affaire_id,
            entreprise_id=self.instance.entreprise_id,
            contact=contact,
        ).exclude(pk=self.instance.pk)
        if doublon.exists():
            raise forms.ValidationError("Cette ligne existe déjà sur l'affaire.")
        return contact


class IntervenantForm(forms.Form):
    """Une seule liste : chaque entreprise, puis chacun de ses contacts.

    Valeurs : « e12 » pour l'entreprise 12 seule, « c34 » pour le contact 34.
    Pas de JavaScript : un choix suffit pour l'entreprise et le contact.
    """

    qui = forms.ChoiceField(label="Entreprise")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choix = [("", "—")]
        for entreprise in Entreprise.objects.prefetch_related("contacts"):
            options = [(f"e{entreprise.pk}", entreprise.nom)]
            options += [
                (f"c{contact.pk}", f"{entreprise.nom} — {contact.nom}")
                for contact in entreprise.contacts.all()
            ]
            choix.append((entreprise.nom, options))
        self.fields["qui"].choices = choix

    def clean_qui(self):
        """Renvoie le couple (entreprise, contact ou None)."""
        valeur = self.cleaned_data["qui"]
        if valeur.startswith("c"):
            contact = Contact.objects.select_related("entreprise").filter(pk=valeur[1:]).first()
            if contact:
                return contact.entreprise, contact
        else:
            entreprise = Entreprise.objects.filter(pk=valeur[1:]).first()
            if entreprise:
                return entreprise, None
        raise forms.ValidationError("Ce choix n'existe plus : rechargez la page.")


# --- Réglages et dossiers -----------------------------------------------------


class ReglagesForm(forms.ModelForm):
    class Meta:
        model = Reglages
        fields = ["racine", "dossier_technique"]

    def clean_racine(self):
        # Un chemin copié avec « Copier en tant que chemin d'accès » est entre guillemets.
        return self.cleaned_data["racine"].strip().strip('"').rstrip("\\/")

    def clean_dossier_technique(self):
        nom = self.cleaned_data["dossier_technique"].strip().strip('"')
        try:
            chemin_dans_racine("racine", nom)
        except HorsRacine:
            raise forms.ValidationError(
                "Indiquez un nom de dossier dans la racine, par exemple « _Suivi des affaires »."
            ) from None
        return nom


class DossierEntrepriseForm(forms.Form):
    """Choix du dossier d'une entreprise parmi les dossiers de la racine."""

    dossier = forms.ChoiceField(label="Dossier sur le partage", required=False)

    def __init__(self, *args, dossiers, actuel="", **kwargs):
        super().__init__(*args, **kwargs)
        choix = [("", "— Aucun —")] + [(nom, nom) for nom in dossiers]
        if actuel and actuel not in dossiers:
            # Dossier enregistré mais introuvable : on le garde visible, signalé.
            choix.append((actuel, f"{actuel} (introuvable)"))
        self.fields["dossier"].choices = choix
        self.initial.setdefault("dossier", actuel)


class ImportForm(forms.Form):
    """Destination et année d'un import. Les fichiers eux-mêmes arrivent à
    part (request.FILES), le champ étant écrit dans le gabarit."""

    destination = forms.ChoiceField(label="Ranger dans")
    annee = forms.ChoiceField(label="Année")

    def __init__(self, *args, destinations, annees, defaut=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["destination"].choices = destinations  # groupées : entreprises, autres dossiers
        self.fields["annee"].choices = [(annee, annee) for annee in annees]
        self.initial.setdefault("destination", defaut)
        self.initial.setdefault("annee", str(timezone.localdate().year))
