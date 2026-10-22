"""
Écrans de l'outil.

Pas de @login_required : LoginRequiredMiddleware protège toutes les pages.

Les formulaires suivent tous le même schéma : GET affiche le formulaire ;
POST l'enregistre puis redirige. Recharger la page après un enregistrement
ne renvoie donc jamais le formulaire une seconde fois.

Les adresses qui ne font qu'enregistrer (cocher, ajouter depuis la fiche)
renvoient vers la fiche si on les ouvre directement, au lieu d'une erreur.
"""

import re
from datetime import datetime, timezone as tz

from django.contrib import messages
from django.db.models import ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import (
    ActionForm,
    AffaireForm,
    ContactForm,
    DossierEntrepriseForm,
    EntrepriseForm,
    ImportForm,
    IntervenantContactForm,
    IntervenantForm,
    NoteForm,
    NoteModifierForm,
    ReglagesForm,
)
from .models import Action, Affaire, Contact, EntreeJournal, Entreprise, Intervenant, Lien, Reglages
from .partage import (
    HorsRacine,
    accessible,
    TAILLE_MAX,
    chemin_dans_racine,
    deposer,
    est_executable,
    lister,
    montrer,
    nom_sur,
    ouvrir,
    proposer_dossier,
    relatif,
    sous_dossiers,
)
from .vue_ensemble import vue_ensemble


def url_retour(request, defaut):
    """Adresse de retour passée en paramètre « next », si elle est sûre."""
    suivant = request.GET.get("next") or request.POST.get("next") or ""
    if url_has_allowed_host_and_scheme(suivant, allowed_hosts={request.get_host()}):
        return suivant
    return defaut


def confirmer_suppression(request, titre, texte, annuler_url, impossible=""):
    return render(
        request,
        "suivi/confirmer_suppression.html",
        {"titre": titre, "texte": texte, "impossible": impossible, "annuler_url": annuler_url},
    )


def formulaire(request, form, titre, annuler_url):
    return render(
        request,
        "suivi/formulaire.html",
        {"form": form, "titre": titre, "annuler_url": annuler_url},
    )


# --- Accueil et préférences ---------------------------------------------------


def accueil(request):
    """Vue d'ensemble : les affaires ouvertes, classées par urgence.

    Les blocs vides ne sont pas affichés.
    """
    vue = vue_ensemble()
    blocs = [
        ("En retard", "retard", vue.en_retard),
        ("Aujourd'hui", "aujourdhui", vue.aujourdhui),
        ("À venir", "a-venir", vue.a_venir),
        ("Rien de prévu", "rien-de-prevu", vue.rien_de_prevu),
    ]
    return render(
        request,
        "suivi/accueil.html",
        {"blocs": [bloc for bloc in blocs if bloc[2]], "vue": vue},
    )


# --- Historique ---------------------------------------------------------------


def historique(request):
    """Toutes les affaires, ouvertes et closes, avec recherche et filtre par statut.

    La recherche porte sur le titre, le point de situation, le journal, les
    actions, le nom des entreprises et contacts, et le nom des documents liés. La plus récemment modifiée
    d'abord.
    """
    recherche = request.GET.get("q", "").strip()
    filtre = request.GET.get("statut", "")

    affaires = Affaire.objects.prefetch_related("intervenants__entreprise")
    if filtre == "ouvertes":
        affaires = affaires.exclude(statut=Affaire.Statut.CLOS)
    elif filtre == "closes":
        affaires = affaires.filter(statut=Affaire.Statut.CLOS)
    else:
        filtre = ""  # valeur inconnue : on montre tout

    if recherche:
        affaires = affaires.filter(
            Q(titre__icontains=recherche)
            | Q(point_situation__icontains=recherche)
            | Q(journal__texte__icontains=recherche)
            | Q(actions__quoi__icontains=recherche)
            | Q(intervenants__entreprise__nom__icontains=recherche)
            | Q(intervenants__contact__nom__icontains=recherche)
            | Q(liens__chemin__icontains=recherche)
        ).distinct()  # une affaire trouvée par plusieurs chemins n'apparaît qu'une fois

    affaires = list(affaires.order_by("-modifie_le"))
    for affaire in affaires:
        # Une entreprise peut figurer plusieurs fois (un contact par ligne).
        affaire.noms_entreprises = sorted(
            {intervenant.entreprise.nom for intervenant in affaire.intervenants.all()}
        )

    return render(
        request,
        "suivi/historique.html",
        {"affaires": affaires, "recherche": recherche, "filtre": filtre},
    )


# Ordre de passage à chaque clic : système → clair → sombre → système.
THEME_SUIVANT = {"": "light", "light": "dark", "dark": ""}


