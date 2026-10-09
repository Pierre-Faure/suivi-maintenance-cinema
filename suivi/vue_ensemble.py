"""Règles de la vue d'ensemble (page d'accueil)."""

from dataclasses import dataclass, field

from django.db.models import Min, Q
from django.utils import timezone

from .models import Affaire


@dataclass
class VueEnsemble:
    en_retard: list = field(default_factory=list)
    aujourdhui: list = field(default_factory=list)
    rien_de_prevu: list = field(default_factory=list)
    a_venir: list = field(default_factory=list)


def vue_ensemble(aujourdhui=None):
    """Classe les affaires ouvertes (non closes) ; chacune apparaît une seule fois.

    Chaque affaire porte `prochaine_date` : la date de sa plus proche action
    à faire, ou None si elle n'en a aucune.

    - en retard : prochaine action avant aujourd'hui, la plus ancienne d'abord ;
    - aujourd'hui : prochaine action aujourd'hui ;
    - rien de prévu : aucune action à faire, quel que soit le statut,
      la moins récemment modifiée d'abord ;
    - à venir : le reste, par date de prochaine action.
    """
    aujourdhui = aujourdhui or timezone.localdate()

    affaires = (
        Affaire.objects.exclude(statut=Affaire.Statut.CLOS)
        .annotate(
            prochaine_date=Min("actions__date", filter=Q(actions__faite_le__isnull=True))
        )
        .order_by("prochaine_date", "modifie_le")
    )

    vue = VueEnsemble()
    for affaire in affaires:
        if affaire.prochaine_date is None:
            vue.rien_de_prevu.append(affaire)
        elif affaire.prochaine_date < aujourdhui:
            vue.en_retard.append(affaire)
        elif affaire.prochaine_date == aujourdhui:
            vue.aujourdhui.append(affaire)
        else:
            vue.a_venir.append(affaire)
    return vue
