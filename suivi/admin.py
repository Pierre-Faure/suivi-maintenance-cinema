"""
Administration des données métier : outil technique, pas une interface pour
le responsable. Sert à vérifier les données tant que les écrans n'existent pas.

Attention : modifier « faite le » ici ne passe pas par Action.cocher(),
donc ne crée pas d'entrée de journal.
"""

from django.contrib import admin

from .models import Action, Affaire, Contact, EntreeJournal, Entreprise, Intervenant


class ContactInline(admin.TabularInline):
    model = Contact
    extra = 0


@admin.register(Entreprise)
class EntrepriseAdmin(admin.ModelAdmin):
    list_display = ["nom", "telephone", "email"]
    search_fields = ["nom"]
    inlines = [ContactInline]


class IntervenantInline(admin.TabularInline):
    model = Intervenant
    extra = 0


class ActionInline(admin.TabularInline):
    model = Action
    extra = 0


class EntreeJournalInline(admin.TabularInline):
    model = EntreeJournal
    extra = 0


@admin.register(Affaire)
class AffaireAdmin(admin.ModelAdmin):
    list_display = ["titre", "statut", "point_situation", "date_debut", "date_cloture"]
    list_filter = ["statut"]
    search_fields = ["titre", "point_situation"]
    inlines = [IntervenantInline, ActionInline, EntreeJournalInline]