def changer_theme(request):
    """Passe au thème suivant, mémorisé dans un cookie durable du navigateur."""
    reponse = redirect(url_retour(request, reverse("accueil")))
    if request.method != "POST":
        return reponse
    suivant = THEME_SUIVANT.get(request.COOKIES.get("theme", ""), "")
    if suivant:
        dix_ans = 10 * 365 * 24 * 60 * 60
        reponse.set_cookie("theme", suivant, max_age=dix_ans, samesite="Lax", httponly=True)
    else:
        reponse.delete_cookie("theme", samesite="Lax")
    return reponse


# --- Affaires -----------------------------------------------------------------


def fiche_affaire(request, affaire, **formulaires):
    """Affiche la fiche. Les formulaires passés (avec leurs erreurs) remplacent
    les formulaires vides."""
    reglages = Reglages.actuels()
    documents = documents_affaire(affaire, reglages)
    contexte = {
        "affaire": affaire,
        "intervenants": affaire.intervenants.select_related("entreprise", "contact"),
        "actions_a_faire": affaire.actions.filter(faite_le__isnull=True).select_related(
            "avec_qui__entreprise"
        ),
        "actions_faites": affaire.actions.filter(faite_le__isnull=False)
        .select_related("avec_qui__entreprise")
        .order_by("-faite_le", "-date"),
        "journal": affaire.journal.all(),
        "documents": documents,
        "form_import": formulaires.get("form_import") or formulaire_import(affaire, reglages, documents),
        "annuaire_vide": not Entreprise.objects.exists(),
        "form_action": formulaires.get("form_action") or ActionForm(affaire=affaire),
        # Lien « Ajouter une action » de la vue d'ensemble : formulaire ouvert.
        "ouvrir_action": request.GET.get("ajouter") == "action",
        "form_note": formulaires.get("form_note") or NoteForm(),
        "form_intervenant": formulaires.get("form_intervenant") or IntervenantForm(),
    }
    return render(request, "suivi/affaire.html", contexte)


def affaire_fiche(request, pk):
    return fiche_affaire(request, get_object_or_404(Affaire, pk=pk))


def affaire_creer(request):
    if request.method == "POST":
        form = AffaireForm(request.POST)
        if form.is_valid():
            affaire = form.save()
            messages.success(request, "Affaire créée. Ajoutez ses entreprises et ses actions.")
            return redirect("affaire", pk=affaire.pk)
    else:
        form = AffaireForm()
    return formulaire(request, form, "Nouvelle affaire", reverse("accueil"))


def affaire_modifier(request, pk):
    affaire = get_object_or_404(Affaire, pk=pk)
    if request.method == "POST":
        form = AffaireForm(request.POST, instance=affaire)
        if form.is_valid():
            form.save()
            messages.success(request, "Modifications enregistrées.")
            return redirect("affaire", pk=pk)
    else:
        form = AffaireForm(instance=affaire)
    return formulaire(request, form, f"Modifier « {affaire} »", reverse("affaire", args=[pk]))


def affaire_supprimer(request, pk):
    affaire = get_object_or_404(Affaire, pk=pk)
    if request.method == "POST":
        affaire.delete()
        messages.success(request, f"Affaire « {affaire} » supprimée.")
        return redirect("accueil")
    return confirmer_suppression(
        request,
        f"Supprimer « {affaire} »",
        "L'affaire, ses actions, ses entreprises et son journal seront supprimés définitivement.",
        reverse("affaire", args=[pk]),
    )


# --- Intervenants -------------------------------------------------------------


def intervenant_ajouter(request, pk):
    affaire = get_object_or_404(Affaire, pk=pk)
    if request.method != "POST":
        return redirect("affaire", pk=pk)
    form = IntervenantForm(request.POST)
    if not form.is_valid():
        return fiche_affaire(request, affaire, form_intervenant=form)

    entreprise, contact = form.cleaned_data["qui"]
    lignes = affaire.intervenants.filter(entreprise=entreprise)
    entreprise_seule = lignes.filter(contact__isnull=True).first()

    if lignes.filter(contact=contact).exists():
        # Exactement la même ligne : rien à faire.
        messages.info(request, "Déjà sur l'affaire.")
    elif contact and entreprise_seule:
        # L'entreprise était là sans contact : elle prend ce contact,
        # et garde les actions qui la visent.
        entreprise_seule.contact = contact
        entreprise_seule.save()
        messages.success(request, f"Contact précisé : {entreprise_seule}.")
    else:
        intervenant = Intervenant.objects.create(
            affaire=affaire, entreprise=entreprise, contact=contact
        )
        messages.success(request, f"Ajouté à l'affaire : {intervenant}.")
    return redirect(reverse("affaire", args=[pk]) + "#entreprises")


