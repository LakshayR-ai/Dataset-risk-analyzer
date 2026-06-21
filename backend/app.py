# -*- coding: utf-8 -*-
"""
Dataset Quality Analyzer — Backend API  (v3)
=============================================
Flask REST API that receives a dataset file (CSV, XLSX, XLS, JSON, or ZIP
containing multiple CSVs/XLSX/JSON), performs comprehensive data-quality
analysis, and returns a structured JSON report.

Endpoints
---------
POST /api/analyze    — upload + analyze a dataset file (single or ZIP)
GET  /api/health     — liveness probe  {"status":"ok","version":"3.0"}
"""

from __future__ import annotations

import math
import os
import sys
import traceback
import uuid
import zipfile
import shutil
import tempfile

import numpy as np
import pandas as pd
from flask import Flask, request, jsonify
from flask_cors import CORS
from scipy import stats as scipy_stats
import openpyxl  # noqa: F401 — imported to ensure openpyxl is available for pd.read_excel

app = Flask(__name__)
CORS(
    app,
    resources={r"/api/*": {"origins": [
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:8080", "http://127.0.0.1:8080",
        "null",
    ]}},
)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls", "json"}
ALLOWED_EXTENSIONS_ZIP = ALLOWED_EXTENSIONS | {"zip"}
MAX_FILE_BYTES = 200 * 1024 * 1024  # 200 MB

# Keywords that flag a column as a target candidate
_TARGET_KEYWORDS = {
    "target", "label", "class", "outcome", "result",
    "price", "rating", "churn", "fraud", "survived",
    "diagnosis", "default",
}

# Keywords that flag a column as an identifier (not a feature)
_ID_KEYWORDS = {
    "id", "no", "number", "code", "key", "uuid",
    "ref", "serial", "index",
}


