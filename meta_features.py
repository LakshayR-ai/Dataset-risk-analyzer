import pandas as pd
import numpy as np

def extract_meta_features(df, target):
    X = df.drop(columns=[target])
    y = df[target]

    n_samples = X.shape[0]
    n_features = X.shape[1]
    ratio = n_features / n_samples

    variance = X.var(numeric_only=True).mean()

    if n_features > 1:
        correlation = X.corr(numeric_only=True).abs().mean().mean()
    else:
        correlation = 0

    class_distribution = y.value_counts(normalize=True)
    imbalance = class_distribution.max()

    missing = X.isnull().sum().sum() / (n_samples * n_features)

    return [
        n_samples,
        n_features,
        ratio,
        variance,
        correlation,
        imbalance,
        missing
    ]