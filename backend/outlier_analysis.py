"""
Outlier Analysis: Customer Name vs Response ID
===============================================

ROOT CAUSE EXPLAINED
--------------------
The 107 outliers are NOT caused by Customer Name directly.
They come from IQR outlier detection on the 'Response ID' column.

The dataset has TWO formats of Response ID:
  - Short format (4-digit):  1135 – 1999   → 84 rows  (older entries)
  - Long format  (8-digit):  21800000+     → 916 rows (newer entries)

When IQR is computed on a mix of 4-digit and 8-digit numbers:
  Q1  ≈ 21,800,917   Q3  ≈ 21,869,676   IQR ≈ 68,759
  Lower fence = Q1 - 1.5×IQR ≈ 21,697,778

All 84 short-format IDs fall far below this fence → flagged as outliers.
The remaining 23 come from long-format IDs that are unusually low.

SECONDARY ISSUES (Customer Name quality)
-----------------------------------------
1. Trailing/leading spaces  → 'Ambika ' vs 'Ambika', 'Kavin  ' vs 'Kavin '
2. One Response ID shared by two different customers (data entry errors)
   → 14 Response IDs each map to 2 different Customer Names
"""

import pandas as pd
import math

DATASET_PATH = r'D:\Intern\Celebal\Dataset.xlsx'

