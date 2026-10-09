"""
Écrans de l'outil.

Pas de @login_required : LoginRequiredMiddleware protège toutes les pages.

Les formulaires suivent tous le même schéma : GET affiche le formulaire ;
POST l'enregistre puis redirige. Recharger la page après un enregistrement
ne renvoie donc jamais le formulaire une seconde fois.
"""

from django.contrib import messages
from django.db.models import ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import ContactForm, EntrepriseForm
from .models import Contact, Entreprise


def accueil(request):
    """Page d'accueil : la vue d'ensemble des affaires (vide pour l'instant)."""
    return render(request, "suivi/accueil.html")


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
    if request.method == "POST":
        form = EntrepriseForm(request.POST)
        if form.is_valid():
            entreprise = form.save()
            messages.success(request, f"« {entreprise} » ajoutée à l'annuaire.")
            return redirect("entreprise", pk=entreprise.pk)
    else:
        form = EntrepriseForm()
    return render(
        request,
        "suivi/formulaire.html",
        {"form": form, "titre": "Nouvelle entreprise", "annuler_url": reverse("annuaire")},
    )


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
    return render(
        request,
        "suivi/formulaire.html",
        {
            "form": form,
            "titre": f"Modifier « {entreprise} »",
            "annuler_url": reverse("entreprise", args=[pk]),
        },
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
    return render(
        request,
        "suivi/confirmer_suppression.html",
        {
            "titre": f"Supprimer « {entreprise} »",
            "texte": "L'entreprise et ses contacts seront supprimés définitivement.",
            "impossible": impossible,
            "annuler_url": reverse("entreprise", args=[pk]),
        },
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
    return render(
        request,
        "suivi/formulaire.html",
        {
            "form": form,
            "titre": f"Nouveau contact chez {entreprise}",
            "annuler_url": reverse("entreprise", args=[pk]),
        },
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
    return render(
        request,
        "suivi/formulaire.html",
        {
            "form": form,
            "titre": f"Modifier « {contact.nom} »",
            "annuler_url": reverse("entreprise", args=[contact.entreprise_id]),
        },
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
    return render(
        request,
        "suivi/confirmer_suppression.html",
        {
            "titre": f"Supprimer « {contact.nom} »",
            "texte": "Le contact sera supprimé définitivement.",
            "impossible": impossible,
            "annuler_url": retour,
        },
    )
