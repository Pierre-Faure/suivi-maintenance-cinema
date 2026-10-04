from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Utilisateur


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    """Administration des comptes : reprend l'écran standard de Django.
    Il sera simplifié à l'étape 4 (rôles et administration métier)."""
