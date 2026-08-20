"""Moteur de ciblage incrémental.

La source canonique actuelle est la table ``clients``. Cette couche reste
strictement backend et permet au batch de ne retraiter que les clients dont les
données susceptibles d'influencer une cible ont changé depuis le dernier
passage de chaque campagne.
"""

from .incremental import sync_target_changes_for_campaign
from .store import targeting_stats

__all__ = ["sync_target_changes_for_campaign", "targeting_stats"]
