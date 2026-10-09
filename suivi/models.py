"""
Modèles métier du suivi des affaires.

Six objets :
- l'annuaire : Entreprise et Contact ;
- le suivi : Affaire, Intervenant (une entreprise sur une affaire),
  Action (une chose datée à faire) et EntreeJournal.

Règles portées par les modèles :
- passer une affaire en « clos » remplit la date de clôture ; la rouvrir la vide ;
- tout changement de statut est consigné dans le journal ;
- cocher une action consigne « fait » dans le journal ; la décocher retire cette trace ;
- une entreprise ou un contact utilisé dans une affaire ne peut pas être supprimé.
"""

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

# --- Annuaire -----------------------------------------------------------------


class Entreprise(models.Model):
    nom = models.CharField("nom", max_length=200)
    telephone = models.CharField("téléphone", max_length=50, blank=True)
    email = models.EmailField("email", blank=True)
    notes = models.TextField("notes", blank=True, help_text="Contrat, astreinte, horaires…")

    class Meta:
        ordering = ["nom"]
        verbose_name = "entreprise"
        verbose_name_plural = "entreprises"

    def __str__(self):
        return self.nom


class Contact(models.Model):
    # Supprimer une entreprise inutilisée supprime ses contacts.
    entreprise = models.ForeignKey(
        Entreprise,
        on_delete=models.CASCADE,
        related_name="contacts",
        verbose_name="entreprise",
    )
    nom = models.CharField("nom", max_length=200)
    fonction = models.CharField("fonction", max_length=100, blank=True)
    telephone = models.CharField("téléphone", max_length=50, blank=True)
    email = models.EmailField("email", blank=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "contact"
        verbose_name_plural = "contacts"

    def __str__(self):
        return f"{self.nom} ({self.entreprise})"


# --- Suivi --------------------------------------------------------------------


class Affaire(models.Model):
    class Statut(models.TextChoices):
        EN_COURS = "en_cours", "En cours"  # la main est chez lui
        EN_ATTENTE = "en_attente", "En attente"  # la main est chez un tiers
        CLOS = "clos", "Clos"

    titre = models.CharField("titre", max_length=200)
    statut = models.CharField(
        "statut", max_length=20, choices=Statut.choices, default=Statut.EN_COURS
    )
    point_situation = models.CharField(
        "point de situation",
        max_length=500,
        blank=True,
        help_text="Où en est l'affaire, en une phrase.",
    )
    date_debut = models.DateField(
        "date de début",
        null=True,
        blank=True,
        help_text="Indicative : si le début est flou, un jour du bon mois suffit.",
    )
    date_cloture = models.DateField(
        "date de clôture",
        null=True,
        blank=True,
        help_text="Remplie automatiquement au passage en « clos ».",
    )
    cree_le = models.DateTimeField("créée le", auto_now_add=True)
    modifie_le = models.DateTimeField("modifiée le", auto_now=True)

    class Meta:
        ordering = ["-cree_le"]
        verbose_name = "affaire"
        verbose_name_plural = "affaires"

    def __str__(self):
        return self.titre

    @property
    def est_close(self):
        return self.statut == self.Statut.CLOS

    def save(self, *args, **kwargs):
        # Date de clôture : remplie au passage en « clos » (sauf si elle est
        # déjà saisie), vidée quand l'affaire est rouverte.
        if self.est_close:
            if not self.date_cloture:
                self.date_cloture = timezone.localdate()
        else:
            self.date_cloture = None

        # Statut avant modification, lu en base (None pour une nouvelle affaire).
        ancien_statut = None
        if self.pk:
            ancien_statut = (
                Affaire.objects.filter(pk=self.pk)
                .values_list("statut", flat=True)
                .first()
            )

        # L'affaire et la trace au journal sont enregistrées ensemble, ou pas du tout.
        with transaction.atomic():
            super().save(*args, **kwargs)
            if ancien_statut and ancien_statut != self.statut:
                EntreeJournal.objects.create(
                    affaire=self,
                    automatique=True,
                    texte=(
                        f"Statut : {self.Statut(ancien_statut).label} "
                        f"→ {self.get_statut_display()}"
                    ),
                )


class Intervenant(models.Model):
    """Une entreprise, ou un de ses contacts, sur une affaire.

    Une ligne par personne : « XXX — maçon » et « XXX — plâtrier » peuvent
    coexister sur la même affaire. Une même ligne n'apparaît jamais deux fois.
    """

    affaire = models.ForeignKey(
        Affaire,
        on_delete=models.CASCADE,
        related_name="intervenants",
        verbose_name="affaire",
    )
    # PROTECT : impossible de supprimer une entreprise ou un contact utilisé.
    entreprise = models.ForeignKey(
        Entreprise,
        on_delete=models.PROTECT,
        related_name="interventions",
        verbose_name="entreprise",
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="interventions",
        verbose_name="contact",
    )

    class Meta:
        ordering = ["entreprise__nom", "contact__nom"]
        verbose_name = "intervenant"
        verbose_name_plural = "intervenants"
        constraints = [
            # Pas deux fois le même contact sur une affaire.
            models.UniqueConstraint(
                fields=["affaire", "entreprise", "contact"],
                name="intervenant_unique",
                violation_error_message="Ce contact est déjà sur l'affaire.",
            ),
            # Pas deux fois l'entreprise « sans contact » : en base, deux contacts
            # vides ne comptent pas comme identiques, d'où cette seconde règle.
            models.UniqueConstraint(
                fields=["affaire", "entreprise"],
                condition=models.Q(contact__isnull=True),
                name="entreprise_seule_unique",
                violation_error_message=(
                    "Cette entreprise est déjà sur l'affaire sans contact particulier."
                ),
            ),
        ]

    def __str__(self):
        if self.contact:
            return f"{self.entreprise} — {self.contact.nom}"
        return str(self.entreprise)

    def clean(self):
        if (
            self.contact_id
            and self.entreprise_id
            and self.contact.entreprise_id != self.entreprise_id
        ):
            raise ValidationError(
                {"contact": "Ce contact n'appartient pas à cette entreprise."}
            )


class Action(models.Model):
    """Une chose datée à faire sur une affaire. « Faite le » vide = à faire."""

    class Type(models.TextChoices):
        RELANCE = "relance", "Relance"
        PASSAGE = "passage", "Passage"
        AUTRE = "autre", "Autre"

    affaire = models.ForeignKey(
        Affaire,
        on_delete=models.CASCADE,
        related_name="actions",
        verbose_name="affaire",
    )
    type = models.CharField(
        "type", max_length=20, choices=Type.choices, default=Type.RELANCE
    )
    date = models.DateField("date")
    quoi = models.CharField(
        "quoi",
        max_length=300,
        help_text="Par exemple : « Relancer pour le devis », « Passage 9 h ».",
    )
    # SET_NULL : retirer une entreprise d'une affaire ne supprime pas ses actions.
    avec_qui = models.ForeignKey(
        Intervenant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actions",
        verbose_name="avec qui",
    )
    faite_le = models.DateField("faite le", null=True, blank=True)

    class Meta:
        ordering = ["date"]
        verbose_name = "action"
        verbose_name_plural = "actions"

    def __str__(self):
        return f"{self.date:%d/%m/%Y} — {self.quoi}"

    @property
    def est_a_faire(self):
        return self.faite_le is None

    @property
    def en_retard(self):
        return self.est_a_faire and self.date < timezone.localdate()

    def clean(self):
        if (
            self.avec_qui_id
            and self.affaire_id
            and self.avec_qui.affaire_id != self.affaire_id
        ):
            raise ValidationError(
                {"avec_qui": "Cette entreprise n'intervient pas sur l'affaire."}
            )

    def cocher(self):
        """Marque l'action comme faite aujourd'hui et le consigne au journal."""
        if not self.est_a_faire:
            return
        texte = f"Fait : {self.get_type_display().lower()} — {self.quoi}"
        if self.avec_qui:
            texte += f" ({self.avec_qui.entreprise})"
        with transaction.atomic():
            self.faite_le = timezone.localdate()
            self.save(update_fields=["faite_le"])
            EntreeJournal.objects.create(
                affaire=self.affaire, action=self, automatique=True, texte=texte
            )

    def decocher(self):
        """Remet l'action à faire et retire la trace laissée au journal."""
        with transaction.atomic():
            self.faite_le = None
            self.save(update_fields=["faite_le"])
            self.entrees_journal.filter(automatique=True).delete()


class EntreeJournal(models.Model):
    """Une note datée sur une affaire, écrite par lui ou générée par l'outil."""

    affaire = models.ForeignKey(
        Affaire,
        on_delete=models.CASCADE,
        related_name="journal",
        verbose_name="affaire",
    )
    texte = models.TextField("texte")
    # Valeur par défaut, et non auto_now_add : une note peut être datée a posteriori.
    horodatage = models.DateTimeField("date", default=timezone.now)
    automatique = models.BooleanField("automatique", default=False, editable=False)
    # Action qui a produit l'entrée : supprimer l'action supprime sa trace.
    action = models.ForeignKey(
        Action,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        editable=False,
        related_name="entrees_journal",
        verbose_name="action",
    )

    class Meta:
        ordering = ["-horodatage"]
        verbose_name = "entrée de journal"
        verbose_name_plural = "entrées de journal"

    def __str__(self):
        return f"{self.horodatage:%d/%m/%Y} — {self.texte[:50]}"
