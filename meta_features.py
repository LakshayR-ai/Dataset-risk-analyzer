"""
meta_features.py
----------------
Extracts statistical meta-features from a dataset for ML risk prediction.
Extended feature set: 10 features (up from 7) — adds skewness, duplicate_pct,
outlier_pct so the meta-model can distinguish risk patterns more precisely.
"""

import pandas as pd
import numpy as np
from scipy import stats as scipy_stats


def extract_meta_features(df: pd.DataFrame, target: str) -> list:
    """
    Extract meta-features from a dataset.

    Parameters
    ----------
    df     : Raw DataFrame (including target column)
    target : Name of the target/label column

    Returns
    -------
    list of 10 floats:
        [n_samples, n_features, ratio, variance, correlation,
         imbalance, missing, skewness, duplicate_pct, outlier_pct]
    """
    if target not in df.columns:
        raise ValueError(f"Target column '{target}' not found in DataFrame.")

    X = df.drop(columns=[target])
    y = df[target]

    n_samples = int(X.shape[0])
    n_features = int(X.shape[1])

    # Avoid divide-by-zero
    ratio = n_features / n_samples if n_samples > 0 else 0.0

    # Mean variance across numeric columns (NaN-safe)
    numeric_X = X.select_dtypes(include="number")
    variance = float(numeric_X.var(ddof=1).mean()) if not numeric_X.empty else 0.0
    if np.isnan(variance) or np.isinf(variance):
        variance = 0.0

    # Mean absolute correlation (upper triangle only to avoid bias)
    if numeric_X.shape[1] > 1:
        corr_matrix = numeric_X.corr().abs()
        upper = corr_matrix.where(
            np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
        )
        correlation = float(upper.stack().mean())
    else:
        correlation = 0.0
    if np.isnan(correlation) or np.isinf(correlation):
        correlation = 0.0

    # Class imbalance — max class proportion
    class_dist = y.value_counts(normalize=True)
    imbalance = float(class_dist.max()) if not class_dist.empty else 1.0

    # Missing value rate
    total_cells = n_samples * n_features
    missing = float(X.isnull().sum().sum() / total_cells) if total_cells > 0 else 0.0

    # Mean absolute skewness across numeric columns
    if not numeric_X.empty and n_samples > 2:
        skew_vals = numeric_X.apply(lambda col: abs(scipy_stats.skew(col.dropna())))
        skewness = float(skew_vals.mean())
    else:
        skewness = 0.0
    if np.isnan(skewness) or np.isinf(skewness):
        skewness = 0.0

    # Duplicate row percentage
    duplicate_pct = float(df.duplicated().sum() / n_samples) if n_samples > 0 else 0.0

    # Outlier percentage using IQR (numeric columns only, excludes ID-like cols)
    outlier_rows = set()
    for col in numeric_X.columns:
        series = numeric_X[col].dropna()
        if len(series) < 4:
            continue
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        mask = (series < q1 - 1.5 * iqr) | (series > q3 + 1.5 * iqr)
        outlier_rows.update(series[mask].index.tolist())
    outlier_pct = len(outlier_rows) / n_samples if n_samples > 0 else 0.0

    return [
        n_samples,
        n_features,
        round(ratio, 6),
        round(variance, 4),
        round(correlation, 4),
        round(imbalance, 4),
        round(missing, 4),
        round(skewness, 4),
        round(duplicate_pct, 4),
        round(outlier_pct, 4),
    ]
