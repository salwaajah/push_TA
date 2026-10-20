"""
pages/1_Dashboard_Admin.py
Dashboard visualisasi untuk Admin:
 - Statistik agregat
 - Bar chart persebaran pendaftar vs kuota
 - Pie chart distribusi cluster FCM
 - Random Forest: feature importance & simulasi prediksi
 - Peta sebaran sekolah berdasarkan cluster
 - Cek wilayah cakupan sekolah (reverse geocoding OSM)
"""

import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from utils.ui_theme import apply_custom_theme
apply_custom_theme()
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from streamlit_folium import st_folium

import numpy as np
from data.sekolah_data import SEKOLAH_NEGERI, SEKOLAH_DOMISILI_BATASAN
from models.predict import get_df_sekolah_clustered, load_models, prediksi_peluang
from models.train_models import train_fcm, generate_training_data
from utils.map_utils import buat_peta_admin, fix_map_tab_render
from utils.zona import ZONA_INFO
from utils.dataset_loader import (
    get_tahun_tersedia, format_tahun_ajaran, load_ringkasan_sekolah, bersihkan_kolom_kosong,
    load_jarak_minmax_jalur,
)

# Keterangan tampilan cluster keketatan (nilai internal cluster_label tetap
# "Tinggi"/"Sedang"/"Rendah" dari hasil training FCM; ini hanya label yang
# ditampilkan ke pengguna).
CLUSTER_TAMPIL = {"Tinggi": "Ketat", "Sedang": "Sedang", "Rendah": "Longgar"}

if not st.session_state.get("logged_in") or st.session_state.get("user_role") != "admin":
    st.warning("⛔ Halaman ini hanya untuk Admin.")
    st.stop()

st.markdown("## 📊 Dashboard Admin – SPMB Kota Bandung")
st.divider()

# ── Load data ─────────────────────────────────────────────────────────────────
df_cluster = get_df_sekolah_clustered()

df_static = pd.DataFrame(SEKOLAH_NEGERI)
if df_cluster is not None:
    df_all = df_static.merge(
        df_cluster[["nama", "cluster_label", "rasio_pendaftar", "membership_max"]],
        left_on="nama", right_on="nama", how="left"
    )
    df_all["cluster_label"] = df_all["cluster_label"].fillna("Sedang")
else:
    df_all = df_static.copy()
    df_all["cluster_label"] = "Sedang"
    df_all["rasio_pendaftar"] = df_all["kuota"] / df_all["pendaftar"]