# ─────────────────────────────────────────────────────────────────────────────
# SERIALISATION HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _clean(val):
    """Recursively replace NaN / Inf / numpy scalars so jsonify never raises."""
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        v = float(val)
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(val, (np.ndarray,)):
        return [_clean(v) for v in val.tolist()]
    if isinstance(val, dict):
        return {k: _clean(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_clean(v) for v in val]
    if isinstance(val, (np.bool_,)):
        return bool(val)
    return val


# ─────────────────────────────────────────────────────────────────────────────
# FILE LOADING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _load_file(filepath: str) -> pd.DataFrame:
    ext = filepath.rsplit(".", 1)[-1].lower()
    loaders = {
        "csv":  lambda p: pd.read_csv(p, low_memory=False),
        "xlsx": lambda p: pd.read_excel(p, engine="openpyxl"),
        "xls":  lambda p: pd.read_excel(p, engine="openpyxl"),
        "json": lambda p: pd.read_json(p),
    }
    if ext not in loaders:
        raise ValueError(f"Unsupported file format: .{ext}")
    df = loaders[ext](filepath)
    print(f"[LOAD]  rows={len(df)}  cols={len(df.columns)}  file={os.path.basename(filepath)}")
    return df


def _resolve_target(df: pd.DataFrame, target: str) -> str:
    """Case-insensitive column lookup. Returns exact column name or raises KeyError."""
    if target in df.columns:
        return target
    mapping = {c.strip().lower(): c for c in df.columns}
    match = mapping.get(target.strip().lower())
    if match:
        print(f"[INFO]  Column matched: '{target}' → '{match}'")
        return match
    raise KeyError(target)


# ─────────────────────────────────────────────────────────────────────────────
# ID-LIKE COLUMN DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def _is_id_like(series: pd.Series, col_name: str) -> bool:
    name_lower = col_name.lower()
    parts = set(name_lower.replace("-", "_").split("_")) | {name_lower}
    if parts & _ID_KEYWORDS:
        return True
    if name_lower.endswith("id") or name_lower.endswith("_id"):
        return True
    n = len(series)
    if n > 0 and series.nunique() / n > 0.85:
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# AUTO TARGET DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def _auto_detect_target(df: pd.DataFrame) -> list[dict]:
    """
    Suggest target columns ranked by confidence (0–1).

    Signals used:
      • Column name contains a known target keyword  (+0.5)
      • Low unique ratio  (< 5% of rows OR < 20 unique values)  (+0.3)
      • Categorical dtype  (+0.2)
      • Is NOT id-like  (prerequisite)
    """
    if df.empty:
        return []

    suggestions = []
    n = len(df)

    for col in df.columns:
        if _is_id_like(df[col], col):
            continue

        score = 0.0
        col_lower = col.lower()

        # keyword match
        if any(kw in col_lower for kw in _TARGET_KEYWORDS):
            score += 0.5

        n_unique = df[col].nunique()
        is_cat = not pd.api.types.is_numeric_dtype(df[col])

        # low cardinality → good target
        if n_unique < 20 or (n > 0 and n_unique / n < 0.05):
            score += 0.3

        # prefer categorical
        if is_cat:
            score += 0.2

        if score > 0:
            suggestions.append({
                "column": col,
                "confidence": round(min(score, 1.0), 2),
                "unique_values": int(n_unique),
                "dtype": str(df[col].dtype),
            })

    suggestions.sort(key=lambda x: x["confidence"], reverse=True)
    return suggestions[:5]


# ─────────────────────────────────────────────────────────────────────────────
# DATA PROFILING ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def _classify_dtype(series: pd.Series) -> tuple[str, str]:
    """
    Returns (dtype_class, suggested_dtype).
    dtype_class: "numeric" | "categorical" | "datetime" | "boolean"
    suggested_dtype: pandas dtype string if conversion is advisable, else ""
    """
    raw = str(series.dtype)
    suggested = ""

    if pd.api.types.is_bool_dtype(series):
        return "boolean", suggested

    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime", suggested

    if pd.api.types.is_numeric_dtype(series):
        return "numeric", suggested

    # Object column — try to coerce
    non_null = series.dropna()
    if len(non_null) == 0:
        return "categorical", suggested

    # Try datetime
    try:
        parsed = pd.to_datetime(non_null, infer_datetime_format=True, errors="raise")
        if len(parsed) == len(non_null):
            return "categorical", "datetime"
    except Exception:
        pass

    # Try numeric
    try:
        pd.to_numeric(non_null, errors="raise")
        return "categorical", "numeric"
    except Exception:
        pass

    return "categorical", suggested


def _profile_dataset(df: pd.DataFrame, target: str | None = None) -> dict:
    """Full dataset + per-column profile."""
    print("[STEP]  Profiling dataset …")

    if df.empty:
        return {"overview": {}, "columns": []}

    n_rows, n_cols = df.shape
    memory_mb = round(df.memory_usage(deep=True).sum() / 1e6, 3)
    dup_rows = int(df.duplicated().sum())
    dup_pct = round(dup_rows / n_rows * 100, 2) if n_rows else 0.0
    missing_cells = int(df.isnull().sum().sum())
    total_cells = n_rows * n_cols
    missing_pct = round(missing_cells / total_cells * 100, 2) if total_cells else 0.0
    complete_rows = int((df.isnull().sum(axis=1) == 0).sum())
    complete_rows_pct = round(complete_rows / n_rows * 100, 2) if n_rows else 0.0

    dtype_classes = {col: _classify_dtype(df[col])[0] for col in df.columns}
    numeric_cols = sum(1 for v in dtype_classes.values() if v == "numeric")
    categorical_cols = sum(1 for v in dtype_classes.values() if v == "categorical")
    datetime_cols = sum(1 for v in dtype_classes.values() if v == "datetime")

    overview = {
        "rows": n_rows,
        "columns": n_cols,
        "memory_mb": memory_mb,
        "numeric_cols": numeric_cols,
        "categorical_cols": categorical_cols,
        "datetime_cols": datetime_cols,
        "duplicate_rows": dup_rows,
        "duplicate_pct": dup_pct,
        "missing_cells": missing_cells,
        "missing_pct": missing_pct,
        "complete_rows": complete_rows,
        "complete_rows_pct": complete_rows_pct,
    }

    col_profiles = []
    for col in df.columns:
        col_profiles.append(_profile_column(df[col], col, n_rows, target))

    return {"overview": overview, "columns": col_profiles}


def _profile_column(series: pd.Series, col: str, n_rows: int, target: str | None) -> dict:
    """Build per-column profile dict."""
    dtype_class, suggested_dtype = _classify_dtype(series)
    missing = int(series.isnull().sum())
    missing_pct = round(missing / n_rows * 100, 2) if n_rows else 0.0
    n_unique = int(series.nunique())
    unique_pct = round(n_unique / n_rows * 100, 2) if n_rows else 0.0
    is_id = _is_id_like(series, col)
    is_constant = n_unique <= 1

    # target candidate heuristic
    is_target_candidate = (
        not is_id
        and col != target
        and (n_unique < 20 or (n_rows > 0 and n_unique / n_rows < 0.05))
    )

    base = {
        "name": col,
        "dtype_raw": str(series.dtype),
        "dtype_class": dtype_class,
        "suggested_dtype": suggested_dtype,
        "missing": missing,
        "missing_pct": missing_pct,
        "unique": n_unique,
        "unique_pct": unique_pct,
        "is_id_like": is_id,
        "is_constant": is_constant,
        "is_target_candidate": is_target_candidate,
    }

    clean = series.dropna()

    if dtype_class == "numeric" and len(clean) >= 2:
        arr = clean.astype(float)
        q25 = float(arr.quantile(0.25))
        q75 = float(arr.quantile(0.75))
        iqr = q75 - q25
        mean_ = float(arr.mean())
        std_ = float(arr.std())

        # IQR outliers
        if iqr > 0:
            outliers_iqr = int(((arr < q25 - 1.5 * iqr) | (arr > q75 + 1.5 * iqr)).sum())
        else:
            outliers_iqr = 0

        # Z-score outliers
        if std_ > 0 and len(arr) >= 3:
            z = np.abs(scipy_stats.zscore(arr))
            outliers_zscore = int((z > 3).sum())
        else:
            outliers_zscore = 0

        sk = float(scipy_stats.skew(arr)) if len(arr) >= 3 else 0.0
        kt = float(scipy_stats.kurtosis(arr)) if len(arr) >= 4 else 0.0
        cv = abs(std_ / mean_) if mean_ != 0 else None

        base.update({
            "mean": round(mean_, 4),
            "median": round(float(arr.median()), 4),
            "std": round(std_, 4),
            "min": round(float(arr.min()), 4),
            "max": round(float(arr.max()), 4),
            "q25": round(q25, 4),
            "q75": round(q75, 4),
            "skewness": round(sk, 4) if not math.isnan(sk) else None,
            "kurtosis": round(kt, 4) if not math.isnan(kt) else None,
            "outliers_iqr": outliers_iqr,
            "outliers_zscore": outliers_zscore,
            "cv": round(cv, 4) if cv is not None else None,
        })
    elif dtype_class == "categorical" and len(clean) > 0:
        vc = clean.value_counts()
        top_value = str(vc.index[0]) if len(vc) > 0 else None
        top_freq = int(vc.iloc[0]) if len(vc) > 0 else 0
        top_freq_pct = round(top_freq / len(clean) * 100, 2) if len(clean) > 0 else 0.0
        base.update({
            "top_value": top_value,
            "top_freq": top_freq,
            "top_freq_pct": top_freq_pct,
        })

    return base


# ─────────────────────────────────────────────────────────────────────────────
# DATA QUALITY CHECK ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def _missing_risk(pct: float) -> str:
    if pct > 50:  return "CRITICAL"
    if pct > 20:  return "HIGH"
    if pct > 5:   return "MEDIUM"
    return "LOW"


def _outlier_risk(count: int, n_rows: int) -> str:
    if n_rows == 0:
        return "LOW"
    pct = count / n_rows * 100
    if pct > 15: return "HIGH"
    if pct > 5:  return "MEDIUM"
    return "LOW"


def _run_quality_checks(df: pd.DataFrame, profile: dict, target: str | None = None) -> dict:
    """Return structured quality check results."""
    print("[STEP]  Running quality checks …")

    if df.empty:
        return {
            "missing": {"total_missing_pct": 0.0, "columns": []},
            "duplicates": {"duplicate_rows": 0, "duplicate_pct": 0.0, "risk": "LOW"},
            "outliers": {"affected_columns": []},
            "wrong_types": {"columns": []},
            "invalid_values": {"negative_where_invalid": [], "zero_where_invalid": []},
            "skewness": {"columns": []},
            "correlation": {"high_pairs": [], "medium_pairs": []},
        }

    overview = profile.get("overview", {})
    col_profiles = {c["name"]: c for c in profile.get("columns", [])}
    n_rows = len(df)

    # ── Missing ──────────────────────────────────────────────────────────────
    missing_cols = []
    for col in df.columns:
        cp = col_profiles.get(col, {})
        m = cp.get("missing", 0)
        pct = cp.get("missing_pct", 0.0)
        if m > 0:
            missing_cols.append({
                "col": col,
                "missing": m,
                "pct": pct,
                "risk": _missing_risk(pct),
            })
    missing_cols.sort(key=lambda x: x["pct"], reverse=True)

    # ── Duplicates ───────────────────────────────────────────────────────────
    dup_rows = overview.get("duplicate_rows", 0)
    dup_pct = overview.get("duplicate_pct", 0.0)
    if dup_pct > 20:   dup_risk = "HIGH"
    elif dup_pct > 5:  dup_risk = "MEDIUM"
    elif dup_pct > 0:  dup_risk = "LOW"
    else:              dup_risk = "LOW"

    # ── Outliers ─────────────────────────────────────────────────────────────
    outlier_cols = []
    for col in df.columns:
        cp = col_profiles.get(col, {})
        if cp.get("dtype_class") != "numeric":
            continue
        iqr_c = cp.get("outliers_iqr", 0)
        zsc_c = cp.get("outliers_zscore", 0)
        if iqr_c > 0 or zsc_c > 0:
            outlier_cols.append({
                "col": col,
                "iqr_count": iqr_c,
                "zscore_count": zsc_c,
                "risk": _outlier_risk(max(iqr_c, zsc_c), n_rows),
            })

    # ── Wrong types ──────────────────────────────────────────────────────────
    wrong_types = []
    for col in df.columns:
        cp = col_profiles.get(col, {})
        sug = cp.get("suggested_dtype", "")
        if sug:
            wrong_types.append({
                "col": col,
                "current_type": cp.get("dtype_raw", ""),
                "suggested_type": sug,
            })

    # ── Invalid values ───────────────────────────────────────────────────────
    _NEG_INVALID_KW = {"price", "age", "qty", "quantity", "amount",
                       "salary", "weight", "height", "distance", "count"}
    _ZERO_INVALID_KW = {"bmi", "salary", "price", "age", "weight", "height"}

    neg_invalid = []
    zero_invalid = []
    for col in df.select_dtypes(include="number").columns:
        col_lower = col.lower()
        if any(kw in col_lower for kw in _NEG_INVALID_KW):
            n_neg = int((df[col] < 0).sum())
            if n_neg > 0:
                neg_invalid.append({"col": col, "count": n_neg})
        if any(kw in col_lower for kw in _ZERO_INVALID_KW):
            n_zero = int((df[col] == 0).sum())
            if n_zero > 0:
                zero_invalid.append({"col": col, "count": n_zero})

    # ── Skewness ─────────────────────────────────────────────────────────────
    skew_cols = []
    for col in df.columns:
        cp = col_profiles.get(col, {})
        if cp.get("dtype_class") != "numeric":
            continue
        sk = cp.get("skewness")
        if sk is None:
            continue
        abs_sk = abs(sk)
        if abs_sk > 2:    level = "HIGH"
        elif abs_sk > 1:  level = "MEDIUM"
        else:             level = "LOW"
        if level != "LOW":
            skew_cols.append({"col": col, "skewness": sk, "level": level})

    # ── Correlation ──────────────────────────────────────────────────────────
    high_pairs = []
    medium_pairs = []
    num_df = df.select_dtypes(include="number")
    if len(num_df.columns) >= 2:
        sample = num_df if len(num_df) <= 100_000 else num_df.sample(50_000, random_state=42)
        try:
            corr_matrix = sample.corr()
            cols_list = corr_matrix.columns.tolist()
            for i in range(len(cols_list)):
                for j in range(i + 1, len(cols_list)):
                    r = corr_matrix.iloc[i, j]
                    if math.isnan(r):
                        continue
                    abs_r = abs(r)
                    pair = {"col1": cols_list[i], "col2": cols_list[j], "correlation": round(r, 3)}
                    if abs_r > 0.9:
                        high_pairs.append(pair)
                    elif abs_r > 0.7:
                        medium_pairs.append(pair)
        except Exception as exc:
            print(f"[WARN]  Correlation matrix failed: {exc}")

    return {
        "missing": {
            "total_missing_pct": overview.get("missing_pct", 0.0),
            "columns": missing_cols,
        },
        "duplicates": {
            "duplicate_rows": dup_rows,
            "duplicate_pct": dup_pct,
            "risk": dup_risk,
        },
        "outliers": {"affected_columns": outlier_cols},
        "wrong_types": {"columns": wrong_types},
        "invalid_values": {
            "negative_where_invalid": neg_invalid,
            "zero_where_invalid": zero_invalid,
        },
        "skewness": {"columns": skew_cols},
        "correlation": {"high_pairs": high_pairs, "medium_pairs": medium_pairs},
    }


# ─────────────────────────────────────────────────────────────────────────────
# ML READINESS
# ─────────────────────────────────────────────────────────────────────────────

def _ml_readiness(df: pd.DataFrame, target: str, profile: dict) -> dict:
    """ML readiness report. Only called when target is provided."""
    print("[STEP]  Computing ML readiness …")

    if df.empty or target not in df.columns:
        return {}

    col_profiles = {c["name"]: c for c in profile.get("columns", [])}
    target_series = df[target].dropna()
    n_unique_target = target_series.nunique()

    # Determine task type
    is_numeric_target = pd.api.types.is_numeric_dtype(df[target])
    if not is_numeric_target:
        task_type = "classification"
    elif n_unique_target <= 20:
        task_type = "classification"
    else:
        task_type = "regression"

    result: dict = {"task_type": task_type}

    if task_type == "classification":
        vc = target_series.value_counts()
        dominant_class = str(vc.index[0]) if len(vc) > 0 else ""
        dominant_pct = round(float(vc.iloc[0] / len(target_series) * 100), 2) if len(target_series) > 0 else 0.0
        minority_pct = round(float(vc.iloc[-1] / len(target_series) * 100), 2) if len(vc) > 1 else dominant_pct

        if dominant_pct > 90:   imb_risk = "CRITICAL"
        elif dominant_pct > 80: imb_risk = "HIGH"
        elif dominant_pct > 70: imb_risk = "MEDIUM"
        else:                   imb_risk = "LOW"

        result["class_imbalance"] = {
            "dominant_class": dominant_class,
            "dominant_pct": dominant_pct,
            "minority_pct": minority_pct,
            "risk": imb_risk,
            "class_counts": {str(k): int(v) for k, v in vc.items()},
        }
    else:
        sk = float(scipy_stats.skew(target_series.astype(float))) if len(target_series) >= 3 else 0.0
        result["target_skewness"] = round(sk, 4) if not math.isnan(sk) else None

    # Leakage risk: numeric cols with |r| > 0.95 to target
    leakage_cols = []
    if is_numeric_target:
        num_df = df.select_dtypes(include="number").drop(columns=[target], errors="ignore")
        for col in num_df.columns:
            try:
                r = df[col].corr(df[target])
                if not math.isnan(r) and abs(r) > 0.95:
                    leakage_cols.append(col)
            except Exception:
                pass
    result["leakage_risk_cols"] = leakage_cols

    # Constant features
    constant_feats = [
        c["name"] for c in profile.get("columns", [])
        if c["name"] != target and c.get("is_constant", False)
    ]
    result["constant_features"] = constant_feats

    # Low variance: variance < 0.01 for numeric cols
    low_var = []
    for col in df.select_dtypes(include="number").columns:
        if col == target:
            continue
        try:
            v = float(df[col].dropna().var())
            if not math.isnan(v) and v < 0.01:
                low_var.append(col)
        except Exception:
            pass
    result["low_variance_features"] = low_var

    return result


# ─────────────────────────────────────────────────────────────────────────────
# SCORE SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

def _compute_score(profile: dict, checks: dict, ml: dict | None = None) -> dict:
    """
    Score 0–100.
      Missing values:   up to -30 pts
      Duplicates:       up to -20 pts
      Outliers:         up to -15 pts
      Invalid values:   up to -10 pts
      Type issues:      up to -10 pts
      Skewness:         up to -10 pts
      Bonus: +5 zero missing, +5 zero duplicates
    """
    overview = profile.get("overview", {})
    missing_pct = overview.get("missing_pct", 0.0)
    dup_pct     = overview.get("duplicate_pct", 0.0)
    n_rows      = overview.get("rows", 1) or 1

    # completeness (0-30)
    completeness = max(0.0, 30.0 - missing_pct * 2.0)

    # consistency / duplicates (0-20)
    consistency = max(0.0, 20.0 - min(dup_pct * 2.0, 20.0))

    # validity / outliers (0-20)
    total_outlier_rows = sum(
        c.get("iqr_count", 0)
        for c in checks.get("outliers", {}).get("affected_columns", [])
    )
    outlier_pct = total_outlier_rows / n_rows * 100 if n_rows else 0.0
    validity = max(0.0, 20.0 - min(outlier_pct * 1.5, 15.0))

    # usability (0-30): type issues + skewness + invalid vals
    type_penalty    = min(len(checks.get("wrong_types", {}).get("columns", [])) * 2, 10)
    skew_high       = sum(1 for c in checks.get("skewness", {}).get("columns", []) if c.get("level") == "HIGH")
    skew_penalty    = min(skew_high * 2, 10)
    inv_penalty     = min(
        (len(checks.get("invalid_values", {}).get("negative_where_invalid", [])) +
         len(checks.get("invalid_values", {}).get("zero_where_invalid", []))) * 2,
        10
    )
    usability = max(0.0, 30.0 - type_penalty - skew_penalty - inv_penalty)

    total = completeness + consistency + validity + usability

    # bonuses
    if missing_pct == 0:
        total += 5
    if dup_pct == 0:
        total += 5

    total = int(min(100, max(0, total)))

    if total >= 90:   grade = "Excellent"
    elif total >= 70: grade = "Good"
    elif total >= 50: grade = "Needs Cleaning"
    else:             grade = "High Risk"

    return {
        "total": total,
        "grade": grade,
        "completeness": int(round(completeness)),
        "consistency":  int(round(consistency)),
        "validity":     int(round(validity)),
        "usability":    int(round(usability)),
    }


# ─────────────────────────────────────────────────────────────────────────────
# RECOMMENDATIONS ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def _build_recommendations(
    profile: dict,
    checks: dict,
    score: dict,
    ml: dict | None = None,
) -> list[dict]:
    recs: list[dict] = []
    overview = profile.get("overview", {})
    missing_pct = overview.get("missing_pct", 0.0)
    dup_pct     = overview.get("duplicate_pct", 0.0)
    dup_rows    = overview.get("duplicate_rows", 0)

    # Missing values
    if missing_pct > 0:
        if missing_pct > 30:
            fix = "Drop columns with >50% missing (df.dropna(thresh=…)), then use SimpleImputer(strategy='median') for numeric and strategy='most_frequent' for categorical."
            priority = "HIGH"
        elif missing_pct > 5:
            fix = "Use SimpleImputer or df.fillna(df.median()) for numeric columns; df.fillna(df.mode().iloc[0]) for categoricals."
            priority = "HIGH"
        else:
            fix = "Use df.fillna(df.median()) / df.fillna(df.mode().iloc[0]) for light imputation, or KNNImputer for correlated columns."
            priority = "MEDIUM"
        recs.append({
            "icon": "🧹",
            "title": "Handle Missing Values",
            "problem": f"{missing_pct:.1f}% of cells are missing across {len(checks.get('missing',{}).get('columns',[]))} columns.",
            "impact": "Most ML algorithms cannot handle NaN. Missing data biases model performance.",
            "fix": fix,
            "priority": priority,
        })

    # Duplicates
    if dup_rows > 0:
        recs.append({
            "icon": "🗑️",
            "title": "Remove Duplicate Rows",
            "problem": f"{dup_rows} duplicate rows ({dup_pct:.1f}%).",
            "impact": "Duplicates inflate training metrics and can cause data leakage between train/test splits.",
            "fix": "df = df.drop_duplicates().reset_index(drop=True)",
            "priority": "HIGH" if dup_pct > 5 else "MEDIUM",
        })

    # Outliers
    outlier_cols = checks.get("outliers", {}).get("affected_columns", [])
    high_outlier_cols = [c for c in outlier_cols if c.get("risk") in ("HIGH", "MEDIUM")]
    if high_outlier_cols:
        cols_str = ", ".join(c["col"] for c in high_outlier_cols[:4])
        recs.append({
            "icon": "🔍",
            "title": "Handle Outliers",
            "problem": f"Outliers detected in: {cols_str}.",
            "impact": "Outliers skew model coefficients, distort scaling, and degrade tree-model splits.",
            "fix": "Use IQR clipping: df[col] = df[col].clip(Q1 - 1.5*IQR, Q3 + 1.5*IQR). Or use RobustScaler instead of StandardScaler.",
            "priority": "HIGH",
        })

    # Wrong types
    type_issues = checks.get("wrong_types", {}).get("columns", [])
    if type_issues:
        cols_str = ", ".join(f"{c['col']} → {c['suggested_type']}" for c in type_issues[:4])
        recs.append({
            "icon": "🔧",
            "title": "Fix Column Data Types",
            "problem": f"Columns stored as wrong type: {cols_str}.",
            "impact": "Wrong types prevent numeric operations, cause silent errors, and waste memory.",
            "fix": "Use pd.to_numeric(df[col], errors='coerce') or pd.to_datetime(df[col]) to coerce columns.",
            "priority": "MEDIUM",
        })

    # Skewness
    high_skew = [c for c in checks.get("skewness", {}).get("columns", []) if c.get("level") == "HIGH"]
    if high_skew:
        cols_str = ", ".join(c["col"] for c in high_skew[:4])
        recs.append({
            "icon": "📐",
            "title": "Fix Highly Skewed Features",
            "problem": f"Highly skewed columns (|skew|>2): {cols_str}.",
            "impact": "Skewed features hurt linear models and distance-based algorithms.",
            "fix": "Apply np.log1p(df[col]) for positive data, or use PowerTransformer(method='box-cox') / 'yeo-johnson'.",
            "priority": "MEDIUM",
        })

    # High correlation
    high_corr_pairs = checks.get("correlation", {}).get("high_pairs", [])
    if high_corr_pairs:
        pair = high_corr_pairs[0]
        recs.append({
            "icon": "🔗",
            "title": "Remove Highly Correlated Features",
            "problem": f"{len(high_corr_pairs)} feature pair(s) with |r|>0.9 (e.g. {pair['col1']} ↔ {pair['col2']}, r={pair['correlation']}).",
            "impact": "Multicollinearity inflates variance of coefficients and makes feature importance unreliable.",
            "fix": "Drop one of each highly correlated pair. Use VIF analysis or sklearn.feature_selection.SelectFromModel.",
            "priority": "MEDIUM",
        })

    # Invalid values
    neg_inv = checks.get("invalid_values", {}).get("negative_where_invalid", [])
    if neg_inv:
        cols_str = ", ".join(c["col"] for c in neg_inv[:3])
        recs.append({
            "icon": "⚠️",
            "title": "Fix Negative Values in Non-Negative Columns",
            "problem": f"Negative values found in columns that should be positive: {cols_str}.",
            "impact": "Negative prices/ages/counts indicate data entry errors and will confuse the model.",
            "fix": "df[col] = df[col].clip(lower=0) or df = df[df[col] >= 0] to remove invalid rows.",
            "priority": "HIGH",
        })

    # Class imbalance
    if ml and "class_imbalance" in ml:
        imb = ml["class_imbalance"]
        if imb.get("risk") in ("HIGH", "CRITICAL"):
            recs.append({
                "icon": "⚖️",
                "title": "Address Class Imbalance",
                "problem": f"Dominant class: {imb['dominant_pct']:.1f}%.",
                "impact": "Imbalanced classes cause models to ignore minority class, inflating accuracy while recall suffers.",
                "fix": "Use class_weight='balanced' in your model, or oversample with SMOTE: from imblearn.over_sampling import SMOTE.",
                "priority": "HIGH",
            })

    # Leakage risk
    if ml and ml.get("leakage_risk_cols"):
        cols_str = ", ".join(ml["leakage_risk_cols"][:3])
        recs.append({
            "icon": "🚨",
            "title": "Potential Data Leakage Detected",
            "problem": f"Columns with near-perfect correlation to target: {cols_str}.",
            "impact": "These columns may be derived from the target, causing unrealistically high model scores.",
            "fix": "Investigate and drop columns that are causally derived from the target before training.",
            "priority": "HIGH",
        })

    # Constant features
    if ml and ml.get("constant_features"):
        cols_str = ", ".join(ml["constant_features"][:4])
        recs.append({
            "icon": "🚫",
            "title": "Drop Constant Features",
            "problem": f"Zero-variance columns: {cols_str}.",
            "impact": "Constant columns carry no information and add noise to some models.",
            "fix": "from sklearn.feature_selection import VarianceThreshold; VT = VarianceThreshold(0).fit_transform(X)",
            "priority": "MEDIUM",
        })

    # Always recommend scaling
    recs.append({
        "icon": "📏",
        "title": "Scale Numeric Features",
        "problem": "Numeric features likely have different scales.",
        "impact": "Unscaled features cause distance-based models (KNN, SVM) and gradient descent to converge poorly.",
        "fix": "from sklearn.preprocessing import StandardScaler; X_scaled = StandardScaler().fit_transform(X_train)",
        "priority": "LOW",
    })

    return recs


