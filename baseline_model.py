"""
baseline_model.py
-----------------
Trains a lightweight baseline classifier on a dataset and returns
train/test accuracy along with the overfitting gap.

Used by meta_dataset_builder to generate risk labels for the meta-model.
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score


def evaluate_dataset(
    df: pd.DataFrame,
    target: str,
    test_size: float = 0.3,
    random_state: int = 42,
) -> tuple[float, float, float]:
    """
    Train a Logistic Regression baseline and measure overfitting gap.

    Parameters
    ----------
    df           : DataFrame containing features + target
    target       : Name of the target column
    test_size    : Fraction of data used for testing (default 0.3)
    random_state : Random seed for reproducibility

    Returns
    -------
    (train_acc, test_acc, gap)
        train_acc : accuracy on training set
        test_acc  : accuracy on test set
        gap       : train_acc - test_acc (positive = overfitting signal)

    Raises
    ------
    ValueError : if target column not found or insufficient samples
    """
    if target not in df.columns:
        raise ValueError(f"Target column '{target}' not found in DataFrame.")

    # Drop rows where target is missing
    df = df.dropna(subset=[target]).copy()

    if len(df) < 20:
        raise ValueError(
            f"Dataset too small for reliable evaluation: {len(df)} rows. Need ≥ 20."
        )

    X = df.drop(columns=[target])
    y = df[target]

    # Encode string/categorical features numerically
    for col in X.select_dtypes(include=["object", "category"]).columns:
        le = LabelEncoder()
        X[col] = le.fit_transform(X[col].astype(str))

    # Fill remaining NaN with column median
    X = X.fillna(X.median(numeric_only=True))

    # Encode target if it's a string
    if y.dtype == object:
        le = LabelEncoder()
        y = pd.Series(le.fit_transform(y.astype(str)), index=y.index)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y if y.nunique() <= 20 else None
    )

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=1000, random_state=random_state)),
    ])

    pipeline.fit(X_train, y_train)

    train_acc = accuracy_score(y_train, pipeline.predict(X_train))
    test_acc = accuracy_score(y_test, pipeline.predict(X_test))
    gap = round(train_acc - test_acc, 4)

    return round(train_acc, 4), round(test_acc, 4), gap
