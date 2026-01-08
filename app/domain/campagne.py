from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


_ALLOWED_ETATS = {"En cours", "Planifiée", "Annulée"}


@dataclass
class Campagne:
    id_campagne: str = ""
    id_modele: str = ""
    id_cible: str = ""
    date_creation: str = ""  # ISO "YYYY-MM-DD"
    date_debut: str = ""     # ISO
    date_fin: str = ""       # ISO
    etat_campagne: str = "Planifiée"  # En cours | Planifiée | Annulée

    def validate(self) -> None:
        if self.etat_campagne not in _ALLOWED_ETATS:
            raise ValueError(f"etat_campagne invalide: {self.etat_campagne} (attendu: {_ALLOWED_ETATS})")

        if not self.id_modele:
            raise ValueError("id_modele est obligatoire")
        if not self.id_cible:
            raise ValueError("id_cible est obligatoire")

        if self.date_debut and self.date_fin:
            # compare lexicographique OK en ISO
            if self.date_fin < self.date_debut:
                raise ValueError("date_fin ne peut pas être avant date_debut")
