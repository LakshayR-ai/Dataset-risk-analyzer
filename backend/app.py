"""
Dataset Quality Analyzer — Backend API  (v2)
=============================================
Flask REST API that receives a dataset file, performs comprehensive
data-quality analysis, and returns a structured JSON report.

Endpoints
---------
POST /api/analyze    — upload + analyze a dataset file
GET  /api/health     — liveness probe

Quality checks performed
------------------------
  1. Missing values (per-column + overall %)
  2. Duplicate rows
  3. Outlier detection via IQR (ID-like columns excluded)
  4. Class imbalance (dominant class %)
  5. Feature correlation heatmap data
  6. Skewness per numeric column
  7. Data-type mismatch detection (mixed types in a column)
  8. Low-cardinality / constant columns
  9. High-cardinality string columns (potential ID leakage)
 10. Data drift proxy (std/mean ratio — coefficient of variation)
 11. ML readiness score (0–100)
 12. AI-generated preprocessing recommendations
"""

from __future__ import annotations

import math
import os
import sys
import traceback

import pandas as pd
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
from scipy import stats as scipy_stats

app = Flask(__name__)
CORS(
    app,
    resources={r"/api/*": {"origins": ["http://localhost:3000", "http://127.0.0.1:3000", "null"]}},
)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls", "json"}
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS — serialisation
# ─────────────────────────────────────────────────────────────────────────────