# ─────────────────────────────────────────────────────────────────────────────
# DISTRIBUTION CHARTS
# ─────────────────────────────────────────────────────────────────────────────

def _compute_distributions(df: pd.DataFrame, target: str | None = None) -> list[dict]:
    """Histogram data for top numeric cols, bar chart for top categorical cols."""
    numeric_cols = [
        c for c in df.select_dtypes(include="number").columns
        if c != target and not _is_id_like(df[c], c)
    ][:4]

    categorical_cols = [
        c for c in df.select_dtypes(include="object").columns
        if c != target and not _is_id_like(df[c], c)
    ][:3]

    distributions = []

    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) < 2:
            continue
        try:
            counts, bins = pd.cut(series, bins=8, retbins=True)
            labels = [f"{bins[i]:.2g}–{bins[i+1]:.2g}" for i in range(len(bins) - 1)]
            values = counts.value_counts(sort=False).tolist()
            distributions.append({"col": col, "type": "histogram", "labels": labels, "values": values})
        except Exception:
            pass

    for col in categorical_cols:
        vc = df[col].dropna().value_counts().head(10)
        if vc.empty:
            continue
        distributions.append({
            "col": col, "type": "bar",
            "labels": [str(v) for v in vc.index.tolist()],
            "values": vc.values.tolist(),
        })

    return distributions


