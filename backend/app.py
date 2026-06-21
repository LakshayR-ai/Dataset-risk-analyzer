# -*- coding: utf-8 -*-
"""
DataQA — Backend API v4
=======================
All 10 enterprise improvements implemented:
  1. Intelligent scoring (column-importance-weighted missing penalty)
  2. Accurate datetime detection (name keywords + sample parsing)
  3. Wrong-type detection working (date/numeric stored as string)
  4. Outlier detection skips ordinal columns (<=10 unique values)
  5. Context-aware, column-specific AI recommendations
  6. Business impact analysis on every recommendation
  7. Severity distribution system (CRITICAL/HIGH/MEDIUM/LOW)
  8. Multi-file ZIP comparison dashboard
  9. Enhanced relationship analysis (PK/FK/broken refs)
 10. Rich report payload for upgraded UI
"""

from __future__ import annotations

import math
import os
import re
import sys
import traceback
import uuid
import zipfile
import shutil

import numpy as np
import pandas as pd
from flask import Flask, request, jsonify
from flask_cors import CORS
from scipy import stats as scipy_stats
import openpyxl  # noqa: F401

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": [
    "http://localhost:3000", "http://127.0.0.1:3000",
    "http://localhost:8080", "http://127.0.0.1:8080",
    "null",
]}})

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS     = {"csv", "xlsx", "xls", "json"}
ALLOWED_EXTENSIONS_ZIP = ALLOWED_EXTENSIONS | {"zip"}

# ── Keyword sets ────────────────────────────────────────────────────────────
_TARGET_KW  = {"target","label","class","outcome","result","price","rating",
               "churn","fraud","survived","diagnosis","default"}
_ID_KW      = {"id","no","number","code","key","uuid","ref","serial","index"}
_DT_KW      = {"date","time","timestamp","datetime","created","updated",
               "modified","at","dt","ts","_at","_date","_time","_ts"}
_CRITICAL_KW = {"id","customer","order","product","transaction","invoice",
                "payment","price","amount","revenue","cost","salary",
                "target","label","class","outcome","fraud","churn"}
_OPTIONAL_KW = {"comment","description","note","review","text","message",
                "feedback","remark","body","content","summary","detail",
                "title","subject","narrative"}


# ════════════════════════════════════════════════════════════════════════════
# SERIALISATION
# ════════════════════════════════════════════════════════════════════════════

def _clean(val):
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    if isinstance(val, np.integer):
        return int(val)
    if isinstance(val, np.floating):
        v = float(val)
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(val, np.ndarray):
        return [_clean(v) for v in val.tolist()]
    if isinstance(val, np.bool_):
        return bool(val)
    if isinstance(val, dict):
        return {k: _clean(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_clean(v) for v in val]
    return val


# ════════════════════════════════════════════════════════════════════════════
# FILE LOADING
# ════════════════════════════════════════════════════════════════════════════

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
    if target in df.columns:
        return target
    mapping = {c.strip().lower(): c for c in df.columns}
    match = mapping.get(target.strip().lower())
    if match:
        return match
    raise KeyError(target)


# ════════════════════════════════════════════════════════════════════════════
# COLUMN CLASSIFIERS
# ════════════════════════════════════════════════════════════════════════════

def _col_parts(col_name: str) -> set:
    lower = col_name.lower()
    return set(re.split(r"[_\-\s]+", lower)) | {lower}


def _is_id_like(series: pd.Series, col_name: str) -> bool:
    parts = _col_parts(col_name)
    if parts & _ID_KW:
        return True
    n = len(series)
    if n > 0 and series.nunique() / n > 0.85:
        return True
    return False


def _column_importance(col_name: str, target: str | None) -> str:
    """CRITICAL | IMPORTANT | OPTIONAL"""
    if col_name == target:
        return "CRITICAL"
    parts = _col_parts(col_name)
    lower = col_name.lower()
    if parts & _CRITICAL_KW or any(kw in lower for kw in _CRITICAL_KW):
        return "CRITICAL"
    if any(kw in lower for kw in _OPTIONAL_KW):
        return "OPTIONAL"
    return "IMPORTANT"


def _name_suggests_datetime(col_name: str) -> bool:
    parts = _col_parts(col_name)
    lower = col_name.lower()
    if parts & _DT_KW:
        return True
    if any(lower.endswith(suf) for suf in ("_at", "_date", "_time", "_ts", "_datetime")):
        return True
    return False


# ════════════════════════════════════════════════════════════════════════════
# DTYPE CLASSIFICATION  (FIX #2 + #3)
# ════════════════════════════════════════════════════════════════════════════

def _classify_dtype(series: pd.Series, col_name: str = "") -> tuple[str, str]:
    """
    Returns (dtype_class, suggested_dtype).
    FIX #2: Uses column name keywords to detect dates before expensive parsing.
    FIX #3: Correctly surfaces wrong-type suggestions even for datetime columns.
    """
    if pd.api.types.is_bool_dtype(series):
        return "boolean", ""
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime", ""
    if pd.api.types.is_numeric_dtype(series):
        return "numeric", ""

    non_null = series.dropna()
    if len(non_null) == 0:
        return "categorical", ""

    probe = non_null.iloc[:300]  # sample for speed

    # Fast-path: column name strongly suggests datetime
    if _name_suggests_datetime(col_name):
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pd.to_datetime(probe, errors="raise")
            return "categorical", "datetime"
        except Exception:
            pass  # name hint wrong, fall through

    # General datetime probe (sample only, suppress format warning)
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pd.to_datetime(probe, errors="raise")
        return "categorical", "datetime"
    except Exception:
        pass

    # Numeric-as-string probe (only if NOT a datetime candidate)
    if not _name_suggests_datetime(col_name):
        try:
            pd.to_numeric(probe, errors="raise")
            return "categorical", "numeric"
        except Exception:
            pass

    return "categorical", ""


# ════════════════════════════════════════════════════════════════════════════
# AUTO TARGET DETECTION
# ════════════════════════════════════════════════════════════════════════════

def _auto_detect_target(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    suggestions = []
    n = len(df)
    for col in df.columns:
        if _is_id_like(df[col], col):
            continue
        score = 0.0
        lower = col.lower()
        if any(kw in lower for kw in _TARGET_KW):
            score += 0.5
        n_unique = df[col].nunique()
        if n_unique < 20 or (n > 0 and n_unique / n < 0.05):
            score += 0.3
        if not pd.api.types.is_numeric_dtype(df[col]):
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


# ════════════════════════════════════════════════════════════════════════════
# DATA PROFILING
# ════════════════════════════════════════════════════════════════════════════

def _profile_column(series: pd.Series, col: str, n_rows: int,
                    target: str | None) -> dict:
    dtype_class, suggested_dtype = _classify_dtype(series, col)
    missing    = int(series.isnull().sum())
    missing_pct = round(missing / n_rows * 100, 2) if n_rows else 0.0
    n_unique   = int(series.nunique())
    unique_pct = round(n_unique / n_rows * 100, 2) if n_rows else 0.0
    is_id      = _is_id_like(series, col)
    importance = _column_importance(col, target)

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
        "is_constant": n_unique <= 1,
        "is_target_candidate": (not is_id and col != target
                                 and (n_unique < 20 or (n_rows > 0 and n_unique / n_rows < 0.05))),
        "importance": importance,
    }

    clean = series.dropna()

    if dtype_class == "numeric" and len(clean) >= 2:
        arr = clean.astype(float)
        q25 = float(arr.quantile(0.25))
        q75 = float(arr.quantile(0.75))
        iqr = q75 - q25
        mean_ = float(arr.mean())
        std_  = float(arr.std())

        # FIX #4: Skip IQR/Z-score for ordinal columns (<=10 unique values)
        is_ordinal = n_unique <= 10
        if iqr > 0 and not is_ordinal:
            outliers_iqr = int(((arr < q25 - 1.5 * iqr) | (arr > q75 + 1.5 * iqr)).sum())
        else:
            outliers_iqr = 0
        if std_ > 0 and len(arr) >= 3 and not is_ordinal:
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
            "is_ordinal": is_ordinal,
        })
    elif dtype_class == "categorical" and len(clean) > 0:
        vc = clean.value_counts()
        base.update({
            "top_value": str(vc.index[0]),
            "top_freq": int(vc.iloc[0]),
            "top_freq_pct": round(int(vc.iloc[0]) / len(clean) * 100, 2),
        })

    return base


