"""Variables disponibles dans tous les gabarits."""

LIBELLES_THEME = {"light": "clair", "dark": "sombre"}


def theme(request):
    """Thème choisi dans le menu, lu dans le cookie « theme ».

    Absent ou inconnu : on suit le réglage du système.
    """
    choix = request.COOKIES.get("theme", "")
    if choix not in LIBELLES_THEME:
        choix = ""
    return {"theme": choix, "theme_libelle": LIBELLES_THEME.get(choix, "système")}
