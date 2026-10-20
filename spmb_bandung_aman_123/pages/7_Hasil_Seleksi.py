"""
pages/7_Hasil_Seleksi.py
Menu Hasil Seleksi (Admin only).

Menampilkan ringkasan hasil seleksi SPMB per sekolah & tahun ajaran
(2022-2026), dipisah dua jalur:
  - Jalur Domisili          : pendaftar dalam daerah/kecamatan zona sekolah.
  - Jalur Domisili Batasan  : pendaftar luar daerah yang tetap diterima lewat
                               perluasan radius/batas jarak penerimaan.
                               Jalur ini HANYA dibuka di 8 SMP Negeri resmi
                               (lihat SEKOLAH_DOMISILI_BATASAN).

Untuk setiap jalur ditampilkan: kuota, jumlah pendaftar, jumlah diterima
(= min(kuota, pendaftar)), jumlah ditolak (= pendaftar - diterima bila
positif), serta rentang jarak (min-max) pendaftar yang diterima. Untuk
tahun yang punya data per-siswa (2025 & 2026), turut ditampilkan daftar
nama pendaftar yang diterima per sekolah.

Menu ini juga menyediakan CRUD (Tambah/Edit/Hapus) data kuota & pendaftar
seperti di menu Kelola Sekolah, dan Tambah Tahun Ajaran seperti di menu
Kelola Kuota, karena data Hasil Seleksi diturunkan langsung dari data
kuota/pendaftar yang sama.
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
    load_hasil_seleksi, load_diterima_detail, load_ringkasan_sekolah,
    load_jarak_minmax_jalur, update_kuota_sekolah, insert_kuota_sekolah,
    delete_kuota_sekolah, tambah_tahun_ajaran, bersihkan_kolom_kosong,
)

if not st.session_state.get("logged_in") or st.session_state.get("user_role") != "admin":
    st.warning("⛔ Halaman ini hanya untuk Admin.")
    st.stop()

st.markdown("## 📑 Hasil Seleksi – SPMB Kota Bandung")
st.caption(
    "Ringkasan diterima/ditolak tiap sekolah per tahun ajaran, dipisah "
    "**Jalur Domisili** (dalam daerah) dan **Jalur Domisili Batasan** "
    "(luar daerah/perluasan radius batas jarak)."
)
st.divider()

TAHUN_TERSEDIA = get_tahun_tersedia()
TAHUN_PUNYA_SHEET_PER_SEKOLAH = get_tahun_punya_sheet_per_sekolah()
NAMA_SEKOLAH_BATASAN = [f"SMP Negeri {n}" for n in SEKOLAH_DOMISILI_BATASAN]

zona_by_nomor = {}
for s in SEKOLAH_NEGERI:
    try:
        nomor = int(s["nama"].split()[-1])
        zona_by_nomor[nomor] = s["zona"]
    except (ValueError, IndexError):
        pass

col_tahun, col_jalur, col_zona = st.columns([1, 1.4, 1])
tahun = col_tahun.selectbox("📅 Tahun Ajaran", TAHUN_TERSEDIA,
                             index=len(TAHUN_TERSEDIA) - 1, format_func=format_tahun_ajaran)
jalur_pilih = col_jalur.multiselect("Jalur", ["Domisili", "Domisili Batasan"],
                                     default=["Domisili", "Domisili Batasan"])
zona_pilih = col_zona.multiselect("Filter Zona", ["A", "B", "C", "D"], default=["A", "B", "C", "D"])

df_hasil_raw = load_hasil_seleksi(tahun)
if df_hasil_raw.empty:
    st.error(f"Data hasil seleksi untuk tahun {format_tahun_ajaran(tahun)} tidak ditemukan.")
    st.stop()

df_hasil_raw["nomor"] = df_hasil_raw["nama"].str.extract(r"(\d+)")[0].astype(float)
df_hasil_raw["zona"] = df_hasil_raw["nomor"].map(zona_by_nomor).fillna("-")

# Jalur Domisili Batasan hanya berlaku untuk 8 SMP Negeri resmi (lihat
# data/sekolah_data.py -> SEKOLAH_DOMISILI_BATASAN, sesuai daftar resmi).
mask_batasan_valid = (df_hasil_raw["jalur"] != "Domisili Batasan") | (
    df_hasil_raw["nomor"].isin(SEKOLAH_DOMISILI_BATASAN)
)
df_hasil_raw = df_hasil_raw[mask_batasan_valid]

# 8 SMP Negeri Jalur Domisili Batasan dipisah sepenuhnya dari Jalur
# Domisili biasa: sekolah tsb hanya tampil pada baris Domisili Batasan,
# tidak lagi dihitung/ditampilkan pada baris Domisili.
mask_domisili_terpisah = (df_hasil_raw["jalur"] != "Domisili") | (
    ~df_hasil_raw["nomor"].isin(SEKOLAH_DOMISILI_BATASAN)
)
df_hasil_raw = df_hasil_raw[mask_domisili_terpisah]

df_hasil = df_hasil_raw[df_hasil_raw["jalur"].isin(jalur_pilih)] if jalur_pilih else df_hasil_raw
df_hasil = df_hasil[df_hasil["zona"].isin(zona_pilih)] if zona_pilih else df_hasil

tab_ringkas, tab_jarak, tab_tambah, tab_edit, tab_tahun = st.tabs([
    "📊 Ringkasan & Visualisasi",
    "📏 Jarak Min-Max", "➕ Tambah", "✏️ Edit / Hapus", "🆕 Tambah Tahun Ajaran",
])

# ── Tab: Ringkasan & Visualisasi ─────────────────────────────────────────
with tab_ringkas:
    st.caption(
        f"ℹ️ Jalur Domisili Batasan hanya tersedia untuk **{len(SEKOLAH_DOMISILI_BATASAN)} SMP Negeri** "
        f"resmi: {', '.join(str(n) for n in SEKOLAH_DOMISILI_BATASAN)}."
    )

    st.divider()

    st.subheader(f"📊 Diterima vs Ditolak per Jalur – Tahun Ajaran {format_tahun_ajaran(tahun)}")
    tab_chart1, tab_chart2 = st.tabs(["📈 Per Jalur (Total)", "🏫 Per Sekolah (Top 15 Pendaftar)"])

    with tab_chart1:
        ringkas_jalur = df_hasil.groupby("jalur")[["diterima", "ditolak"]].sum().reset_index()
        if not ringkas_jalur.empty:
            fig_jalur = px.bar(
                ringkas_jalur, x="jalur", y=["diterima", "ditolak"], barmode="group",
                labels={"value": "Jumlah Pendaftar", "jalur": "Jalur", "variable": "Status"},
                color_discrete_sequence=["#2ecc71", "#e74c3c"],
            )
            fig_jalur.update_layout(height=380)
            st.plotly_chart(fig_jalur, use_container_width=True)

    with tab_chart2:
        df_top = df_hasil.sort_values("pendaftar", ascending=False).head(15)
        if not df_top.empty:
            fig_sek = px.bar(
                df_top, x="nama", y=["diterima", "ditolak"], barmode="stack", color_discrete_sequence=["#2ecc71", "#e74c3c"],
                facet_col="jalur", labels={"value": "Jumlah", "nama": "Sekolah", "variable": "Status"},
            )
            fig_sek.update_layout(height=420, xaxis_tickangle=-45, xaxis_tickfont_size=8, margin=dict(b=150))
            st.plotly_chart(fig_sek, use_container_width=True)

    st.divider()

    st.subheader("📋 Tabel Ringkasan Hasil Seleksi")
    rename_map = {
        "nama": "Nama Sekolah", "zona": "Zona", "jalur": "Jalur",
        "kuota": "Kuota", "pendaftar": "Pendaftar",
        "diterima": "Diterima", "ditolak": "Ditolak",
        "jarak_min": "Jarak Min Diterima (m)", "jarak_max": "Jarak Max Diterima (m)",
    }
    kolom_tampil = ["nama", "zona", "jalur", "kuota", "pendaftar", "diterima", "ditolak",
                     "jarak_min", "jarak_max"]
    df_tampil = df_hasil[kolom_tampil].rename(columns=rename_map).sort_values(
        ["Nama Sekolah", "Jalur"]
    )
    df_tampil = bersihkan_kolom_kosong(df_tampil)
    st.dataframe(df_tampil, use_container_width=True, hide_index=True)
    st.caption(
        "ℹ️ Jarak Min/Max Diterima hanya tersedia bila data sumber tahun ini "
        "menyediakan rincian jarak (lihat kolom Keterangan pada menu Kelola Pendaftar)."
    )
    st.download_button(
        "⬇️ Unduh CSV Ringkasan Hasil Seleksi",
        data=df_tampil.to_csv(index=False),
        file_name=f"hasil_seleksi_{tahun}.csv",
        mime="text/csv",
    )

    st.divider()

    st.subheader("👥 Detail Pendaftar Diterima per Sekolah")

    if tahun not in TAHUN_PUNYA_SHEET_PER_SEKOLAH:
        st.info(
            f"ℹ️ Tahun ajaran {format_tahun_ajaran(tahun)} tidak memiliki data pendaftar "
            "per-siswa pada berkas sumber, sehingga daftar nama pendaftar yang diterima "
            "tidak dapat ditampilkan (hanya ringkasan jarak min-max di atas)."
        )
    else:
        nama_sekolah_list = sorted(
            df_hasil[(df_hasil["jalur"] == "Domisili") & (df_hasil["kuota"] > 0)]["nama"].unique().tolist()
        )
        if not nama_sekolah_list:
            st.info("Tidak ada sekolah pada filter saat ini.")
        else:
            sekolah_detail = st.selectbox("🏫 Pilih Sekolah:", nama_sekolah_list, key="sekolah_detail_diterima")
            try:
                nomor_detail = int(sekolah_detail.split()[-1])
            except (ValueError, IndexError):
                nomor_detail = None

            row_kuota = df_hasil[(df_hasil["nama"] == sekolah_detail) & (df_hasil["jalur"] == "Domisili")]
            kuota_dalam = int(row_kuota.iloc[0]["kuota"]) if not row_kuota.empty else 0

            if nomor_detail and kuota_dalam:
                df_diterima = load_diterima_detail(tahun, nomor_detail, kuota_dalam)
                if df_diterima is None or df_diterima.empty:
                    st.warning(f"Data pendaftar untuk **{sekolah_detail}** tidak ditemukan.")
                else:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("✅ Diterima (Jalur Domisili)", len(df_diterima))
                    c2.metric("📏 Jarak Min", f"{df_diterima['Jarak (m)'].min():,.2f} m"
                              if df_diterima["Jarak (m)"].notna().any() else "-")
                    c3.metric("📏 Jarak Max", f"{df_diterima['Jarak (m)'].max():,.2f} m"
                              if df_diterima["Jarak (m)"].notna().any() else "-")

                    kolom_nama = ["No", "Nama", "Asal Sekolah Dasar", "Jarak (m)"]
                    kolom_ada = [k for k in kolom_nama if k in df_diterima.columns]
                    st.dataframe(df_diterima[kolom_ada], use_container_width=True, hide_index=True)
                    st.download_button(
                        "⬇️ Unduh CSV Pendaftar Diterima",
                        data=df_diterima[kolom_ada].to_csv(index=False),
                        file_name=f"diterima_{sekolah_detail.replace(' ', '_')}_{tahun}.csv",
                        mime="text/csv",
                        key="dl_diterima_detail",
                    )

# ── Tab: Jarak Min-Max per Jalur ──────────────────────────────────────────
with tab_jarak:
    st.subheader(f"📏 Tabel Jarak Min-Max per Sekolah – {format_tahun_ajaran(tahun)}")
    st.caption(
        "Jarak dihitung dari data pendaftar riil pada berkas dataset. Untuk "
        "tahun dengan data per-siswa (2025/2026 dst.), jarak Jalur Domisili "
        "Batasan hanya dihitung untuk 8 SMP Negeri resmi. Untuk tahun tanpa "
        "data per-siswa (2022/2024), hanya tersedia ringkasan Jalur Domisili."
    )

    df_jarak = load_jarak_minmax_jalur(tahun, tuple(SEKOLAH_DOMISILI_BATASAN))
    if df_jarak.empty:
        st.info("Data jarak untuk tahun ini tidak ditemukan.")
    else:
        df_jarak = df_jarak[df_jarak["jalur"].isin(jalur_pilih)] if jalur_pilih else df_jarak
        if "zona" in df_jarak.columns:
            df_jarak = df_jarak[df_jarak["zona"].isin(zona_pilih)] if zona_pilih else df_jarak

        df_jarak_tampil = df_jarak.rename(columns={
            "nama": "Nama Sekolah", "zona": "Zona", "jalur": "Jalur",
            "jumlah": "Jumlah Pendaftar", "jarak_min": "Jarak Min (m)", "jarak_max": "Jarak Max (m)",
        }).sort_values(["Nama Sekolah", "Jalur"])
        df_jarak_tampil = bersihkan_kolom_kosong(df_jarak_tampil)
        st.dataframe(df_jarak_tampil, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Unduh CSV Jarak Min-Max",
            data=df_jarak_tampil.to_csv(index=False),
            file_name=f"jarak_minmax_{tahun}.csv",
            mime="text/csv",
            key="dl_jarak",
        )

# ── Tab: Tambah ────────────────────────────────────────────────────────────
with tab_tambah:
    st.subheader(f"➕ Tambah Data Kuota / Pendaftar – Tahun {format_tahun_ajaran(tahun)}")
    st.caption(
        "Data Hasil Seleksi diturunkan langsung dari data kuota & pendaftar; "
        "menambah baris di sini sama efeknya dengan menambah di menu Kelola Kuota."
    )
    df_ref = load_ringkasan_sekolah(tahun)
    kuota_luar_tersedia_hs = df_ref["kuota_luar"].notna().any() if not df_ref.empty else False

    with st.form("form_tambah_hasil"):
        nama_baru_hs = st.text_input("Nama Sekolah *", placeholder="SMP Negeri XX")
        c1, c2 = st.columns(2)
        kuota_dalam_baru_hs = c1.number_input("Kuota Domisili", min_value=0, value=0)
        pendaftar_dalam_baru_hs = c2.number_input("Pendaftar Domisili", min_value=0, value=0)
        if kuota_luar_tersedia_hs:
            c3, c4 = st.columns(2)
            kuota_luar_baru_hs = c3.number_input("Kuota Domisili Batasan", min_value=0, value=0)
            pendaftar_luar_baru_hs = c4.number_input("Pendaftar Domisili Batasan", min_value=0, value=0)
        else:
            kuota_luar_baru_hs = None
            pendaftar_luar_baru_hs = None
            st.caption("ℹ️ Data sumber tahun ini tidak memiliki kolom Kuota/Pendaftar Batasan terpisah.")
        submit_tambah_hs = st.form_submit_button("💾 Simpan", type="primary")

    if submit_tambah_hs:
        if not nama_baru_hs:
            st.error("Nama sekolah wajib diisi.")
        else:
            try:
                insert_kuota_sekolah(
                    tahun, nama_baru_hs,
                    kuota_dalam=kuota_dalam_baru_hs, kuota_luar=kuota_luar_baru_hs,
                    pendaftar_dalam=pendaftar_dalam_baru_hs, pendaftar_luar=pendaftar_luar_baru_hs,
                )
                st.success(f"✅ Data '{nama_baru_hs}' berhasil ditambahkan.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Gagal menyimpan: {e}")

# ── Tab: Edit / Hapus ─────────────────────────────────────────────────────
with tab_edit:
    st.subheader(f"✏️ Edit atau Hapus Data Kuota / Pendaftar – Tahun {format_tahun_ajaran(tahun)}")
    df_ref2 = load_ringkasan_sekolah(tahun)
    if df_ref2.empty:
        st.info("Belum ada data untuk tahun ini.")
    else:
        nama_edit_hs = st.selectbox("Pilih Sekolah:", df_ref2["nama"].tolist(), key="hs_edit_sekolah")
        row_edit_hs = df_ref2[df_ref2["nama"] == nama_edit_hs].iloc[0]
        kuota_luar_tersedia_edit = df_ref2["kuota_luar"].notna().any()

        with st.form("form_edit_hasil"):
            c1, c2 = st.columns(2)
            new_kuota_dalam_hs = c1.number_input(
                "Kuota Domisili", min_value=0,
                value=int(row_edit_hs["kuota_dalam"]) if pd.notna(row_edit_hs["kuota_dalam"]) else 0,
            )
            if kuota_luar_tersedia_edit:
                new_kuota_luar_hs = c2.number_input(
                    "Kuota Domisili Batasan", min_value=0,
                    value=int(row_edit_hs["kuota_luar"]) if pd.notna(row_edit_hs["kuota_luar"]) else 0,
                )
            else:
                new_kuota_luar_hs = None
                c2.caption("ℹ️ Tidak ada kolom Kuota Batasan terpisah pada data sumber tahun ini.")

            col_btn1, col_btn2, _ = st.columns([1, 1, 3])
            simpan_hs = col_btn1.form_submit_button("💾 Update", type="primary")
            hapus_hs = col_btn2.form_submit_button("🗑️ Hapus", type="secondary")

        if simpan_hs:
            try:
                update_kuota_sekolah(
                    tahun, nama_edit_hs,
                    kuota_dalam=new_kuota_dalam_hs, kuota_luar=new_kuota_luar_hs,
                )
                st.success(f"✅ Data '{nama_edit_hs}' tahun {tahun} berhasil diperbarui.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Gagal menyimpan: {e}")

        if hapus_hs:
            try:
                delete_kuota_sekolah(tahun, nama_edit_hs)
                st.success(f"🗑️ Data '{nama_edit_hs}' tahun {tahun} dihapus.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Gagal hapus: {e}")

# ── Tab: Tambah Tahun Ajaran Baru ─────────────────────────────────────────
with tab_tahun:
    st.subheader("🆕 Tambah Tahun Ajaran Baru")
    st.caption(
        "Buat data tahun ajaran baru (mis. tahun setelah 2026) dengan menyalin "
        "struktur sheet dari tahun yang sudah ada — daftar 75 sekolah beserta "
        "kolom Kuota/Pendaftar/Sheet per-siswa ikut dibuat, tetapi seluruh "
        "angkanya dikosongkan (0 / tanpa baris pendaftar) sehingga siap diisi dari awal."
    )

    tahun_terakhir_hs = max(TAHUN_TERSEDIA)
    with st.form("form_tambah_tahun_hs"):
        c1, c2 = st.columns(2)
        tahun_baru_hs = c1.number_input(
            "Tahun Ajaran Baru (mulai)", min_value=tahun_terakhir_hs + 1,
            max_value=tahun_terakhir_hs + 10, value=tahun_terakhir_hs + 1, step=1,
        )
        salin_dari_hs = c2.selectbox(
            "Salin struktur dari tahun", TAHUN_TERSEDIA,
            index=len(TAHUN_TERSEDIA) - 1, format_func=format_tahun_ajaran,
            key="salin_dari_hs",
            help="Tahun ajaran baru akan punya struktur sheet yang sama persis "
                 "dengan tahun ini (disarankan pilih tahun terbaru yang sudah punya "
                 "data per-siswa, seperti 2025/2026 atau 2026/2027).",
        )
        st.info(f"Tahun ajaran baru akan tampil sebagai **{format_tahun_ajaran(int(tahun_baru_hs))}**.")
        submit_tahun_hs = st.form_submit_button("🆕 Buat Tahun Ajaran", type="primary")

    if submit_tahun_hs:
        try:
            path_baru_hs = tambah_tahun_ajaran(int(tahun_baru_hs), int(salin_dari_hs))
            st.success(
                f"✅ Tahun ajaran **{format_tahun_ajaran(int(tahun_baru_hs))}** berhasil dibuat "
                f"({os.path.basename(path_baru_hs)}). Silakan pilih tahun ini di dropdown "
                "Tahun Ajaran di atas."
            )
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Gagal membuat tahun ajaran baru: {e}")