def _profile_dataset(df: pd.DataFrame, target: str | None = None) -> dict:
    print("[STEP]  Profiling dataset …")
    if df.empty:
        return {"overview": {}, "columns": []}

    n_rows, n_cols = df.shape
    memory_mb     = round(df.memory_usage(deep=True).sum() / 1e6, 3)
    dup_rows      = int(df.duplicated().sum())
    dup_pct       = round(dup_rows / n_rows * 100, 2) if n_rows else 0.0
    missing_cells = int(df.isnull().sum().sum())
    total_cells   = n_rows * n_cols
    missing_pct   = round(missing_cells / total_cells * 100, 2) if total_cells else 0.0
    complete_rows = int((df.isnull().sum(axis=1) == 0).sum())

    col_profiles = [_profile_column(df[c], c, n_rows, target) for c in df.columns]
    dtype_map    = {cp["name"]: cp["dtype_class"] for cp in col_profiles}

    overview = {
        "rows": n_rows,
        "columns": n_cols,
        "memory_mb": memory_mb,
        "numeric_cols": sum(1 for v in dtype_map.values() if v == "numeric"),
        "categorical_cols": sum(1 for v in dtype_map.values() if v == "categorical"),
        "datetime_cols": sum(1 for v in dtype_map.values() if v == "datetime"),
        "duplicate_rows": dup_rows,
        "duplicate_pct": dup_pct,
        "missing_cells": missing_cells,
        "missing_pct": missing_pct,
        "complete_rows": complete_rows,
        "complete_rows_pct": round(complete_rows / n_rows * 100, 2) if n_rows else 0.0,
    }
    return {"overview": overview, "columns": col_profiles}


# ════════════════════════════════════════════════════════════════════════════
# QUALITY CHECKS
# ════════════════════════════════════════════════════════════════════════════

def _missing_risk(pct: float, importance: str) -> str:
    """FIX #1: Risk level depends on column importance, not just percentage."""
    if importance == "CRITICAL":
        if pct > 5:  return "CRITICAL"
        if pct > 0:  return "HIGH"
    if importance == "OPTIONAL":
        if pct > 80: return "MEDIUM"
        return "LOW"
    # IMPORTANT
    if pct > 50:  return "HIGH"
    if pct > 20:  return "MEDIUM"
    if pct > 5:   return "LOW"
    return "LOW"


def _outlier_risk(count: int, n_rows: int) -> str:
    if n_rows == 0: return "LOW"
    pct = count / n_rows * 100
    if pct > 15: return "HIGH"
    if pct > 5:  return "MEDIUM"
    return "LOW"