def intervenant_modifier(request, pk):
    """Change le contact d'une ligne, sans la retirer : ses actions sont conservées."""
    intervenant = get_object_or_404(Intervenant.objects.select_related("entreprise"), pk=pk)
    retour = reverse("affaire", args=[intervenant.affaire_id]) + "#entreprises"
    if request.method == "POST":
        form = IntervenantContactForm(request.POST, instance=intervenant)
        if form.is_valid():
            form.save()
            messages.success(request, f"Modifié : {intervenant}.")
            return redirect(retour)
    else:
        form = IntervenantContactForm(instance=intervenant)
    return formulaire(request, form, f"Contact chez {intervenant.entreprise}", retour)


def intervenant_retirer(request, pk):
    intervenant = get_object_or_404(Intervenant.objects.select_related("entreprise"), pk=pk)
    retour = reverse("affaire", args=[intervenant.affaire_id]) + "#entreprises"
    if request.method == "POST":
        intervenant.delete()
        messages.success(request, f"{intervenant.entreprise} retirée de l'affaire.")
        return redirect(retour)
    return confirmer_suppression(
        request,
        f"Retirer {intervenant.entreprise} de l'affaire",
        "L'entreprise reste dans l'annuaire. Ses actions sur l'affaire sont conservées, "
        "sans « avec qui ».",
        retour,
    )


# --- Actions ------------------------------------------------------------------


def action_ajouter(request, pk):
    affaire = get_object_or_404(Affaire, pk=pk)
    if request.method != "POST":
        return redirect("affaire", pk=pk)
    form = ActionForm(request.POST, affaire=affaire)
    if not form.is_valid():
        return fiche_affaire(request, affaire, form_action=form)
    form.save()
    messages.success(request, "Action ajoutée.")
    return redirect(reverse("affaire", args=[pk]) + "#actions")


def action_cocher(request, pk):
    """Coche une action à faire, ou décoche une action faite.

    Revient à la page d'origine (« next ») : la fiche, ou la vue d'ensemble.
    """
    action = get_object_or_404(
        Action.objects.select_related("affaire", "avec_qui__entreprise"), pk=pk
    )
    retour = url_retour(request, reverse("affaire", args=[action.affaire_id]) + "#actions")
    if request.method == "POST":
        if action.est_a_faire:
            action.cocher()
            messages.success(request, f"Fait : {action.quoi} ({action.affaire}).")
        else:
            action.decocher()
    return redirect(retour)


def action_modifier(request, pk):
    action = get_object_or_404(Action.objects.select_related("affaire"), pk=pk)
    retour = reverse("affaire", args=[action.affaire_id]) + "#actions"
    if request.method == "POST":
        form = ActionForm(request.POST, instance=action, affaire=action.affaire)
        if form.is_valid():
            form.save()
            messages.success(request, "Action modifiée.")
            return redirect(retour)
    else:
        form = ActionForm(instance=action, affaire=action.affaire)
    return formulaire(request, form, "Modifier l'action", retour)


def action_supprimer(request, pk):
    action = get_object_or_404(Action, pk=pk)
    retour = reverse("affaire", args=[action.affaire_id]) + "#actions"
    if request.method == "POST":
        action.delete()
        messages.success(request, "Action supprimée.")
        return redirect(retour)
    return confirmer_suppression(
        request,
        "Supprimer l'action",
        f"« {action.quoi} » sera supprimée, ainsi que sa trace éventuelle au journal.",
        retour,
    )


# --- Journal ------------------------------------------------------------------


def note_ajouter(request, pk):
    affaire = get_object_or_404(Affaire, pk=pk)
    if request.method != "POST":
        return redirect("affaire", pk=pk)
    form = NoteForm(request.POST, instance=EntreeJournal(affaire=affaire))
    if not form.is_valid():
        return fiche_affaire(request, affaire, form_note=form)
    form.save()
    return redirect(reverse("affaire", args=[pk]) + "#journal")


def note_modifier(request, pk):
    # Les entrées automatiques ne se modifient pas : elles n'existent pas ici.
    note = get_object_or_404(EntreeJournal, pk=pk, automatique=False)
    retour = reverse("affaire", args=[note.affaire_id]) + "#journal"
    if request.method == "POST":
        form = NoteModifierForm(request.POST, instance=note)
        if form.is_valid():
            form.save()
            messages.success(request, "Note modifiée.")
            return redirect(retour)
    else:
        form = NoteModifierForm(instance=note)
    return formulaire(request, form, "Modifier la note", retour)


