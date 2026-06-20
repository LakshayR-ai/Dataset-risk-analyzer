// ============================================================
// Dataset Quality Analyzer — React SPA  (v2)
// ============================================================
const { useState, useEffect, useRef, useCallback, createContext, useContext } = React;

// ============================================================
// CONTEXT
// ============================================================
const AppContext = createContext(null);

function AppProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('dqa_user')); } catch { return null; }
  });
  const [dark, setDark] = useState(() => localStorage.getItem('dqa_dark') === 'true');
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    document.body.classList.toggle('dark', dark);
    localStorage.setItem('dqa_dark', dark);
  }, [dark]);

  const login = useCallback((userData, token) => {
    localStorage.setItem('dqa_user', JSON.stringify(userData));
    localStorage.setItem('dqa_token', token);
    setUser(userData);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('dqa_user');
    localStorage.removeItem('dqa_token');
    setUser(null);
  }, []);

  const toast = useCallback((msg, type = 'info') => {
    const id = Date.now();
    setToasts(t => [...t, { id, msg, type }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4000);
  }, []);

  return (
    <AppContext.Provider value={{ user, login, logout, dark, setDark, toast }}>
      {children}
      <ToastContainer toasts={toasts} />
    </AppContext.Provider>
  );
}
const useApp = () => useContext(AppContext);

// ============================================================
// TOAST
// ============================================================
function ToastContainer({ toasts }) {
  const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
  return (
    <div className="toast-container">
      {toasts.map(t => (
        <div key={t.id} className={`toast toast-${t.type}`}>
          <span>{icons[t.type] || 'ℹ️'}</span><span>{t.msg}</span>
        </div>
      ))}
    </div>
  );
}

// ============================================================
// SCORE RING
// ============================================================
function ScoreRing({ score, size = 120 }) {
  const r = 46, cx = 60, cy = 60;
  const circ = 2 * Math.PI * r;
  const pct = Math.min(Math.max(score || 0, 0), 100);
  const offset = circ - (pct / 100) * circ;
  const color = pct >= 75 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#ef4444';
  return (
    <div className="score-ring-wrap">
      <div className="score-ring" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox="0 0 120 120">
          <circle cx={cx} cy={cy} r={r} fill="none" stroke="#e2e8f0" strokeWidth="10" />
          <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth="10"
            strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
            style={{ transition: 'stroke-dashoffset 1.2s ease' }} />
        </svg>
        <div className="score-ring-text">
          <span className="score-num" style={{ color }}>{pct}</span>
          <span className="score-lbl">/ 100</span>
        </div>
      </div>
      <span style={{ fontSize: 13, fontWeight: 600, color }}>
        {pct >= 75 ? 'Good Quality' : pct >= 50 ? 'Fair Quality' : 'Poor Quality'}
      </span>
    </div>
  );
}

// ============================================================
// MINI SCORE BAR  (for score breakdown)
// ============================================================
function ScoreBar({ label, value, max, color }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 3 }}>
        <span style={{ color: 'var(--text-muted)' }}>{label}</span>
        <span style={{ fontWeight: 700 }}>{value}/{max}</span>
      </div>
      <div style={{ height: 6, borderRadius: 99, background: 'var(--border)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 99, transition: 'width 1s ease' }} />
      </div>
    </div>
  );
}

// ============================================================
// LANDING PAGE
// ============================================================
function LandingPage({ onNavigate }) {
  const { dark, setDark } = useApp();
  const features = [
    { icon: '🔍', title: 'Deep Quality Analysis', desc: 'Detect missing values, duplicates, outliers, type mismatches, and skewed distributions.' },
    { icon: '📊', title: 'Visual EDA Dashboard', desc: 'Interactive histograms, bar charts, and correlation charts for instant insight.' },
    { icon: '🤖', title: 'ML Risk Prediction', desc: 'Predict Overfitting, Underfitting, and Safe Dataset status before you train.' },
    { icon: '⚡', title: 'ML Readiness Score', desc: '5-dimension scoring: Completeness, Consistency, Validity, Balance, Usability.' },
    { icon: '🛡️', title: 'AI Recommendations', desc: 'Actionable, priority-ranked preprocessing steps with specific code advice.' },
    { icon: '📁', title: 'Multi-format Support', desc: 'Upload CSV, Excel (.xlsx/.xls), or JSON. Max 50 MB.' },
  ];
  return (
    <div className="landing">
      <nav className="landing-nav">
        <div className="nav-logo"><div className="logo-icon">🔍</div>DataQA</div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <button className="icon-btn" onClick={() => setDark(!dark)} title="Toggle theme">{dark ? '☀️' : '🌙'}</button>
          <button className="btn btn-ghost btn-sm" onClick={() => onNavigate('login')}>Log in</button>
          <button className="btn btn-primary btn-sm" onClick={() => onNavigate('signup')}>Get Started</button>
        </div>
      </nav>
      <div className="hero">
        <div className="hero-badge">✨ AI-Powered Dataset Analysis</div>
        <h1>Analyze Dataset Quality<br /><span>Before You Train</span></h1>
        <p>Upload your dataset and get an instant quality report — missing values, outliers, correlations, ML risk predictions, and a readiness score in one place.</p>
        <div className="hero-actions">
          <button className="btn btn-primary btn-lg" onClick={() => onNavigate('signup')}>🚀 Start Analyzing Free</button>
          <button className="btn btn-outline btn-lg" onClick={() => onNavigate('login')}>View Demo</button>
        </div>
      </div>
      <div className="features-grid">
        {features.map((f, i) => (
          <div key={i} className="feature-card">
            <div className="feature-icon">{f.icon}</div>
            <h3>{f.title}</h3><p>{f.desc}</p>
          </div>
        ))}
      </div>
      <div style={{ textAlign: 'center', padding: '40px 20px 60px', color: 'var(--text-muted)', fontSize: 14 }}>
        © 2026 DataQA · Dataset Quality Analyzer
      </div>
    </div>
  );
}

