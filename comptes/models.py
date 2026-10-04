from django.contrib.auth.models import AbstractUser


class Utilisateur(AbstractUser):
    """
    Utilisateur de l'outil.

    Vide pour l'instant : il reprend tout du modèle standard de Django.
    Il existe dès le départ pour pouvoir ajouter des champs plus tard
    (ex. téléphone, rôle affiché) sans migration douloureuse.
    """

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"
