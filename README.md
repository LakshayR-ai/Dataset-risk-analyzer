# Dataset Risk Analyzer — Pre-Training Data Quality Platform

## 📌 Project Overview

An end-to-end **AI-powered data quality platform** that analyzes any uploaded dataset and automatically detects data quality risks before machine learning model training. It combines a professional risk-scoring engine, a meta-learning ML model, and a full-stack interactive web UI.

**Core value proposition:** Data scientists waste hours debugging models that fail due to bad data — missing values, outliers, class imbalance, type errors. This tool surfaces all these problems in seconds, before a single model is trained.

---

## 🧠 How It Works

```
Upload Dataset (CSV / Excel / JSON)
         ↓
 Flask API receives file
         ↓
 10 Quality Checks run in parallel
         ↓
 ML Readiness Score (0–100, 5 dimensions)
         ↓
 Meta-Feature Extraction (10 features)
         ↓
 RandomForest Meta-Model Prediction
         ↓
 AI Recommendations (priority-ranked)
         ↓
 Interactive Report + EDA Charts + Download
```

---

## 🔬 Quality Checks Performed

| # | Check | Detail |
|---|-------|--------|
| 1 | Missing Values | Per-column + overall % |
| 2 | Duplicate Rows | Count + % |
| 3 | Outlier Detection | IQR method, ID columns excluded |
| 4 | Class Imbalance | Dominant class proportion |
| 5 | Feature Correlation | Pearson heatmap data |
| 6 | Skewness | Per-column scipy.stats.skew |
| 7 | Type Mismatch | Numeric data stored as strings |
| 8 | Constant Columns | Zero-variance features |
| 9 | High-Cardinality Strings | ID/free-text leakage detection |
| 10 | Data Drift Proxy | Coefficient of variation (std/mean > 2) |

---

## 📊 ML Readiness Score (0–100)

5-dimension scoring system, inspired by industry data quality frameworks:

| Dimension | Max Pts | Penalty |
|-----------|---------|---------|
| Completeness | 30 | Missing % × 2.5 |
| Consistency  | 20 | Duplicate % × 3 + type mismatch |
| Validity     | 20 | Outlier % × 1.5 |
| Balance      | 15 | Tiered by dominant class % |
| Usability    | 15 | Constant cols + skewness + high-CV |

---

## 🤖 Meta-Model Architecture

The ML risk predictor uses **meta-learning**: it was trained on datasets with known risk labels and predicts the risk of new, unseen datasets based on statistical properties.

### Meta-Features (10)

| Feature | Description |
|---------|-------------|
| n_samples | Total row count |
| n_features | Total feature count |
| ratio | n_features / n_samples |
| variance | Mean feature variance |
| correlation | Mean absolute pairwise correlation |
| imbalance | Dominant class proportion |
| missing | Missing value fraction |
| skewness | Mean absolute skewness |
| duplicate_pct | Duplicate row fraction |
| outlier_pct | Outlier row fraction (IQR) |

### Model

- **Algorithm:** RandomForest Classifier
- **Tuning:** GridSearchCV (n_estimators, max_depth, min_samples_split, class_weight)
- **Validation:** 5-fold stratified cross-validation, F1-macro
- **Training Data:** 150 synthetic samples, 3 balanced classes (50 each)
- **Test Accuracy:** 1.00 (30-sample hold-out, balanced classes)
- **CV F1 (mean):** 0.975

### Risk Labels

| Label | Meaning |
|-------|---------|
| Safe Dataset | Acceptable train/test behaviour expected |
| Overfitting Risk | High feature/sample ratio, severe imbalance, many outliers |
| Underfitting Risk | Too few samples, very low variance, excessive missing data |

---

## 🖥️ Web Application

Built with React 18 (CDN, no build tools) + Chart.js + Flask.

### Pages

| Page | Description |
|------|-------------|
| Landing | Hero, features overview, call-to-action |
| Login / Signup | Form validation, localStorage-based auth |
| Dashboard | Stats: total analyzed, quality breakdown, avg score |
| Upload Dataset | Drag-and-drop, progress bar, column picker fallback |
| Analysis Report | Full quality report with all charts and recommendations |
| History | All past analyses with score, risk, and re-view |

### Report Sections

- **Quality Score Ring** — animated 0–100 with color tiers
- **ML Readiness Breakdown** — 5-bar chart (Completeness → Usability)
- **ML Risk Prediction** — Safe / Overfitting / Underfitting badge
- **Advanced Metrics** — Skewed cols, drift proxy, constant cols, high-cardinality
- **EDA Distributions** — histogram per numeric column, bar chart per categorical
- **Feature Correlations** — horizontal bar chart (ID columns excluded)
- **Column Analysis Table** — dtype, missing, outliers, skewness, flags per column
- **AI Recommendations** — priority-ranked (🔴 High / 🟡 Medium / 🟢 Low) with code-level advice
- **Download JSON** — full report export
- **Export PDF** — browser print

---

## 🏗 Project Structure