// ============================================================
// AUTH PAGE
// ============================================================
function AuthPage({ mode, onNavigate }) {
  const { login, toast } = useApp();
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const isLogin = mode === 'login';

  useEffect(() => { setForm({ name: '', email: '', password: '' }); setErrors({}); }, [mode]);

  const validate = () => {
    const e = {};
    if (!isLogin && !form.name.trim()) e.name = 'Name is required';
    if (!form.email.match(/^[^\s@]+@[^\s@]+\.[^\s@]+$/)) e.email = 'Valid email required';
    if (form.password.length < 6) e.password = 'Minimum 6 characters';
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validate()) return;
    setLoading(true);
    try {
      await new Promise(r => setTimeout(r, 600));
      const userData = { name: form.name || form.email.split('@')[0], email: form.email };
      login(userData, 'demo-jwt-' + Date.now());
      toast(`Welcome${isLogin ? ' back' : ''}, ${userData.name}!`, 'success');
      onNavigate('dashboard');
    } catch { toast('Authentication failed.', 'error'); }
    finally { setLoading(false); }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">
          <div className="logo-big">🔍</div>
          <h1>DataQA</h1>
          <p>{isLogin ? 'Sign in to your account' : 'Create your free account'}</p>
        </div>
        <form onSubmit={handleSubmit}>
          {!isLogin && (
            <div className="form-group">
              <label className="form-label">Full Name</label>
              <input className="form-input" placeholder="Your name" value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })} />
              {errors.name && <div className="form-error">{errors.name}</div>}
            </div>
          )}
          <div className="form-group">
            <label className="form-label">Email Address</label>
            <input className="form-input" type="email" placeholder="you@example.com" value={form.email}
              onChange={e => setForm({ ...form, email: e.target.value })} />
            {errors.email && <div className="form-error">{errors.email}</div>}
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input className="form-input" type="password" placeholder="••••••••" value={form.password}
              onChange={e => setForm({ ...form, password: e.target.value })} />
            {errors.password && <div className="form-error">{errors.password}</div>}
          </div>
          <button className="btn btn-primary w-full" type="submit" disabled={loading}
            style={{ justifyContent: 'center', marginTop: 4 }}>
            {loading ? '⏳ Please wait...' : isLogin ? '🔐 Sign In' : '🚀 Create Account'}
          </button>
        </form>
        <div className="auth-switch">
          {isLogin
            ? <><span>Don't have an account? </span><a onClick={() => onNavigate('signup')}>Sign up free</a></>
            : <><span>Already have an account? </span><a onClick={() => onNavigate('login')}>Sign in</a></>}
        </div>
        <div style={{ textAlign: 'center', marginTop: 12 }}>
          <a style={{ fontSize: 13, color: 'var(--text-muted)', cursor: 'pointer' }}
            onClick={() => onNavigate('landing')}>← Back to home</a>
        </div>
      </div>
    </div>
  );
}


