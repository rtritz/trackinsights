"""Database queries, grouped by feature.

Split out of a single 6,800-line module so that "where do I change this?" has an
answer. Every name the package defines is re-exported here, so
`from app.queries import X` and `queries.X` work exactly as before -- callers
did not have to change, and new code can import from the specific module instead.

    shared.py            helpers and constants this package owns
    formatting.py        turning marks, gaps and places into display strings
    cache.py             emptying the caches when Track.db is replaced
    event_ranking.py     where one mark stands in a field
    search_scoring.py    name matching and relevance for the search box

    school_dashboard.py  the dashboards themselves
    program_rankings.py  where a whole program sits statewide
    scorecard.py         one school's entries, round by round
    outlook.py           returning athletes and head-to-head
    meets.py             meet results, team scoring, relays
    qualifiers.py        regional and state qualifiers, advancement rules
    athletes.py          athlete dashboards, rankings, badges
    percentiles.py       percentile tables and tools
    insights.py          sectional trends, hypothetical rankings
    search.py            site-wide athlete and school search

The first group is the base every feature draws on; the second is the features.

ADDING A FUNCTION
-----------------
Put it in the feature file it belongs to and import it straight from there:
`from app.queries.athletes import your_function`. That needs no entry below.

The list below is this package's public surface -- what routes, jobs and
services reach for as `from app.queries import X`. It is deliberately short.
It was once every name in every module, 200 of them, including `Dict`,
`Optional` and the SQLAlchemy models; 168 were never used outside the package
and only made it harder to see which module owned what. Add a name here only
when something outside the package genuinely imports it from the package.
"""

from .shared import (  # noqa: F401
    _covered_rank_seasons,
    _get_event_types_map,
    _schools_with_logos,
)
from .cache import (  # noqa: F401
    _clear_query_caches,
    ensure_fresh_queries,
)

from .qualifiers import (  # noqa: F401
    _regional_events_for_gender,
    get_regional_qualifiers,
    get_regional_qualifiers_status,
    get_state_qualifiers,
    get_state_qualifiers_status,
)

from .athletes import (  # noqa: F401
    add_athlete,
    get_athlete_by_id,
    get_athlete_dashboard_data,
    get_athlete_result_rankings,
    get_athletes,
    get_hypothetical_result_rankings,
)

from .school_dashboard import (  # noqa: F401
    get_school_dashboard_data,
    get_school_qualifiers,
    get_school_season_core,
)

from .program_rankings import (  # noqa: F401
    _build_statewide_program_rankings,
    get_program_rank,
)

from .scorecard import (  # noqa: F401
    get_athlete_scorecard,
)

from .outlook import (  # noqa: F401
    get_returning_athletes,
    get_season_h2h,
)

from .percentiles import (  # noqa: F401
    _compute_school_percentiles,
    get_percentile_options,
    get_percentiles_report,
)

from .insights import (  # noqa: F401
    get_hypothetical_ranking_options,
    get_sectional_event_trends,
    get_sectional_event_trends_options,
)

from .search import (  # noqa: F401
    search_bar,
)
