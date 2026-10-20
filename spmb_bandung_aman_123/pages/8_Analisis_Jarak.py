"""
pages/8_Analisis_Jarak.py
Menu Analisis Jarak Pendaftar (Admin only).

Menampilkan rentang (selisih) jarak min-max pendaftar tiap sekolah per
tahun ajaran, dipadukan dengan rasio aksesibilitas 2SFCA (kuota/pendaftar),
kategori cluster FCM (Tinggi/Sedang/Rendah, hasil rumus M ± 1 SD), dan
simulasi peluang diterima dari model Random Forest pada titik jarak_max.

Tujuan: membantu admin melihat sekolah mana yang rentang jarak
pendaftarnya sangat lebar (selisih besar) - biasanya karena kuota belum
penuh sehingga pendaftar yang rumahnya jauh pun ikut tercatat - sehingga
jarak_batas yang dipakai FCM/RF berpotensi kurang representatif.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from utils.ui_theme import apply_custom_theme
apply_custom_theme()
import pandas as pd
import plotly.express as px

from data.sekolah_data import SEKOLAH_NEGERI, SEKOLAH_DOMISILI_BATASAN
from utils.dataset_loader import (
    get_tahun_tersedia, get_tahun_punya_sheet_per_sekolah, format_tahun_ajaran,
    load_jarak_minmax_jalur, bersihkan_kolom_kosong,
)
from models.predict import get_df_sekolah_clustered, prediksi_peluang

if not st.session_state.get("logged_in") or st.session_state.get("user_role") != "admin":
    st.warning("⛔ Halaman ini hanya untuk Admin.")
    st.stop()

CLUSTER_TAMPIL = {"Tinggi": "Ketat", "Sedang": "Sedang", "Rendah": "Longgar"}
COLOR_MAP = {"Ketat": "#e74c3c", "Sedang": "#f1c40f", "Longgar": "#2ecc71"}

st.markdown("## 📏 Analisis Selisih Jarak Pendaftar")
st.caption(
    "Melihat rentang (selisih) jarak pendaftar terdekat-terjauh tiap sekolah, "
    "dipadukan dengan rasio aksesibilitas **2SFCA** (kuota÷pendaftar), kategori "
    "cluster **FCM** (rumus M ± 1 SD), dan simulasi peluang **Random Forest**."
)
st.divider()

df_cluster = get_df_sekolah_clustered()
if df_cluster is None:
    st.error("Model belum ditraining. Jalankan: `python models/train_models.py`")
    st.stop()

TAHUN_TERSEDIA = get_tahun_tersedia()
TAHUN_PUNYA_SHEET = get_tahun_punya_sheet_per_sekolah()
tahun_pilih = st.selectbox(
    "📅 Tahun Ajaran", TAHUN_TERSEDIA,
    format_func=format_tahun_ajaran, index=len(TAHUN_TERSEDIA) - 1, key="jarak_tahun_pilih",
)
if tahun_pilih not in TAHUN_PUNYA_SHEET:
    st.info(
        "ℹ️ Tahun ini hanya punya data ringkasan (bukan data per-siswa), jadi "
        "jarak min/max Jalur Domisili Batasan tidak tersedia rinciannya."
    )

with st.spinner("Menghitung selisih jarak..."):
    df_jarak = load_jarak_minmax_jalur(tahun_pilih, tuple(SEKOLAH_DOMISILI_BATASAN))

if df_jarak.empty:
    st.warning("Data jarak pendaftar tidak tersedia untuk tahun ini.")
    st.stop()

df_jarak = df_jarak[df_jarak["jalur"] == "Domisili"].copy()
df_jarak["selisih"] = df_jarak["jarak_max"] - df_jarak["jarak_min"]

# ── Gabungkan dengan rasio 2SFCA & kategori cluster FCM ─────────────────────
df_gabung = df_jarak.merge(
    df_cluster[["nama", "rasio_pendaftar", "cluster_label", "jarak_batas_km"]],
    on="nama", how="left",
)
df_gabung["cluster_label"] = df_gabung["cluster_label"].fillna("Sedang")
df_gabung["cluster_tampil"] = df_gabung["cluster_label"].map(CLUSTER_TAMPIL)
df_gabung["jarak_batas_model_m"] = df_gabung["jarak_batas_km"] * 1000

# ── Simulasi peluang RF pada titik jarak_max (ekor terjauh pendaftar) ───────
def _simulasi_prob(row):
    if pd.isna(row["jarak_max"]):
        return None
    hasil = prediksi_peluang(float(row["jarak_max"]), True, row["nama"])
    return hasil.get("prob_diterima") if "error" not in hasil else None

df_gabung["prob_di_jarak_max"] = df_gabung.apply(_simulasi_prob, axis=1)

# ── Tandai sekolah dengan rentang jarak sangat lebar (outlier) ──────────────
M_selisih = df_gabung["selisih"].mean()
SD_selisih = df_gabung["selisih"].std(ddof=0)
batas_outlier = M_selisih + SD_selisih
df_gabung["rentang_lebar"] = df_gabung["selisih"] > batas_outlier

st.divider()

# ── Ringkasan metrik ─────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Rata-rata Selisih Jarak", f"{M_selisih:,.0f} m")
c2.metric("Selisih Terbesar", f"{df_gabung['selisih'].max():,.0f} m")
c3.metric("Selisih Terkecil", f"{df_gabung['selisih'].min():,.0f} m")
c4.metric("Sekolah Rentang Lebar", int(df_gabung["rentang_lebar"].sum()))

st.caption(
    "ℹ️ **Rentang Lebar** = selisih jarak sekolah tersebut melebihi rata-rata "
    "+ 1 standar deviasi selisih seluruh sekolah. Biasanya terjadi pada sekolah "
    "yang kuotanya belum penuh (pendaftar < kuota), sehingga pendaftar yang "
    "rumahnya sangat jauh pun tetap tercatat — membuat radius sekolah terlihat "
    "lebih lebar dari kondisi kompetisi yang sebenarnya."
)

st.divider()

# ── Chart selisih per sekolah, diwarnai kategori cluster ────────────────────
st.subheader("📊 Selisih Jarak per Sekolah")
df_chart = df_gabung.sort_values("selisih", ascending=False).head(25)
fig = px.bar(
    df_chart, x="nama", y="selisih", color="cluster_tampil",
    color_discrete_map=COLOR_MAP,
    labels={"nama": "Sekolah", "selisih": "Selisih Jarak Min-Max (m)",
            "cluster_tampil": "Kategori Cluster"},
    title=f"25 Sekolah dengan Selisih Jarak Terbesar ({format_tahun_ajaran(tahun_pilih)})",
)
fig.update_layout(xaxis_tickangle=-45, height=450)
fig.add_hline(y=batas_outlier, line_dash="dash", line_color="gray",
              annotation_text="Batas Rentang Lebar (M + 1 SD)")
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Tabel lengkap ─────────────────────────────────────────────────────────
st.subheader("📋 Tabel Selisih Jarak, Rasio 2SFCA, Cluster & Simulasi RF")
st.caption(
    "ℹ️ **Kategori Cluster** dikategorikan pakai rumus **M ± 1 SD** atas rasio "
    "aksesibilitas 2SFCA (kuota÷pendaftar) yang di-log-transform, dihitung "
    "langsung per sekolah. **Peluang di Jarak "
    "Max (RF)** adalah simulasi peluang diterima model Random Forest bila ada "
    "pendaftar tepat di jarak_max tersebut — dipakai untuk melihat apakah "
    "ekor jarak terjauh itu masih realistis diterima atau sudah di luar wajar."
)

df_tabel = df_gabung.sort_values("selisih", ascending=False)[[
    "nama", "zona", "cluster_tampil", "rasio_pendaftar", "jumlah",
    "jarak_min", "jarak_max", "selisih", "jarak_batas_model_m",
    "prob_di_jarak_max", "rentang_lebar",
]].copy()
df_tabel["rentang_lebar"] = df_tabel["rentang_lebar"].map({True: "⚠️ Lebar", False: "Normal"})
df_tabel.columns = [
    "Nama Sekolah", "Zona", "Kategori Cluster", "Rasio 2SFCA", "Jumlah Pendaftar",
    "Jarak Min (m)", "Jarak Max (m)", "Selisih (m)", "Jarak Batas Model (m)",
    "Peluang di Jarak Max (RF, %)", "Status Rentang",
]

st.dataframe(
    bersihkan_kolom_kosong(df_tabel), use_container_width=True, hide_index=True,
    column_config={
        "Rasio 2SFCA": st.column_config.NumberColumn(format="%.3f"),
        "Jarak Min (m)": st.column_config.NumberColumn(format="%.1f"),
        "Jarak Max (m)": st.column_config.NumberColumn(format="%.1f"),
        "Selisih (m)": st.column_config.NumberColumn(format="%.1f"),
        "Jarak Batas Model (m)": st.column_config.NumberColumn(format="%.1f"),
        "Peluang di Jarak Max (RF, %)": st.column_config.ProgressColumn(
            min_value=0, max_value=100, format="%.1f%%"),
    },
)

st.download_button(
    "⬇️ Unduh CSV",
    df_tabel.to_csv(index=False).encode("utf-8"),
    file_name=f"selisih_jarak_{tahun_pilih}.csv",
    mime="text/csv",
)
