"""
pages/5_Kelola_Kuota.py
Kelola Kuota (Admin only).
Menampilkan kuota & pendaftar tiap sekolah negeri, dengan filter Tahun & Zona,
plus CRUD lengkap (Tambah / Edit / Hapus sekolah pada data kuota) seperti di
menu Kelola Sekolah, dan Tambah Tahun Ajaran.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from utils.ui_theme import apply_custom_theme
apply_custom_theme()
import pandas as pd
import plotly.express as px

from data.sekolah_data import SEKOLAH_NEGERI
from utils.dataset_loader import (
    get_tahun_tersedia, format_tahun_ajaran, get_tahun_punya_sheet_per_sekolah,
    load_ringkasan_sekolah, update_kuota_sekolah, insert_kuota_sekolah,
    delete_kuota_sekolah, tambah_tahun_ajaran, bersihkan_kolom_kosong,
)

TAHUN_TERSEDIA = get_tahun_tersedia()

if not st.session_state.get("logged_in") or st.session_state.get("user_role") != "admin":
    st.warning("⛔ Halaman ini hanya untuk Admin.")
    st.stop()

st.markdown("## 🎓 Kelola Kuota – SPMB Kota Bandung")
st.caption("Pantau kuota, jumlah pendaftar, dan rasio keketatan tiap sekolah per tahun ajaran.")
st.divider()

# ── Peta nomor sekolah -> zona (dari data statis sekolah negeri) ────────────
zona_by_nomor = {}
for s in SEKOLAH_NEGERI:
    try:
        nomor = int(s["nama"].split()[-1])
        zona_by_nomor[nomor] = s["zona"]
    except (ValueError, IndexError):
        pass

col_tahun, col_zona = st.columns([1, 1])
tahun = col_tahun.selectbox(
    "📅 Tahun Ajaran", TAHUN_TERSEDIA, index=len(TAHUN_TERSEDIA) - 1,
    format_func=format_tahun_ajaran, key="kuota_tahun",
)
zona_pilih = col_zona.multiselect("Filter Zona", ["A", "B", "C", "D"], default=["A", "B", "C", "D"])

df = load_ringkasan_sekolah(tahun)

if df.empty:
    st.error(f"Data kuota untuk tahun {tahun} tidak ditemukan.")
    st.stop()

df["nomor"] = df["nama"].str.extract(r"(\d+)")[0].astype(float)
df["zona"] = df["nomor"].map(zona_by_nomor).fillna("-")
df_f = df[df["zona"].isin(zona_pilih)] if zona_pilih else df

df_f = df_f.copy()
df_f["kuota_total"] = df_f["kuota_dalam"].fillna(0) + df_f["kuota_luar"].fillna(0)
df_f["pendaftar_total"] = df_f["pendaftar_dalam"].fillna(0) + df_f["pendaftar_luar"].fillna(0)
df_f["rasio"] = df_f.apply(
    lambda r: round(r["pendaftar_total"] / r["kuota_total"], 2) if r["kuota_total"] else 0,
    axis=1,
)

# ── Tab ──────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(
    ["📋 Lihat Data", "➕ Tambah Sekolah", "✏️ Edit / Hapus", "🆕 Tambah Tahun Ajaran"]
)

with tab1:
    # ── Metric ────────────────────────────────────────────────────────────
    m1, m2, m3 = st.columns(3)
    m1.metric("🏫 Total Sekolah", len(df_f))
    m2.metric("🎓 Total Kuota", f"{df_f['kuota_total'].sum():,.0f}")
    m3.metric("📝 Total Pendaftar", f"{df_f['pendaftar_total'].sum():,.0f}")

    st.divider()

    # ── Chart ─────────────────────────────────────────────────────────────
    st.subheader(f"📈 Kuota vs Pendaftar – Tahun {tahun}")
    ZONA_URUTAN = {"A": 0, "B": 1, "C": 2, "D": 3}
    ZONA_WARNA_GARIS = {"A": "#3498db", "B": "#2ecc71", "C": "#f1c40f", "D": "#e74c3c"}
    df_sort = df_f.copy()
    df_sort["_urut_zona"] = df_sort["zona"].map(ZONA_URUTAN)
    df_sort = df_sort.sort_values(["_urut_zona", "rasio"], ascending=[True, False])
    fig = px.bar(
        df_sort, x="nama", y=["kuota_total", "pendaftar_total"],
        barmode="group",
        labels={"value": "Jumlah", "nama": "Sekolah", "variable": "Kategori"},
        color_discrete_sequence=["#3f51b5", "#f44336"],
    )

    # ── Garis pembanding antar Zona A/B/C/D ─────────────────────────────
    posisi = 0
    for zona in ["A", "B", "C", "D"]:
        jumlah_zona = int((df_sort["zona"] == zona).sum())
        if jumlah_zona == 0:
            continue
        if posisi > 0:
            fig.add_vline(x=posisi - 0.5, line_width=1.5, line_dash="dash",
                          line_color="#555555", opacity=0.7)
        fig.add_annotation(x=posisi + jumlah_zona / 2 - 0.5, y=1.1, yref="paper",
                           showarrow=False, text=f"<b>Zona {zona}</b>",
                           font=dict(size=12, color=ZONA_WARNA_GARIS.get(zona, "#333")))
        posisi += jumlah_zona

    fig.update_layout(height=460, xaxis_tickangle=-45, xaxis_tickfont_size=9, margin=dict(t=60, b=160))
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Tabel ────────────────────────────────────────────────────────────
    st.subheader("📋 Tabel Kuota Lengkap")
    rename_map = {
        "nama": "Nama Sekolah", "zona": "Zona",
        "kuota_dalam": "Kuota Dalam", "kuota_luar": "Kuota Luar",
        "pendaftar_dalam": "Pendaftar Dalam", "pendaftar_luar": "Pendaftar Luar",
        "kuota_total": "Total Kuota", "pendaftar_total": "Total Pendaftar",
    }
    kolom_tampil = ["nama", "zona", "kuota_dalam", "kuota_luar", "pendaftar_dalam",
                     "pendaftar_luar", "kuota_total", "pendaftar_total"]
    df_tampil = df_f[kolom_tampil].rename(columns=rename_map).merge(
        df_f[["nama", "rasio"]].rename(columns={"nama": "Nama Sekolah"}), on="Nama Sekolah"
    ).sort_values("rasio", ascending=False).drop(columns=["rasio"])
    df_tampil = bersihkan_kolom_kosong(df_tampil)

    st.dataframe(df_tampil, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Unduh CSV",
        data=df_tampil.to_csv(index=False),
        file_name=f"kuota_sekolah_{tahun}.csv",
        mime="text/csv",
    )

# ── Tab 2: Tambah Sekolah ──────────────────────────────────────────────────
with tab2:
    st.subheader(f"➕ Tambah Data Kuota Sekolah – Tahun {format_tahun_ajaran(tahun)}")
    st.caption(
        "Tambahkan baris kuota/pendaftar untuk sekolah yang belum ada pada data "
        "kuota tahun ini. Nama harus persis sama dengan nama sekolah (mis. 'SMP Negeri 76')."
    )
    kuota_luar_tersedia_tambah = df["kuota_luar"].notna().any()

    with st.form("form_tambah_kuota"):
        nama_baru = st.text_input("Nama Sekolah *", placeholder="SMP Negeri XX")
        c1, c2 = st.columns(2)
        kuota_dalam_baru = c1.number_input("Kuota Dalam", min_value=0, value=0)
        pendaftar_dalam_baru = c2.number_input("Pendaftar Dalam", min_value=0, value=0)
        if kuota_luar_tersedia_tambah:
            c3, c4 = st.columns(2)
            kuota_luar_baru = c3.number_input("Kuota Luar", min_value=0, value=0)
            pendaftar_luar_baru = c4.number_input("Pendaftar Luar", min_value=0, value=0)
        else:
            kuota_luar_baru = None
            pendaftar_luar_baru = None
            st.caption("ℹ️ Data sumber tahun ini tidak memiliki kolom Kuota/Pendaftar Luar terpisah.")
        submit_tambah_kuota = st.form_submit_button("💾 Simpan", type="primary")

    if submit_tambah_kuota:
        if not nama_baru:
            st.error("Nama sekolah wajib diisi.")
        else:
            try:
                insert_kuota_sekolah(
                    tahun, nama_baru,
                    kuota_dalam=kuota_dalam_baru, kuota_luar=kuota_luar_baru,
                    pendaftar_dalam=pendaftar_dalam_baru, pendaftar_luar=pendaftar_luar_baru,
                )
                st.success(f"✅ Data kuota '{nama_baru}' berhasil ditambahkan.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Gagal menyimpan: {e}")

# ── Tab 3: Edit / Hapus ─────────────────────────────────────────────────────
with tab3:
    st.subheader(f"✏️ Edit atau Hapus Kuota Sekolah – Tahun {format_tahun_ajaran(tahun)}")
    st.caption("Perubahan disimpan langsung ke berkas dataset.")

    nama_sekolah_edit = st.selectbox("Pilih Sekolah:", df["nama"].tolist(), key="kuota_edit_sekolah")
    row_edit = df[df["nama"] == nama_sekolah_edit].iloc[0]
    kuota_luar_tersedia = df["kuota_luar"].notna().any()

    with st.form("form_edit_kuota"):
        c1, c2 = st.columns(2)
        new_kuota_dalam = c1.number_input(
            "Kuota Dalam", min_value=0,
            value=int(row_edit["kuota_dalam"]) if pd.notna(row_edit["kuota_dalam"]) else 0,
        )
        if kuota_luar_tersedia:
            new_kuota_luar = c2.number_input(
                "Kuota Luar", min_value=0,
                value=int(row_edit["kuota_luar"]) if pd.notna(row_edit["kuota_luar"]) else 0,
            )
        else:
            new_kuota_luar = None
            c2.caption("ℹ️ Data sumber tahun ini tidak memiliki kolom Kuota Luar terpisah.")

        col_btn1, col_btn2, _ = st.columns([1, 1, 3])
        simpan_kuota = col_btn1.form_submit_button("💾 Update", type="primary")
        hapus_kuota = col_btn2.form_submit_button("🗑️ Hapus", type="secondary")

    if simpan_kuota:
        try:
            update_kuota_sekolah(
                tahun, nama_sekolah_edit,
                kuota_dalam=new_kuota_dalam,
                kuota_luar=new_kuota_luar,
            )
            st.success(f"✅ Kuota '{nama_sekolah_edit}' tahun {tahun} berhasil diperbarui.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Gagal menyimpan kuota: {e}")

    if hapus_kuota:
        try:
            delete_kuota_sekolah(tahun, nama_sekolah_edit)
            st.success(f"🗑️ Data kuota '{nama_sekolah_edit}' tahun {tahun} dihapus.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Gagal hapus: {e}")

# ── Tab 4: Tambah Tahun Ajaran Baru ────────────────────────────────────────
with tab4:
    st.subheader("🆕 Tambah Tahun Ajaran Baru")
    st.caption(
        "Buat data tahun ajaran baru (mis. tahun setelah 2026) dengan menyalin "
        "struktur sheet dari tahun yang sudah ada — daftar 75 sekolah beserta "
        "kolom Kuota/Pendaftar/Sheet per-siswa ikut dibuat, tetapi seluruh "
        "angkanya dikosongkan (0 / tanpa baris pendaftar) sehingga siap diisi dari awal."
    )

    tahun_terakhir = max(TAHUN_TERSEDIA)
    with st.form("form_tambah_tahun"):
        c1, c2 = st.columns(2)
        tahun_baru = c1.number_input(
            "Tahun Ajaran Baru (mulai)", min_value=tahun_terakhir + 1,
            max_value=tahun_terakhir + 10, value=tahun_terakhir + 1, step=1,
        )
        salin_dari = c2.selectbox(
            "Salin struktur dari tahun", TAHUN_TERSEDIA,
            index=len(TAHUN_TERSEDIA) - 1, format_func=format_tahun_ajaran,
            help="Tahun ajaran baru akan punya struktur sheet yang sama persis "
                 "dengan tahun ini (disarankan pilih tahun terbaru, 2025/2026 atau "
                 "2026/2027, karena sudah punya data per-siswa).",
        )
        st.info(f"Tahun ajaran baru akan tampil sebagai **{format_tahun_ajaran(int(tahun_baru))}**.")
        submit_tahun = st.form_submit_button("🆕 Buat Tahun Ajaran", type="primary")

    if submit_tahun:
        try:
            path_baru = tambah_tahun_ajaran(int(tahun_baru), int(salin_dari))
            st.success(
                f"✅ Tahun ajaran **{format_tahun_ajaran(int(tahun_baru))}** berhasil dibuat "
                f"({os.path.basename(path_baru)}). Silakan pilih tahun ini di dropdown "
                "Tahun Ajaran di atas, lalu isi data pendaftar lewat menu **Kelola Pendaftar**."
            )
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Gagal membuat tahun ajaran baru: {e}")
