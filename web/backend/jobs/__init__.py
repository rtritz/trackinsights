"""Batch/precompute jobs -- run periodically (not per-request) to refresh
the static JSON files web/backend/routes serves. Run from web/, e.g.:

    python -m backend.jobs.precompute_combined_rankings
"""
