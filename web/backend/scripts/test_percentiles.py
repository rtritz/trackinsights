"""
Test script to demonstrate the get_percentiles function.
Run from backend/scripts directory: python test_percentiles.py
"""

from percentiles import get_percentiles

print("="*70)
print("Example 1: Get percentiles for specific events (Girls only)")
print("="*70)
df = get_percentiles(
    events=('100 Meters', '200 Meters', '400 Meters'),
    genders=('Girls',),
    percentiles=(25, 50, 75)
)
print(df)

print("\n" + "="*70)
print("Example 2: Get percentiles for both genders (single DataFrame)")
print("="*70)
df = get_percentiles(
    events=('100 Meters', 'High Jump'),
    percentiles=(50, 75, 95)
)
print(df)

print("\n" + "="*70)
print("Example 3: Filter by year and meet type")
print("="*70)
df = get_percentiles(
    events=('100 Meters', '200 Meters'),
    genders=('Boys',),
    percentiles=(25, 50, 75),
    years=(2024,),
    meet_types=('Sectional',)
)
print(df)

print("\n" + "="*70)
print("Example 4: Get all events for Sectional percentiles with default settings (compare this one with results from Aashiv's code)")
print("="*70)
df = get_percentiles(meet_types=('Sectional',))
print(f"\nAll DataFrame - {df.shape[0]} events, {df.shape[1]} columns")
print(df)

print("\n" + "="*70)
print("Example 5: Get all events for Sectionals [2023,2024] (compare with the instagram)")
print("="*70)
df = get_percentiles(meet_types=('Sectional',), years=(2023, 2024))
print(f"\nAll DataFrame - {df.shape[0]} events, {df.shape[1]} columns")
print(df)

print("\n" + "="*70)
print("Example 6: Get Boys 400m and 1600m time for Sectionals across grade levels")
print("="*70)
df_fr = get_percentiles(events=('400 Meters','1600 Meters',), genders=('Boys',), meet_types=('Sectional',), grade_levels=('FR',))
df_so = get_percentiles(events=('400 Meters','1600 Meters',), genders=('Boys',), meet_types=('Sectional',), grade_levels=('SO',))
df_jr = get_percentiles(events=('400 Meters','1600 Meters',), genders=('Boys',), meet_types=('Sectional',), grade_levels=('JR',))
df_sr = get_percentiles(events=('400 Meters','1600 Meters',), genders=('Boys',), meet_types=('Sectional',), grade_levels=('SR',))
print(f"\nFreshmen - {df_fr.shape[0]} events, {df_fr.shape[1]} columns")
print(df_fr)
print(f"\nSophomores - {df_so.shape[0]} events, {df_so.shape[1]} columns")
print(df_so)
print(f"\nJuniors - {df_jr.shape[0]} events, {df_jr.shape[1]} columns")
print(df_jr)
print(f"\nSeniors - {df_sr.shape[0]} events, {df_sr.shape[1]} columns")
print(df_sr)