def _run_quality_checks(df: pd.DataFrame, profile: dict,
                        target: str | None = None) -> dict:
    print("[STEP]  Running quality checks …")
    if df.empty:
        return {
            "missing":       {"total_missing_pct": 0.0, "columns": []},
            "duplicates":    {"duplicate_rows": 0, "duplicate_pct": 0.0, "risk": "LOW"},
            "outliers":      {"affected_columns": []},
            "wrong_types":   {"columns": []},
            "invalid_values":{"negative_where_invalid": [], "zero_where_invalid": []},
            "skewness":      {"columns": []},
            "correlation":   {"high_pairs": [], "medium_pairs": []},
        }

    overview     = profile.get("overview", {})
    col_profiles = {c["name"]: c for c in profile.get("columns", [])}
    n_rows       = len(df)

    # Missing
    missing_cols = []
    for col in df.columns:
        cp  = col_profiles.get(col, {})
        m   = cp.get("missing", 0)
        pct = cp.get("missing_pct", 0.0)
        imp = cp.get("importance", "IMPORTANT")
        if m > 0:
            missing_cols.append({
                "col": col,
                "missing": m,
                "pct": pct,
                "risk": _missing_risk(pct, imp),
                "importance": imp,
            })
    missing_cols.sort(key=lambda x: (
        {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(x["risk"], 4),
        -x["pct"]
    ))

    # Duplicates
    dup_rows = overview.get("duplicate_rows", 0)
    dup_pct  = overview.get("duplicate_pct", 0.0)
    dup_risk = "HIGH" if dup_pct > 20 else "MEDIUM" if dup_pct > 5 else "LOW"

    # Outliers (FIX #4: ordinal cols already have outliers_iqr=0 from profiler)
    outlier_cols = []
    for col in df.columns:
        cp    = col_profiles.get(col, {})
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
                "is_ordinal": cp.get("is_ordinal", False),
            })

    # Wrong types (FIX #3: now correctly populated from profiler)
    wrong_types = []
    for col in df.columns:
        cp  = col_profiles.get(col, {})
        sug = cp.get("suggested_dtype", "")
        if sug:
            wrong_types.append({
                "col": col,
                "current_type": cp.get("dtype_raw", "object"),
                "suggested_type": sug,
            })

    # Invalid values
    _NEG_KW  = {"price","age","qty","quantity","amount","salary",
                "weight","height","distance","count","payment","value"}
    _ZERO_KW = {"bmi","salary","price","age","weight","height"}
    neg_invalid  = []
    zero_invalid = []
    for col in df.select_dtypes(include="number").columns:
        cl = col.lower()
        if any(kw in cl for kw in _NEG_KW):
            n_neg = int((df[col] < 0).sum())
            if n_neg > 0:
                neg_invalid.append({"col": col, "count": n_neg})
        if any(kw in cl for kw in _ZERO_KW):
            n_zero = int((df[col] == 0).sum())
            if n_zero > 0:
                zero_invalid.append({"col": col, "count": n_zero})

    # Skewness
    skew_cols = []
    for col in df.columns:
        cp = col_profiles.get(col, {})
        if cp.get("dtype_class") != "numeric" or cp.get("is_ordinal"):
            continue
        sk = cp.get("skewness")
        if sk is None:
            continue
        abs_sk = abs(sk)
        level  = "HIGH" if abs_sk > 2 else "MEDIUM" if abs_sk > 1 else "LOW"
        if level != "LOW":
            skew_cols.append({"col": col, "skewness": sk, "level": level})

    # Correlation
    high_pairs, medium_pairs = [], []
    num_df = df.select_dtypes(include="number")
    # Exclude ordinal columns from correlation analysis
    cont_cols = [c for c in num_df.columns
                 if not col_profiles.get(c, {}).get("is_ordinal", False)]
    num_df = num_df[cont_cols]
    if len(num_df.columns) >= 2:
        sample = num_df if len(num_df) <= 100_000 else num_df.sample(50_000, random_state=42)
        try:
            corr_matrix = sample.corr()
            cols_list   = corr_matrix.columns.tolist()
            for i in range(len(cols_list)):
                for j in range(i + 1, len(cols_list)):
                    r = corr_matrix.iloc[i, j]
                    if math.isnan(r):
                        continue
                    abs_r = abs(r)
                    pair  = {"col1": cols_list[i], "col2": cols_list[j],
                             "correlation": round(r, 3)}
                    if abs_r > 0.9:
                        high_pairs.append(pair)
                    elif abs_r > 0.7:
                        medium_pairs.append(pair)
        except Exception as exc:
            print(f"[WARN]  Correlation failed: {exc}")

    return {
        "missing":       {"total_missing_pct": overview.get("missing_pct", 0.0),
                          "columns": missing_cols},
        "duplicates":    {"duplicate_rows": dup_rows, "duplicate_pct": dup_pct,
                          "risk": dup_risk},
        "outliers":      {"affected_columns": outlier_cols},
        "wrong_types":   {"columns": wrong_types},
        "invalid_values":{"negative_where_invalid": neg_invalid,
                          "zero_where_invalid": zero_invalid},
        "skewness":      {"columns": skew_cols},
        "correlation":   {"high_pairs": high_pairs, "medium_pairs": medium_pairs},
    }


# ════════════════════════════════════════════════════════════════════════════
# SEVERITY DISTRIBUTION  (FIX #7)
# ════════════════════════════════════════════════════════════════════════════

def _build_severity_distribution(checks: dict, profile: dict,
                                  target: str | None) -> dict:
    """Classify every detected issue into CRITICAL/HIGH/MEDIUM/LOW."""
    issues: list[dict] = []

    # Missing
    for m in checks.get("missing", {}).get("columns", []):
        issues.append({
            "type": "missing",
            "col": m["col"],
            "desc": f"Missing values: {m['pct']}% in {m['col']} [{m['importance']}]",
            "severity": m.get("risk", "LOW"),
            "importance": m.get("importance", "IMPORTANT"),
        })

    # Duplicates
    dup_pct = checks.get("duplicates", {}).get("duplicate_pct", 0)
    if dup_pct > 0:
        sev = "HIGH" if dup_pct > 10 else "MEDIUM" if dup_pct > 2 else "LOW"
        issues.append({"type": "duplicate", "col": "—",
                       "desc": f"{dup_pct}% duplicate rows", "severity": sev,
                       "importance": "IMPORTANT"})

    # Outliers
    for o in checks.get("outliers", {}).get("affected_columns", []):
        issues.append({"type": "outlier", "col": o["col"],
                       "desc": f"Outliers: {o['iqr_count']} in {o['col']}",
                       "severity": o.get("risk", "LOW"),
                       "importance": "IMPORTANT"})

    # Wrong types
    for t in checks.get("wrong_types", {}).get("columns", []):
        issues.append({"type": "wrong_type", "col": t["col"],
                       "desc": f"Type mismatch: {t['col']} ({t['current_type']} → {t['suggested_type']})",
                       "severity": "MEDIUM", "importance": "IMPORTANT"})

    # Skewness
    for s in checks.get("skewness", {}).get("columns", []):
        sev = "HIGH" if s["level"] == "HIGH" else "MEDIUM"
        issues.append({"type": "skewness", "col": s["col"],
                       "desc": f"Skewed: {s['col']} (skew={s['skewness']})",
                       "severity": sev, "importance": "IMPORTANT"})

    # High correlation
    for p in checks.get("correlation", {}).get("high_pairs", []):
        issues.append({"type": "correlation",
                       "col": f"{p['col1']} ↔ {p['col2']}",
                       "desc": f"High correlation {p['correlation']} between {p['col1']} and {p['col2']}",
                       "severity": "MEDIUM", "importance": "IMPORTANT"})

    # Invalid values
    for inv in checks.get("invalid_values", {}).get("negative_where_invalid", []):
        issues.append({"type": "invalid_value", "col": inv["col"],
                       "desc": f"Negative values in {inv['col']} ({inv['count']} rows)",
                       "severity": "HIGH", "importance": "CRITICAL"})

    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for iss in issues:
        counts[iss["severity"]] = counts.get(iss["severity"], 0) + 1

    return {"counts": counts, "issues": issues, "total": len(issues)}


