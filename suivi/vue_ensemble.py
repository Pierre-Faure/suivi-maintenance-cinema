"""Règles de la vue d'ensemble (page d'accueil)."""

from dataclasses import dataclass, field

from django.db.models import Min, Prefetch, Q
from django.utils import timezone

from .models import Action, Affaire


@dataclass
class VueEnsemble:
    en_retard: list = field(default_factory=list)
    aujourdhui: list = field(default_factory=list)
    a_venir: list = field(default_factory=list)
    rien_de_prevu: list = field(default_factory=list)

    @property
    def est_vide(self):
        return not (self.en_retard or self.aujourdhui or self.a_venir or self.rien_de_prevu)


def vue_ensemble(aujourdhui=None):
    """Classe les affaires ouvertes (non closes) ; chacune apparaît une seule fois.

    Chaque affaire porte :
    - `prochaine_date` : la date de sa plus proche action à faire (None sinon) ;
    - `prochaine_action` : cette action (None sinon) ;
    - `autres_actions` : le nombre d'autres actions à faire ;
    - `jours_de_retard` : pour une affaire en retard, depuis combien de jours.

    Groupes, dans l'ordre d'affichage :
    - en retard : prochaine action avant aujourd'hui, la plus ancienne d'abord ;
    - aujourd'hui : prochaine action aujourd'hui ;
    - à venir : par date de prochaine action ;
    - rien de prévu : aucune action à faire, quel que soit le statut,
      la moins récemment modifiée d'abord.
    """
    aujourdhui = aujourdhui or timezone.localdate()

    actions_a_faire = (
        Action.objects.filter(faite_le__isnull=True)
        .select_related("avec_qui__entreprise", "avec_qui__contact")
        .order_by("date", "pk")
    )
    affaires = (
        Affaire.objects.exclude(statut=Affaire.Statut.CLOS)
        .annotate(
            prochaine_date=Min("actions__date", filter=Q(actions__faite_le__isnull=True))
        )
        # Les actions à faire de chaque affaire, chargées en une seule requête.
        .prefetch_related(Prefetch("actions", queryset=actions_a_faire, to_attr="a_faire"))
        .order_by("prochaine_date", "modifie_le")
    )

    vue = VueEnsemble()
    for affaire in affaires:
        affaire.prochaine_action = affaire.a_faire[0] if affaire.a_faire else None
        affaire.autres_actions = max(len(affaire.a_faire) - 1, 0)
        affaire.jours_de_retard = 0

        if affaire.prochaine_date is None:
            vue.rien_de_prevu.append(affaire)
        elif affaire.prochaine_date < aujourdhui:
            affaire.jours_de_retard = (aujourdhui - affaire.prochaine_date).days
            vue.en_retard.append(affaire)
        elif affaire.prochaine_date == aujourdhui:
            vue.aujourdhui.append(affaire)
        else:
            vue.a_venir.append(affaire)
    return vue
