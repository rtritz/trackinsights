"""
Test script for projected team score calculations.
Run from backend/scripts directory: python test_projected_team_scores.py
"""

from projected_team_scores import (
    NOT_READY_MESSAGE,
    get_available_projected_score_seasons,
    get_projected_team_scores,
)


def _assert_scored_dataframe(df):
    assert "Place" in df.columns
    assert "Team" in df.columns
    assert "Score" in df.columns
    assert not df.empty
    assert df["Place"].min() == 1
    assert (df["Score"].diff().fillna(0) <= 0).all()


print("=" * 70)
print("Example 1: 2024 Boys Regional 1 projected team scores")
print("=" * 70)
regional_df = get_projected_team_scores(
    meet_type="Regional",
    year=2024,
    gender="Boys",
    meet_num=1,
)
print(f"Rows: {len(regional_df)}")
print(regional_df)
_assert_scored_dataframe(regional_df)

print("\n" + "=" * 70)
print("Example 2: 2025 Girls State projected team scores")
print("=" * 70)
state_df = get_projected_team_scores(
    meet_type="State",
    year=2025,
    gender="Girls",
    meet_num=1,
)
print(f"Rows: {len(state_df)}")
print(state_df)
_assert_scored_dataframe(state_df)

print("\n" + "=" * 70)
print("Example 3: current year filter support")
print("=" * 70)
seasons = get_available_projected_score_seasons()
print("Seasons:", seasons)
assert seasons[0] == 2023

print("\n" + "=" * 70)
print("Example 4: not-ready fallback message")
print("=" * 70)
not_ready_df = get_projected_team_scores(
    meet_type="Regional",
    year=2026,
    gender="Boys",
    meet_num=1,
)
print(not_ready_df)
assert "Message" in not_ready_df.columns
assert not_ready_df.iloc[0]["Message"] == NOT_READY_MESSAGE

print("\n" + "=" * 70)
print("Example 5: 2025 Girls Regional 4 projected team scores")
print("=" * 70)
regional4_df = get_projected_team_scores(
    meet_type="Regional",
    year=2025,
    gender="Girls",
    meet_num=4,
)
print(f"Rows: {len(regional4_df)}")
print(regional4_df)
_assert_scored_dataframe(regional4_df)

print("\n" + "=" * 70)
print("Example 6: 2025 Girls Regional 5 projected team scores")
print("=" * 70)
regional5_df = get_projected_team_scores(
    meet_type="Regional",
    year=2025,
    gender="Girls",
    meet_num=5,
)
print(f"Rows: {len(regional5_df)}")
print(regional5_df)
_assert_scored_dataframe(regional5_df)

print("\nAll projected team score tests passed.")
