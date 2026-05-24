import time, cProfile, pstats, io
from backend import create_app
from backend.queries import get_regional_qualifiers

app = create_app()
with app.app_context():
    t0 = time.perf_counter()
    payload = get_regional_qualifiers.__wrapped__('Boys', 1, 2026)
    print(f"Cold call regional 1: {time.perf_counter()-t0:.3f}s | events={len(payload['events'])}")

    profiler = cProfile.Profile()
    profiler.enable()
    get_regional_qualifiers.__wrapped__('Boys', 2, 2026)
    profiler.disable()

    s = io.StringIO()
    pstats.Stats(profiler, stream=s).sort_stats('cumulative').print_stats(30)
    print(s.getvalue())

    t0 = time.perf_counter()
    for r in range(1, 9):
        get_regional_qualifiers.__wrapped__('Boys', r, 2026)
    print(f"All 8 regionals sequential: {time.perf_counter()-t0:.3f}s")
