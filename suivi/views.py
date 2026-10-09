from django.shortcuts import render


def accueil(request):
    """Page d'accueil : la vue d'ensemble des affaires (vide pour l'instant).

    Pas de @login_required : LoginRequiredMiddleware protège toutes les pages.
    """
    return render(request, "suivi/accueil.html")