# ════════════════════════════════════════════════════════════════════════════
# INTELLIGENT SCORING  (FIX #1)
# ════════════════════════════════════════════════════════════════════════════

def _compute_score(profile: dict, checks: dict,
                   ml: dict | None = None,
                   target: str | None = None) -> dict:
    """
    Importance-weighted scoring.
    CRITICAL columns: full penalty (×2.5 per % missing)
    IMPORTANT columns: normal     (×1.5 per % missing)
    OPTIONAL columns:  reduced    (×0.3 per % missing)
    """
    overview = profile.get("overview", {})
    dup_pct  = overview.get("duplicate_pct", 0.0)
    n_rows   = overview.get("rows", 1) or 1

    # Completeness (0–30): weighted per column
    col_profiles = profile.get("columns", [])
    n_cols = max(len(col_profiles), 1)
    weighted_penalty = 0.0
    for cp in col_profiles:
        pct = cp.get("missing_pct", 0.0)
        if pct <= 0:
            continue
        imp = cp.get("importance", "IMPORTANT")
        w   = {"CRITICAL": 2.5, "IMPORTANT": 1.5, "OPTIONAL": 0.3}.get(imp, 1.5)
        weighted_penalty += (pct * w) / n_cols
    completeness = max(0.0, 30.0 - min(weighted_penalty * 3, 30.0))

    # Consistency (0–20)
    consistency = max(0.0, 20.0 - min(dup_pct * 2.0, 20.0))

    # Validity (0–20) — only continuous outlier columns
    total_outlier_rows = sum(
        c.get("iqr_count", 0)
        for c in checks.get("outliers", {}).get("affected_columns", [])
        if not c.get("is_ordinal", False)
    )
    outlier_pct = total_outlier_rows / n_rows * 100 if n_rows else 0.0
    validity = max(0.0, 20.0 - min(outlier_pct * 1.5, 15.0))

    # Usability (0–30)
    type_penalty = min(len(checks.get("wrong_types", {}).get("columns", [])) * 2, 10)
    skew_high    = sum(1 for c in checks.get("skewness", {}).get("columns", [])
                       if c.get("level") == "HIGH")
    skew_penalty = min(skew_high * 2, 10)
    inv_penalty  = min(
        (len(checks.get("invalid_values", {}).get("negative_where_invalid", [])) +
         len(checks.get("invalid_values", {}).get("zero_where_invalid", []))) * 2, 10)
    usability = max(0.0, 30.0 - type_penalty - skew_penalty - inv_penalty)

    total = completeness + consistency + validity + usability
    if overview.get("missing_pct", 1) == 0:
        total += 5
    if dup_pct == 0:
        total += 5
    total = int(min(100, max(0, total)))

    grade = ("Excellent" if total >= 90 else
             "Good"          if total >= 70 else
             "Needs Cleaning" if total >= 50 else
             "High Risk")

    return {
        "total": total, "grade": grade,
        "completeness": int(round(completeness)),
        "consistency":  int(round(consistency)),
        "validity":     int(round(validity)),
        "usability":    int(round(usability)),
    }


# ════════════════════════════════════════════════════════════════════════════
# CONTEXT-AWARE RECOMMENDATIONS  (FIX #5 + #6)
# ════════════════════════════════════════════════════════════════════════════

def _rec_missing(col: str, pct: float, target: str | None) -> dict:
    """Column-specific missing value recommendation with business impact."""
    imp   = _column_importance(col, target)
    lower = col.lower()

    if imp == "OPTIONAL":
        return {
            "icon": "💬", "priority": "LOW",
            "title": f"Optional field missing: {col}",
            "problem": f"{col} has {pct:.1f}% missing values.",
            "reason": "This is a user-generated optional field. Users can submit without filling it — missing values here are expected and do not indicate a data quality failure.",
            "technical_impact": "Text analytics and sentiment analysis will have reduced input. Core models using non-text features remain unaffected.",
            "business_impact": "No business reporting impact. NLP pipelines on this column will process fewer records.",
            "fix": f"df['{col}'] = df['{col}'].fillna('Not Provided')\n# Do NOT drop rows — the record is still valid.",
        }

    if imp == "CRITICAL" and any(k in lower for k in ("_id", "id_", "customerid", "orderid", "productid")):
        return {
            "icon": "🚨", "priority": "HIGH",
            "title": f"Critical key missing: {col}",
            "problem": f"{col} has {pct:.1f}% missing values in a primary/foreign key column.",
            "reason": f"{col} is likely a primary or foreign key. Missing keys break joins and relationships between datasets.",
            "technical_impact": f"JOIN operations on {col} will produce NaN rows. Any model or aggregation relying on this ID will fail or return biased results.",
            "business_impact": "Customer segmentation, order tracking, and cross-dataset analytics become impossible for affected rows.",
            "fix": f"# Option 1 — Remove anonymous records\ndf = df.dropna(subset=['{col}'])\n# Option 2 — Flag separately\ndf['has_{col.lower()}'] = df['{col}'].notnull().astype(int)",
        }

    if any(k in lower for k in ("price", "amount", "payment", "revenue", "cost", "value", "salary")):
        return {
            "icon": "💰", "priority": "HIGH" if pct > 10 else "MEDIUM",
            "title": f"Financial column missing: {col}",
            "problem": f"{col} has {pct:.1f}% missing values.",
            "reason": f"{col} is a financial/transaction column. Missing values likely indicate failed transactions, refunds, or data pipeline errors.",
            "technical_impact": "Regression models using this as target/feature will silently exclude these rows. Revenue aggregations will be understated.",
            "business_impact": "Revenue reports and forecasting models will undercount by the missing percentage. Financial KPIs become unreliable.",
            "fix": f"# Investigate root cause first\nprint(df[df['{col}'].isnull()].head())\n# Impute with median (safer than mean for financial data)\ndf['{col}'] = df['{col}'].fillna(df['{col}'].median())",
        }

    # Generic
    if pct > 30:
        fix_code = f"if df['{col}'].isnull().mean() > 0.5:\n    df = df.drop(columns=['{col}'])\nelse:\n    df['{col}'] = df['{col}'].fillna(df['{col}'].median())"
        priority = "HIGH"
    elif pct > 5:
        fix_code = f"df['{col}'] = df['{col}'].fillna(df['{col}'].median())  # numeric\n# df['{col}'] = df['{col}'].fillna(df['{col}'].mode()[0])  # categorical"
        priority = "MEDIUM"
    else:
        fix_code = f"df['{col}'] = df['{col}'].fillna(df['{col}'].median())"
        priority = "LOW"

    return {
        "icon": "🧹", "priority": priority,
        "title": f"Handle missing values: {col}",
        "problem": f"{col} has {pct:.1f}% missing values.",
        "reason": "Missing values in feature columns reduce model training data and may introduce bias if not random.",
        "technical_impact": "ML models that cannot handle NaN (LinearRegression, SVM, KNN) will fail. Tree models silently exclude missing rows.",
        "business_impact": "Reports and dashboards using this column will show incomplete data for affected rows.",
        "fix": fix_code,
    }