def hitung_cluster_per_tahun(df_all: "pd.DataFrame", tahun: int) -> "pd.DataFrame":
    """Perbarui kuota/pendaftar/rasio SEKALIGUS cluster keketatan (FCM) supaya
    menyesuaikan data tahun ajaran yang difilter (bukan lagi cluster tetap
    hasil rata-rata multi-tahun)."""
    df_hasil = df_all.copy()
    df_ringkasan_tahun = load_ringkasan_sekolah(tahun)
    if not df_ringkasan_tahun.empty:
        df_ringkasan_tahun = df_ringkasan_tahun.copy()
        df_ringkasan_tahun["kuota_tahun"] = (
            df_ringkasan_tahun["kuota_dalam"].fillna(0) + df_ringkasan_tahun["kuota_luar"].fillna(0)
        )
        df_ringkasan_tahun["pendaftar_tahun"] = (
            df_ringkasan_tahun["pendaftar_dalam"].fillna(0) + df_ringkasan_tahun["pendaftar_luar"].fillna(0)
        )
        # Nama sekolah pada ringkasan per-tahun tidak selalu identik dengan data
        # statis (beda kapitalisasi/akhiran, mis. "SMP NEGERI 1 - DOMISILI" vs
        # "SMP Negeri 1"), sehingga dicocokkan lewat nomor sekolah supaya data
        # kuota/pendaftar tahun yang dipilih benar-benar terpakai (bukan selalu
        # jatuh ke nilai statis akibat merge nama yang gagal).
        df_hasil["_nomor_sekolah"] = df_hasil["nama"].str.extract(r"(\d+)")[0].astype(float)
        df_ringkasan_tahun["_nomor_sekolah"] = df_ringkasan_tahun["nama"].str.extract(r"(\d+)")[0].astype(float)
        df_hasil = df_hasil.merge(
            df_ringkasan_tahun[["_nomor_sekolah", "kuota_tahun", "pendaftar_tahun"]],
            on="_nomor_sekolah", how="left"
        ).drop(columns=["_nomor_sekolah"])
        df_hasil["kuota"] = df_hasil["kuota_tahun"].fillna(df_hasil["kuota"])
        df_hasil["pendaftar"] = df_hasil["pendaftar_tahun"].fillna(df_hasil["pendaftar"])
        # rasio_pendaftar = rasio aksesibilitas 2SFCA (Rj = Sj/Pk = kuota/pendaftar).
        df_hasil["rasio_pendaftar"] = df_hasil.apply(
            lambda r: (r["kuota"] / r["pendaftar"]) if r["pendaftar"] else r["rasio_pendaftar"], axis=1
        )
        try:
            df_fitur_tahun = pd.DataFrame({
                "rasio_pendaftar": df_hasil["rasio_pendaftar"],
                "jarak_batas_km": df_hasil["jarak_batas"] / 1000,
                "utilitas_kuota": df_hasil.apply(
                    lambda r: max(0.0, 1 - r["kuota"] / max(r["pendaftar"], 1)), axis=1
                ),
            })
            # Standarisasi (z-score) tiap fitur supaya skala jarak_batas_km (ratusan-
            # ribuan meter, tetap/statis tiap sekolah) tidak mendominasi rasio_pendaftar
            # (yang berubah tiap tahun) saat clustering -> cluster jadi benar-benar
            # menyesuaikan rasio aksesibilitas 2SFCA tahun yang difilter.
            # rasio_pendaftar_asli disimpan SEBELUM di-z-score, karena kategorisasi
            # M±1SD di train_fcm() butuh rasio mentah (>0) untuk di-log-transform.
            df_fitur_tahun["rasio_pendaftar_asli"] = df_fitur_tahun["rasio_pendaftar"]
            for kolom in ["rasio_pendaftar", "jarak_batas_km", "utilitas_kuota"]:
                std = df_fitur_tahun[kolom].std()
                df_fitur_tahun[kolom] = (df_fitur_tahun[kolom] - df_fitur_tahun[kolom].mean()) / std if std else 0.0
            _, _, _, df_fcm_tahun = train_fcm(
                df_fitur_tahun, n_clusters=3, kolom_rasio_asli="rasio_pendaftar_asli"
            )
            df_hasil["cluster_label"] = df_fcm_tahun["cluster_label"].values
        except Exception:
            pass  # gagal recompute FCM utk tahun ini (mis. data kurang) -> pertahankan cluster lama
    return df_hasil

# ── Tab visualisasi ───────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(
    ["📈 Pendaftar vs Kuota", "🔵 Cluster FCM", "🌳 Random Forest",
     "🗺️ Peta Sebaran"]
)

