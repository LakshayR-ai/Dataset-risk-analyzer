"""
Dataset Quality Analyzer - Backend API
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import pickle
import os, sys, traceback, math

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": ["http://localhost:3000", "http://127.0.0.1:3000", "null"]}})

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def sanitize(obj):
    """Replace NaN/Inf with None so JSON never breaks."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj


def load_dataset(filepath):
    ext = filepath.rsplit('.', 1)[-1].lower()
    if ext == 'csv':
        df = pd.read_csv(filepath)
    elif ext in ('xlsx', 'xls'):
        df = pd.read_excel(filepath, engine='openpyxl')
    elif ext == 'json':
        df = pd.read_json(filepath)
    else:
        raise ValueError(f"Unsupported format: .{ext}")
    print(f"[LOAD]  Rows after load       : {len(df)}")
    return df


def count_pipeline(df, target):
    original_count = len(df)
    print(f"[STEP1] Original rows          : {original_count}")

    df_dedup = df.drop_duplicates()
    duplicate_count = original_count - len(df_dedup)
    print(f"[STEP2] After dedup            : {len(df_dedup)}  (removed {duplicate_count})")

    missing_total = int(df_dedup.isnull().sum().sum())
    missing_pct = round(missing_total / (len(df_dedup) * len(df_dedup.columns)) * 100, 2) if len(df_dedup) > 0 else 0
    print(f"[STEP3] Missing cells          : {missing_total}  ({missing_pct}%)")

    numeric_cols = df_dedup.select_dtypes(include='number').columns.tolist()
    if target in numeric_cols:
        numeric_cols.remove(target)

    # Exclude ID-like columns from IQR outlier detection.
    # ID columns have nearly all unique values and mixed formats — IQR on them
    # produces false positives (e.g. short vs long format Response IDs).
    id_like = [c for c in numeric_cols if
               df_dedup[c].nunique() / len(df_dedup) > 0.8 or   # >80% unique = likely an ID
               c.lower().endswith('id') or c.lower().endswith('_id') or
               'id' in c.lower().split()]
    if id_like:
        print(f"[STEP4] Skipping ID-like columns from outlier IQR: {id_like}")
    numeric_cols = [c for c in numeric_cols if c not in id_like]

    outlier_rows = set()
    for col in numeric_cols:
        q1, q3 = df_dedup[col].quantile(0.25), df_dedup[col].quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        mask = (df_dedup[col] < q1 - 1.5 * iqr) | (df_dedup[col] > q3 + 1.5 * iqr)
        outlier_rows.update(df_dedup[mask].index.tolist())

    outlier_count = len(outlier_rows)
    outlier_pct = round(outlier_count / len(df_dedup) * 100, 2) if len(df_dedup) > 0 else 0
    print(f"[STEP4] Outlier rows           : {outlier_count}  ({outlier_pct}%)")

    class_imbalance = 1.0
    if target in df_dedup.columns:
        dist = df_dedup[target].value_counts(normalize=True)
        class_imbalance = round(float(dist.max()), 4)
    print(f"[STEP5] Class imbalance        : {class_imbalance}")

    clean_count = len(df_dedup)
    print(f"[FINAL] {original_count} original → {clean_count} clean")

    return {
        "num_samples": original_count,
        "clean_count": clean_count,
        "duplicate_count": duplicate_count,
        "duplicate_pct": round(duplicate_count / original_count * 100, 2) if original_count else 0,
        "outlier_count": outlier_count,
        "outlier_pct": outlier_pct,
        "missing_pct": missing_pct,
        "num_features": len(df.columns) - 1,
        "class_imbalance": class_imbalance,
        "count_source": "file",
    }


def analyze_columns(df, target):
    results = []
    for col in df.columns:
        missing = int(df[col].isnull().sum())
        dtype = 'categorical' if df[col].dtype == object else 'numeric'
        outliers = 0
        if dtype == 'numeric' and col != target:
            q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)
            iqr = q3 - q1
            if iqr > 0:
                outliers = int(((df[col] < q1 - 1.5 * iqr) | (df[col] > q3 + 1.5 * iqr)).sum())
        results.append({"name": col, "dtype": dtype, "missing": missing, "outliers": outliers, "issue": missing > 0 or outliers > 0})
    return results


def compute_score(stats):
    score = 100
    score -= min(stats['missing_pct'] * 2, 30)
    score -= min(stats['duplicate_pct'] * 3, 20)
    score -= min(stats['outlier_pct'] * 1.5, 20)
    if stats['class_imbalance'] > 0.8:
        score -= 10
    return max(0, int(score))


