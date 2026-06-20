"""
meta_model.py
-------------
Trains the meta-model that predicts dataset risk category.

Improvements over v1:
  - 10 meta-features (was 7) — now includes skewness, duplicate_pct, outlier_pct
  - Stratified 80/20 split (was 70/30 with no stratification)
  - GridSearchCV hyperparameter tuning on RandomForest
  - 5-fold cross-validation for generalisation estimate
  - Feature importance report printed to console
  - Saves model as meta_model.pkl (compatible with app.py predictor)

Run:
    python meta_model.py
"""

import os
import pickle
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.preprocessing import LabelEncoder

# ── Load dataset ──────────────────────────────────────────────────────────────
CSV_PATH = os.path.join(os.path.dirname(__file__), "meta_dataset.csv")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "meta_model.pkl")

meta_df = pd.read_csv(CSV_PATH)
print(f"Loaded meta_dataset.csv — shape: {meta_df.shape}")
print(f"Class distribution:\n{meta_df['risk'].value_counts()}\n")

FEATURE_COLS = [
    "n_samples", "n_features", "ratio", "variance", "correlation",
    "imbalance", "missing", "skewness", "duplicate_pct", "outlier_pct",
]

# Guard: older CSV might not have the 3 new columns
missing_cols = [c for c in FEATURE_COLS if c not in meta_df.columns]
if missing_cols:
    raise ValueError(
        f"meta_dataset.csv is missing columns: {missing_cols}\n"
        "Re-run the sub-agent or meta_dataset_builder.py to regenerate it."
    )

X = meta_df[FEATURE_COLS]
y = meta_df["risk"]

# ── Stratified train/test split ───────────────────────────────────────────────
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)
print(f"Train: {len(X_train)}  Test: {len(X_test)}")

# ── Hyperparameter tuning via GridSearchCV ────────────────────────────────────
param_grid = {
    "n_estimators": [100, 200, 300],
    "max_depth": [None, 8, 16],
    "min_samples_split": [2, 4],
    "class_weight": ["balanced", None],
}

print("Running GridSearchCV (5-fold CV) — this may take ~30 seconds...")
gs = GridSearchCV(
    RandomForestClassifier(random_state=42),
    param_grid,
    cv=5,
    scoring="f1_macro",
    n_jobs=-1,
    verbose=0,
)
gs.fit(X_train, y_train)
best_params = gs.best_params_
print(f"Best params : {best_params}")
print(f"Best CV F1  : {gs.best_score_:.4f}\n")

model = gs.best_estimator_

# ── Cross-validation on full training set ────────────────────────────────────
cv_scores = cross_val_score(model, X_train, y_train, cv=5, scoring="f1_macro")
print(f"5-Fold CV F1 (train): {cv_scores.round(4)}  mean={cv_scores.mean():.4f}  std={cv_scores.std():.4f}\n")

# ── Test set evaluation ───────────────────────────────────────────────────────
y_pred = model.predict(X_test)
print("Classification Report (test set):\n")
print(classification_report(y_test, y_pred))

print("Confusion Matrix:")
cm = confusion_matrix(y_test, y_pred, labels=model.classes_)
cm_df = pd.DataFrame(cm, index=model.classes_, columns=model.classes_)
print(cm_df, "\n")

# ── Feature importance ────────────────────────────────────────────────────────
importances = pd.Series(model.feature_importances_, index=FEATURE_COLS).sort_values(ascending=False)
print("Feature Importances:")
for feat, imp in importances.items():
    bar = "█" * int(imp * 40)
    print(f"  {feat:<18} {imp:.4f}  {bar}")
print()

# ── Overfitting check ─────────────────────────────────────────────────────────
train_score = model.score(X_train, y_train)
test_score  = model.score(X_test,  y_test)
gap = train_score - test_score
print(f"Train accuracy : {train_score:.4f}")
print(f"Test  accuracy : {test_score:.4f}")
print(f"Gap            : {gap:.4f}  {'⚠️  possible overfit' if gap > 0.15 else '✅ OK'}\n")

# ── Save model ────────────────────────────────────────────────────────────────
with open(MODEL_PATH, "wb") as f:
    pickle.dump(model, f)
print(f"Meta-model saved → {MODEL_PATH}")