def note_supprimer(request, pk):
    note = get_object_or_404(EntreeJournal, pk=pk, automatique=False)
    retour = reverse("affaire", args=[note.affaire_id]) + "#journal"
    if request.method == "POST":
        note.delete()
        messages.success(request, "Note supprimée.")
        return redirect(retour)
    return confirmer_suppression(
        request, "Supprimer la note", "La note sera supprimée définitivement.", retour
    )


# --- Annuaire : entreprises ---------------------------------------------------


def annuaire(request):
    """Liste des entreprises, avec recherche sur le nom, les contacts et les notes."""
    recherche = request.GET.get("q", "").strip()
    entreprises = Entreprise.objects.prefetch_related("contacts")
    if recherche:
        entreprises = entreprises.filter(
            Q(nom__icontains=recherche)
            | Q(contacts__nom__icontains=recherche)
            | Q(notes__icontains=recherche)
        ).distinct()
    return render(
        request,
        "suivi/annuaire.html",
        {"entreprises": entreprises, "recherche": recherche},
    )


def entreprise_fiche(request, pk):
    """Fiche entreprise : coordonnées, contacts, et les affaires où elle intervient,
    ouvertes d'abord, closes ensuite."""
    entreprise = get_object_or_404(Entreprise, pk=pk)
    affaires = (
        Affaire.objects.filter(intervenants__entreprise=entreprise)
        .distinct()
        .order_by("-modifie_le")
    )
    ouvertes = [affaire for affaire in affaires if not affaire.est_close]
    closes = [affaire for affaire in affaires if affaire.est_close]
    return render(
        request,
        "suivi/entreprise.html",
        {
            "entreprise": entreprise,
            "affaires": ouvertes + closes,
            "dossier": etat_dossier(entreprise, Reglages.actuels()),
        },
    )


# --- Dossiers des entreprises sur le partage ----------------------------------


def dossiers_disponibles(reglages, sauf=None):
    """Dossiers de la racine qui peuvent être rattachés à une entreprise :
    tous, sauf le dossier technique et ceux déjà pris par une autre entreprise."""
    pris = set(Entreprise.objects.exclude(pk=getattr(sauf, "pk", None)).values_list("dossier", flat=True))
    technique = reglages.dossier_technique.strip().casefold()
    return [
        nom
        for nom in sous_dossiers(reglages.chemin_racine)
        if nom not in pris and nom.casefold() != technique
    ]


def etat_dossier(entreprise, reglages):
    """Ce que la fiche affiche à propos du dossier de l'entreprise.

    « etat » vaut : sans_racine, partage_indisponible, ok, introuvable, a_rattacher.
    """
    racine = reglages.chemin_racine
    if racine is None:
        return {"etat": "sans_racine"}
    if not accessible(racine):
        return {"etat": "partage_indisponible", "racine": racine}
    if entreprise.dossier:
        try:
            chemin = chemin_dans_racine(racine, entreprise.dossier)
        except HorsRacine:
            return {"etat": "introuvable"}
        return {"etat": "ok" if accessible(chemin) else "introuvable", "chemin": chemin}
    return {
        "etat": "a_rattacher",
        "proposition": proposer_dossier(entreprise.nom, dossiers_disponibles(reglages, entreprise)),
    }


def entreprise_dossier(request, pk):
    """Choisit le dossier de l'entreprise parmi ceux de la racine.

    Le bouton « Rattacher » de la fiche envoie directement le dossier proposé ici.
    """
    entreprise = get_object_or_404(Entreprise, pk=pk)
    reglages = Reglages.actuels()
    retour = reverse("entreprise", args=[pk])
    if reglages.chemin_racine is None:
        messages.error(request, "Réglez d'abord la racine des documents.")
        return redirect("reglages")

    dossiers = dossiers_disponibles(reglages, entreprise)
    if request.method == "POST":
        form = DossierEntrepriseForm(request.POST, dossiers=dossiers, actuel=entreprise.dossier)
        if form.is_valid():
            entreprise.dossier = form.cleaned_data["dossier"]
            entreprise.save(update_fields=["dossier"])
            if entreprise.dossier:
                messages.success(request, f"Dossier rattaché : {entreprise.dossier}")
            else:
                messages.success(request, "Dossier détaché.")
            return redirect(retour)
    else:
        if not accessible(reglages.chemin_racine):
            messages.error(
                request,
                f"Le partage est indisponible ({reglages.chemin_racine}) : "
                "vérifiez qu'il est connecté, puis réessayez.",
            )
            return redirect(retour)
        form = DossierEntrepriseForm(dossiers=dossiers, actuel=entreprise.dossier)
    return formulaire(request, form, f"Dossier de {entreprise}", retour)


