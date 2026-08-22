from __future__ import annotations

from typing import Any

PRODUCTS = ("card", "conso", "immo", "epargne")
PRODUCT_LABELS = {
    "card": "Carte",
    "conso": "Credit conso",
    "immo": "Credit immo",
    "epargne": "Epargne",
}
CARD_PRODUCTS = ("Silver", "Titanium", "Platinium", "Infinite")
CARD_RANK = {name: idx for idx, name in enumerate(CARD_PRODUCTS, start=1)}

# Les valeurs historiques du datamart ne correspondent pas toutes aux quatre
# produits scorés. Le mapping est volontairement centralisé pour être ajusté
# facilement lors du raccordement au référentiel cartes réel de la banque.
LEGACY_CARD_RANK = {
    "": 0,
    "aucune": 0,
    "standard": 0,
    "classic": 0,
    "code 30": 0,
    "code 212": 0,
    "silver": 1,
    "titanium": 2,
    "gold": 2,
    "platinium": 3,
    "platinum": 3,
    "black": 3,
    "infinite": 4,
    "carte visa infinite": 4,
}

CREDIT_STATES = ("never", "finished", "active")
MODEL_VERSION = "product_propensity_xgboost_v1"
APPETENCE_THRESHOLD = 0.50


def norm_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def yes(value: Any) -> bool:
    return norm_text(value).lower() in {"oui", "yes", "1", "true", "o"}


def card_rank(value: Any) -> int:
    key = norm_text(value).lower()
    return int(LEGACY_CARD_RANK.get(key, 0))


def eligible_cards(current_card: Any) -> list[str]:
    rank = card_rank(current_card)
    return [card for card in CARD_PRODUCTS if CARD_RANK[card] > rank]


def credit_state(flag: Any, outstanding: Any, *, active_floor: float) -> str:
    try:
        amount = float(outstanding or 0.0)
    except Exception:
        amount = 0.0
    if yes(flag):
        return "active" if amount > active_floor else "finished"
    return "never"


def objective_product_from_column(column: Any) -> str | None:
    key = norm_text(column).lower().replace(" ", "_")
    if key in {"epargne", "épargne"}:
        return "epargne"
    if key in {"carte_actuelle", "activation_carte", "nature_carte"}:
        return "card"
    if key in {"credit_conso", "encours_conso"}:
        return "conso"
    if key in {"credit_immo", "encours_immo"}:
        return "immo"
    return None
