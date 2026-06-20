"""
risk_label.py
-------------
Assigns a risk label to a dataset based on baseline model performance gaps
AND dataset structural properties (meta-features).

Risk categories:
  - "Overfitting Risk"   : model memorises training data, fails on unseen data
  - "Underfitting Risk"  : model too simple or data too noisy / insufficient
  - "Safe Dataset"       : acceptable train/test behaviour
"""


def assign_risk(
    train_acc: float,
    test_acc: float,
    gap: float,
    n_samples: int = None,
    imbalance: float = None,
    missing: float = None,
) -> str:
    """
    Assign a risk label from baseline model metrics and optional meta-features.

    Parameters
    ----------
    train_acc  : Training set accuracy (0–1)
    test_acc   : Test set accuracy (0–1)
    gap        : train_acc - test_acc  (positive = overfitting)
    n_samples  : (optional) total rows in dataset
    imbalance  : (optional) dominant class proportion (0–1)
    missing    : (optional) fraction of missing values (0–1)

    Returns
    -------
    str : "Overfitting Risk" | "Underfitting Risk" | "Safe Dataset"
    """
    # ── Overfitting heuristics ────────────────────────────────────────────────
    # Large train/test gap is the primary signal
    if gap > 0.15:
        return "Overfitting Risk"

    # High imbalance + small dataset also leads to overfitting
    if n_samples is not None and imbalance is not None:
        if imbalance > 0.85 and n_samples < 1000:
            return "Overfitting Risk"

    # ── Underfitting heuristics ───────────────────────────────────────────────
    # Both train AND test accuracy are low → model can't learn
    if train_acc < 0.60 and test_acc < 0.60:
        return "Underfitting Risk"

    # Tiny dataset — not enough signal to learn reliably
    if n_samples is not None and n_samples < 100:
        return "Underfitting Risk"

    # High missing rate destroys signal
    if missing is not None and missing > 0.30:
        return "Underfitting Risk"

    # ── Safe ─────────────────────────────────────────────────────────────────
    return "Safe Dataset"