def run_analysis(path=DATASET_PATH):
    df = pd.read_excel(path, engine='openpyxl')
    print(f"\n{'='*60}")
    print("DATASET QUALITY ANALYSIS: Customer Name vs Response ID")
    print(f"{'='*60}\n")

    # ── STEP 1: Basic stats ──────────────────────────────────────
    print("STEP 1 — RAW DATA STATS")
    print(f"  Total rows                    : {len(df)}")
    print(f"  Unique Customer Names (raw)   : {df['Customer Name'].nunique()}")
    print(f"  Unique Response IDs           : {df['Response ID'].nunique()}")
    print()

    # ── STEP 2: Explain the 107 outliers ────────────────────────
    print("STEP 2 — WHY 107 OUTLIERS? (IQR on Response ID)")
    short = df[df['Response ID'] < 10000]
    long_ = df[df['Response ID'] >= 10000]
    print(f"  Short-format IDs (4-digit)    : {len(short)}  range {int(short['Response ID'].min())}–{int(short['Response ID'].max())}")
    print(f"  Long-format  IDs (8-digit)    : {len(long_)}  range {int(long_['Response ID'].min())}–{int(long_['Response ID'].max())}")

    q1 = df['Response ID'].quantile(0.25)
    q3 = df['Response ID'].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outlier_mask = (df['Response ID'] < lower) | (df['Response ID'] > upper)
    outliers_orig = df[outlier_mask].copy()

    print(f"\n  IQR stats:")
    print(f"    Q1={q1:,.0f}  Q3={q3:,.0f}  IQR={iqr:,.0f}")
    print(f"    Lower fence = {lower:,.0f}")
    print(f"    Upper fence = {upper:,.0f}")
    print(f"\n  Rows flagged as outliers      : {len(outliers_orig)}")
    print(f"  → All {len(short)} short-format IDs fall below lower fence")
    print(f"  → Plus {len(outliers_orig)-len(short)} long-format IDs below fence")
    print()

    print("  Sample outlier rows:")
    print(outliers_orig[['Customer Name', 'Response ID']].head(10).to_string(index=True))
    print(f"  ... ({len(outliers_orig)} total)\n")

    # ── STEP 3: Customer Name quality issues ────────────────────
    print("STEP 3 — CUSTOMER NAME QUALITY ISSUES")

    # 3a. Whitespace variants
    df['name_norm'] = df['Customer Name'].str.lower().str.strip()
    raw_unique = df['Customer Name'].nunique()
    norm_unique = df['name_norm'].nunique()
    print(f"  Unique names (raw)            : {raw_unique}")
    print(f"  Unique names (normalized)     : {norm_unique}")
    print(f"  Names fixed by normalization  : {raw_unique - norm_unique}")

    dup_norm = df.groupby('name_norm')['Customer Name'].apply(lambda x: list(x.unique()))
    variants = dup_norm[dup_norm.apply(len) > 1]
    if len(variants):
        print(f"\n  Whitespace variants found:")
        for norm, names in variants.items():
            print(f"    '{norm}' → {names}")
    print()

    # 3b. One Response ID → multiple Customer Names (data entry errors)
    id_to_names = df.groupby('Response ID')['name_norm'].nunique()
    multi_name_ids = id_to_names[id_to_names > 1]
    print(f"  Response IDs with multiple Customer Names: {len(multi_name_ids)}")
    for rid in multi_name_ids.index:
        rows = df[df['Response ID'] == rid][['Customer Name', 'Response ID']]
        names = rows['Customer Name'].tolist()
        print(f"    Response ID {rid} → {names}  ← DATA ENTRY ERROR")
    print()

    # 3c. One Customer Name → multiple Response IDs
    name_to_ids = df.groupby('name_norm')['Response ID'].nunique()
    multi_id_names = name_to_ids[name_to_ids > 1]
    print(f"  Customer Names with multiple Response IDs: {len(multi_id_names)}")
    for name in multi_id_names.index:
        ids = df[df['name_norm'] == name]['Response ID'].tolist()
        print(f"    '{name}' → Response IDs {ids}")
    print()

    # ── STEP 4: Clean data ───────────────────────────────────────
    print("STEP 4 — CLEANING")

    df_clean = df.copy()

    # 4a. Normalize Customer Name
    df_clean['Customer Name'] = df_clean['Customer Name'].str.strip()
    print(f"  Stripped whitespace from Customer Name")

    # 4b. Standardize Response ID format
    # Short-format IDs are legitimate older entries — do NOT delete them.
    # Flag them separately so they are not counted as IQR outliers.
    df_clean['id_format'] = df_clean['Response ID'].apply(
        lambda x: 'short' if x < 10000 else 'long'
    )

    # 4c. Remove exact duplicate rows
    before = len(df_clean)
    df_clean = df_clean.drop_duplicates(subset=['Customer Name', 'Response ID'])
    after = len(df_clean)
    print(f"  Removed {before - after} duplicate (Name, Response ID) pairs")

    # 4d. Recalculate outliers SEPARATELY per ID format group
    print(f"\n  Recalculating outliers per ID format group:")
    total_outliers_clean = 0
    for fmt in ['short', 'long']:
        grp = df_clean[df_clean['id_format'] == fmt]['Response ID']
        if len(grp) < 4:
            continue
        q1g, q3g = grp.quantile(0.25), grp.quantile(0.75)
        iqrg = q3g - q1g
        if iqrg == 0:
            print(f"    {fmt}-format: IQR=0, no outliers")
            continue
        mask = (grp < q1g - 1.5 * iqrg) | (grp > q3g + 1.5 * iqrg)
        n = mask.sum()
        total_outliers_clean += n
        print(f"    {fmt}-format ({len(grp)} rows): Q1={q1g:,.0f} Q3={q3g:,.0f} IQR={iqrg:,.0f} → {n} outliers")

    print()

    # ── STEP 5: Summary ─────────────────────────────────────────
    print("="*60)
    print("SUMMARY")
    print("="*60)
    print(f"  Original outlier count        : 107")
    print(f"  Root cause                    : IQR applied across mixed ID formats")
    print(f"  Short-format IDs (legitimate) : {len(short)} rows flagged incorrectly")
    print(f"  Outliers after clean split    : {total_outliers_clean}")
    print(f"  Reduction                     : {107 - total_outliers_clean} false positives removed")
    print()
    print("  Customer Name issues found:")
    print(f"    Whitespace variants         : {raw_unique - norm_unique} names")
    print(f"    Shared Response IDs         : {len(multi_name_ids)} IDs with 2 different names")
    print(f"    Names with multiple IDs     : {len(multi_id_names)} names")
    print()
    print("  CONCLUSION:")
    print("  The 107 outliers are NOT anomalous customers.")
    print("  They are 84 older entries with short-format Response IDs")
    print("  that get flagged when IQR is computed on the full mixed column.")
    print("  Fix: split IQR analysis by ID format group, or exclude")
    print("  Response ID from numeric outlier detection entirely.")
    print("="*60)

    return df_clean

if __name__ == '__main__':
    run_analysis()
