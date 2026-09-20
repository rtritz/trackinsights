"""Sectional and regional host names, read from a precomputed file.

Track.db records a tournament meet as "IHSAA Sectional 12"; the host school is
what people recognise. IHSAA publishes the pairing, so it is scraped -- but
*offline*, by ``app.jobs.precompute_tournament_hosts``, never while a visitor
waits.

    ihsaa.org  --(the job, run by hand)-->  tournament_hosts.json  -->  the site

This module is the one place that knows where that file lives and what shape it
has, so the job that writes it and the web app that reads it cannot drift apart.

WHY NOT FETCH IT LIVE
---------------------
It used to, in two separate places -- ``_ihsaa_sectional_hosts`` in the queries
package and ``_ihsaa_regional_hosts`` beside it -- each opening a socket to
ihsaa.org with a twenty-second timeout from inside the request that renders the
qualifiers pages. A slow third party made the site slow; a hung one held a worker
for twenty seconds, which on a host with a handful of workers is an outage caused
entirely by someone else's server. The in-process caches meant to blunt this were
emptied on every Track.db swap along with every other cache, so the next request
paid for it again.

The hosts change once a year. Fetching them per request was buying nothing.

RELATED
-------
``common/regional_hosts.py`` holds *hand-entered* regional hosts, which take
priority over anything scraped. This module is the scraped layer underneath it.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Dict

from .const import CONST

# The tournament rounds this file covers. These are the IHSAA page's own names
# for them, and they appear verbatim in the JSON keys.
ROUND_SECTIONAL = "sectional"
ROUND_REGIONAL = "regional"
ALL_ROUNDS = (ROUND_SECTIONAL, ROUND_REGIONAL)

# Beside the other precomputed JSON the site serves.
TOURNAMENT_HOSTS_DIR = os.path.join(
    CONST.WEB_DIR, "app", "static", "data", "tournament_hosts")
TOURNAMENT_HOSTS_PATH = os.path.join(TOURNAMENT_HOSTS_DIR, "tournament_hosts.json")

# On disk the keys are strings, because JSON has no tuples and no integer keys:
#   {"2026|Boys|sectional": {"1": "Portage", "2": "Goshen", ...}, ...}
# _KEY_SEPARATOR is the one place that format is spelled out.
_KEY_SEPARATOR = "|"


def storage_key(year: int, gender: str, round_name: str) -> str:
    """The JSON key for one season, gender and round."""
    return _KEY_SEPARATOR.join(
        (str(int(year)), _normalize_gender(gender), _normalize_round(round_name)))


def _normalize_gender(gender: str) -> str:
    return (gender or "").strip().title()


def _normalize_round(round_name: str) -> str:
    name = (round_name or "").strip().lower()
    if name not in ALL_ROUNDS:
        raise ValueError("unknown tournament round: %r" % (round_name,))
    return name


def _file_stamp():
    """Cheap identity of the file, so an edit is picked up without a restart."""
    try:
        stat = os.stat(TOURNAMENT_HOSTS_PATH)
    except OSError:
        return None
    return (stat.st_size, stat.st_mtime_ns)


@lru_cache(maxsize=4)
def _load_stamped(stamp):
    """Parse the file once per distinct version of it.

    Keyed on the stamp rather than taking no arguments, so that replacing the
    file invalidates the entry by changing the key. mtime is safe here because it
    is only ever compared against itself inside one process -- nothing derived
    from it is stored or shipped to another machine.
    """
    if stamp is None:
        return {}
    try:
        with open(TOURNAMENT_HOSTS_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_all() -> Dict[str, Dict[str, str]]:
    """Every mapping in the file, or {} when it has not been built.

    One os.stat per call; the JSON is parsed once per version of the file. The
    qualifier pages ask for a host once per row, so this is on a hot path.

    A missing or unreadable file is not an error: callers fall back to the host
    recorded in Track.db, which is what happened whenever the live fetch failed
    too. The site renders either way.
    """
    return _load_stamped(_file_stamp())


def get_hosts(year: int, gender: str, round_name: str) -> Dict[int, str]:
    """{meet number: host name} for one season, gender and round.

    Empty when the file has not been built or holds nothing for that key.
    """
    try:
        key = storage_key(year, gender, round_name)
    except (TypeError, ValueError):
        return {}

    entry = load_all().get(key) or {}
    hosts = {}
    for number, host in entry.items():
        try:
            hosts[int(number)] = host
        except (TypeError, ValueError):
            continue
    return hosts


def get_sectional_hosts(year: int, gender: str) -> Dict[int, str]:
    """{sectional number: host name} for one season and gender."""
    return get_hosts(year, gender, ROUND_SECTIONAL)


def get_regional_hosts(year: int, gender: str) -> Dict[int, str]:
    """{regional number: host name} for one season and gender."""
    return get_hosts(year, gender, ROUND_REGIONAL)


def save_all(mapping: Dict[str, Dict[int, str]]) -> str:
    """Write the whole file. Used by the precompute job, not by the site."""
    os.makedirs(TOURNAMENT_HOSTS_DIR, exist_ok=True)
    serialisable = {
        key: {str(number): host for number, host in sorted(hosts.items())}
        for key, hosts in sorted(mapping.items())
    }
    with open(TOURNAMENT_HOSTS_PATH, "w", encoding="utf-8") as handle:
        json.dump(serialisable, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return TOURNAMENT_HOSTS_PATH