def _build_recommendations(profile: dict, checks: dict, score: dict,
                            ml: dict | None = None,
                            target: str | None = None) -> list[dict]:
    recs: list[dict] = []
    overview = profile.get("overview", {})

    # Per-column missing recommendations (context-aware)
    missing_cols = checks.get("missing", {}).get("columns", [])
    # Sort: CRITICAL first, OPTIONAL last, then by pct
    def _sort_key(m):
        ord_ = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        return (ord_.get(m.get("risk", "LOW"), 4), -m["pct"])
    for m in sorted(missing_cols, key=_sort_key)[:7]:
        recs.append(_rec_missing(m["col"], m["pct"], target))

    # Duplicates
    dup_rows = overview.get("duplicate_rows", 0)
    dup_pct  = overview.get("duplicate_pct", 0.0)
    if dup_rows > 0:
        recs.append({
            "icon": "🗑️", "priority": "HIGH" if dup_pct > 5 else "MEDIUM",
            "title": "Remove Duplicate Rows",
            "problem": f"{dup_rows:,} duplicate rows ({dup_pct:.1f}%).",
            "reason": "Exact duplicate rows indicate upstream ETL or data import errors.",
            "technical_impact": "Duplicates in training data cause data leakage between train/test splits, inflating accuracy metrics.",
            "business_impact": "Duplicate transactions inflate revenue metrics. Duplicate customers skew segmentation counts and loyalty calculations.",
            "fix": "df = df.drop_duplicates().reset_index(drop=True)",
        })

    # Outliers (only continuous)
    outlier_cols = [c for c in checks.get("outliers", {}).get("affected_columns", [])
                    if c.get("risk") in ("HIGH", "MEDIUM") and not c.get("is_ordinal")]
    if outlier_cols:
        cols_str = ", ".join(c["col"] for c in outlier_cols[:3])
        recs.append({
            "icon": "🔍", "priority": "HIGH",
            "title": "Handle Outliers in Continuous Columns",
            "problem": f"Statistical outliers found in: {cols_str}.",
            "reason": "These are continuous numeric columns with values far outside the typical range — likely data entry errors or genuine extreme events.",
            "technical_impact": "Outliers skew StandardScaler, distort linear model coefficients, and can degrade tree-model split quality.",
            "business_impact": "Extreme values in price/payment columns can corrupt revenue reports and distort business KPIs.",
            "fix": "Q1  = df[col].quantile(0.25)\nQ3  = df[col].quantile(0.75)\nIQR = Q3 - Q1\ndf[col] = df[col].clip(Q1 - 1.5*IQR, Q3 + 1.5*IQR)\n# Or use RobustScaler instead of StandardScaler.",
        })

    # Wrong types — split datetime vs numeric
    type_issues = checks.get("wrong_types", {}).get("columns", [])
    dt_issues  = [c for c in type_issues if c["suggested_type"] == "datetime"]
    num_issues = [c for c in type_issues if c["suggested_type"] == "numeric"]

    if dt_issues:
        cols_str = ", ".join(c["col"] for c in dt_issues[:4])
        recs.append({
            "icon": "📅", "priority": "MEDIUM",
            "title": "Convert Date Columns to datetime",
            "problem": f"Columns stored as strings but contain dates: {cols_str}.",
            "reason": "pandas reads date columns as object/string by default unless explicitly parsed.",
            "technical_impact": "String dates cannot be used in date arithmetic, time-series resampling, or as temporal features in ML.",
            "business_impact": "Cohort analysis, time-series forecasting, and date-based filtering in BI tools will fail.",
            "fix": "\n".join([f"df['{c['col']}'] = pd.to_datetime(df['{c['col']}'], errors='coerce')"
                              for c in dt_issues[:4]]),
        })

    if num_issues:
        cols_str = ", ".join(c["col"] for c in num_issues[:4])
        recs.append({
            "icon": "🔢", "priority": "MEDIUM",
            "title": "Convert Numeric Columns Stored as Strings",
            "problem": f"Numeric data stored as text: {cols_str}.",
            "reason": "Numeric columns with non-numeric characters (commas, currency symbols) are loaded as strings.",
            "technical_impact": "String numerics are treated as categoricals — wrong encoding, wasted memory, incorrect aggregations.",
            "business_impact": "SUM/AVG operations on these columns will silently fail or return wrong results in BI tools.",
            "fix": "\n".join([f"df['{c['col']}'] = pd.to_numeric(df['{c['col']}'], errors='coerce')"
                              for c in num_issues[:4]]),
        })

    # Skewness
    high_skew = [c for c in checks.get("skewness", {}).get("columns", [])
                 if c.get("level") == "HIGH"]
    if high_skew:
        cols_str = ", ".join(c["col"] for c in high_skew[:3])
        recs.append({
            "icon": "📐", "priority": "MEDIUM",
            "title": "Fix Highly Skewed Features",
            "problem": f"Columns with |skewness|>2: {cols_str}.",
            "reason": "Financial columns like price and payment_value are often right-skewed — a few very large transactions dominate the distribution.",
            "technical_impact": "Skewed features degrade linear models and distance-based algorithms. Tree models are mostly unaffected.",
            "business_impact": "Mean-based KPIs become misleading — median is more representative for skewed financial data.",
            "fix": "import numpy as np\n# For positive-only columns:\ndf[col] = np.log1p(df[col])\n# General solution:\nfrom sklearn.preprocessing import PowerTransformer\ndf[col] = PowerTransformer(method='yeo-johnson').fit_transform(df[[col]])",
        })

    # High correlation
    high_corr = checks.get("correlation", {}).get("high_pairs", [])
    if high_corr:
        p = high_corr[0]
        recs.append({
            "icon": "🔗", "priority": "MEDIUM",
            "title": "Remove Redundant Correlated Features",
            "problem": f"{len(high_corr)} feature pair(s) with |r|>0.9 (e.g. {p['col1']} ↔ {p['col2']}, r={p['correlation']}).",
            "reason": "Highly correlated features carry redundant information and increase model complexity without benefit.",
            "technical_impact": "Multicollinearity inflates coefficient variance in linear models and makes feature importance scores unreliable.",
            "business_impact": "Redundant features increase infrastructure cost (storage, compute) without adding predictive value.",
            "fix": "corr = df.corr().abs()\nupper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))\nto_drop = [c for c in upper.columns if any(upper[c] > 0.9)]\ndf = df.drop(columns=to_drop)",
        })

    # Invalid values
    neg_inv = checks.get("invalid_values", {}).get("negative_where_invalid", [])
    if neg_inv:
        cols_str = ", ".join(c["col"] for c in neg_inv[:3])
        recs.append({
            "icon": "⚠️", "priority": "HIGH",
            "title": "Fix Invalid Negative Values",
            "problem": f"Negative values where impossible: {cols_str}.",
            "reason": "Negative prices or quantities indicate data entry errors, refund records coded incorrectly, or corrupted imports.",
            "technical_impact": "Log transforms (for skewness correction) will fail on negative values. Models may learn wrong patterns.",
            "business_impact": "Negative revenue figures corrupt financial dashboards and P&L reports.",
            "fix": "df[col] = df[col].clip(lower=0)\n# Or remove the rows:\ndf = df[df[col] >= 0]",
        })

    # ML-specific
    if ml and "class_imbalance" in ml:
        imb = ml["class_imbalance"]
        if imb.get("risk") in ("HIGH", "CRITICAL"):
            recs.append({
                "icon": "⚖️", "priority": "HIGH",
                "title": "Address Class Imbalance",
                "problem": f"Target dominant class: {imb['dominant_pct']:.1f}%, minority: {imb['minority_pct']:.1f}%.",
                "reason": "Imbalanced classes mean the model will see far more examples of one class during training.",
                "technical_impact": "Model will predict majority class for almost all records. Accuracy is high but Recall/F1 for minority class will be near zero.",
                "business_impact": "Critical cases (fraud, churn, defects) are the minority class — missing them has direct business cost.",
                "fix": "# Option 1 — class weighting (no data change needed)\nmodel = RandomForestClassifier(class_weight='balanced')\n# Option 2 — SMOTE oversampling\nfrom imblearn.over_sampling import SMOTE\nX_res, y_res = SMOTE().fit_resample(X, y)",
            })

    if ml and ml.get("leakage_risk_cols"):
        cols_str = ", ".join(ml["leakage_risk_cols"][:3])
        recs.append({
            "icon": "🚨", "priority": "HIGH",
            "title": "Potential Data Leakage Detected",
            "problem": f"Near-perfect correlation to target in: {cols_str}.",
            "reason": "These columns may be derived from the target or collected after the prediction event, making them unavailable at inference time.",
            "technical_impact": "Model appears to achieve near-100% accuracy in testing but will fail in production.",
            "business_impact": "Deploying a leaky model creates false confidence. Production performance will be significantly worse than reported.",
            "fix": f"df = df.drop(columns={ml['leakage_risk_cols'][:3]})\n# Investigate causality before dropping.",
        })

    # Always: scaling
    recs.append({
        "icon": "📏", "priority": "LOW",
        "title": "Scale Numeric Features Before Training",
        "problem": "Numeric features likely have different scales.",
        "reason": "Different scales (e.g. age 0–100 vs salary 0–200000) cause distance-based algorithms to be dominated by large-scale features.",
        "technical_impact": "Unscaled features break KNN, SVM, and gradient descent convergence. Feature importance becomes scale-dependent.",
        "business_impact": "N/A — pure preprocessing step with no business interpretation.",
        "fix": "from sklearn.preprocessing import StandardScaler\nscaler = StandardScaler()\nX_train_scaled = scaler.fit_transform(X_train)\nX_test_scaled  = scaler.transform(X_test)  # transform only, never fit on test",
    })

    return recs


