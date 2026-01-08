from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict


@dataclass
class Cible:
    """
    Entité métier:
    - source: "DB" | "Fichier plat"
    - filtre: dict (uniquement si source DB)
    - chemin: str (uniquement si source fichier plat)
    """
    id_cible: str
    nom_cible: str
    source: str  # "DB" | "Fichier plat"
    date_creation: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    filtre: Dict[str, Any] = field(default_factory=dict)
    chemin: str = ""

    def validate(self) -> None:
        # id_cible peut être vide AVANT insert (le store le génère)
        if self.nom_cible is None or not str(self.nom_cible).strip():
            raise ValueError("nom_cible obligatoire")

        if self.source not in ("DB", "Fichier plat"):
            raise ValueError("source doit être 'DB' ou 'Fichier plat'")

        if self.source == "DB":
            if not isinstance(self.filtre, dict):
                raise ValueError("filtre doit être un dict pour une cible DB")
            # chemin doit rester vide
            self.chemin = ""
        else:
            # fichier plat => filtre vide, chemin obligatoire
            self.filtre = {}
            if self.chemin is None or not str(self.chemin).strip():
                raise ValueError("chemin obligatoire pour une cible fichier plat")

    def to_row(self) -> Dict[str, str]:
        """Format de stockage DB (filtre sera sérialisé côté store)."""
        self.validate()
        return {
            "id_cible": self.id_cible,
            "nom_cible": str(self.nom_cible).strip(),
            "date_creation": self.date_creation,
            "source": self.source,
            "chemin": str(self.chemin or "").strip(),
        }