# ════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Perbandingan Pendaftar vs Kuota per Sekolah")
    zona_filter = st.multiselect("Filter Zona:", ["A", "B", "C", "D"],
                                  default=["A", "B", "C", "D"], key="zona_bar")

    ZONA_URUTAN = {"A": 0, "B": 1, "C": 2, "D": 3}
    ZONA_WARNA_GARIS = {"A": "#3498db", "B": "#2ecc71", "C": "#f1c40f", "D": "#e74c3c"}

    df_f = df_all[df_all["zona"].isin(zona_filter)].copy()
    df_f["_urut_zona"] = df_f["zona"].map(ZONA_URUTAN)
    # rasio_pendaftar = rasio aksesibilitas 2SFCA (kuota/pendaftar): makin
    # kecil makin ketat, jadi diurutkan ascending supaya sekolah paling ketat
    # tampil duluan tiap zona.
    df_f = df_f.sort_values(["_urut_zona", "rasio_pendaftar"], ascending=[True, True])

    fig = go.Figure()
    fig.add_bar(name="Kuota",     x=df_f["nama"], y=df_f["kuota"],
                marker_color="#3f51b5", opacity=0.8)
    fig.add_bar(name="Pendaftar", x=df_f["nama"], y=df_f["pendaftar"],
                marker_color="#f44336", opacity=0.7)

    # ── Garis pembanding antar Zona A/B/C/D ─────────────────────────────
    posisi = 0
    for zona in ["A", "B", "C", "D"]:
        jumlah_zona = int((df_f["zona"] == zona).sum())
        if jumlah_zona == 0:
            continue
        if posisi > 0:
            fig.add_vline(x=posisi - 0.5, line_width=1.5, line_dash="dash",
                          line_color="#555555", opacity=0.7)
        fig.add_annotation(x=posisi + jumlah_zona / 2 - 0.5, y=1.1, yref="paper",
                           showarrow=False, text=f"<b>Zona {zona}</b>",
                           font=dict(size=12, color=ZONA_WARNA_GARIS.get(zona, "#333")))
        posisi += jumlah_zona

    fig.update_layout(barmode="group", height=480,
                      xaxis_tickangle=-45, xaxis_tickfont_size=9,
                      legend=dict(orientation="h", y=1.05),
                      margin=dict(t=60, b=160))
    st.plotly_chart(fig, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Distribusi Cluster Keketatan Sekolah (Fuzzy C-Means)")
    st.caption(
        "ℹ️ **Rasio** yang dipakai adalah rasio aksesibilitas **2SFCA** "
        "(Luo & Wang), Rj = Sj/Pk = **kuota ÷ pendaftar** — semakin **besar** "
        "nilainya semakin **longgar**, semakin **kecil** semakin **ketat**. "
        "Label kategori **Tinggi/Sedang/Rendah** tiap sekolah diperoleh dari "
        "**rumus kategorisasi M ± 1 SD**, diterapkan pada rasio yang sudah "
        "di-**log-transform** (supaya distribusi rasio yang condong/skewed "
        "tidak membuat kategori Tinggi/Ketat mustahil muncul), dengan arah "
        "threshold disesuaikan arah rasio ini: log(Rj) < M−1SD → *Tinggi* "
        "(ketat), M−1SD s/d M+1SD → *Sedang*, log(Rj) ≥ M+1SD → *Rendah* "
        "(longgar) — (M = rata-rata, SD = standar deviasi log-rasio 2SFCA "
        "seluruh sekolah), dihitung langsung per sekolah (bukan rata-rata "
        "cluster) supaya nilai ekstrem tiap sekolah tetap terlihat."
    )

    TAHUN_TERSEDIA_CLUSTER = get_tahun_tersedia()
    tahun_cluster = st.selectbox(
        "📅 Filter Tahun Ajaran", TAHUN_TERSEDIA_CLUSTER,
        index=len(TAHUN_TERSEDIA_CLUSTER) - 1,
        format_func=format_tahun_ajaran, key="cluster_fcm_tahun",
    )

    # Kuota/Pendaftar/Rasio DAN label cluster keketatan (FCM) dihitung ulang
    # sesuai tahun ajaran yang dipilih, supaya cluster ikut menyesuaikan data
    # pendaftar/kuota tahun tersebut.
    df_all_tab2 = hitung_cluster_per_tahun(df_all, tahun_cluster)

    df_all_tab2["cluster_tampil"] = df_all_tab2["cluster_label"].map(CLUSTER_TAMPIL).fillna(df_all_tab2["cluster_label"])

    c1, c2 = st.columns([1, 1])
    color_map = {"Ketat": "#e74c3c", "Sedang": "#f1c40f", "Longgar": "#2ecc71"}
    with c1:
        pie_data = df_all_tab2["cluster_tampil"].value_counts().reset_index()
        pie_data.columns = ["Cluster", "Jumlah"]
        fig_pie = px.pie(pie_data, names="Cluster", values="Jumlah",
                         color="Cluster", color_discrete_map=color_map,
                         title=f"Proporsi Cluster Keketatan – Tahun {format_tahun_ajaran(tahun_cluster)}")
        st.plotly_chart(fig_pie, use_container_width=True)

    with c2:
        fig_box = px.box(df_all_tab2, x="cluster_tampil", y="rasio_pendaftar",
                         color="cluster_tampil", color_discrete_map=color_map,
                         title=f"Sebaran Rasio Aksesibilitas 2SFCA per Cluster – Tahun {format_tahun_ajaran(tahun_cluster)}",
                         labels={"rasio_pendaftar": "Rasio Aksesibilitas 2SFCA (Kuota/Pendaftar)",
                                 "cluster_tampil": "Cluster"})
        st.plotly_chart(fig_box, use_container_width=True)

    st.divider()

    # ── Statistik Cluster per Zona ───────────────────────────────────────────
    st.subheader("📊 Statistik Cluster per Zona")
    st.caption(
        "Menampilkan bagaimana distribusi kategori Tinggi/Sedang/Rendah dan "
        "rata-rata rasio aksesibilitas 2SFCA (kuota/pendaftar) berbeda-beda "
        "di tiap Zona A/B/C/D, sebagai insight tambahan di luar distribusi "
        "cluster secara keseluruhan."
    )

    zc1, zc2 = st.columns([1.3, 1])
    with zc1:
        crosstab_zona = pd.crosstab(df_all_tab2["zona"], df_all_tab2["cluster_tampil"])
        for kolom in ["Ketat", "Sedang", "Longgar"]:
            if kolom not in crosstab_zona.columns:
                crosstab_zona[kolom] = 0
        crosstab_zona = crosstab_zona[["Ketat", "Sedang", "Longgar"]].reindex(
            ["A", "B", "C", "D"]
        ).fillna(0).astype(int)

        fig_zona_stack = go.Figure()
        for kolom in ["Ketat", "Sedang", "Longgar"]:
            fig_zona_stack.add_bar(
                name=kolom, x=crosstab_zona.index, y=crosstab_zona[kolom],
                marker_color=color_map[kolom]
            )
        fig_zona_stack.update_layout(
            barmode="stack", height=380,
            title=f"Jumlah Sekolah per Cluster – Tiap Zona ({format_tahun_ajaran(tahun_cluster)})",
            xaxis_title="Zona", yaxis_title="Jumlah Sekolah",
            legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig_zona_stack, use_container_width=True)

    with zc2:
        ringkasan_zona = df_all_tab2.groupby("zona").agg(
            Jumlah_Sekolah=("nama", "count"),
            Rata2_Rasio=("rasio_pendaftar", "mean"),
            Rata2_Jarak_Batas_m=("jarak_batas", "mean"),
        ).reindex(["A", "B", "C", "D"]).reset_index()
        ringkasan_zona.columns = ["Zona", "Jumlah Sekolah", "Rata-rata Rasio 2SFCA",
                                  "Rata-rata Jarak Batas (m)"]
        ringkasan_zona["Rata-rata Rasio 2SFCA"] = ringkasan_zona["Rata-rata Rasio 2SFCA"].round(2)
        ringkasan_zona["Rata-rata Jarak Batas (m)"] = ringkasan_zona["Rata-rata Jarak Batas (m)"].round(0)
        st.markdown("**Ringkasan per Zona**")
        st.dataframe(ringkasan_zona, use_container_width=True, hide_index=True)
        # Rasio 2SFCA besar = longgar, kecil = ketat -> zona paling ketat
        # adalah yang rata-rata rasionya PALING KECIL.
        zona_paling_ketat = ringkasan_zona.loc[ringkasan_zona["Rata-rata Rasio 2SFCA"].idxmin(), "Zona"]
        zona_paling_longgar = ringkasan_zona.loc[ringkasan_zona["Rata-rata Rasio 2SFCA"].idxmax(), "Zona"]
        st.caption(
            f"🔴 Zona dengan persaingan rata-rata tertinggi: **Zona {zona_paling_ketat}**. "
            f"🟢 Zona dengan persaingan rata-rata terendah: **Zona {zona_paling_longgar}**."
        )

    # ── Interpretasi naratif per Zona ────────────────────────────────────────
    st.markdown("**📝 Interpretasi tiap Zona**")
    for zona in ["A", "B", "C", "D"]:
        if zona not in crosstab_zona.index or int(crosstab_zona.loc[zona].sum()) == 0:
            continue
        jumlah_total = int(crosstab_zona.loc[zona].sum())
        n_ketat = int(crosstab_zona.loc[zona, "Ketat"])
        n_sedang = int(crosstab_zona.loc[zona, "Sedang"])
        n_longgar = int(crosstab_zona.loc[zona, "Longgar"])
        pct_ketat = n_ketat / jumlah_total * 100
        pct_sedang = n_sedang / jumlah_total * 100
        pct_longgar = n_longgar / jumlah_total * 100

        baris_zona = ringkasan_zona.loc[ringkasan_zona["Zona"] == zona]
        rata_rasio = float(baris_zona["Rata-rata Rasio 2SFCA"].values[0]) if not baris_zona.empty else None

        dominan = max(
            [("Ketat", n_ketat), ("Sedang", n_sedang), ("Longgar", n_longgar)],
            key=lambda x: x[1],
        )[0]
        narasi_dominan = {
            "Ketat": (
                "mayoritas sekolah berkompetisi **tinggi** — daya tampung relatif sempit "
                "dibanding jumlah pendaftar, sehingga calon peserta didik di zona ini "
                "perlu lebih memperhatikan jarak rumah ke sekolah karena persaingan "
                "cenderung ketat."
            ),
            "Sedang": (
                "mayoritas sekolah berada pada tingkat persaingan **sedang** — daya "
                "tampung dan jumlah pendaftar relatif seimbang."
            ),
            "Longgar": (
                "mayoritas sekolah relatif **longgar** — daya tampung cukup lega "
                "dibanding jumlah pendaftar, sehingga peluang diterima secara umum "
                "lebih tinggi dibanding zona lain."
            ),
        }[dominan]

        info_zona = ZONA_INFO.get(zona, {})
        label_zona = info_zona.get("label", f"Zona {zona}")
        kecamatan_zona = ", ".join(info_zona.get("kecamatan", []))
        badge = {"Ketat": "🔴", "Sedang": "🟡", "Longgar": "🟢"}[dominan]

        with st.expander(f"{badge} {label_zona} — {jumlah_total} sekolah, dominan {dominan}"):
            st.markdown(
                f"**Cakupan kecamatan:** {kecamatan_zona if kecamatan_zona else '-'}\n\n"
                f"Dari **{jumlah_total} sekolah negeri** di zona ini: "
                f"**{n_ketat} Ketat** ({pct_ketat:.0f}%), "
                f"**{n_sedang} Sedang** ({pct_sedang:.0f}%), "
                f"**{n_longgar} Longgar** ({pct_longgar:.0f}%)"
                + (f", dengan rata-rata rasio aksesibilitas 2SFCA **{rata_rasio:.2f}**." if rata_rasio is not None else ".")
                + f"\n\nSecara umum, {narasi_dominan}"
            )

            # ── Tabel Kecamatan & Sekolah per Zona ───────────────────────
            df_zona_sekolah = df_all_tab2[df_all_tab2["zona"] == zona].copy()
            df_zona_sekolah["Kecamatan"] = df_zona_sekolah["alamat"].str.extract(
                r"Kec\.\s*(.+)$", flags=re.IGNORECASE
            )[0].fillna("-")
            df_zona_sekolah["cluster_tampil_sekolah"] = df_zona_sekolah["cluster_label"].map(
                CLUSTER_TAMPIL
            ).fillna(df_zona_sekolah["cluster_label"])

            df_zona_tabel = df_zona_sekolah[[
                "nama", "Kecamatan", "cluster_tampil_sekolah",
                "kuota", "pendaftar", "rasio_pendaftar",
            ]].rename(columns={
                "nama": "Nama Sekolah",
                "cluster_tampil_sekolah": "Cluster",
                "kuota": "Kuota",
                "pendaftar": "Pendaftar",
                "rasio_pendaftar": "Rasio 2SFCA",
            }).sort_values("Rasio 2SFCA", ascending=True)
            df_zona_tabel["Rasio 2SFCA"] = df_zona_tabel["Rasio 2SFCA"].round(4)

            st.dataframe(df_zona_tabel, use_container_width=True, hide_index=True)

    st.subheader("Daftar Sekolah per Cluster")
    st.caption("Diurutkan dari rasio 2SFCA paling kecil (paling ketat) ke paling besar (paling longgar).")

    # ── Jarak Min/Max riil per sekolah, sesuai data pendaftar tahun yang
    # difilter (bukan angka statis) — jalur Domisili (zonasi umum). Dicocokkan
    # lewat nomor sekolah (bukan nama persis) karena penamaan sekolah pada
    # berkas sumber tahun 2022/2024 memakai huruf besar semua ("SMP NEGERI 1")
    # sedangkan tahun 2025/2026 dst. memakai "SMP Negeri 1".
    df_jarak_riil = load_jarak_minmax_jalur(tahun_cluster, tuple(SEKOLAH_DOMISILI_BATASAN))
    if not df_jarak_riil.empty:
        df_jarak_riil = df_jarak_riil[df_jarak_riil["jalur"] == "Domisili"][
            ["nama", "jarak_min", "jarak_max"]
        ].copy()
        df_jarak_riil["selisih"] = df_jarak_riil["jarak_max"] - df_jarak_riil["jarak_min"]
        df_jarak_riil["_nomor_sekolah"] = df_jarak_riil["nama"].str.extract(r"(\d+)")[0].astype(float)
        df_jarak_riil = df_jarak_riil.drop(columns=["nama"])

    for cluster in ["Tinggi", "Sedang", "Rendah"]:
        badge_color = {"Tinggi": "🔴", "Sedang": "🟡", "Rendah": "🟢"}[cluster]
        label_cluster = CLUSTER_TAMPIL[cluster]
        with st.expander(f"{badge_color} Cluster {label_cluster} – {len(df_all_tab2[df_all_tab2.cluster_label==cluster])} Sekolah"):
            df_cluster_raw = df_all_tab2[df_all_tab2["cluster_label"] == cluster].copy()
            df_cluster_raw["_nomor_sekolah"] = df_cluster_raw["nama"].str.extract(r"(\d+)")[0].astype(float)

            cols_show = ["nama", "zona", "kuota", "pendaftar", "rasio_pendaftar", "_nomor_sekolah"]
            df_cluster_tampil = df_cluster_raw[cols_show].rename(columns={
                "nama": "Nama Sekolah", "zona": "Zona",
                "kuota": "Kuota", "pendaftar": "Pendaftar",
                "rasio_pendaftar": "Rasio 2SFCA",
            }).sort_values("Rasio 2SFCA", ascending=True)

            # ── Kolom Jarak Min, Max, dan Selisih per Sekolah (data riil
            # pendaftar tahun yang dipilih, bukan angka statis) ───────────
            if not df_jarak_riil.empty:
                df_cluster_tampil = df_cluster_tampil.merge(
                    df_jarak_riil.rename(columns={
                        "jarak_min": "Jarak Min (m)",
                        "jarak_max": "Jarak Max (m)", "selisih": "Selisih Min-Max (m)",
                    }),
                    on="_nomor_sekolah", how="left",
                )
                for kolom in ["Jarak Min (m)", "Jarak Max (m)", "Selisih Min-Max (m)"]:
                    df_cluster_tampil[kolom] = df_cluster_tampil[kolom].round(2)
            else:
                df_cluster_tampil["Jarak Min (m)"] = None
                df_cluster_tampil["Jarak Max (m)"] = None
                df_cluster_tampil["Selisih Min-Max (m)"] = None

            df_cluster_tampil = df_cluster_tampil.drop(columns=["_nomor_sekolah"])

            st.dataframe(
                bersihkan_kolom_kosong(df_cluster_tampil),
                use_container_width=True, hide_index=True
            )

# ════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("🌳 Prediksi Random Forest – Peluang Penerimaan")
    st.caption("Simulasi peluang diterima berdasarkan jarak rumah ke sekolah, untuk setiap sekolah negeri.")

    fcm_art, rf_art = load_models()

    if rf_art is None:
        st.warning("⚠️ Model RF belum ditraining. Jalankan `python models/train_models.py`")
    else:
        rf_model = rf_art["model"]

        # ── Feature Importance ──────────────────────────────────────────────
        st.markdown("#### 📊 Feature Importance")
        feature_names_label = {
            "jarak_m": "Jarak Rumah-Sekolah",
            "dalam_zona": "Status Dalam Zona",
            "rasio_pendaftar": "Rasio Aksesibilitas 2SFCA (Kuota/Pendaftar)",
            "cluster_enc": "Cluster Keketatan (FCM)",
        }
        importances = rf_model.feature_importances_
        feat_df = pd.DataFrame({
            "Fitur": [feature_names_label.get(f, f) for f in rf_art["feature_names"]],
            "Importance": importances
        }).sort_values("Importance", ascending=True)

        fig_imp = px.bar(feat_df, x="Importance", y="Fitur", orientation="h",
                        title="Kontribusi Fitur dalam Prediksi Random Forest",
                        color="Importance", color_continuous_scale="Blues")
        fig_imp.update_layout(height=280)
        st.plotly_chart(fig_imp, use_container_width=True)

        st.divider()

        # ── Simulasi Prediksi per Sekolah ────────────────────────────────────
        st.markdown("#### 🎯 Simulasi Peluang Diterima per Jarak")
        st.caption("Pilih sekolah dan jarak untuk melihat prediksi peluang diterima dari model RF.")
        st.caption(
            "ℹ️ **Cluster Keketatan** yang tampil di bawah adalah kategori "
            "Tinggi/Sedang/Rendah hasil rumus kategorisasi **M ± 1 SD** "
            "(lihat tab 🔵 Cluster FCM untuk detail rumusnya)."
        )

        col_sel, col_jarak = st.columns([2, 1])
        sekolah_pilih = col_sel.selectbox("Pilih Sekolah:", df_all["nama"].tolist(), key="rf_sekolah_pilih")
        jarak_sim = col_jarak.slider("Jarak Rumah ke Sekolah (m):", 50, 5000, 500, step=50, key="rf_jarak_sim")

        hasil_sim = prediksi_peluang(jarak_sim, True, sekolah_pilih)

        if "error" not in hasil_sim:
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("🎯 Peluang Diterima", f"{hasil_sim['prob_diterima']:.1f}%")
            sc2.metric("🔥 Cluster Keketatan", CLUSTER_TAMPIL.get(hasil_sim['cluster_label'], hasil_sim['cluster_label']))
            sc3.metric("📐 Batas Historis", f"{hasil_sim['jarak_batas_m']:,.0f} m")
        else:
            st.error(hasil_sim["error"])


# ════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("🗺️ Peta Sebaran Sekolah – Warna berdasarkan Cluster FCM")
    # Peta sebaran memakai cluster keketatan berdasarkan data tahun ajaran 2026 saja.
    TAHUN_PETA_SEBARAN = 2026
    df_all_peta = hitung_cluster_per_tahun(df_all, TAHUN_PETA_SEBARAN)
    sekolah_peta = df_all_peta.to_dict("records")
    for s in sekolah_peta:
        s["cluster"] = s.get("cluster_label", "Sedang")
    m = buat_peta_admin(sekolah_peta)

    _reload_key_dash = "peta_reload_dashboard"
    _reload_n_dash = st.session_state.get(_reload_key_dash, 0)
    col_info_dash, col_btn_dash = st.columns([5, 1.4])
    with col_info_dash:
        st.caption(
            "⏳ Peta memuat komponen (Leaflet/marker) dari internet setiap "
            "kali halaman dibuka. Jika area di bawah tampak kosong/putih "
            "lebih dari beberapa detik, klik **Muat Ulang Peta**."
        )
    with col_btn_dash:
        if st.button("🔄 Muat Ulang Peta", key="btn_reload_peta_dashboard"):
            st.session_state[_reload_key_dash] = _reload_n_dash + 1
            _reload_n_dash += 1
    with st.spinner("🗺️ Menyiapkan peta..."):
        st_folium(
            m, width=None, height=550, returned_objects=[],
            key=f"peta_admin_dashboard_{_reload_n_dash}",
        )
    fix_map_tab_render()