# ════════════════════════════════════════════════════════════════════════════
# ML READINESS
# ════════════════════════════════════════════════════════════════════════════

def _ml_readiness(df: pd.DataFrame, target: str, profile: dict) -> dict:
    print("[STEP]  Computing ML readiness …")
    if df.empty or target not in df.columns:
        return {}

    col_profiles   = {c["name"]: c for c in profile.get("columns", [])}
    target_series  = df[target].dropna()
    n_unique_target = target_series.nunique()
    is_num_target  = pd.api.types.is_numeric_dtype(df[target])
    task_type = ("classification" if not is_num_target or n_unique_target <= 20
                 else "regression")

    result: dict = {"task_type": task_type}

    if task_type == "classification":
        vc = target_series.value_counts()
        dom_pct = round(float(vc.iloc[0] / len(target_series) * 100), 2) if len(target_series) else 0.0
        min_pct = round(float(vc.iloc[-1] / len(target_series) * 100), 2) if len(vc) > 1 else dom_pct
        imb_risk = ("CRITICAL" if dom_pct > 90 else "HIGH" if dom_pct > 80 else
                    "MEDIUM" if dom_pct > 70 else "LOW")
        result["class_imbalance"] = {
            "dominant_class": str(vc.index[0]),
            "dominant_pct": dom_pct,
            "minority_pct": min_pct,
            "risk": imb_risk,
            "class_counts": {str(k): int(v) for k, v in vc.items()},
        }
    else:
        sk = (float(scipy_stats.skew(target_series.astype(float)))
              if len(target_series) >= 3 else 0.0)
        result["target_skewness"] = round(sk, 4) if not math.isnan(sk) else None

    leakage_cols = []
    if is_num_target:
        num_df = df.select_dtypes(include="number").drop(columns=[target], errors="ignore")
        for col in num_df.columns:
            try:
                r = df[col].corr(df[target])
                if not math.isnan(r) and abs(r) > 0.95:
                    leakage_cols.append(col)
            except Exception:
                pass
    result["leakage_risk_cols"] = leakage_cols
    result["constant_features"] = [c["name"] for c in profile.get("columns", [])
                                    if c["name"] != target and c.get("is_constant")]
    result["low_variance_features"] = []
    for col in df.select_dtypes(include="number").columns:
        if col == target:
            continue
        try:
            v = float(df[col].dropna().var())
            if not math.isnan(v) and v < 0.01:
                result["low_variance_features"].append(col)
        except Exception:
            pass
    return result