# ─────────────────────────────────────────────────────────────────────────────
# CORRELATION MATRIX (NxN for top 6 numeric cols)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_correlation_matrix(df: pd.DataFrame, target: str | None = None) -> dict:
    """Return cols + NxN matrix for up to 6 numeric columns."""
    num_df = df.select_dtypes(include="number")
    if target and target in num_df.columns:
        # Put target first so it's always included
        other_cols = [c for c in num_df.columns if c != target][:5]
        top_cols = [target] + other_cols
    else:
        top_cols = [
            c for c in num_df.columns
            if not _is_id_like(num_df[c], c)
        ][:6]

    if len(top_cols) < 2:
        return {"cols": [], "matrix": []}

    sample = df[top_cols]
    if len(sample) > 100_000:
        sample = sample.sample(50_000, random_state=42)

    try:
        corr = sample.corr()
    except Exception:
        return {"cols": top_cols, "matrix": []}

    matrix = []
    for col in top_cols:
        row = []
        for col2 in top_cols:
            val = corr.loc[col, col2] if col in corr.index and col2 in corr.columns else None
            if val is None or (isinstance(val, float) and math.isnan(val)):
                row.append(None)
            else:
                row.append(round(float(val), 3))
        matrix.append(row)

    return {"cols": top_cols, "matrix": matrix}


