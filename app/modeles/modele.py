from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional


VERS_CC_BY_VARIABLE = {
    "STATUT_CLIENT": "Non",
    "Dossier Complet": "Oui",
    "Validation KYC": "Non",
    "Activation du compte": "Non",
    "Activation carte": "Non",
    "Epargne": "Oui",
    "Carte Actuelle": "Oui",
    "Assurance Actuelle": "Oui",
}

MODALITES_BY_VARIABLE = {
    "STATUT_CLIENT": ["Actif", "Inactif", "Prospect", "Rupture de relation"],
    "Dossier Complet": ["OUI", "NON"],
    "Validation KYC": ["OUI", "NON"],
    "Activation du compte": ["OUI", "NON"],
    "Activation carte": ["OUI", "NON"],
    "Epargne": ["OUI", "NON"],
    "Carte Actuelle": ["Silver", "Gold", "Standard", "Black", "Aucune"],
    "Assurance Actuelle": ["Immobilier", "Vie", "Aucune"],
}


def vers_cc_for(variable_cible: str) -> str:
    if variable_cible not in VERS_CC_BY_VARIABLE:
        raise ValueError(f"Variable cible inconnue: {variable_cible}")
    return VERS_CC_BY_VARIABLE[variable_cible]


def modalites_for(variable_cible: str) -> List[str]:
    if variable_cible not in MODALITES_BY_VARIABLE:
        raise ValueError(f"Variable cible inconnue: {variable_cible}")
    return MODALITES_BY_VARIABLE[variable_cible]


@dataclass
class Modele:
    id_modele: Optional[str]
    nom_modele: str
    variable_cible: str
    objectif: str
    date_creation: str  # ISO "YYYY-MM-DD"
    vers_cc: str
    liste_action: List[Dict[str, Any]]
    graphe_json: Dict[str, Any]  # ✅ sauvegarde du graphe (nodes/edges)

    @staticmethod
    def new(
        nom_modele: str,
        variable_cible: str,
        objectif: str,
        liste_action: List[Dict[str, Any]],
        graphe_json: Dict[str, Any],
        id_modele: Optional[str] = None,
        date_creation: Optional[str] = None,
    ) -> "Modele":
        dc = date_creation or date.today().isoformat()
        vcc = vers_cc_for(variable_cible)

        if objectif not in modalites_for(variable_cible):
            raise ValueError(
                f"Objectif '{objectif}' invalide pour '{variable_cible}'. "
                f"Choix: {modalites_for(variable_cible)}"
            )

        return Modele(
            id_modele=id_modele,
            nom_modele=nom_modele,
            variable_cible=variable_cible,
            objectif=objectif,
            date_creation=dc,
            vers_cc=vcc,
            liste_action=liste_action or [],
            graphe_json=graphe_json or {"nodes": [], "edges": []},
        )

    def liste_action_json(self) -> str:
        return json.dumps(self.liste_action, ensure_ascii=False)

    def graphe_json_str(self) -> str:
        return json.dumps(self.graphe_json, ensure_ascii=False)

    @staticmethod
    def delete(id_modele: str) -> None:
        from app.storage.modele_store_sqlite import delete_modele
        delete_modele(id_modele)
