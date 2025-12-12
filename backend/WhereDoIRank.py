"""Legacy helper bridging to the shared ranking query."""

from __future__ import annotations

from backend.queries import estimate_event_rank

EVENT_OPTIONS = (
    "100 Meters",
    "200 Meters",
    "400 Meters",
    "800 Meters",
    "1600 Meters",
    "3200 Meters",
    "100 Hurdles",
    "110 Hurdles",
    "300 Hurdles",
    "High Jump",
    "Long Jump",
    "Shot Put",
    "Discus",
    "Pole Vault",
)


def where_do_i_rank(
    *,
    event_name: str,
    performance_value,
    gender: str,
    year: int,
    meet_type: str = "Sectional",
):
    """Thin wrapper so existing callers can import from this module.

    The heavy lifting lives in :func:`backend.queries.estimate_event_rank` – this
    wrapper simply forwards arguments to keep backward compatibility with any
    scripts that used to import ``WhereDoIRank``.
    """

    return estimate_event_rank(
        event_name=event_name,
        performance_value=performance_value,
        gender=gender,
        year=year,
        meet_type=meet_type,
    )


__all__ = ["where_do_i_rank", "EVENT_OPTIONS"]