# ─────────────────────────────────────────────────────────────────────────────
# SINGLE-FILE ANALYSIS PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def _analyze_single_file(filepath: str, target: str | None = None) -> dict:
    """
    Run the full analysis pipeline for one file.
    Returns a report dict ready for JSON serialisation.
    """
    filename = os.path.basename(filepath)
    print(f"[STEP]  Analyzing file: {filename}")

    try:
        df = _load_file(filepath)
    except Exception as exc:
        return {"filename": filename, "error": str(exc)}

    if df.empty:
        return {
            "filename": filename,
            "error": "File loaded but DataFrame is empty.",
            "target_used": None,
            "suggested_targets": [],
        }

    # Resolve or ignore target
    target_used = None
    if target:
        try:
            target_used = _resolve_target(df, target)
        except KeyError:
            print(f"[WARN]  Target '{target}' not found in {filename}, running without target.")
            target_used = None

    suggested_targets = _auto_detect_target(df)

    print("[STEP]  Building profile …")
    profile = _profile_dataset(df, target_used)

    print("[STEP]  Running quality checks …")
    checks = _run_quality_checks(df, profile, target_used)

    ml = None
    if target_used:
        ml = _ml_readiness(df, target_used, profile)

    print("[STEP]  Computing score …")
    score = _compute_score(profile, checks, ml)

    print("[STEP]  Building distributions …")
    distributions = _compute_distributions(df, target_used)

    print("[STEP]  Computing correlation matrix …")
    correlation_matrix = _compute_correlation_matrix(df, target_used)

    print("[STEP]  Building recommendations …")
    recommendations = _build_recommendations(profile, checks, score, ml)

    return _clean({
        "filename": filename,
        "target_used": target_used,
        "suggested_targets": suggested_targets,
        "profile": profile,
        "checks": checks,
        "ml_readiness": ml,
        "score": score,
        "distributions": distributions,
        "correlation_matrix": correlation_matrix,
        "recommendations": recommendations,
    })


