"""Adresses de l'outil."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from suivi import views

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path(
        "connexion/",
        # Déjà connecté : la page de connexion renvoie directement à l'accueil.
        auth_views.LoginView.as_view(redirect_authenticated_user=True),
        name="connexion",
    ),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="deconnexion"),
    # Outil technique, pas une interface pour le responsable.
    path("admin/", admin.site.urls),
]
