"""
utils/ui_theme.py
Lapisan tampilan (CSS) bersama untuk seluruh halaman SPMB Bandung.

PENTING: modul ini murni kosmetik (warna, spacing, bentuk komponen).
Tidak ada perubahan logika/alur data apa pun di sini — hanya styling
lewat CSS yang disuntikkan via st.markdown(..., unsafe_allow_html=True).
"""

import streamlit as st

_CUSTOM_CSS = """
<style>
:root{
  --spmb-primary:#3f51b5;
  --spmb-primary-dark:#1a237e;
  --spmb-primary-light:#e8eaf6;
  --spmb-accent:#00acc1;
  --spmb-success:#2e7d32;
  --spmb-warning:#ef6c00;
  --spmb-danger:#c62828;
  --spmb-text:#1c1e2b;
  --spmb-muted:#6b7099;
  --spmb-card-bg:#ffffff;
  --spmb-radius:14px;
}

/* ── Layout dasar ─────────────────────────────────────────────────────── */
.block-container{
  padding-top:2rem;
  padding-bottom:3rem;
  max-width:1200px;
}
html, body, [class*="css"]{
  font-family:"Segoe UI","Inter",system-ui,-apple-system,sans-serif;
}

/* ── Sidebar ──────────────────────────────────────────────────────────── */
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#eaf4fd 0%,#d3e9fb 100%);
}
[data-testid="stSidebar"] *{
  color:var(--spmb-primary-dark) !important;
}
[data-testid="stSidebar"] hr{ border-color:rgba(26,35,126,0.15); }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{ opacity:0.95; }

/* Nav links di sidebar (halaman multipage) */
[data-testid="stSidebarNav"] a{
  border-radius:10px;
  margin:2px 8px;
  transition:background .15s ease;
}
[data-testid="stSidebarNav"] a:hover{
  background:rgba(26,35,126,0.10);
}
[data-testid="stSidebarNav"] a[aria-current="page"]{
  background:rgba(26,35,126,0.16);
  font-weight:600;
}

/* Tombol di sidebar (mis. Logout) — pastikan tulisan tetap terlihat jelas */
[data-testid="stSidebar"] .stButton>button{
  background:var(--spmb-primary-dark) !important;
  color:#ffffff !important;
  border:1px solid var(--spmb-primary-dark) !important;
}
[data-testid="stSidebar"] .stButton>button:hover{
  background:var(--spmb-primary) !important;
  color:#ffffff !important;
}
[data-testid="stSidebar"] .stButton>button *{
  color:#ffffff !important;
}

/* ── Judul & teks ─────────────────────────────────────────────────────── */
h1, h2, h3{ color:var(--spmb-primary-dark); letter-spacing:-0.01em; }
.main-header{ font-size:2rem; font-weight:800; color:var(--spmb-primary-dark); }
.sub-header{ font-size:1rem; color:var(--spmb-muted); margin-bottom:1.5rem; }

/* ── Tombol ───────────────────────────────────────────────────────────── */
.stButton>button, .stDownloadButton>button, .stFormSubmitButton>button{
  border-radius:10px;
  font-weight:600;
  padding:0.5rem 1.1rem;
  transition:all .15s ease;
  border:1px solid rgba(63,81,181,0.25);
}
.stButton>button:hover, .stDownloadButton>button:hover, .stFormSubmitButton>button:hover{
  transform:translateY(-1px);
  box-shadow:0 4px 10px rgba(63,81,181,0.18);
}
button[kind="primary"]{
  background:var(--spmb-primary) !important;
  border-color:var(--spmb-primary) !important;
}

/* ── Metric cards ─────────────────────────────────────────────────────── */
[data-testid="stMetric"]{
  background:var(--spmb-card-bg);
  border:1px solid #e6e8f5;
  border-radius:var(--spmb-radius);
  padding:14px 16px 10px 16px;
  box-shadow:0 1px 3px rgba(26,35,126,0.06);
}
[data-testid="stMetricLabel"]{ color:var(--spmb-muted); font-weight:600; }
[data-testid="stMetricValue"]{ color:var(--spmb-primary-dark); }

/* ── Tabs (dibuat seperti pill, biar tidak terasa numpuk) ───────────────── */
.stTabs [data-baseweb="tab-list"]{
  gap:6px;
  border-bottom:2px solid #e6e8f5;
}
.stTabs [data-baseweb="tab"]{
  border-radius:10px 10px 0 0;
  padding:8px 18px;
  background:var(--spmb-primary-light);
  font-weight:600;
  color:var(--spmb-primary-dark);
}
.stTabs [aria-selected="true"]{
  background:var(--spmb-primary) !important;
  color:#fff !important;
}

/* ── Expander & alert boxes ──────────────────────────────────────────── */
[data-testid="stExpander"]{
  border-radius:var(--spmb-radius);
  border:1px solid #e6e8f5;
}
div[data-testid="stAlert"]{
  border-radius:12px;
}

/* ── Dataframe / tabel ───────────────────────────────────────────────── */
[data-testid="stDataFrame"]{
  border-radius:12px;
  overflow:hidden;
  border:1px solid #e6e8f5;
}

/* ── Form container ─────────────────────────────────────────────────── */
div[data-testid="stForm"]{
  background:var(--spmb-card-bg);
  border:1px solid #e6e8f5;
  border-radius:var(--spmb-radius);
  padding:1.2rem 1.4rem;
  box-shadow:0 1px 3px rgba(26,35,126,0.05);
}

/* ── Divider lebih halus ────────────────────────────────────────────── */
hr{ margin:1.1rem 0; opacity:0.35; }

/* ── Selectbox / input rounded ───────────────────────────────────────── */
div[data-baseweb="select"]>div, .stTextInput input, .stNumberInput input{
  border-radius:10px !important;
}
</style>
"""


def apply_custom_theme() -> None:
    """Suntikkan CSS tampilan bersama ke halaman saat ini.

    Panggil sekali di bagian atas tiap halaman, setelah import.
    Tidak mengubah state, data, maupun alur logika apa pun.
    """
    st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)
