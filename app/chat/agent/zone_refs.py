"""
Translate the zone references the chat agent produces (names like «жилая», or plain ids)
into the numeric zone ids GenPlanner's DTOs expect.

The chat vocabulary is names -- ids are an implementation detail no user should have to
know -- but drafts stored in ChatStorage history and older model outputs still carry ids,
so both forms are accepted here and normalized to ids on the way into the draft.
"""

from typing import Any

from loguru import logger

from app.common.constants.api_constants import resolve_territory_zone_id


def resolve_zone_ratio_map(value: Any) -> dict[int, float] | None:
    """
    Normalize a {zone name or id -> number} mapping to {zone id -> number}.

    Unresolvable zones are dropped rather than passed through: GenPlanner silently
    ignores unknown ids anyway, and dropping them here keeps the draft honest about what
    generation will actually use. Returns None when nothing survives, so the caller can
    leave the previous draft value untouched instead of wiping it with an empty map.
    """

    if not isinstance(value, dict):
        return None

    resolved: dict[int, float] = {}
    for zone, number in value.items():
        zone_id = resolve_territory_zone_id(zone)
        if zone_id is None:
            logger.warning(f"chat agent used an unknown zone reference {zone!r}, dropping it")
            continue
        try:
            resolved[zone_id] = float(number)
        except (TypeError, ValueError):
            logger.warning(f"chat agent gave a non-numeric value {number!r} for zone {zone!r}, dropping it")

    return resolved or None


def resolve_zone_pairs(value: Any) -> list[tuple[int, int]] | None:
    """
    Normalize a list of two-element zone references (names and/or ids) to id pairs.

    A pair with an unresolvable side is dropped whole -- a half-resolved pair would mean
    a neighbourhood rule between a zone and nothing.
    """

    if not isinstance(value, (list, tuple)):
        return None

    resolved: list[tuple[int, int]] = []
    for pair in value:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            logger.warning(f"chat agent gave a malformed zone pair {pair!r}, dropping it")
            continue
        left, right = (resolve_territory_zone_id(side) for side in pair)
        if left is None or right is None:
            logger.warning(f"chat agent used an unknown zone reference in pair {pair!r}, dropping it")
            continue
        resolved.append((left, right))

    return resolved or None
