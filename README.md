# Pre-Training Dataset Risk Analyzer for Machine Learning

## 📌 Project Overview

This project builds a **machine learning system that analyzes a dataset before training and predicts potential risks such as:**

* Overfitting risk
* Underfitting risk
* Safe dataset behavior

The goal is to help data scientists **understand dataset quality before expensive model training** by studying dataset characteristics and past model behavior.

It also includes a **full-stack interactive web UI** that allows users to upload datasets, view quality reports, and get preprocessing recommendations — all in one place.

---

## 🚀 Motivation

In many ML pipelines, issues like **overfitting, underfitting, and noisy data are discovered only after training models**.
This project proposes a **pre-training risk analysis system** that evaluates dataset properties and predicts possible training problems in advance.

---

## 🧠 System Workflow

```
Dataset → Meta Feature Extraction → Baseline Model Evaluation → Risk Labeling → Meta-Model Training → Risk Prediction
```

Steps performed:

1. Extract dataset meta-features
2. Train baseline ML models
3. Measure training vs testing accuracy gap
4. Assign dataset risk label
5. Train a meta-model to predict dataset risk
6. Predict risk for new unseen datasets

---

## 📊 Meta Features Used

The system analyzes statistical properties of datasets including:

* Number of samples
* Number of features
* Feature-to-sample ratio
* Average feature variance
* Feature correlation
* Class imbalance ratio
* Missing value percentage

These properties help estimate how the dataset might behave during training.

---

## 🖥️ Web UI Overview

The project includes a production-ready interactive web application built with React.js.

### Pages

| Page | Description |
|---|---|
| Landing Page | Hero section with product overview and call-to-action |
| Login / Signup | Form validation, JWT-ready authentication |
| Dashboard | Stats overview, quick actions, recent uploads |
| Upload Dataset | Drag-and-drop file upload with progress indicator |
| Analysis Report | Quality score, charts, column analysis, recommendations |
| History | All previously analyzed datasets with scores |

### Report Features

* **Quality Score (0–100)** — computed from missing values, duplicates, outliers, and class imbalance
* **ML Risk Prediction** — Safe Dataset / Overfitting Risk / Underfitting Risk
* **Value Distribution Charts** — histograms for Age, Product Price, Rating (ID columns excluded)
* **Feature Correlation Chart** — only valid numeric columns (no Response ID, Bill No, etc.)
* **Column Analysis Table** — per-column missing values, outlier counts, data type
* **Preprocessing Recommendations** — actionable steps to fix data issues
* **Dark Mode** — full dark/light theme toggle
* **Export PDF** — print report via browser

---

## 🏗 Project Structure

```
dataset-risk-analyzer-main/
│
├── start.py                    ← Start frontend + backend together
│
├── frontend/
│   ├── index.html              ← App entry point
│   ├── app.jsx                 ← Full React SPA
│   ├── style.css               ← All styles
│   └── serve.py                ← Static file server (port 3000)
│
├── backend/
│   ├── app.py                  ← Flask REST API (port 5000)
│   ├── outlier_analysis.py     ← Standalone outlier audit script
│   └── requirements.txt        ← Backend dependencies
│
├── meta_features.py            ← Feature extraction
├── baseline_model.py           ← Baseline model evaluation
├── risk_label.py               ← Risk label assignment
├── meta_dataset_builder.py     ← Builds meta_dataset.csv
├── meta_model.py               ← Trains and saves meta_model.pkl
├── predictor.py                ← Prediction helper
├── rebuild_model.py            ← Rebuild model if pkl is incompatible
│
├── meta_dataset.csv            ← Training data (4 benchmark datasets)
└── meta_model.pkl              ← Saved trained Random Forest model
```

---

## ⚙️ Technologies Used

**Core ML Pipeline**
* Python
* Pandas, NumPy
* Scikit-learn (Random Forest Classifier)

**Web Application**
* React.js 18 (via CDN, no build tools required)
* Chart.js (bar charts, histograms, correlation charts)
* Flask + Flask-CORS (REST API)
* Python `http.server` (static frontend server)
* CSS3 (custom design system, dark mode, responsive)

---

## 🧪 Datasets Used for Meta-Model Training

The meta-model was trained on 4 sklearn benchmark datasets:

| Dataset | Samples | Features | Risk Label |
|---|---|---|---|
| Iris | 150 | 4 | Safe Dataset |
| Breast Cancer | 569 | 30 | Safe Dataset |
| Wine | 178 | 13 | Safe Dataset |
| Digits | 1797 | 64 | Safe Dataset |

> **Note:** All training samples are labeled Safe Dataset. The model needs more diverse datasets with overfitting/underfitting examples to improve risk prediction accuracy. The quality score (0–100) is the more reliable metric.

---

## 🤖 Meta-Model

A **Random Forest Classifier** was trained on dataset meta-features to predict the risk category of new datasets.

Model Output Example:

```
Predicted Risk: Safe Dataset
```

---

## ▶️ How to Run the Project

### Step 1 — Install dependencies (one time only)

```bash
pip install flask flask-cors pandas openpyxl scikit-learn
```

### Step 2 — Navigate to the project folder

```bash
cd D:\dataset-risk-analyzer-main\dataset-risk-analyzer-main
```

### Step 3 — Start both servers together

```bash
python start.py
```

### Step 4 — Open the browser

```
http://localhost:3000
```

Press `Ctrl+C` to stop both servers.

---

### Run separately (two terminals)

**Terminal 1 — Backend API:**
```bash
python backend/app.py
```

**Terminal 2 — Frontend:**
```bash
python frontend/serve.py
```

---

## 🌐 URLs

| Service | URL |
|---|---|
| Website | http://localhost:3000 |
| Health Check | http://localhost:5000/api/health |

---

## 🔧 Troubleshooting

**`No module named 'numpy._core.numeric'`**
```bash
pip uninstall numpy pandas scikit-learn -y
pip install numpy pandas scikit-learn --no-cache-dir
```

**`meta_model.pkl` incompatible with current numpy version**
```bash
python rebuild_model.py
```

**Port already in use**
```bash
netstat -ano | findstr :3000
taskkill /PID <PID_NUMBER> /F
```

**Column not found error**
The backend does case-insensitive column matching automatically. If still not found, the UI shows all available column names as clickable buttons.

---

## 📈 Future Improvements

* Add more datasets with overfitting/underfitting examples for better risk prediction
* Add noise detection metrics
* Improve risk labeling strategy
* Integrate with AutoML pipelines
* Add user authentication with real JWT backend
* WebSocket support for real-time progress updates

---

## 🎓 Academic Value

This project demonstrates concepts from:

* Meta-Learning
* Dataset Complexity Analysis
* Automated Machine Learning (AutoML)
* Data Quality Assessment
* Full-Stack Web Development


---

## 📜 License

This project is for educational and research purposes.
