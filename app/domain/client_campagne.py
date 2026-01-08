from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


_ALLOWED_ETATS = {"En cours", "Annulée", "Terminée", "En pause"}


@dataclass
class ClientCampagne:
    ID_CAMPAGNE: str
    Radical_compte: str

    statut_avant_campagne: str = ""
    statut_actuel: str = ""

    Etat_campagne: str = "En cours"  # En cours | Annulée | Terminée | En pause
    NB_jour_campagne: int = 0

    ID_Action: str = ""
    Action: str = ""

    Last_action: str = ""
    Resultat_last_action: str = ""
    Date_last_action: str = ""  # ISO "YYYY-MM-DD"
    NB_jour_last_action: int = 0

    NB_appel: int = 0
    NB_sms: int = 0
    NB_mail: int = 0
    NB_message: int = 0

    def validate(self) -> None:
        if not self.ID_CAMPAGNE:
            raise ValueError("ID_CAMPAGNE est obligatoire")
        if not self.Radical_compte:
            raise ValueError("Radical_compte est obligatoire")

        if self.Etat_campagne not in _ALLOWED_ETATS:
            raise ValueError(f"Etat_campagne invalide: {self.Etat_campagne} (attendu: {_ALLOWED_ETATS})")
