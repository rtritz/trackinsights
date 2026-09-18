"""Batch/precompute jobs -- run periodically (not per-request) to refresh
the static JSON files web/app/routes serves. Run from web/, e.g.:

    python -m app.jobs.precompute_combined_rankings
"""