```
dataset-risk-analyzer/
│
├── start.py                  ← Start frontend + backend together
│
├── frontend/
│   ├── index.html            ← App entry point (React via CDN)
│   ├── app.jsx               ← Full React SPA (v2)
│   ├── style.css             ← Design system + dark mode
│   └── serve.py              ← Static file server (port 3000)
│
├── backend/
│   ├── app.py                ← Flask REST API v2 (10 quality checks)
│   ├── outlier_analysis.py   ← Standalone outlier audit script
│   └── requirements.txt      ← Pinned dependencies
│
├── meta_features.py          ← 10-feature extractor (scipy skewness, IQR outliers)
├── baseline_model.py         ← Baseline LR with Pipeline + LabelEncoder
├── risk_label.py             ← Multi-condition risk labeling logic
├── meta_dataset_builder.py   ← Builds meta_dataset.csv from CSV files
├── meta_model.py             ← Trains + tunes RandomForest, saves pkl
├── predictor.py              ← Predict risk for a single file
│
├── meta_dataset.csv          ← 150-sample training data (3 balanced classes)
└── meta_model.pkl            ← Saved trained model (GridSearchCV best estimator)
```

---

## ⚙️ Technologies

**ML Pipeline**
- Python 3.10+
- Pandas, NumPy, SciPy
- Scikit-learn (RandomForest, GridSearchCV, Pipeline, LabelEncoder)

**Web Application**
- React 18 (CDN — no Node.js / build tools needed)
- Chart.js (bar, histogram, horizontal bar, doughnut)
- Flask 3 + Flask-CORS
- Python `http.server` (static frontend)

---

## ▶️ How to Run

### Step 1 — Install dependencies

```bash
pip install flask flask-cors pandas openpyxl scikit-learn scipy numpy
```

### Step 2 — Start both servers

```bash
python start.py
```

Open **http://localhost:3000** in your browser.

### Run separately

```bash
# Terminal 1 — Backend
python backend/app.py

# Terminal 2 — Frontend  
python frontend/serve.py
```

### Rebuild meta-model (if pkl is incompatible)

```bash
python meta_model.py
```

---

## 🌐 API Reference

### `POST /api/analyze`

Upload a dataset file and receive a full quality report.

**Request:** `multipart/form-data`
- `file` — CSV / XLSX / XLS / JSON (max 50 MB)
- `target_column` — name of the label column

**Response (200):**
```json
{
  "score": 78,
  "score_breakdown": { "total": 78, "completeness": 28, "consistency": 18, "validity": 16, "balance": 10, "usability": 6 },
  "prediction": "Safe Dataset",
  "summary": { "num_samples": 1000, "missing_pct": 2.1, "duplicate_count": 5, ... },
  "advanced": { "highly_skewed_cols": ["Age"], "constant_cols": [], ... },
  "columns": [ { "name": "Age", "dtype": "numeric", "missing": 21, "skewness": 1.8, ... } ],
  "distributions": [ { "col": "Age", "type": "histogram", "labels": [...], "values": [...] } ],
  "correlation": [0.42, 0.31],
  "corr_cols": ["Age", "Salary"],
  "recommendations": [ { "icon": "🧹", "title": "Handle Missing Values", "desc": "...", "priority": "medium" } ]
}
```

### `GET /api/health`
```json
{ "status": "ok", "version": "2.0" }
```

---

## 🔧 Troubleshooting

**`No module named 'sklearn'`**
```bash
pip install scikit-learn scipy
```

**`meta_model.pkl` incompatible**
```bash
python meta_model.py
```

**Port already in use**
```powershell
netstat -ano | findstr :5000
taskkill /PID <PID> /F
```

**Column not found**
The backend does case-insensitive matching. If still not found, all available column names are returned as clickable buttons in the UI.

---

## 🚀 Deployment Options

| Platform | Approach |
|----------|----------|
| **Render** | Flask backend as Web Service, static frontend via Static Site |
| **Railway** | `python backend/app.py` with Procfile |
| **Docker** | Multi-stage: Python backend + nginx for frontend |
| **Vercel** | Frontend only (static); backend as separate serverless |
| **Heroku** | `Procfile: web: python backend/app.py` |

Environment variable to set in production:
```
FLASK_ENV=production
CORS_ORIGINS=https://yourdomain.com
```

---

## 🎓 Interview Talking Points

| Topic | What to say |
|-------|-------------|
| **Meta-Learning** | "The model is trained on dataset properties (meta-features), not the data itself — so it generalises to any domain" |
| **Feature Engineering** | "Added skewness, duplicate %, outlier % to the original 7 features based on what actually causes model failure" |
| **Scoring System** | "5-dimension scoring inspired by IBM/Great Expectations frameworks: completeness, consistency, validity, balance, usability" |
| **Outlier Logic** | "ID columns are excluded using both name-based keywords and cardinality thresholds — prevents false positives" |
| **Recommendations** | "Priority-ranked (High/Medium/Low) with specific sklearn/pandas code strategies, not just generic warnings" |
| **Architecture** | "Decoupled: Flask REST API + React SPA communicating via JSON. Falls back to mock in demo mode if backend is offline" |

---

## 📜 License

Educational and research use. Not for production deployment without security hardening.