# ════════════════════════════════════════════════════════════════════════════
# DISTRIBUTIONS + CORRELATION MATRIX
# ════════════════════════════════════════════════════════════════════════════

def _compute_distributions(df: pd.DataFrame,
                           target: str | None = None) -> list[dict]:
    numeric_cols = [c for c in df.select_dtypes(include="number").columns
                    if c != target and not _is_id_like(df[c], c)][:4]
    cat_cols = [c for c in df.select_dtypes(include="object").columns
                if c != target and not _is_id_like(df[c], c)][:3]
    distributions = []
    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) < 2:
            continue
        try:
            counts, bins = pd.cut(series, bins=8, retbins=True)
            labels = [f"{bins[i]:.2g}–{bins[i+1]:.2g}" for i in range(len(bins) - 1)]
            values = counts.value_counts(sort=False).tolist()
            distributions.append({"col": col, "type": "histogram",
                                   "labels": labels, "values": values})
        except Exception:
            pass
    for col in cat_cols:
        vc = df[col].dropna().value_counts().head(10)
        if vc.empty:
            continue
        distributions.append({"col": col, "type": "bar",
                               "labels": [str(v) for v in vc.index],
                               "values": vc.values.tolist()})
    return distributions


def _compute_correlation_matrix(df: pd.DataFrame,
                                target: str | None = None) -> dict:
    num_df = df.select_dtypes(include="number")
    if target and target in num_df.columns:
        other = [c for c in num_df.columns if c != target][:5]
        top_cols = [target] + other
    else:
        top_cols = [c for c in num_df.columns
                    if not _is_id_like(num_df[c], c)][:6]
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


# ════════════════════════════════════════════════════════════════════════════
# ENHANCED RELATIONSHIP ANALYSIS  (FIX #9)
# ════════════════════════════════════════════════════════════════════════════

def _analyze_relationships(file_reports: list[dict]) -> list[dict]:
    """
    Enhanced FK/PK detection:
    - Finds shared column names across files
    - Checks if all FK values exist in the PK file (referential integrity)
    - Detects duplicate keys in what should be PK columns
    """
    relationships = []

    # Build: filename → {col_name: set_of_values}
    file_data: dict[str, dict[str, set]] = {}
    file_cols: dict[str, list[str]] = {}

    for rpt in file_reports:
        fname = rpt.get("filename", "")
        col_names = []
        col_vals  = {}
        if "profile" in rpt:
            for cp in rpt["profile"].get("columns", []):
                col_names.append(cp["name"])
        file_cols[fname] = col_names
        file_data[fname] = col_vals  # values populated lazily below

    fnames = list(file_cols.keys())

    for i in range(len(fnames)):
        for j in range(i + 1, len(fnames)):
            f1, f2 = fnames[i], fnames[j]
            shared = set(file_cols[f1]) & set(file_cols[f2])
            for col in sorted(shared):
                col_lower = col.lower()
                is_pk_like = any(k in col_lower for k in ("id", "key", "code", "no"))

                rel: dict = {
                    "file1": f1, "col1": col,
                    "file2": f2, "col2": col,
                    "relationship_type": "FK" if is_pk_like else "shared_column",
                    "integrity_check": None,
                }

                # Referential integrity check — requires actual data
                # (skipped here since we only have profiles, not DataFrames)
                # The route handler can pass DataFrames if needed.
                relationships.append(rel)

    return relationships


def _check_referential_integrity(df1: pd.DataFrame, col1: str,
                                  df2: pd.DataFrame, col2: str) -> dict:
    """Check if all values in df1[col1] exist in df2[col2]."""
    vals1 = set(df1[col1].dropna().unique())
    vals2 = set(df2[col2].dropna().unique())
    missing_refs = vals1 - vals2
    return {
        "total_in_source": len(vals1),
        "matched": len(vals1 - missing_refs),
        "missing_references": len(missing_refs),
        "integrity_ok": len(missing_refs) == 0,
        "sample_missing": list(missing_refs)[:5],
    }


def _detect_pk_duplicates(df: pd.DataFrame, col: str) -> dict:
    n_total  = len(df[col].dropna())
    n_unique = df[col].nunique()
    dups     = n_total - n_unique
    return {
        "col": col,
        "total_values": n_total,
        "unique_values": n_unique,
        "duplicate_count": dups,
        "is_unique_key": dups == 0,
    }


# ════════════════════════════════════════════════════════════════════════════
# SINGLE-FILE PIPELINE
# ════════════════════════════════════════════════════════════════════════════

def _analyze_single_file(filepath: str, target: str | None = None) -> dict:
    filename = os.path.basename(filepath)
    print(f"[STEP]  Analyzing: {filename}")
    try:
        df = _load_file(filepath)
    except Exception as exc:
        return {"filename": filename, "error": str(exc)}

    if df.empty:
        return {"filename": filename, "error": "Empty DataFrame.",
                "target_used": None, "suggested_targets": []}

    target_used = None
    if target:
        try:
            target_used = _resolve_target(df, target)
        except KeyError:
            print(f"[WARN]  Target '{target}' not found in {filename}.")

    suggested_targets = _auto_detect_target(df)
    profile = _profile_dataset(df, target_used)
    checks  = _run_quality_checks(df, profile, target_used)
    ml      = _ml_readiness(df, target_used, profile) if target_used else None
    score   = _compute_score(profile, checks, ml, target_used)
    severity = _build_severity_distribution(checks, profile, target_used)
    dists   = _compute_distributions(df, target_used)
    corr_mat = _compute_correlation_matrix(df, target_used)
    recs    = _build_recommendations(profile, checks, score, ml, target_used)

    # Column importance summary for UI
    col_importance_summary = {
        "CRITICAL": [c["name"] for c in profile.get("columns", [])
                     if c.get("importance") == "CRITICAL"],
        "IMPORTANT": [c["name"] for c in profile.get("columns", [])
                      if c.get("importance") == "IMPORTANT"],
        "OPTIONAL": [c["name"] for c in profile.get("columns", [])
                     if c.get("importance") == "OPTIONAL"],
    }

    return _clean({
        "filename": filename,
        "target_used": target_used,
        "suggested_targets": suggested_targets,
        "profile": profile,
        "checks": checks,
        "ml_readiness": ml,
        "score": score,
        "severity": severity,
        "col_importance_summary": col_importance_summary,
        "distributions": dists,
        "correlation_matrix": corr_mat,
        "recommendations": recs,
    })


