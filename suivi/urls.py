"""Adresses des écrans métier."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.accueil, name="accueil"),
    # Annuaire
    path("annuaire/", views.annuaire, name="annuaire"),
    path("annuaire/nouvelle/", views.entreprise_creer, name="entreprise_creer"),
    path("annuaire/<int:pk>/", views.entreprise_fiche, name="entreprise"),
    path("annuaire/<int:pk>/modifier/", views.entreprise_modifier, name="entreprise_modifier"),
    path("annuaire/<int:pk>/supprimer/", views.entreprise_supprimer, name="entreprise_supprimer"),
    path("annuaire/<int:pk>/contacts/nouveau/", views.contact_creer, name="contact_creer"),
    path("contacts/<int:pk>/modifier/", views.contact_modifier, name="contact_modifier"),
    path("contacts/<int:pk>/supprimer/", views.contact_supprimer, name="contact_supprimer"),
]
