from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List


@dataclass(frozen=True)
class TargetPreview:
    rows: List[Dict[str, Any]]
    total: int


class DataSourceAdapter(ABC):
    """Contrat minimal d'une source de population.

    Le métier manipule des *client_key* et ne dépend pas du lieu physique
    où vivent les données. Une implémentation peut donc lire le PostgreSQL
    interne ou un datamart externe sans changer le moteur de ciblage.
    """

    code: str
    kind: str

    @abstractmethod
    def healthcheck(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def count_target(self, cible: Dict[str, Any], *, exclude_rupture_relation: bool = False) -> int:
        raise NotImplementedError

    @abstractmethod
    def preview_target(self, cible: Dict[str, Any], *, limit: int = 200) -> TargetPreview:
        raise NotImplementedError

    @abstractmethod
    def stream_target_keys(
        self,
        cible: Dict[str, Any],
        *,
        batch_size: int = 2000,
        exclude_rupture_relation: bool = False,
    ) -> Iterator[List[str]]:
        raise NotImplementedError