# ════════════════════════════════════════════════════════════════════════════
# ZIP SUPPORT — with comparison dashboard  (FIX #8)
# ════════════════════════════════════════════════════════════════════════════

def _analyze_zip(filepath: str, target: str | None = None) -> dict:
    print(f"[STEP]  Extracting ZIP: {filepath}")
    extract_dir = os.path.join(UPLOAD_FOLDER, str(uuid.uuid4()))
    os.makedirs(extract_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(filepath, "r") as zf:
            zf.extractall(extract_dir)

        data_files = []
        for root, _dirs, files in os.walk(extract_dir):
            for fname in files:
                if fname.startswith(".") or "__MACOSX" in root:
                    continue
                ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
                if ext in ALLOWED_EXTENSIONS:
                    data_files.append(os.path.join(root, fname))

        if not data_files:
            return {"files": [], "relationships": [], "comparison": {},
                    "error": "ZIP contains no supported data files."}

        # Load DataFrames for relationship integrity checks
        loaded_dfs: dict[str, pd.DataFrame] = {}
        file_reports = []
        for fp in data_files:
            rpt = _analyze_single_file(fp, target)
            file_reports.append(rpt)
            try:
                loaded_dfs[rpt.get("filename", "")] = _load_file(fp)
            except Exception:
                pass

        # Enhanced relationship detection
        relationships = _analyze_relationships(file_reports)

        # Referential integrity checks for ID columns
        enhanced_rels = []
        fnames = list(loaded_dfs.keys())
        for i in range(len(fnames)):
            for j in range(i + 1, len(fnames)):
                f1, f2 = fnames[i], fnames[j]
                df1, df2 = loaded_dfs[f1], loaded_dfs[f2]
                shared_id_cols = (set(df1.columns) & set(df2.columns))
                shared_id_cols = {c for c in shared_id_cols
                                  if any(k in c.lower() for k in ("id", "key"))}
                for col in sorted(shared_id_cols):
                    integrity = _check_referential_integrity(df1, col, df2, col)
                    pk_check1 = _detect_pk_duplicates(df1, col)
                    pk_check2 = _detect_pk_duplicates(df2, col)
                    enhanced_rels.append({
                        "file1": f1, "col1": col,
                        "file2": f2, "col2": col,
                        "relationship_type": "FK/PK",
                        "referential_integrity": integrity,
                        "pk_check_file1": pk_check1,
                        "pk_check_file2": pk_check2,
                    })

        # Merge basic + enhanced
        basic_rels_non_id = [r for r in relationships
                             if not any(k in r["col1"].lower()
                                        for k in ("id", "key"))]
        all_rels = enhanced_rels + basic_rels_non_id

        # FIX #8: Dataset comparison dashboard
        scored = sorted(
            [{"filename": r.get("filename", ""),
              "score": (r.get("score") or {}).get("total", 0),
              "grade": (r.get("score") or {}).get("grade", "—"),
              "rows": (r.get("profile") or {}).get("overview", {}).get("rows", 0),
              "missing_pct": (r.get("profile") or {}).get("overview", {}).get("missing_pct", 0),
              "critical_issues": (r.get("severity") or {}).get("counts", {}).get("CRITICAL", 0),
              "high_issues": (r.get("severity") or {}).get("counts", {}).get("HIGH", 0),
              }
             for r in file_reports if not r.get("error")],
            key=lambda x: x["score"], reverse=True
        )

        # Most problematic columns across all files
        all_missing = []
        for rpt in file_reports:
            fname = rpt.get("filename", "")
            for m in (rpt.get("checks") or {}).get("missing", {}).get("columns", []):
                if m["pct"] > 5:
                    all_missing.append({
                        "file": fname, "col": m["col"],
                        "pct": m["pct"], "risk": m.get("risk", "LOW")
                    })
        all_missing.sort(key=lambda x: x["pct"], reverse=True)

        comparison = {
            "ranking": scored,
            "best_file": scored[0]["filename"] if scored else None,
            "worst_file": scored[-1]["filename"] if scored else None,
            "most_problematic_columns": all_missing[:10],
        }

        return _clean({
            "files": file_reports,
            "relationships": all_rels,
            "comparison": comparison,
        })

    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)


# ════════════════════════════════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/analyze", methods=["POST"])
def analyze():
    request_id = str(uuid.uuid4())[:8]
    upload_dir = os.path.join(UPLOAD_FOLDER, request_id)
    os.makedirs(upload_dir, exist_ok=True)

    try:
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded."}), 400
        file = request.files["file"]
        if not file.filename:
            return jsonify({"error": "No file selected."}), 400

        raw_target = request.form.get("target_column", "").strip()
        target_column = raw_target if raw_target else None

        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_EXTENSIONS_ZIP:
            return jsonify({"error": f"Unsupported file type: .{ext}",
                            "allowed": sorted(ALLOWED_EXTENSIONS_ZIP)}), 400

        safe_name = os.path.basename(file.filename)
        filepath  = os.path.join(upload_dir, safe_name)
        file.save(filepath)
        print(f"\n[REQUEST {request_id}]  file={safe_name}  target={target_column}")

        if ext == "zip":
            result = _analyze_zip(filepath, target_column)
            return jsonify(_clean(result))

        report = _analyze_single_file(filepath, target_column)
        if "error" in report and len(report) <= 4:
            return jsonify(report), 422
        return jsonify(_clean(report))

    except Exception:
        print(traceback.format_exc())
        return jsonify({"error": "Internal server error — check backend logs."}), 500

    finally:
        if upload_dir and os.path.exists(upload_dir):
            shutil.rmtree(upload_dir, ignore_errors=True)


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": "4.0"})


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "1") != "0"
    app.run(debug=debug_mode, port=5000, use_reloader=debug_mode)