def _clean(val):
    """Recursively replace NaN / Inf / numpy scalars so jsonify never breaks."""
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return None if (math.isnan(float(val)) or math.isinf(float(val))) else float(val)
    if isinstance(val, (np.ndarray,)):
        return [_clean(v) for v in val.tolist()]
    if isinstance(val, dict):
        return {k: _clean(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_clean(v) for v in val]
    return val


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS — file loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_file(filepath: str) -> pd.DataFrame:
    ext = filepath.rsplit(".", 1)[-1].lower()
    loaders = {
        "csv": lambda p: pd.read_csv(p),
        "xlsx": lambda p: pd.read_excel(p, engine="openpyxl"),
        "xls": lambda p: pd.read_excel(p, engine="openpyxl"),
        "json": lambda p: pd.read_json(p),
    }
    if ext not in loaders:
        raise ValueError(f"Unsupported file format: .{ext}")
    df = loaders[ext](filepath)
    print(f"[LOAD]  rows={len(df)}  cols={len(df.columns)}")
    return df


def _resolve_target(df: pd.DataFrame, target: str) -> str:
    """Case-insensitive column lookup. Returns exact column name or raises."""
    if target in df.columns:
        return target
    mapping = {c.strip().lower(): c for c in df.columns}
    match = mapping.get(target.strip().lower())
    if match:
        print(f"[INFO] Column matched: '{target}' → '{match}'")
        return match
    raise KeyError(target)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS — ID-like column detection
# ─────────────────────────────────────────────────────────────────────────────

_ID_KEYWORDS = {"id", "no", "number", "code", "key", "uuid", "ref", "serial", "index"}

def _is_id_like(series: pd.Series, col_name: str) -> bool:
    """Heuristic: column is an identifier, not a meaningful feature."""
    name_lower = col_name.lower()
    # Name-based check
    if any(kw in name_lower.split("_") or kw in name_lower.split() for kw in _ID_KEYWORDS):
        return True
    if name_lower.endswith("id") or name_lower.endswith("_id"):
        return True
    # Cardinality-based check (>85 % unique values → likely an ID)
    if len(series) > 0 and series.nunique() / len(series) > 0.85:
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# CORE ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def _compute_summary(df: pd.DataFrame, target: str) -> dict:
    """Dataset-level quality statistics."""
    original_rows = len(df)
    df_dedup = df.drop_duplicates()
    duplicate_count = original_rows - len(df_dedup)

    total_cells = df_dedup.size
    missing_total = int(df_dedup.isnull().sum().sum())
    missing_pct = round(missing_total / total_cells * 100, 2) if total_cells > 0 else 0.0

    # Outlier detection — exclude ID-like and target columns
    numeric_cols = df_dedup.select_dtypes(include="number").columns.tolist()
    analysis_numeric = [
        c for c in numeric_cols
        if c != target and not _is_id_like(df_dedup[c], c)
    ]

    outlier_rows: set = set()
    for col in analysis_numeric:
        series = df_dedup[col].dropna()
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        mask = (df_dedup[col] < q1 - 1.5 * iqr) | (df_dedup[col] > q3 + 1.5 * iqr)
        outlier_rows.update(df_dedup[mask].index.tolist())

    outlier_count = len(outlier_rows)
    outlier_pct = round(outlier_count / len(df_dedup) * 100, 2) if len(df_dedup) > 0 else 0.0

    # Class imbalance
    class_imbalance = 1.0
    if target in df_dedup.columns:
        dist = df_dedup[target].value_counts(normalize=True)
        class_imbalance = round(float(dist.max()), 4)

    return {
        "num_samples": original_rows,
        "clean_count": len(df_dedup),
        "duplicate_count": duplicate_count,
        "duplicate_pct": round(duplicate_count / original_rows * 100, 2) if original_rows else 0.0,
        "outlier_count": outlier_count,
        "outlier_pct": outlier_pct,
        "missing_pct": missing_pct,
        "missing_total": missing_total,
        "num_features": len(df.columns) - 1,
        "class_imbalance": class_imbalance,
        "count_source": "file",
    }


def _analyze_columns(df: pd.DataFrame, target: str) -> list[dict]:
    """Per-column quality metrics including skewness and type issues."""
    results = []
    for col in df.columns:
        series = df[col]
        missing = int(series.isnull().sum())
        is_numeric = pd.api.types.is_numeric_dtype(series)
        dtype_label = "numeric" if is_numeric else "categorical"

        outliers = 0
        skewness = None
        constant = False
        high_cardinality = False
        type_mismatch = False

        if is_numeric and col != target and not _is_id_like(series, col):
            clean = series.dropna()
            if len(clean) >= 4:
                q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
                iqr = q3 - q1
                if iqr > 0:
                    outliers = int(((clean < q1 - 1.5 * iqr) | (clean > q3 + 1.5 * iqr)).sum())
            if len(clean) >= 3:
                sk = scipy_stats.skew(clean)
                skewness = round(float(sk), 3) if not (math.isnan(sk) or math.isinf(sk)) else None
            constant = int(series.nunique()) <= 1

        elif not is_numeric and col != target:
            high_cardinality = (series.nunique() / len(df) > 0.85) if len(df) > 0 else False
            # Detect type mismatch: non-numeric column that could be numeric
            try:
                pd.to_numeric(series.dropna())
                type_mismatch = True  # stored as string but all values are numbers
            except (ValueError, TypeError):
                pass

        issue = missing > 0 or outliers > 0 or constant or high_cardinality or type_mismatch

        results.append({
            "name": col,
            "dtype": dtype_label,
            "missing": missing,
            "missing_pct": round(missing / len(df) * 100, 1) if len(df) > 0 else 0,
            "outliers": outliers,
            "skewness": skewness,
            "constant": constant,
            "high_cardinality": high_cardinality,
            "type_mismatch": type_mismatch,
            "issue": issue,
        })
    return results


def _compute_distributions(df: pd.DataFrame, target: str) -> list[dict]:
    """Build chart data for numeric (histogram) and categorical (bar) columns."""
    numeric_cols = [
        c for c in df.select_dtypes(include="number").columns
        if c != target and not _is_id_like(df[c], c)
    ][:4]  # cap at 4 numeric charts

    categorical_cols = [
        c for c in df.select_dtypes(include="object").columns
        if c != target and not _is_id_like(df[c], c)
    ][:3]  # cap at 3 categorical charts

    distributions = []

    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) < 2:
            continue
        try:
            counts, bins = pd.cut(series, bins=8, retbins=True)
            labels = [f"{bins[i]:.1f}–{bins[i+1]:.1f}" for i in range(len(bins) - 1)]
            values = counts.value_counts(sort=False).tolist()
            distributions.append({
                "col": col, "type": "histogram",
                "labels": labels, "values": values,
            })
        except Exception:
            pass

    for col in categorical_cols:
        vc = df[col].dropna().value_counts().head(10)
        if vc.empty:
            continue
        distributions.append({
            "col": col, "type": "bar",
            "labels": vc.index.tolist(),
            "values": vc.values.tolist(),
        })

    return distributions


