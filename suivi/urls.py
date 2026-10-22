"""Adresses des écrans métier."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("historique/", views.historique, name="historique"),
    path("reglages/", views.reglages, name="reglages"),
    path("theme/", views.changer_theme, name="theme"),
    # Affaires
    path("affaires/nouvelle/", views.affaire_creer, name="affaire_creer"),
    path("affaires/<int:pk>/", views.affaire_fiche, name="affaire"),
    path("affaires/<int:pk>/modifier/", views.affaire_modifier, name="affaire_modifier"),
    path("affaires/<int:pk>/supprimer/", views.affaire_supprimer, name="affaire_supprimer"),
    path("affaires/<int:pk>/entreprises/ajouter/", views.intervenant_ajouter, name="intervenant_ajouter"),
    path("affaires/<int:pk>/actions/ajouter/", views.action_ajouter, name="action_ajouter"),
    path("affaires/<int:pk>/journal/ajouter/", views.note_ajouter, name="note_ajouter"),
    path("affaires/<int:pk>/documents/lier/", views.explorateur, name="explorateur"),
    path("affaires/<int:pk>/documents/importer/", views.importer, name="importer"),
    path("documents/<int:pk>/ouvrir/", views.lien_ouvrir, name="lien_ouvrir"),
    path("documents/<int:pk>/montrer/", views.lien_montrer, name="lien_montrer"),
    path("documents/<int:pk>/retirer/", views.lien_retirer, name="lien_retirer"),
    path("intervenants/<int:pk>/modifier/", views.intervenant_modifier, name="intervenant_modifier"),
    path("intervenants/<int:pk>/retirer/", views.intervenant_retirer, name="intervenant_retirer"),
    path("actions/<int:pk>/cocher/", views.action_cocher, name="action_cocher"),
    path("actions/<int:pk>/modifier/", views.action_modifier, name="action_modifier"),
    path("actions/<int:pk>/supprimer/", views.action_supprimer, name="action_supprimer"),
    path("journal/<int:pk>/modifier/", views.note_modifier, name="note_modifier"),
    path("journal/<int:pk>/supprimer/", views.note_supprimer, name="note_supprimer"),
    # Annuaire
    path("annuaire/", views.annuaire, name="annuaire"),
    path("annuaire/nouvelle/", views.entreprise_creer, name="entreprise_creer"),
    path("annuaire/<int:pk>/", views.entreprise_fiche, name="entreprise"),
    path("annuaire/<int:pk>/modifier/", views.entreprise_modifier, name="entreprise_modifier"),
    path("annuaire/<int:pk>/supprimer/", views.entreprise_supprimer, name="entreprise_supprimer"),
    path("annuaire/<int:pk>/dossier/", views.entreprise_dossier, name="entreprise_dossier"),
    path("annuaire/<int:pk>/dossier/ouvrir/", views.entreprise_ouvrir_dossier, name="entreprise_ouvrir_dossier"),
    path("annuaire/<int:pk>/contacts/nouveau/", views.contact_creer, name="contact_creer"),
    path("contacts/<int:pk>/modifier/", views.contact_modifier, name="contact_modifier"),
    path("contacts/<int:pk>/supprimer/", views.contact_supprimer, name="contact_supprimer"),
]
