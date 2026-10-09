"""Formulaires de l'outil."""

from django import forms

from .models import Contact, Entreprise


class EntrepriseForm(forms.ModelForm):
    class Meta:
        model = Entreprise
        fields = ["nom", "telephone", "email", "notes"]
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