def _compute_correlation(df: pd.DataFrame, target: str) -> tuple[list[str], list[float]]:
    """Correlation of each analysis numeric column with the target (or among themselves)."""
    numeric_cols = [
        c for c in df.select_dtypes(include="number").columns
        if c != target and not _is_id_like(df[c], c)
    ][:6]

    if not numeric_cols:
        return [], []

    correlation_values: list[float] = []

    if target in df.columns and pd.api.types.is_numeric_dtype(df[target]):
        for c in numeric_cols:
            val = df[c].corr(df[target])
            correlation_values.append(
                0.0 if (math.isnan(val) or math.isinf(val)) else round(abs(float(val)), 3)
            )
        return numeric_cols, correlation_values

    # Categorical target: correlate numeric cols among themselves
    if len(numeric_cols) >= 2:
        base = df[numeric_cols[0]]
        for c in numeric_cols[1:]:
            val = base.corr(df[c])
            correlation_values.append(
                0.0 if (math.isnan(val) or math.isinf(val)) else round(abs(float(val)), 3)
            )
        return numeric_cols[1:], correlation_values

    return [], []


def _compute_advanced_metrics(df: pd.DataFrame, target: str) -> dict:
    """
    Advanced quality metrics:
      - skewness profile (highly skewed columns)
      - coefficient of variation (data drift proxy)
      - constant / near-constant columns
      - high-cardinality string columns
    """
    numeric_cols = [
        c for c in df.select_dtypes(include="number").columns
        if c != target and not _is_id_like(df[c], c)
    ]

    highly_skewed: list[str] = []
    high_cv: list[str] = []
    constant_cols: list[str] = []

    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) < 3:
            continue
        sk = scipy_stats.skew(series)
        if not math.isnan(sk) and abs(sk) > 1.5:
            highly_skewed.append(col)
        mean_ = series.mean()
        std_ = series.std()
        if mean_ != 0:
            cv = abs(std_ / mean_)
            if cv > 2.0:
                high_cv.append(col)
        if series.nunique() <= 1:
            constant_cols.append(col)

    # High cardinality string columns (possible ID leakage into features)
    string_cols = df.select_dtypes(include="object").columns.tolist()
    high_card_strings = [
        c for c in string_cols
        if c != target and len(df) > 0 and df[c].nunique() / len(df) > 0.85
    ]

    return {
        "highly_skewed_cols": highly_skewed,
        "high_cv_cols": high_cv,
        "constant_cols": constant_cols,
        "high_cardinality_cols": high_card_strings,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SCORING
# ─────────────────────────────────────────────────────────────────────────────

def _compute_score(stats: dict, advanced: dict) -> dict:
    """
    Compute ML Readiness Score (0–100) with per-dimension subscores.

    Dimensions:
      Completeness  (30 pts) — missing values
      Consistency   (20 pts) — duplicates + type mismatches
      Validity      (20 pts) — outliers
      Balance       (15 pts) — class imbalance
      Usability     (15 pts) — constant cols, high-card strings, skewed cols
    """
    completeness = max(0.0, 30.0 - stats["missing_pct"] * 2.5)

    dup_penalty = min(stats["duplicate_pct"] * 3, 15)
    type_mismatch_penalty = min(len(advanced.get("high_cardinality_cols", [])) * 2, 5)
    consistency = max(0.0, 20.0 - dup_penalty - type_mismatch_penalty)

    validity = max(0.0, 20.0 - min(stats["outlier_pct"] * 1.5, 20))

    if stats["class_imbalance"] > 0.9:
        balance = 5.0
    elif stats["class_imbalance"] > 0.8:
        balance = 10.0
    else:
        balance = 15.0

    const_penalty = min(len(advanced.get("constant_cols", [])) * 3, 6)
    skew_penalty = min(len(advanced.get("highly_skewed_cols", [])) * 1, 5)
    cv_penalty = min(len(advanced.get("high_cv_cols", [])) * 1, 4)
    usability = max(0.0, 15.0 - const_penalty - skew_penalty - cv_penalty)

    total = int(completeness + consistency + validity + balance + usability)

    return {
        "total": min(100, total),
        "completeness": round(completeness),
        "consistency": round(consistency),
        "validity": round(validity),
        "balance": round(balance),
        "usability": round(usability),
    }


# ─────────────────────────────────────────────────────────────────────────────
# RECOMMENDATIONS
# ─────────────────────────────────────────────────────────────────────────────

def _build_recommendations(stats: dict, advanced: dict) -> list[dict]:
    recs: list[dict] = []

    if stats["missing_pct"] > 0:
        strategy = (
            "Drop columns with >50% missing. Use median imputation for numeric, "
            "mode for categorical columns with <30% missing."
            if stats["missing_pct"] > 15
            else "Use median/mode imputation. Consider KNN imputer for correlated columns."
        )
        recs.append({
            "icon": "🧹",
            "title": "Handle Missing Values",
            "desc": f"{stats['missing_pct']}% of cells are missing. {strategy}",
            "priority": "high" if stats["missing_pct"] > 10 else "medium",
        })

    if stats["duplicate_count"] > 0:
        recs.append({
            "icon": "🗑️",
            "title": "Remove Duplicate Rows",
            "desc": (
                f"{stats['duplicate_count']} duplicate rows ({stats['duplicate_pct']}%). "
                "Call df.drop_duplicates() before splitting train/test."
            ),
            "priority": "high",
        })

    if stats["outlier_pct"] > 3:
        recs.append({
            "icon": "🔍",
            "title": "Handle Outliers",
            "desc": (
                f"{stats['outlier_count']} outlier rows ({stats['outlier_pct']}%). "
                "Use IQR clipping (clip to Q1-1.5×IQR, Q3+1.5×IQR) or "
                "RobustScaler instead of StandardScaler."
            ),
            "priority": "high" if stats["outlier_pct"] > 10 else "medium",
        })

    if stats["class_imbalance"] > 0.8:
        recs.append({
            "icon": "⚖️",
            "title": "Address Class Imbalance",
            "desc": (
                f"Dominant class holds {stats['class_imbalance']*100:.1f}% of samples. "
                "Use SMOTE for oversampling, class_weight='balanced' in your model, "
                "or stratified k-fold cross-validation."
            ),
            "priority": "high" if stats["class_imbalance"] > 0.9 else "medium",
        })

    if advanced.get("highly_skewed_cols"):
        cols = ", ".join(advanced["highly_skewed_cols"][:4])
        recs.append({
            "icon": "📐",
            "title": "Fix Skewed Features",
            "desc": (
                f"Highly skewed columns: {cols}. "
                "Apply log1p or Box-Cox transform before training."
            ),
            "priority": "medium",
        })

    if advanced.get("constant_cols"):
        cols = ", ".join(advanced["constant_cols"])
        recs.append({
            "icon": "🚫",
            "title": "Drop Constant Columns",
            "desc": (
                f"Constant (zero-variance) columns: {cols}. "
                "These add no predictive signal — remove before training."
            ),
            "priority": "high",
        })

    if advanced.get("high_cardinality_cols"):
        cols = ", ".join(advanced["high_cardinality_cols"][:3])
        recs.append({
            "icon": "🔑",
            "title": "Check High-Cardinality Columns",
            "desc": (
                f"Possible ID/free-text columns: {cols}. "
                "Encoding them directly causes data leakage. Drop or hash-encode."
            ),
            "priority": "high",
        })

    # Always recommend scaling
    recs.append({
        "icon": "📏",
        "title": "Scale Numeric Features",
        "desc": (
            "Apply StandardScaler (Gaussian data) or MinMaxScaler (bounded data) "
            "to all numeric features after splitting train/test."
        ),
        "priority": "low",
    })

    if advanced.get("high_cv_cols"):
        recs.append({
            "icon": "📉",
            "title": "High Variance — Possible Data Drift",
            "desc": (
                f"Columns with coefficient of variation > 2: "
                f"{', '.join(advanced['high_cv_cols'][:3])}. "
                "Monitor for distribution shift if this is production data."
            ),
            "priority": "low",
        })

    return recs


# ─────────────────────────────────────────────────────────────────────────────
# ML PREDICTION
# ─────────────────────────────────────────────────────────────────────────────

def _ml_predict(df: pd.DataFrame, target: str) -> str:
    """Run the trained meta-model. Returns risk label string."""
    model_path = os.path.join(os.path.dirname(__file__), "..", "meta_model.pkl")
    model_path = os.path.normpath(model_path)

    if not os.path.exists(model_path):
        return "Unknown (model not found)"

    try:
        import pickle
        sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))
        from meta_features import extract_meta_features  # noqa: PLC0415

        features = extract_meta_features(df, target)
        with open(model_path, "rb") as fh:
            model = pickle.load(fh)
        return str(model.predict([features])[0])
    except Exception as exc:
        print(f"[WARN] ML prediction skipped: {exc}")
        return "Unknown (prediction error)"


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/analyze", methods=["POST"])
def analyze():
    filepath = None
    try:
        # ── Validation ───────────────────────────────────────────────────────
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files["file"]
        target_column = request.form.get("target_column", "").strip()

        if not file.filename:
            return jsonify({"error": "No file selected"}), 400
        if not target_column:
            return jsonify({"error": "Target column name is required"}), 400

        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({"error": f"Unsupported file type: .{ext}"}), 400

        # ── Save & load ──────────────────────────────────────────────────────
        safe_name = os.path.basename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, safe_name)
        file.save(filepath)
        print(f"\n[REQUEST] file={safe_name}  target={target_column}")

        df = _load_file(filepath)

        # ── Resolve target column ────────────────────────────────────────────
        try:
            target_column = _resolve_target(df, target_column)
        except KeyError:
            return jsonify({
                "error": f'Column "{target_column}" not found.',
                "available_columns": df.columns.tolist(),
            }), 400

        # ── Run all quality checks ───────────────────────────────────────────
        stats = _compute_summary(df, target_column)
        columns = _analyze_columns(df, target_column)
        advanced = _compute_advanced_metrics(df, target_column)
        score_breakdown = _compute_score(stats, advanced)
        corr_cols, correlation = _compute_correlation(df, target_column)
        distributions = _compute_distributions(df, target_column)
        recommendations = _build_recommendations(stats, advanced)
        prediction = _ml_predict(df, target_column)

        # Legacy single-distribution field (backward compat with older frontend)
        dist_labels = distributions[0]["labels"] if distributions else []
        dist_values = distributions[0]["values"] if distributions else []

        payload = {
            "score": score_breakdown["total"],
            "score_breakdown": score_breakdown,
            "prediction": prediction,
            "summary": stats,
            "advanced": advanced,
            "columns": columns,
            "distributions": distributions,
            "distribution": {"labels": dist_labels, "values": dist_values},
            "correlation": correlation,
            "corr_cols": corr_cols,
            "recommendations": recommendations,
        }

        return jsonify(_clean(payload))

    except Exception:
        print(traceback.format_exc())
        return jsonify({"error": "Internal server error — check backend logs"}), 500

    finally:
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": "2.0"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