// ============================================================
// SIDEBAR + TOPBAR
// ============================================================
function Sidebar({ page, onNavigate, open, onClose }) {
  const { user, logout } = useApp();
  const navItems = [
    { id: 'dashboard', icon: '🏠', label: 'Dashboard' },
    { id: 'upload',    icon: '📤', label: 'Upload Dataset' },
    { id: 'reports',   icon: '📊', label: 'Analysis Report' },
    { id: 'history',   icon: '🕐', label: 'History' },
  ];
  return (
    <>
      {open && <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)', zIndex: 99 }} />}
      <aside className={`sidebar ${open ? 'open' : ''}`}>
        <div className="sidebar-logo">
          <div className="logo-icon">🔍</div><span>DataQA</span>
        </div>
        <nav className="sidebar-nav">
          {navItems.map(item => (
            <button key={item.id} className={`nav-item ${page === item.id ? 'active' : ''}`}
              onClick={() => { onNavigate(item.id); onClose(); }}>
              <span className="nav-icon">{item.icon}</span>{item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'linear-gradient(135deg, var(--primary), #a855f7)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontWeight: 700, fontSize: 15 }}>
              {user?.name?.[0]?.toUpperCase() || 'U'}
            </div>
            <div style={{ overflow: 'hidden' }}>
              <div style={{ fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{user?.name}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{user?.email}</div>
            </div>
          </div>
          <button className="btn btn-ghost btn-sm w-full" onClick={logout} style={{ justifyContent: 'center' }}>
            🚪 Sign Out
          </button>
        </div>
      </aside>
    </>
  );
}

function Topbar({ title, onMenuClick }) {
  const { dark, setDark } = useApp();
  return (
    <header className="topbar">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <button className="icon-btn menu-btn" onClick={onMenuClick} aria-label="Open menu">☰</button>
        <span className="topbar-title">{title}</span>
      </div>
      <div className="topbar-actions">
        <button className="icon-btn" onClick={() => setDark(!dark)} title="Toggle dark mode" aria-label="Toggle dark mode">
          {dark ? '☀️' : '🌙'}
        </button>
      </div>
    </header>
  );
}

// ============================================================
// DASHBOARD
// ============================================================
function DashboardPage({ onNavigate, history }) {
  const { user } = useApp();
  const stats = [
    { icon: '📁', label: 'Datasets Analyzed', value: history.length, color: 'purple' },
    { icon: '✅', label: 'Good Quality',       value: history.filter(h => (h.score || 0) >= 75).length, color: 'green' },
    { icon: '⚠️', label: 'Needs Attention',   value: history.filter(h => (h.score || 0) >= 50 && (h.score || 0) < 75).length, color: 'yellow' },
    { icon: '❌', label: 'Poor Quality',       value: history.filter(h => (h.score || 0) < 50).length, color: 'red' },
  ];

  // Average score for last 5 analyses
  const recentScores = history.slice(-5).map(h => h.score || 0);
  const avgScore = recentScores.length ? Math.round(recentScores.reduce((a, b) => a + b, 0) / recentScores.length) : null;

  return (
    <div>
      <div style={{ marginBottom: 28 }}>
        <h2 className="section-title">Welcome back, {user?.name} 👋</h2>
        <p className="section-subtitle">Here's an overview of your dataset analysis activity.</p>
      </div>
      <div className="stat-grid">
        {stats.map((s, i) => (
          <div key={i} className="stat-card">
            <div className={`stat-icon ${s.color}`}>{s.icon}</div>
            <div><div className="stat-value">{s.value}</div><div className="stat-label">{s.label}</div></div>
          </div>
        ))}
      </div>
      <div className="grid-2" style={{ marginBottom: 24 }}>
        <div className="card">
          <div className="card-header">
            <div><div className="card-title">Quick Actions</div><div className="card-subtitle">Get started quickly</div></div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <button className="btn btn-primary" onClick={() => onNavigate('upload')}>📤 Upload New Dataset</button>
            <button className="btn btn-outline" onClick={() => onNavigate('reports')}>📊 View Latest Report</button>
            <button className="btn btn-ghost" onClick={() => onNavigate('history')}>🕐 Browse History</button>
          </div>
        </div>
        <div className="card">
          <div className="card-header">
            <div><div className="card-title">Recent Uploads</div><div className="card-subtitle">Your last 3 datasets</div></div>
            {avgScore !== null && (
              <span className={`badge ${avgScore >= 75 ? 'badge-success' : avgScore >= 50 ? 'badge-warning' : 'badge-danger'}`}>
                Avg {avgScore}/100
              </span>
            )}
          </div>
          {history.length === 0 ? (
            <div className="empty-state" style={{ padding: '20px 0' }}>
              <div className="empty-icon">📂</div>
              <p>No datasets yet. Upload one to get started!</p>
            </div>
          ) : (
            history.slice(-3).reverse().map((h, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', borderBottom: i < 2 ? '1px solid var(--border)' : 'none' }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{h.filename}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{h.date}</div>
                </div>
                <span className={`badge ${(h.score||0) >= 75 ? 'badge-success' : (h.score||0) >= 50 ? 'badge-warning' : 'badge-danger'}`}>
                  {h.score ?? '—'}/100
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}


// ============================================================
// MOCK REPORT (demo mode when backend is offline)
// ============================================================
function seededRng(seed) {
  let s = seed >>> 0;
  return () => {
    s += 0x6d2b79f5;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t ^= t + Math.imul(t ^ (t >>> 7), 61 | t);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function hashStr(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

function generateMockReport(filename, targetCol, actualRowCount = null) {
  const seed = hashStr(filename.toLowerCase() + '|' + targetCol.toLowerCase());
  const rng = seededRng(seed);
  const score = Math.floor(rng() * 40) + 55;
  const num_samples = actualRowCount !== null ? actualRowCount : Math.floor(rng() * 2000) + 200;
  const num_features = Math.floor(rng() * 15) + 3;
  const missing_pct = +(rng() * 12).toFixed(2);
  const duplicate_pct = +(rng() * 8).toFixed(2);
  const outlier_pct = +(rng() * 10).toFixed(2);
  const class_imbalance = +(rng() * 0.4 + 0.6).toFixed(3);
  const duplicate_count = Math.round(num_samples * duplicate_pct / 100);
  const outlier_count = Math.round(num_samples * outlier_pct / 100);
  const clean_count = num_samples - duplicate_count;
  return {
    score,
    score_breakdown: {
      total: score,
      completeness: Math.max(0, 30 - Math.round(missing_pct * 2.5)),
      consistency: Math.max(0, 20 - Math.round(duplicate_pct * 3)),
      validity: Math.max(0, 20 - Math.round(outlier_pct * 1.5)),
      balance: class_imbalance > 0.9 ? 5 : class_imbalance > 0.8 ? 10 : 15,
      usability: 12,
    },
    prediction: score >= 75 ? 'Safe Dataset' : score >= 55 ? 'Overfitting Risk' : 'Underfitting Risk',
    summary: { num_samples, clean_count, duplicate_count, duplicate_pct, outlier_count, outlier_pct,
               num_features, missing_pct, class_imbalance, count_source: actualRowCount ? 'file' : 'estimated' },
    advanced: { highly_skewed_cols: ['Age'], high_cv_cols: [], constant_cols: [], high_cardinality_cols: [] },
    columns: [
      { name: 'Age', dtype: 'numeric', missing: 5, missing_pct: 1.2, outliers: 3, skewness: 0.8, constant: false, high_cardinality: false, type_mismatch: false, issue: true },
      { name: 'Product Price', dtype: 'numeric', missing: 0, missing_pct: 0, outliers: 12, skewness: 1.9, constant: false, high_cardinality: false, type_mismatch: false, issue: true },
      { name: 'Rating', dtype: 'numeric', missing: 2, missing_pct: 0.5, outliers: 0, skewness: -0.3, constant: false, high_cardinality: false, type_mismatch: false, issue: true },
      { name: targetCol, dtype: 'categorical', missing: 0, missing_pct: 0, outliers: 0, skewness: null, constant: false, high_cardinality: false, type_mismatch: false, issue: false },
    ],
    distributions: [
      { col: 'Age', type: 'histogram', labels: ['18–25','26–33','34–41','42–49','50–57','58–65'], values: [120,210,180,160,90,40] },
      { col: 'Product Price', type: 'histogram', labels: ['0–250','250–500','500–750','750–1000','1000+'], values: [80,220,310,250,140] },
      { col: 'Rating', type: 'histogram', labels: ['1–2','3–4','5–6','7–8','9–10'], values: [40,90,200,380,290] },
    ],
    distribution: { labels: ['18–25','26–33','34–41','42–49','50+'], values: [120,210,180,160,130] },
    correlation: [0.42, 0.31],
    corr_cols: ['Age', 'Product Price'],
    recommendations: [
      { icon: '🧹', title: 'Handle Missing Values', desc: 'Use median imputation for numeric columns with < 5% missing data.', priority: 'medium' },
      { icon: '📐', title: 'Fix Skewed Features', desc: 'Apply log1p or Box-Cox transform to Age, Product Price.', priority: 'medium' },
      { icon: '📏', title: 'Scale Numeric Features', desc: 'Apply StandardScaler after train/test split.', priority: 'low' },
      { icon: '⚖️', title: 'Address Class Imbalance', desc: 'Use SMOTE or class_weight="balanced".', priority: 'medium' },
    ],
  };
}

// ============================================================
// UPLOAD PAGE
// ============================================================
function UploadPage({ onAnalyzed }) {
  const { toast } = useApp();
  const [file, setFile] = useState(null);
  const [drag, setDrag] = useState(false);
  const [progress, setProgress] = useState(0);
  const [loading, setLoading] = useState(false);
  const [targetCol, setTargetCol] = useState('');
  const [availableCols, setAvailableCols] = useState([]);
  const inputRef = useRef();
  const ACCEPTED = ['.csv', '.xlsx', '.xls', '.json'];

  const validateFile = (f) => {
    const ext = '.' + f.name.split('.').pop().toLowerCase();
    if (!ACCEPTED.includes(ext)) { toast('Unsupported type. Use CSV, Excel, or JSON.', 'error'); return false; }
    if (f.size > 50 * 1024 * 1024) { toast('File too large. Max 50 MB.', 'error'); return false; }
    return true;
  };

  const handleFile = (f) => { if (f && validateFile(f)) { setFile(f); setAvailableCols([]); } };
  const handleDrop = (e) => { e.preventDefault(); setDrag(false); handleFile(e.dataTransfer.files[0]); };

  const readActualRowCount = (f) => new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const lines = e.target.result.split('\n').filter(l => l.trim().length > 0);
        resolve(Math.max(0, lines.length - 1));
      } catch { resolve(null); }
    };
    reader.onerror = () => resolve(null);
    reader.readAsText(f.slice(0, 2 * 1024 * 1024));
  });

  const handleAnalyze = async () => {
    if (!file) { toast('Please select a file first.', 'error'); return; }
    if (!targetCol.trim()) { toast('Please enter the target column name.', 'error'); return; }
    setLoading(true); setProgress(0); setAvailableCols([]);

    const ext = file.name.split('.').pop().toLowerCase();
    let actualRowCount = null;
    if (ext === 'csv') actualRowCount = await readActualRowCount(file);

    for (let i = 10; i <= 80; i += 10) {
      await new Promise(r => setTimeout(r, 100));
      setProgress(i);
    }

    try {
      let result; let usedBackend = false;
      try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('target_column', targetCol);
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 30000);
        const response = await fetch('http://localhost:5000/api/analyze', {
          method: 'POST', body: formData, signal: controller.signal,
        });
        clearTimeout(timeout);
        const data = await response.json();
        if (!response.ok || data.error) {
          if (data.available_columns) {
            setAvailableCols(data.available_columns);
            toast(`❌ ${data.error}`, 'error');
            setLoading(false); setProgress(0); return;
          }
          throw new Error(data.error || `Backend error: ${response.status}`);
        }
        result = data; usedBackend = true;
      } catch (backendErr) {
        const isNetwork = backendErr.name === 'AbortError' ||
          ['fetch', 'Failed to fetch', 'NetworkError', 'Load failed'].some(s => backendErr.message.includes(s));
        if (isNetwork) {
          console.warn('[DataQA] Backend unreachable, using mock:', backendErr.message);
          result = generateMockReport(file.name, targetCol, actualRowCount);
        } else { throw backendErr; }
      }

      setProgress(100);
      await new Promise(r => setTimeout(r, 200));
      toast(usedBackend ? '✅ Analysis complete!' : '✅ Demo mode (backend offline)', usedBackend ? 'success' : 'warning');
      onAnalyzed({ ...result, filename: file.name, date: new Date().toLocaleDateString(), usedBackend });
    } catch (err) {
      toast('Analysis failed: ' + err.message, 'error');
      setProgress(0);
    } finally { setLoading(false); }
  };

  return (
    <div>
      <h2 className="section-title">Upload Dataset</h2>
      <p className="section-subtitle">Get a full quality analysis — missing values, outliers, skewness, correlations, and ML risk in seconds.</p>
      <div style={{ maxWidth: 640 }}>
        <div className="card" style={{ marginBottom: 20 }}>
          <div className={`upload-zone ${drag ? 'drag-over' : ''}`}
            onDragOver={e => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={handleDrop}
            onClick={() => !file && inputRef.current.click()}>
            <input ref={inputRef} type="file" accept=".csv,.xlsx,.xls,.json" style={{ display: 'none' }}
              onChange={e => handleFile(e.target.files[0])} />
            {file ? (
              <>
                <div className="upload-icon">✅</div>
                <div className="upload-title">File Ready</div>
                <div className="upload-file-info">
                  <span style={{ fontSize: 24 }}>📄</span>
                  <span className="upload-file-name">{file.name}</span>
                  <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{(file.size / 1024).toFixed(1)} KB</span>
                  <button className="btn btn-ghost btn-sm" onClick={e => { e.stopPropagation(); setFile(null); setProgress(0); setAvailableCols([]); }}>✕</button>
                </div>
              </>
            ) : (
              <>
                <div className="upload-icon">📁</div>
                <div className="upload-title">Drop your dataset here</div>
                <div className="upload-subtitle">or click to browse · CSV, Excel, JSON · Max 50 MB</div>
              </>
            )}
          </div>
          {loading && (
            <div style={{ marginTop: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6 }}>
                <span>Analyzing dataset...</span><span>{progress}%</span>
              </div>
              <div className="progress-bar-wrap"><div className="progress-bar" style={{ width: `${progress}%` }} /></div>
            </div>
          )}
        </div>
        <div className="card">
          <div className="form-group">
            <label className="form-label">Target Column Name</label>
            <input className="form-input" placeholder="e.g., Rating, Promoter Score, label, target"
              value={targetCol} onChange={e => { setTargetCol(e.target.value); setAvailableCols([]); }} />
            <div className="form-hint">The column your ML model will predict (the label/output column).</div>
            {availableCols.length > 0 && (
              <div style={{ marginTop: 10, padding: 12, background: 'rgba(239,68,68,.06)', borderRadius: 8, border: '1px solid rgba(239,68,68,.2)' }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--danger)', marginBottom: 8 }}>❌ Column not found. Click to select:</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {availableCols.map(col => (
                    <button key={col} className="badge badge-info"
                      style={{ cursor: 'pointer', border: 'none', fontSize: 12, padding: '4px 10px' }}
                      onClick={() => { setTargetCol(col); setAvailableCols([]); }}>{col}</button>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <button className="btn btn-primary" onClick={handleAnalyze} disabled={loading || !file}
              style={{ flex: 1, justifyContent: 'center' }}>
              {loading ? '⏳ Analyzing...' : '🔍 Analyze Dataset'}
            </button>
            <button className="btn btn-ghost" onClick={() => { setFile(null); setTargetCol(''); setProgress(0); setAvailableCols([]); }} disabled={loading}>
              Reset
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}


// ============================================================
// CHARTS
// ============================================================
function BarChart({ labels, values, color = '#6366f1' }) {
  const canvasRef = useRef(); const chartRef = useRef();
  useEffect(() => {
    if (!canvasRef.current || !labels?.length || !values?.length) return;
    if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null; }
    chartRef.current = new Chart(canvasRef.current, {
      type: 'bar',
      data: { labels, datasets: [{ data: values, backgroundColor: color + 'cc', borderColor: color, borderWidth: 2, borderRadius: 6 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, grid: { color: 'rgba(100,100,100,.08)' } },
          x: { grid: { display: false }, ticks: { maxRotation: 30 } },
        },
      },
    });
    return () => { if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null; } };
  }, [JSON.stringify(labels), JSON.stringify(values), color]);
  return <canvas ref={canvasRef} />;
}

function HorizontalBar({ labels, values }) {
  const canvasRef = useRef(); const chartRef = useRef();
  const COLORS = ['#6366f1','#10b981','#f59e0b','#ef4444','#3b82f6','#a855f7'];
  useEffect(() => {
    if (!canvasRef.current || !labels?.length || !values?.length) return;
    if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null; }
    chartRef.current = new Chart(canvasRef.current, {
      type: 'bar',
      data: { labels, datasets: [{ data: values, backgroundColor: values.map((_, i) => COLORS[i % 6] + 'cc'), borderRadius: 4 }] },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { beginAtZero: true, max: 1, grid: { color: 'rgba(100,100,100,.08)' } },
          y: { grid: { display: false } },
        },
      },
    });
    return () => { if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null; } };
  }, [JSON.stringify(labels), JSON.stringify(values)]);
  return <canvas ref={canvasRef} />;
}

function DonutChart({ labels, values, colors }) {
  const canvasRef = useRef(); const chartRef = useRef();
  useEffect(() => {
    if (!canvasRef.current || !labels?.length || !values?.length) return;
    if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null; }
    chartRef.current = new Chart(canvasRef.current, {
      type: 'doughnut',
      data: { labels, datasets: [{ data: values, backgroundColor: colors || ['#10b981','#f59e0b','#ef4444'], borderWidth: 0, hoverOffset: 4 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { font: { size: 11 }, padding: 14 } } },
        cutout: '65%',
      },
    });
    return () => { if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null; } };
  }, [JSON.stringify(labels), JSON.stringify(values)]);
  return <canvas ref={canvasRef} />;
}

// ============================================================
// REPORT PAGE  — full v2 with score breakdown, advanced metrics,
//               EDA section, ML readiness, download
// ============================================================

// Priority badge helper
function PriorityBadge({ priority }) {
  const map = { high: ['badge-danger','🔴 High'], medium: ['badge-warning','🟡 Medium'], low: ['badge-info','🟢 Low'] };
  const [cls, label] = map[priority] || ['badge-info', priority];
  return <span className={`badge ${cls}`} style={{ fontSize: 11 }}>{label}</span>;
}

function ReportPage({ report }) {
  if (!report) {
    return (
      <div>
        <h2 className="section-title">Analysis Report</h2>
        <div className="empty-state">
          <div className="empty-icon">📊</div>
          <h3>No Analysis Yet</h3>
          <p>Upload a dataset to generate your first quality report.</p>
        </div>
      </div>
    );
  }

  const {
    score = 0, score_breakdown = {}, prediction = '—', filename = '',
    summary = {}, advanced = {}, columns = [], distribution = {},
    correlation = [], recommendations = [],
  } = report;

  const riskColor = score >= 75 ? 'badge-success' : score >= 50 ? 'badge-warning' : 'badge-danger';

  // Download JSON report
  const downloadReport = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dqa_report_${filename.replace(/\W/g, '_')}_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      {/* ── Header ────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 className="section-title">Analysis Report</h2>
          <p className="section-subtitle">📄 {filename}</p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          {report.usedBackend === false && <span className="badge badge-warning">⚠️ Demo Mode</span>}
          {report.usedBackend === true  && <span className="badge badge-success">✅ Live Data</span>}
          <button className="btn btn-outline btn-sm" onClick={downloadReport}>⬇️ Download JSON</button>
          <button className="btn btn-outline btn-sm" onClick={() => window.print()}>🖨️ Export PDF</button>
        </div>
      </div>

      {/* ── Score + ML Risk ────────────────────────────── */}
      <div className="card" style={{ marginBottom: 20, display: 'flex', alignItems: 'flex-start', gap: 32, flexWrap: 'wrap' }}>
        <ScoreRing score={score} />
        <div style={{ flex: 1, minWidth: 240 }}>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 6 }}>ML Risk Prediction</div>
          <span className={`badge ${riskColor}`} style={{ fontSize: 15, padding: '6px 16px' }}>
            {score >= 75 ? '✅' : score >= 50 ? '⚠️' : '❌'} {prediction}
          </span>
          {summary.count_source === 'estimated' && (
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--warning)', background: 'rgba(245,158,11,.1)', padding: '6px 10px', borderRadius: 6, display: 'inline-block' }}>
              ⚠️ Sample count estimated — connect backend for exact numbers
            </div>
          )}
          <div style={{ marginTop: 16, display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            {[
              ['Total Samples',  summary.num_samples?.toLocaleString() ?? '—',  summary.count_source === 'file' ? '✅ from file' : '⚠️ estimated'],
              ['Clean Samples',  summary.clean_count?.toLocaleString() ?? '—',  'after dedup'],
              ['Features',       summary.num_features ?? '—', null],
              ['Missing',        (summary.missing_pct ?? '—') + (summary.missing_pct != null ? '%' : ''), null],
              ['Duplicates',     summary.duplicate_count != null ? `${summary.duplicate_count} (${summary.duplicate_pct}%)` : '—', null],
              ['Outliers',       summary.outlier_count   != null ? `${summary.outlier_count} (${summary.outlier_pct}%)`   : '—', null],
            ].map(([k, v, hint]) => (
              <div key={k}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 500 }}>{k}</div>
                <div style={{ fontSize: 18, fontWeight: 700 }}>{v}</div>
                {hint && <div style={{ fontSize: 10, marginTop: 1, color: hint.startsWith('✅') ? 'var(--success)' : hint.startsWith('⚠️') ? 'var(--warning)' : 'var(--text-muted)' }}>{hint}</div>}
              </div>
            ))}
          </div>
        </div>

        {/* ── ML Readiness Score Breakdown ── */}
        {score_breakdown.total != null && (
          <div style={{ minWidth: 220, flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>ML Readiness Breakdown</div>
            <ScoreBar label="Completeness (missing)"   value={score_breakdown.completeness ?? 0} max={30} color="#6366f1" />
            <ScoreBar label="Consistency (dupes)"      value={score_breakdown.consistency  ?? 0} max={20} color="#10b981" />
            <ScoreBar label="Validity (outliers)"      value={score_breakdown.validity     ?? 0} max={20} color="#f59e0b" />
            <ScoreBar label="Balance (imbalance)"      value={score_breakdown.balance      ?? 0} max={15} color="#3b82f6" />
            <ScoreBar label="Usability (structure)"    value={score_breakdown.usability    ?? 0} max={15} color="#a855f7" />
          </div>
        )}
      </div>

      {/* ── Advanced Metrics ────────────────────────────── */}
      {advanced && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-header"><div className="card-title">🧠 Advanced Data Metrics</div></div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
            {[
              { label: '📐 Highly Skewed Cols',     val: advanced.highly_skewed_cols, empty: 'None detected ✅' },
              { label: '📉 High-Variance Cols (drift proxy)', val: advanced.high_cv_cols, empty: 'None detected ✅' },
              { label: '🚫 Constant Cols',           val: advanced.constant_cols,       empty: 'None detected ✅' },
              { label: '🔑 High-Cardinality Strings',val: advanced.high_cardinality_cols, empty: 'None detected ✅' },
            ].map(({ label, val, empty }) => (
              <div key={label} style={{ padding: 14, background: 'var(--bg)', borderRadius: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>{label}</div>
                {val && val.length > 0
                  ? val.map(c => <span key={c} className="badge badge-warning" style={{ margin: '2px 4px 2px 0', fontSize: 11 }}>{c}</span>)
                  : <span style={{ fontSize: 12, color: 'var(--success)' }}>{empty}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── EDA: Value Distribution Charts ───────────────── */}
      {report.distributions?.length > 0 ? (
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 14 }}>📊 EDA — Value Distributions</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
            {report.distributions.map((d, i) => (
              <div key={i} className="card">
                <div className="card-header">
                  <div><div className="card-title">{d.col}</div><div className="card-subtitle">{d.type === 'histogram' ? 'Numeric distribution' : 'Category counts'}</div></div>
                  <span className="badge badge-purple">{d.type}</span>
                </div>
                <div className="chart-container">
                  <BarChart labels={d.labels} values={d.values} color={d.type === 'histogram' ? '#6366f1' : '#10b981'} />
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : distribution?.labels?.length > 0 && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-header"><div className="card-title">📊 Value Distribution</div></div>
          <div className="chart-container"><BarChart labels={distribution.labels} values={distribution.values} /></div>
        </div>
      )}

      {/* ── Feature Correlation ───────────────────────────── */}
      {report.corr_cols?.length > 0 && correlation?.some(v => v > 0) && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-header">
            <div><div className="card-title">🔗 Feature Correlations</div><div className="card-subtitle">Absolute Pearson correlation (ID columns excluded)</div></div>
          </div>
          <div className="chart-container">
            <HorizontalBar labels={report.corr_cols} values={correlation.slice(0, report.corr_cols.length)} />
          </div>
        </div>
      )}

      {/* ── Column Analysis Table ─────────────────────────── */}
      {columns.length > 0 && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-header">
            <div className="card-title">🗂️ Column Analysis</div>
            <span className="badge badge-info">{columns.length} columns</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Column</th><th>Type</th><th>Missing</th><th>Outliers</th><th>Skewness</th><th>Flags</th><th>Status</th></tr>
              </thead>
              <tbody>
                {columns.map((col, i) => (
                  <tr key={i} className={col.issue ? 'highlight-row' : ''}>
                    <td><strong>{col.name}</strong></td>
                    <td><span className="badge badge-purple">{col.dtype}</span></td>
                    <td>{col.missing} {col.missing_pct > 0 && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>({col.missing_pct}%)</span>}</td>
                    <td>{col.outliers}</td>
                    <td>
                      {col.skewness != null
                        ? <span style={{ color: Math.abs(col.skewness) > 1.5 ? 'var(--warning)' : 'inherit' }}>
                            {col.skewness} {Math.abs(col.skewness) > 1.5 ? '⚠️' : ''}
                          </span>
                        : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                    </td>
                    <td>
                      {col.constant && <span className="badge badge-danger" style={{ fontSize: 10, marginRight: 3 }}>Constant</span>}
                      {col.high_cardinality && <span className="badge badge-warning" style={{ fontSize: 10, marginRight: 3 }}>High-card</span>}
                      {col.type_mismatch && <span className="badge badge-warning" style={{ fontSize: 10 }}>Type mismatch</span>}
                    </td>
                    <td><span className={`badge ${col.issue ? 'badge-warning' : 'badge-success'}`}>{col.issue ? '⚠️ Review' : '✅ OK'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Recommendations ───────────────────────────────── */}
      {recommendations.length > 0 && (
        <div className="card">
          <div className="card-header"><div className="card-title">💡 AI Preprocessing Recommendations</div></div>
          {recommendations.map((r, i) => (
            <div key={i} className="recommendation-item" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ display: 'flex', gap: 12 }}>
                <span className="rec-icon">{r.icon}</span>
                <div className="rec-text"><strong>{r.title}</strong>{r.desc}</div>
              </div>
              {r.priority && <div style={{ marginLeft: 12, flexShrink: 0 }}><PriorityBadge priority={r.priority} /></div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


// ============================================================
// HISTORY PAGE
// ============================================================
function HistoryPage({ history, onViewReport }) {
  return (
    <div>
      <h2 className="section-title">Upload History</h2>
      <p className="section-subtitle">All your previously analyzed datasets.</p>
      {history.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🕐</div>
          <h3>No History Yet</h3>
          <p>Your analyzed datasets will appear here.</p>
        </div>
      ) : (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Dataset</th><th>Date</th><th>Samples</th><th>Score</th><th>Risk</th><th>Action</th></tr>
              </thead>
              <tbody>
                {[...history].reverse().map((h, i) => (
                  <tr key={i}>
                    <td><strong>📄 {h.filename}</strong></td>
                    <td style={{ color: 'var(--text-muted)', fontSize: 13 }}>{h.date}</td>
                    <td>
                      {h.summary?.num_samples?.toLocaleString() || '—'}
                      {h.summary?.count_source === 'file' && <span style={{ fontSize: 10, color: 'var(--success)', marginLeft: 4 }}>✅</span>}
                    </td>
                    <td><span className={`badge ${(h.score||0) >= 75 ? 'badge-success' : (h.score||0) >= 50 ? 'badge-warning' : 'badge-danger'}`}>{h.score ?? '—'}/100</span></td>
                    <td><span className={`badge ${(h.score||0) >= 75 ? 'badge-success' : (h.score||0) >= 50 ? 'badge-warning' : 'badge-danger'}`}>{h.prediction || '—'}</span></td>
                    <td><button className="btn btn-ghost btn-sm" onClick={() => onViewReport(h)}>View Report</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// APP SHELL
// ============================================================
function AppShell() {
  const { user } = useApp();
  const [page, setPage] = useState(() => user ? 'dashboard' : 'landing');
  const [report, setReport] = useState(null);
  const [history, setHistory] = useState(() => {
    try { return JSON.parse(localStorage.getItem('dqa_history')) || []; } catch { return []; }
  });
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (!user && !['landing','login','signup'].includes(page)) setPage('landing');
    if (user  &&  ['landing','login','signup'].includes(page)) setPage('dashboard');
  }, [user]);

  const handleAnalyzed = useCallback((result) => {
    setReport(result);
    setHistory(prev => {
      const updated = [...prev, result];
      localStorage.setItem('dqa_history', JSON.stringify(updated));
      return updated;
    });
    setPage('reports');
  }, []);

  const handleViewReport = useCallback((r) => { setReport(r); setPage('reports'); }, []);

  const pageTitles = {
    dashboard: 'Dashboard', upload: 'Upload Dataset',
    reports: 'Analysis Report', history: 'History',
  };

  if (page === 'landing') return <LandingPage onNavigate={setPage} />;
  if (page === 'login')   return <AuthPage mode="login"  onNavigate={setPage} />;
  if (page === 'signup')  return <AuthPage mode="signup" onNavigate={setPage} />;

  return (
    <div className="app-layout">
      <Sidebar page={page} onNavigate={setPage} open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="main-content">
        <Topbar title={pageTitles[page] || 'DataQA'} onMenuClick={() => setSidebarOpen(s => !s)} />
        <main className="page-content">
          {page === 'dashboard' && <DashboardPage onNavigate={setPage} history={history} />}
          {page === 'upload'    && <UploadPage onAnalyzed={handleAnalyzed} />}
          {page === 'reports'   && <ReportPage report={report} />}
          {page === 'history'   && <HistoryPage history={history} onViewReport={handleViewReport} />}
        </main>
      </div>
    </div>
  );
}

function App() {
  return <AppProvider><AppShell /></AppProvider>;
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