def build_recommendations(stats):
    recs = []
    if stats['missing_pct'] > 0:
        recs.append({'icon': '🧹', 'title': 'Handle Missing Values',
                     'desc': f"{stats['missing_pct']}% missing. Use median/mode imputation or drop sparse columns."})
    if stats['duplicate_count'] > 0:
        recs.append({'icon': '🗑️', 'title': 'Remove Duplicates',
                     'desc': f"{stats['duplicate_count']} duplicate rows ({stats['duplicate_pct']}%). Remove before training."})
    if stats['outlier_pct'] > 5:
        recs.append({'icon': '🔍', 'title': 'Handle Outliers',
                     'desc': f"{stats['outlier_count']} outlier rows ({stats['outlier_pct']}%). Use IQR clipping or robust scalers."})
    if stats['class_imbalance'] > 0.8:
        recs.append({'icon': '⚖️', 'title': 'Address Class Imbalance',
                     'desc': f"Dominant class is {stats['class_imbalance']*100:.1f}%. Use SMOTE or class_weight='balanced'."})
    recs.append({'icon': '📏', 'title': 'Scale Features',
                 'desc': 'Apply StandardScaler or MinMaxScaler to numeric features before training.'})
    return recs


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route('/api/analyze', methods=['POST'])
def analyze():
    filepath = None
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400

        file = request.files['file']
        target_column = request.form.get('target_column', '').strip()

        if not file.filename:
            return jsonify({'error': 'No file selected'}), 400
        if not target_column:
            return jsonify({'error': 'Target column name is required'}), 400

        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        print(f"\n[REQUEST] File: {file.filename}, Target: {target_column}")

        df = load_dataset(filepath)

        # Case-insensitive column match
        if target_column not in df.columns:
            col_map = {c.strip().lower(): c for c in df.columns}
            match = col_map.get(target_column.strip().lower())
            if match:
                print(f"[INFO] Matched column: '{target_column}' -> '{match}'")
                target_column = match
            else:
                return jsonify({'error': f'Column "{target_column}" not found.', 'available_columns': df.columns.tolist()}), 400

        stats = count_pipeline(df, target_column)
        columns = analyze_columns(df, target_column)
        score = compute_score(stats)

        # ── Column classification ─────────────────────────────
        # Explicitly exclude identifier/phone columns from all analysis
        ID_COLS = {'response id', 'bill no', 'order id', 'mobile no',
                   'response_id', 'bill_number', 'order_id', 'mobile_number'}
        NUMERIC_ANALYSIS_COLS = {'age', 'product price', 'rating'}
        CATEGORICAL_ANALYSIS_COLS = {'survey type', 'brand name', 'gender',
                                     'location', 'promoter score', 'month', 'year', 'occupation', 'product'}

        def col_key(c): return c.strip().lower()

        # Safe numeric cols: not ID-like, not target
        safe_numeric = [
            c for c in df.columns
            if col_key(c) in NUMERIC_ANALYSIS_COLS
            and c != target_column
            and pd.api.types.is_numeric_dtype(df[c])
        ]

        # Safe categorical cols: not ID-like, not target
        safe_categorical = [
            c for c in df.columns
            if col_key(c) in CATEGORICAL_ANALYSIS_COLS
            and c != target_column
        ]

        print(f"[VIZ] Numeric cols for analysis   : {safe_numeric}")
        print(f"[VIZ] Categorical cols for analysis: {safe_categorical}")

        # ── Value Distribution ────────────────────────────────
        # Build one chart per meaningful column (numeric = histogram, categorical = bar)
        distributions = []

        for col in safe_numeric:
            series = df[col].dropna()
            counts, bins = pd.cut(series, bins=8, retbins=True)
            labels = [f"{bins[i]:.0f}–{bins[i+1]:.0f}" for i in range(len(bins) - 1)]
            values = counts.value_counts(sort=False).tolist()
            distributions.append({
                'col': col, 'type': 'histogram',
                'labels': labels, 'values': values
            })

        for col in safe_categorical[:3]:  # max 3 categorical charts
            vc = df[col].dropna().value_counts().head(10)
            distributions.append({
                'col': col, 'type': 'bar',
                'labels': vc.index.tolist(),
                'values': vc.values.tolist()
            })

        # Legacy single distribution (first numeric) for backward compat
        dist_labels = distributions[0]['labels'] if distributions else []
        dist_values = distributions[0]['values'] if distributions else []

        # ── Correlation ───────────────────────────────────────
        # Only among safe numeric cols — never IDs
        correlation = []
        corr_cols = safe_numeric[:5]
        if target_column in df.columns and pd.api.types.is_numeric_dtype(df[target_column]):
            for c in corr_cols:
                val = df[c].corr(df[target_column])
                correlation.append(0.0 if (math.isnan(val) or math.isinf(val)) else round(abs(float(val)), 3))
        else:
            # Correlate numeric cols among themselves (first vs rest)
            if len(corr_cols) >= 2:
                base = df[corr_cols[0]]
                for c in corr_cols[1:]:
                    val = base.corr(df[c])
                    correlation.append(0.0 if (math.isnan(val) or math.isinf(val)) else round(abs(float(val)), 3))
                corr_cols = corr_cols[1:]
            else:
                correlation = [0.0] * len(corr_cols)

        print(f"[VIZ] Correlation cols: {corr_cols} → {correlation}")

        # ML prediction (optional)
        prediction = 'Safe Dataset'
        model_path = os.path.join(os.path.dirname(__file__), '..', 'meta_model.pkl')
        if os.path.exists(model_path):
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')
                from meta_features import extract_meta_features
                features = extract_meta_features(df, target_column)
                with open(model_path, 'rb') as f:
                    model = pickle.load(f)
                prediction = str(model.predict([features])[0])
            except Exception as e:
                print(f"[WARN] ML prediction skipped: {e}")

        return jsonify(sanitize({
            'score': score,
            'prediction': prediction,
            'summary': stats,
            'columns': columns,
            'distributions': distributions,
            'distribution': {'labels': dist_labels, 'values': dist_values},
            'correlation': correlation,
            'corr_cols': corr_cols,
            'recommendations': build_recommendations(stats),
        }))

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500
    finally:
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
