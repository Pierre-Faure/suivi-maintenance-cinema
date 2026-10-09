"""
Écrans de l'outil.

Pas de @login_required : LoginRequiredMiddleware protège toutes les pages.

Les formulaires suivent tous le même schéma : GET affiche le formulaire ;
POST l'enregistre puis redirige. Recharger la page après un enregistrement
ne renvoie donc jamais le formulaire une seconde fois.

Les adresses qui ne font qu'enregistrer (cocher, ajouter depuis la fiche)
renvoient vers la fiche si on les ouvre directement, au lieu d'une erreur.
"""

from django.contrib import messages
from django.db.models import ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import (
    ActionForm,
    AffaireForm,
    ContactForm,
    EntrepriseForm,
    IntervenantForm,
    NoteForm,
    NoteModifierForm,
)
from .models import Action, Affaire, Contact, EntreeJournal, Entreprise, Intervenant


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
    """Page d'accueil : liste simple des affaires ouvertes, en attendant la vue
    d'ensemble de l'étape 5."""
    affaires = Affaire.objects.exclude(statut=Affaire.Statut.CLOS).order_by("-modifie_le")
    return render(request, "suivi/accueil.html", {"affaires": affaires})


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
        "annuaire_vide": not Entreprise.objects.exists(),
        "form_action": formulaires.get("form_action") or ActionForm(affaire=affaire),
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
    intervenant, cree = Intervenant.objects.get_or_create(
        affaire=affaire, entreprise=entreprise, defaults={"contact": contact}
    )
    if cree:
        messages.success(request, f"{intervenant} ajoutée à l'affaire.")
    elif contact and intervenant.contact != contact:
        # Déjà présente : on met simplement à jour le contact.
        intervenant.contact = contact
        intervenant.save()
        messages.success(request, f"Contact mis à jour : {intervenant}.")
    else:
        messages.info(request, f"{entreprise} intervient déjà sur l'affaire.")
    return redirect(reverse("affaire", args=[pk]) + "#entreprises")


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
    """Coche une action à faire, ou décoche une action faite."""
    action = get_object_or_404(
        Action.objects.select_related("affaire", "avec_qui__entreprise"), pk=pk
    )
    if request.method == "POST":
        if action.est_a_faire:
            action.cocher()
        else:
            action.decocher()
    return redirect(reverse("affaire", args=[action.affaire_id]) + "#actions")


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
    entreprise = get_object_or_404(Entreprise, pk=pk)
    return render(request, "suivi/entreprise.html", {"entreprise": entreprise})


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
            f"Elle intervient sur {nb_affaires} affaire{s}. "
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