def entreprise_ouvrir_dossier(request, pk):
    """Ouvre le dossier de l'entreprise dans l'Explorateur Windows.

    Le chemin vient de la base (jamais de la requête) et reste dans la racine.
    """
    entreprise = get_object_or_404(Entreprise, pk=pk)
    retour = reverse("entreprise", args=[pk])
    if request.method != "POST":
        return redirect(retour)
    etat = etat_dossier(entreprise, Reglages.actuels())
    if etat["etat"] != "ok":
        messages.error(request, "Dossier introuvable ou partage indisponible.")
        return redirect(retour)
    try:
        ouvrir(etat["chemin"])
    except OSError as erreur:
        messages.error(request, f"Impossible d'ouvrir le dossier : {erreur}")
    return redirect(retour)


# --- Réglages -----------------------------------------------------------------


def reglages(request):
    reglages_actuels = Reglages.actuels()
    if request.method == "POST":
        form = ReglagesForm(request.POST, instance=reglages_actuels)
        if form.is_valid():
            reglages_actuels = form.save()
            messages.success(request, "Réglages enregistrés.")
            racine = reglages_actuels.chemin_racine
            if racine and not accessible(racine):
                messages.warning(
                    request,
                    f"La racine {racine} est introuvable ou le partage n'est pas connecté. "
                    "L'outil fonctionne quand même ; les documents seront disponibles "
                    "quand elle sera accessible.",
                )
            return redirect("reglages")
    else:
        form = ReglagesForm(instance=reglages_actuels)

    racine = reglages_actuels.chemin_racine
    etat = {"racine": racine, "accessible": bool(racine) and accessible(racine)}
    if etat["accessible"]:
        etat["nb_dossiers"] = len(sous_dossiers(racine))
        etat["sauvegardes"] = reglages_actuels.chemin_sauvegardes
    etat["nb_entreprises"] = Entreprise.objects.count()
    etat["nb_rattachees"] = Entreprise.objects.exclude(dossier="").count()
    return render(request, "suivi/reglages.html", {"form": form, "etat": etat})


def entreprise_creer(request):
    """Crée une entreprise. Avec « ?next=… » (depuis une affaire), y revient ensuite."""
    if request.method == "POST":
        form = EntrepriseForm(request.POST)
        if form.is_valid():
            entreprise = form.save()
            messages.success(request, f"« {entreprise} » ajoutée à l'annuaire.")
            return redirect(url_retour(request, reverse("entreprise", args=[entreprise.pk])))
    else:
        form = EntrepriseForm()
    return formulaire(request, form, "Nouvelle entreprise", url_retour(request, reverse("annuaire")))


def entreprise_modifier(request, pk):
    entreprise = get_object_or_404(Entreprise, pk=pk)
    if request.method == "POST":
        form = EntrepriseForm(request.POST, instance=entreprise)
        if form.is_valid():
            form.save()
            messages.success(request, "Modifications enregistrées.")
            return redirect("entreprise", pk=pk)
    else:
        form = EntrepriseForm(instance=entreprise)
    return formulaire(
        request, form, f"Modifier « {entreprise} »", reverse("entreprise", args=[pk])
    )


def entreprise_supprimer(request, pk):
    entreprise = get_object_or_404(Entreprise, pk=pk)
    nb_affaires = entreprise.interventions.count()

    if request.method == "POST" and not nb_affaires:
        try:
            entreprise.delete()
        except ProtectedError:
            # Filet de sécurité : utilisée entre l'affichage et la validation.
            messages.error(request, "Cette entreprise est utilisée : suppression impossible.")
            return redirect("entreprise", pk=pk)
        messages.success(request, f"« {entreprise} » supprimée de l'annuaire.")
        return redirect("annuaire")

    impossible = ""
    if nb_affaires:
        s = "s" if nb_affaires > 1 else ""
        impossible = (
            f"Elle intervient sur {nb_affaires} affaire{s}, listée{s} sur sa fiche. "
            "Retirez-la de ces affaires pour pouvoir la supprimer."
        )
    return confirmer_suppression(
        request,
        f"Supprimer « {entreprise} »",
        "L'entreprise et ses contacts seront supprimés définitivement.",
        reverse("entreprise", args=[pk]),
        impossible,
    )


# --- Annuaire : contacts ------------------------------------------------------


def contact_creer(request, pk):
    """Ajoute un contact à l'entreprise `pk`."""
    entreprise = get_object_or_404(Entreprise, pk=pk)
    contact = Contact(entreprise=entreprise)
    if request.method == "POST":
        form = ContactForm(request.POST, instance=contact)
        if form.is_valid():
            form.save()
            messages.success(request, f"Contact « {contact.nom} » ajouté.")
            return redirect("entreprise", pk=pk)
    else:
        form = ContactForm(instance=contact)
    return formulaire(
        request, form, f"Nouveau contact chez {entreprise}", reverse("entreprise", args=[pk])
    )