# ─────────────────────────────────────────────────────────────────────────────
# ZIP SUPPORT
# ─────────────────────────────────────────────────────────────────────────────

def _analyze_zip(filepath: str, target: str | None = None) -> dict:
    """
    Extract a ZIP, analyze each CSV/XLSX/JSON inside, detect cross-file relationships.
    """
    print(f"[STEP]  Extracting ZIP: {filepath}")
    extract_dir = os.path.join(UPLOAD_FOLDER, str(uuid.uuid4()))
    os.makedirs(extract_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(filepath, "r") as zf:
            zf.extractall(extract_dir)

        # Collect eligible files (skip hidden / __MACOSX)
        data_files = []
        for root, _dirs, files in os.walk(extract_dir):
            for fname in files:
                if fname.startswith(".") or "__MACOSX" in root:
                    continue
                ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
                if ext in ALLOWED_EXTENSIONS:
                    data_files.append(os.path.join(root, fname))

        print(f"[STEP]  Found {len(data_files)} data file(s) inside ZIP.")

        if not data_files:
            return {"files": [], "relationships": [], "error": "ZIP contains no supported data files."}

        file_reports = []
        for fp in data_files:
            report = _analyze_single_file(fp, target)
            file_reports.append(report)

        # Auto relationship detection: shared column names across file pairs
        relationships = []
        file_cols: dict[str, set] = {}
        for report in file_reports:
            fname = report.get("filename", "")
            cols = set()
            if "profile" in report:
                for col_info in report["profile"].get("columns", []):
                    cols.add(col_info["name"])
            file_cols[fname] = cols

        fnames = list(file_cols.keys())
        for i in range(len(fnames)):
            for j in range(i + 1, len(fnames)):
                shared = file_cols[fnames[i]] & file_cols[fnames[j]]
                for col in sorted(shared):
                    relationships.append({
                        "file1": fnames[i],
                        "col1": col,
                        "file2": fnames[j],
                        "col2": col,
                    })

        return {"files": file_reports, "relationships": relationships}

    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/analyze", methods=["POST"])
def analyze():
    """
    Accept: multipart/form-data
      file          (required) — CSV, XLSX, XLS, JSON, or ZIP
      target_column (optional) — target / label column name

    Returns single-file report OR ZIP report depending on input.
    """
    request_id = str(uuid.uuid4())[:8]
    upload_dir = os.path.join(UPLOAD_FOLDER, request_id)
    os.makedirs(upload_dir, exist_ok=True)
    filepath = None

    try:
        # ── Validate input ────────────────────────────────────────────────────
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded. Provide a 'file' field."}), 400

        file = request.files["file"]
        if not file.filename:
            return jsonify({"error": "No file selected."}), 400

        # target_column is optional — empty string treated as None
        raw_target = request.form.get("target_column", "").strip()
        target_column = raw_target if raw_target else None

        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_EXTENSIONS_ZIP:
            return jsonify({
                "error": f"Unsupported file type: .{ext}",
                "allowed": sorted(ALLOWED_EXTENSIONS_ZIP),
            }), 400

        # ── Save uploaded file ────────────────────────────────────────────────
        safe_name = os.path.basename(file.filename)
        filepath = os.path.join(upload_dir, safe_name)
        file.save(filepath)
        print(f"\n[REQUEST {request_id}]  file={safe_name}  target={target_column}")

        # ── Dispatch: ZIP vs single file ─────────────────────────────────────
        if ext == "zip":
            print("[STEP]  Detected ZIP — entering multi-file mode.")
            result = _analyze_zip(filepath, target_column)
            return jsonify(_clean(result))

        else:
            print("[STEP]  Detected single file — entering single-file mode.")
            report = _analyze_single_file(filepath, target_column)

            # Surface top-level error if file failed to load
            if "error" in report and len(report) <= 4:
                return jsonify(report), 422

            return jsonify(_clean(report))

    except Exception:
        print(traceback.format_exc())
        return jsonify({"error": "Internal server error — check backend logs."}), 500

    finally:
        # Always clean up the per-request upload directory
        if upload_dir and os.path.exists(upload_dir):
            try:
                shutil.rmtree(upload_dir, ignore_errors=True)
            except OSError:
                pass


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": "3.0"})


# ─────────────────────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "1") != "0"
    app.run(debug=debug_mode, port=5000, use_reloader=debug_mode)