def contact_modifier(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    if request.method == "POST":
        form = ContactForm(request.POST, instance=contact)
        if form.is_valid():
            form.save()
            messages.success(request, "Modifications enregistrées.")
            return redirect("entreprise", pk=contact.entreprise_id)
    else:
        form = ContactForm(instance=contact)
    return formulaire(
        request,
        form,
        f"Modifier « {contact.nom} »",
        reverse("entreprise", args=[contact.entreprise_id]),
    )


def contact_supprimer(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    retour = reverse("entreprise", args=[contact.entreprise_id])
    nb_affaires = contact.interventions.count()

    if request.method == "POST" and not nb_affaires:
        try:
            contact.delete()
        except ProtectedError:
            messages.error(request, "Ce contact est utilisé : suppression impossible.")
            return redirect(retour)
        messages.success(request, f"Contact « {contact.nom} » supprimé.")
        return redirect(retour)

    impossible = ""
    if nb_affaires:
        s = "s" if nb_affaires > 1 else ""
        impossible = (
            f"Ce contact est indiqué sur {nb_affaires} affaire{s}. "
            "Retirez-le de ces affaires pour pouvoir le supprimer."
        )
    return confirmer_suppression(
        request,
        f"Supprimer « {contact.nom} »",
        "Le contact sera supprimé définitivement.",
        retour,
        impossible,
    )


# --- Documents : liens vers les fichiers du partage ---------------------------


def documents_affaire(affaire, reglages):
    """Les liens de l'affaire, chacun marqué « trouve » ou non.

    Si le partage est indisponible, on ne vérifie rien : on l'indique une fois.
    """
    liens = list(affaire.liens.all())
    racine = reglages.chemin_racine
    partage_ok = racine is not None and accessible(racine)
    for lien in liens:
        lien.trouve = None
        if partage_ok:
            try:
                lien.trouve = chemin_dans_racine(racine, lien.chemin).is_file()
            except (HorsRacine, OSError):
                lien.trouve = False
    return {"liens": liens, "racine": racine, "partage_ok": partage_ok}


def fichier_du_lien(request, lien):
    """Chemin complet du fichier d'un lien, après tous les contrôles ; None
    (avec un message) si on ne peut pas l'ouvrir."""
    racine = Reglages.actuels().chemin_racine
    if racine is None or not accessible(racine):
        messages.error(request, "Partage indisponible : vérifiez qu'il est connecté.")
        return None
    if est_executable(lien.chemin):
        messages.error(request, "Ce type de fichier n'est jamais ouvert par l'outil.")
        return None
    try:
        chemin = chemin_dans_racine(racine, lien.chemin)
    except HorsRacine:
        chemin = None
    if chemin is None or not chemin.is_file():
        messages.error(request, f"Fichier introuvable : {lien.nom}. Utilisez « Relier ».")
        return None
    return chemin


def lien_ouvrir(request, pk):
    """Ouvre le fichier dans son application Windows (Acrobat, Word, Outlook…)."""
    lien = get_object_or_404(Lien, pk=pk)
    if request.method == "POST":
        chemin = fichier_du_lien(request, lien)
        if chemin:
            try:
                ouvrir(chemin)
            except OSError as erreur:
                messages.error(request, f"Impossible d'ouvrir le fichier : {erreur}")
    return redirect(reverse("affaire", args=[lien.affaire_id]) + "#documents")


def lien_montrer(request, pk):
    """Ouvre l'Explorateur Windows sur le dossier, avec le fichier sélectionné."""
    lien = get_object_or_404(Lien, pk=pk)
    if request.method == "POST":
        chemin = fichier_du_lien(request, lien)
        if chemin:
            try:
                montrer(chemin)
            except OSError as erreur:
                messages.error(request, f"Impossible d'ouvrir le dossier : {erreur}")
    return redirect(reverse("affaire", args=[lien.affaire_id]) + "#documents")


def lien_retirer(request, pk):
    """Retire le lien. Le fichier reste sur le partage."""
    lien = get_object_or_404(Lien, pk=pk)
    if request.method == "POST":
        lien.delete()
        messages.success(request, f"Lien retiré : {lien.nom} (le fichier reste sur le partage).")
    return redirect(reverse("affaire", args=[lien.affaire_id]) + "#documents")


def dossiers_des_entreprises(affaire, racine):
    """Dossiers existants des entreprises de l'affaire (raccourcis de l'explorateur)."""
    resultat = []
    entreprises = Entreprise.objects.filter(interventions__affaire=affaire).exclude(dossier="").distinct()
    for entreprise in entreprises.order_by("nom"):
        try:
            if accessible(chemin_dans_racine(racine, entreprise.dossier)):
                resultat.append((entreprise.nom, entreprise.dossier))
        except HorsRacine:
            continue
    return resultat


def explorateur(request, pk):
    """Explorateur intégré : parcourir le partage et lier des fichiers à l'affaire.

    Paramètres : « d » = dossier courant (relatif à la racine) ; « relier » =
    identifiant d'un lien introuvable à faire pointer vers un autre fichier.
    On ne remonte jamais au-dessus de la racine, et on ne fait que lister.
    """
    affaire = get_object_or_404(Affaire, pk=pk)
    fiche = reverse("affaire", args=[pk]) + "#documents"
    racine = Reglages.actuels().chemin_racine
    if racine is None:
        messages.error(request, "Réglez d'abord la racine des documents.")
        return redirect("reglages")
    if not accessible(racine):
        messages.error(request, f"Partage indisponible ({racine}) : vérifiez qu'il est connecté.")
        return redirect(fiche)

    a_relier = None
    if request.GET.get("relier") or request.POST.get("relier"):
        a_relier = get_object_or_404(Lien, pk=request.GET.get("relier") or request.POST.get("relier"), affaire=affaire)

    if request.method == "POST":
        return lier_fichiers(request, affaire, racine, a_relier, fiche)

    raccourcis = dossiers_des_entreprises(affaire, racine)
    courant = request.GET.get("d")
    if courant is None:
        # Point de départ : l'ancien dossier du lien à relier, sinon le dossier
        # de l'entreprise s'il n'y en a qu'une, sinon la racine.
        if a_relier:
            courant = a_relier.dossier_relatif
        elif len(raccourcis) == 1:
            courant = raccourcis[0][1]
        else:
            courant = ""
    courant = courant.strip().strip("/")
    try:
        dossier = chemin_dans_racine(racine, courant) if courant else racine
        noms_dossiers, fichiers = lister(dossier)
    except (HorsRacine, OSError):
        if courant:
            messages.error(request, f"Dossier introuvable : {courant}. Retour à la racine.")
        courant, dossier = "", racine
        try:
            noms_dossiers, fichiers = lister(racine)
        except OSError:
            messages.error(request, f"Partage illisible ({racine}) : vérifiez qu'il est connecté.")
            return redirect(fiche)

    deja_lies = set(affaire.liens.values_list("chemin", flat=True))
    prefixe = f"{courant}/" if courant else ""
    for fichier in fichiers:
        fichier["chemin"] = prefixe + fichier["nom"]
        fichier["modifie"] = datetime.fromtimestamp(fichier["modifie"], tz=tz.utc)
        fichier["deja_lie"] = fichier["chemin"] in deja_lies
        fichier["executable"] = est_executable(fichier["nom"])

    # Fil d'Ariane : « Bâtiment › OTIS › 2026 », chaque étape cliquable.
    ariane = [(racine.name or str(racine), "")]
    morceaux = []
    for morceau in courant.split("/") if courant else []:
        morceaux.append(morceau)
        ariane.append((morceau, "/".join(morceaux)))

    return render(
        request,
        "suivi/explorateur.html",
        {
            "affaire": affaire,
            "a_relier": a_relier,
            "courant": courant,
            "ariane": ariane,
            "parent": "/".join(courant.split("/")[:-1]) if courant else None,
            "raccourcis": raccourcis,
            "dossiers": [{"nom": nom, "chemin": prefixe + nom} for nom in noms_dossiers],
            "fichiers": fichiers,
            "fiche": fiche,
        },
    )


def lier_fichiers(request, affaire, racine, a_relier, fiche):
    """Enregistre les fichiers cochés dans l'explorateur. Chaque chemin reçu est
    revérifié : dans la racine, fichier existant, pas un exécutable."""
    valides = []
    for chemin in request.POST.getlist("fichiers"):
        try:
            complet = chemin_dans_racine(racine, chemin)
            if complet.is_file() and not est_executable(complet.name):
                valides.append(relatif(racine, complet))
        except (HorsRacine, OSError, ValueError):
            continue

    if a_relier:
        if not valides:
            messages.error(request, "Choisissez le fichier à relier.")
            return redirect(f"{reverse('explorateur', args=[affaire.pk])}?relier={a_relier.pk}")
        if affaire.liens.filter(chemin=valides[0]).exclude(pk=a_relier.pk).exists():
            a_relier.delete()  # ce fichier était déjà lié : on garde un seul lien
        else:
            a_relier.chemin = valides[0]
            a_relier.save(update_fields=["chemin"])
        messages.success(request, f"Lien rétabli : {valides[0].rsplit('/', 1)[-1]}")
        return redirect(fiche)

    nouveaux = 0
    for chemin in valides:
        _, cree = Lien.objects.get_or_create(affaire=affaire, chemin=chemin)
        nouveaux += cree
    if nouveaux:
        s = "s" if nouveaux > 1 else ""
        messages.success(request, f"{nouveaux} fichier{s} lié{s} à l'affaire.")
    else:
        messages.info(request, "Aucun nouveau fichier lié.")
    return redirect(fiche)


# --- Import de fichiers sur le partage ------------------------------------------


def destinations_import(affaire, reglages):
    """Où ranger un fichier importé : (choix groupés, choix par défaut, années).

    D'abord les dossiers des entreprises de l'affaire, puis les dossiers de la
    racine qui ne sont à aucune entreprise (« Autres », « Sinistres »…).
    Par défaut : la première entreprise de l'affaire, sinon « Autres ».
    Années proposées : l'année en cours, la précédente, et celles qui existent
    déjà dans les dossiers des entreprises de l'affaire (ou dans « Autres »).
    """
    racine = reglages.chemin_racine
    entreprises = [(dossier, nom) for nom, dossier in dossiers_des_entreprises(affaire, racine)]
    autres = [(nom, nom) for nom in dossiers_disponibles(reglages)]
    choix = []
    if entreprises:
        choix.append(("Entreprises de l'affaire", entreprises))
    if autres:
        choix.append(("Autres dossiers", autres))

    defaut = None
    if entreprises:
        defaut = entreprises[0][0]
    elif autres:
        defaut = next((c for c, _ in autres if c.casefold() == "autres"), autres[0][0])

    annee = timezone.localdate().year
    annees = {str(annee), str(annee - 1)}
    for dossier in [c for c, _ in entreprises] or ([defaut] if defaut else []):
        try:
            annees.update(n for n in sous_dossiers(chemin_dans_racine(racine, dossier)) if re.fullmatch(r"\d{4}", n))
        except HorsRacine:
            continue
    return choix, defaut, sorted(annees, reverse=True)


def formulaire_import(affaire, reglages, documents, data=None):
    """Le formulaire d'import, ou None si le partage n'est pas disponible."""
    if not documents["partage_ok"]:
        return None
    choix, defaut, annees = destinations_import(affaire, reglages)
    if not choix:
        return None
    return ImportForm(data, destinations=choix, annees=annees, defaut=defaut)


def importer(request, pk):
    """Copie les fichiers déposés dans « destination/année » sur le partage et
    les lie à l'affaire. Rien n'est jamais écrasé ; un fichier déjà présent dans
    ce dossier (même contenu) est lié sans être recopié."""
    affaire = get_object_or_404(Affaire, pk=pk)
    fiche = reverse("affaire", args=[pk]) + "#documents"
    if request.method != "POST":
        return redirect(fiche)
    reglages = Reglages.actuels()
    documents = documents_affaire(affaire, reglages)
    form = formulaire_import(affaire, reglages, documents, request.POST)
    if form is None:
        messages.error(request, "Partage indisponible : import impossible pour l'instant.")
        return redirect(fiche)

    envois = request.FILES.getlist("fichiers")
    if form.is_valid() and not envois:
        form.add_error(None, "Choisissez ou déposez au moins un fichier.")
    if not form.is_valid():
        return fiche_affaire(request, affaire, form_import=form)

    racine = reglages.chemin_racine
    destination, annee = form.cleaned_data["destination"], form.cleaned_data["annee"]
    try:
        dossier = chemin_dans_racine(racine, destination) / annee
    except HorsRacine:  # impossible avec les choix proposés ; par prudence
        return redirect(fiche)

    copies, deja_la, refus = [], [], []
    for envoi in envois:
        nom = nom_sur(envoi.name)
        if est_executable(nom):
            refus.append(f"{nom} (programme)")
            continue
        if envoi.size > TAILLE_MAX:
            refus.append(f"{nom} (plus de {TAILLE_MAX // (1024 * 1024)} Mo : copiez-le à la main dans le dossier, puis liez-le)")
            continue
        try:
            chemin, copie = deposer(envoi, dossier)
        except OSError as erreur:
            refus.append(f"{nom} ({erreur.strerror or erreur})")
            continue
        Lien.objects.get_or_create(affaire=affaire, chemin=relatif(racine, chemin))
        (copies if copie else deja_la).append(chemin.name)

    lieu = " › ".join([destination, annee])
    if copies:
        s = "s" if len(copies) > 1 else ""
        messages.success(request, f"{len(copies)} fichier{s} importé{s} dans {lieu} : {', '.join(copies)}.")
    if deja_la:
        messages.info(request, f"Déjà dans {lieu}, lié sans copie : {', '.join(deja_la)}.")
    if refus:
        messages.error(request, "Non importé : " + " ; ".join(refus) + ".")
    return redirect(fiche)
