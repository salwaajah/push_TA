"""
pages/4_Kelola_Pendaftar.py
Kelola Pendaftar (Admin only).
Menampilkan data pendaftar per sekolah, dengan filter Tahun, plus CRUD
(Tambah/Edit/Hapus) untuk tahun yang punya data per-siswa.

- Tahun 2025 & 2026 : sumber data punya sheet per sekolah (SMP 1 - SMP 75),
  sehingga ditampilkan daftar pendaftar per-siswa (nama, asal SD, jarak, dll)
  dan bisa Tambah/Edit/Hapus per baris.
- Tahun 2022 & 2024 : sumber data TIDAK punya sheet per sekolah, sehingga
  hanya ditampilkan ringkasan jarak/nilai min-max per sekolah saja (kuota
  bisa diubah lewat menu Kelola Kuota; CRUD per-siswa tidak tersedia).

Catatan tampilan: kolom "Kode Pendaftar" dan "Daftar Ulang" tidak ditampilkan
/ tidak diminta di form (dibuat otomatis / belum relevan saat pendaftaran),
dan kolom yang seluruh isinya kosong pada suatu sekolah otomatis disembunyikan.
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
    get_tahun_tersedia, get_tahun_punya_sheet_per_sekolah, format_tahun_ajaran,
    load_pendaftar_detail, load_ringkasan_sekolah,
    save_pendaftar_row, delete_pendaftar_row, tambah_tahun_ajaran,
)

TAHUN_TERSEDIA = get_tahun_tersedia()
TAHUN_PUNYA_SHEET_PER_SEKOLAH = get_tahun_punya_sheet_per_sekolah()

if not st.session_state.get("logged_in") or st.session_state.get("user_role") != "admin":
    st.warning("⛔ Halaman ini hanya untuk Admin.")
    st.stop()

st.markdown("## 📝 Kelola Pendaftar – SPMB Kota Bandung")
st.caption("Lihat, tambah, ubah, dan hapus data pendaftar tiap sekolah negeri berdasarkan tahun ajaran.")
st.divider()

# ── Filter Tahun / Sekolah / Zona ─────────────────────────────────────────────
col_tahun, col_sekolah, col_zona = st.columns([1, 2, 1])
tahun = col_tahun.selectbox(
    "📅 Tahun Ajaran", TAHUN_TERSEDIA, index=len(TAHUN_TERSEDIA) - 1,
    format_func=format_tahun_ajaran,
)

zona_opsi = ["Semua"] + ["A", "B", "C", "D"]
zona_pilih = col_zona.selectbox("Filter Zona", zona_opsi)

daftar_sekolah = SEKOLAH_NEGERI
if zona_pilih != "Semua":
    daftar_sekolah = [s for s in daftar_sekolah if s["zona"] == zona_pilih]

nama_sekolah_list = [s["nama"] for s in daftar_sekolah]
sekolah_pilih = col_sekolah.selectbox("🏫 Pilih Sekolah", nama_sekolah_list)

# nomor sekolah dari nama, contoh "SMP Negeri 12" -> 12
try:
    nomor_sekolah = int(sekolah_pilih.split()[-1])
except (ValueError, IndexError):
    nomor_sekolah = None

st.divider()

# Kolom yang sengaja tidak ditampilkan / tidak diminta di form CRUD
KOLOM_DISEMBUNYIKAN = ["Kode Pendaftar", "Daftar Ulang"]


def _bersihkan_kolom(df: pd.DataFrame) -> pd.DataFrame:
    """Hapus kolom Kode Pendaftar/Daftar Ulang, dan kolom yang seluruh
    isinya kosong (NaN atau string kosong)."""
    df = df.drop(columns=[c for c in KOLOM_DISEMBUNYIKAN if c in df.columns], errors="ignore")
    kolom_kosong = [c for c in df.columns if df[c].astype(str).str.strip().eq("").all() or df[c].isna().all()]
    return df.drop(columns=kolom_kosong)


if tahun in TAHUN_PUNYA_SHEET_PER_SEKOLAH:
    tab1, tab_viz, tab2, tab3, tab4 = st.tabs(
        ["📋 Daftar Pendaftar", "📊 Visualisasi", "➕ Tambah Pendaftar", "✏️ Edit / Hapus", "🆕 Tambah Tahun Ajaran"]
    )

    with st.spinner("Memuat data pendaftar..."):
        df_detail = load_pendaftar_detail(tahun, nomor_sekolah) if nomor_sekolah else None

    # ── Tab 1: Lihat ──────────────────────────────────────────────────────────
    with tab1:
        st.info(
            f"ℹ️ Data tahun **{tahun}** tersedia per-siswa "
            f"(sumber: sheet 'SMP NEGERI {nomor_sekolah} - DOMISILI')."
        )
        if df_detail is None or df_detail.empty:
            st.warning(f"Data pendaftar untuk **{sekolah_pilih}** tahun {tahun} tidak ditemukan.")
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("👥 Total Pendaftar", len(df_detail))
            m2.metric("📏 Jarak Terdekat", f"{df_detail['Jarak (m)'].min():,.2f} m"
                       if df_detail["Jarak (m)"].notna().any() else "-")
            m3.metric("📏 Jarak Terjauh", f"{df_detail['Jarak (m)'].max():,.2f} m"
                       if df_detail["Jarak (m)"].notna().any() else "-")

            st.subheader(f"📋 Daftar Pendaftar – {sekolah_pilih} ({tahun})")
            cari = st.text_input("🔎 Cari nama / asal SD", "")
            df_show = df_detail.copy()
            if cari:
                mask = (
                    df_show["Nama"].astype(str).str.contains(cari, case=False, na=False) |
                    df_show["Asal Sekolah Dasar"].astype(str).str.contains(cari, case=False, na=False)
                )
                df_show = df_show[mask]

            df_show_tampil = _bersihkan_kolom(df_show.sort_values("Jarak (m)", na_position="last"))

            st.dataframe(df_show_tampil, use_container_width=True, hide_index=True, height=360)
            st.download_button(
                "⬇️ Unduh CSV",
                data=df_show_tampil.to_csv(index=False),
                file_name=f"pendaftar_{sekolah_pilih.replace(' ', '_')}_{tahun}.csv",
                mime="text/csv",
            )

    # ── Tab Visualisasi ───────────────────────────────────────────────────────
    with tab_viz:
        st.subheader(f"📊 Visualisasi Pendaftar – {sekolah_pilih} ({tahun})")
        if df_detail is None or df_detail.empty:
            st.warning(f"Data pendaftar untuk **{sekolah_pilih}** tahun {tahun} tidak ditemukan.")
        else:
            st.markdown("##### 📊 Distribusi Jarak")
            if df_show["Jarak (m)"].notna().any():
                fig_hist = px.histogram(
                    df_show.dropna(subset=["Jarak (m)"]), x="Jarak (m)", nbins=15,
                    color_discrete_sequence=["#3f51b5"],
                    labels={"Jarak (m)": "Jarak (m)", "count": "Jumlah Pendaftar"},
                )
                fig_hist.update_layout(
                    height=420,
                    margin=dict(t=40, b=60, l=60, r=40),
                    bargap=0.15,
                    xaxis_title="Jarak (m)",
                    yaxis_title="Jumlah Pendaftar",
                    plot_bgcolor="white",
                )
                fig_hist.update_xaxes(showgrid=True, gridcolor="#eee")
                fig_hist.update_yaxes(showgrid=True, gridcolor="#eee")
                st.plotly_chart(fig_hist, use_container_width=True)
            else:
                st.info("Tidak ada keterangan jarak untuk data tahun ini.")

    # ── Tab 2: Tambah ─────────────────────────────────────────────────────────
    with tab2:
        st.subheader(f"➕ Tambah Pendaftar – {sekolah_pilih} ({tahun})")
        st.caption("Kode Pendaftar dibuat otomatis dan status Daftar Ulang belum diisi di tahap ini.")
        with st.form("form_tambah_pendaftar"):
            nama_baru = st.text_input("Nama *")
            c1, c2 = st.columns(2)
            luar_daerah_baru = c1.selectbox("Luar Daerah", ["Tidak", "Ya"])
            jarak_baru = c2.number_input("Jarak (m)", min_value=0.0, value=0.0)
            asal_sd_baru = st.text_input("Asal Sekolah Dasar")
            tgl_lahir_baru = st.text_input("Tanggal Lahir", placeholder="DD/MM/YYYY")
            submit_tambah = st.form_submit_button("💾 Simpan", type="primary")

        if submit_tambah:
            if not nama_baru:
                st.error("Nama wajib diisi.")
            elif not nomor_sekolah:
                st.error("Sekolah tidak valid.")
            else:
                try:
                    save_pendaftar_row(tahun, nomor_sekolah, {
                        "nama": nama_baru,
                        "luar_daerah": luar_daerah_baru,
                        "asal_sd": asal_sd_baru,
                        "tgl_lahir": tgl_lahir_baru,
                        "jarak": jarak_baru,
                    })
                    st.success(f"✅ Pendaftar '{nama_baru}' berhasil ditambahkan.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Gagal menyimpan: {e}")

    # ── Tab 3: Edit / Hapus ───────────────────────────────────────────────────
    with tab3:
        st.subheader(f"✏️ Edit / Hapus Pendaftar – {sekolah_pilih} ({tahun})")
        if df_detail is None or df_detail.empty:
            st.info("Belum ada data pendaftar untuk sekolah ini.")
        else:
            opsi = {f"#{r['No']} – {r['Nama']}": r["No"] for _, r in df_detail.iterrows()}
            pilihan = st.selectbox("Pilih Pendaftar:", list(opsi.keys()))
            no_pilih = opsi[pilihan]
            row = df_detail[df_detail["No"] == no_pilih].iloc[0]

            with st.form("form_edit_pendaftar"):
                new_nama = st.text_input("Nama", value=str(row["Nama"]))
                c1, c2 = st.columns(2)
                opsi_luar = ["Tidak", "Ya"]
                nilai_luar = str(row["Luar Daerah"]) if str(row["Luar Daerah"]) in opsi_luar else "Tidak"
                new_luar_daerah = c1.selectbox("Luar Daerah", opsi_luar, index=opsi_luar.index(nilai_luar))
                new_jarak = c2.number_input(
                    "Jarak (m)", min_value=0.0,
                    value=float(row["Jarak (m)"]) if pd.notna(row["Jarak (m)"]) else 0.0,
                )
                new_asal_sd = st.text_input("Asal Sekolah Dasar", value=str(row["Asal Sekolah Dasar"]))
                new_tgl_lahir = st.text_input("Tanggal Lahir", value=str(row["Tanggal Lahir"]))

                col_btn1, col_btn2, _ = st.columns([1, 1, 3])
                simpan = col_btn1.form_submit_button("💾 Update", type="primary")
                hapus = col_btn2.form_submit_button("🗑️ Hapus", type="secondary")

            if simpan:
                try:
                    save_pendaftar_row(tahun, nomor_sekolah, {
                        "nama": new_nama,
                        "luar_daerah": new_luar_daerah,
                        "asal_sd": new_asal_sd,
                        "tgl_lahir": new_tgl_lahir,
                        "jarak": new_jarak,
                    }, no_existing=no_pilih)
                    st.success(f"✅ Data '{new_nama}' berhasil diperbarui.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Gagal update: {e}")

            if hapus:
                try:
                    delete_pendaftar_row(tahun, nomor_sekolah, no_pilih)
                    st.success(f"🗑️ Pendaftar '{row['Nama']}' dihapus.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Gagal hapus: {e}")

    # ── Tab 4: Tambah Tahun Ajaran Baru ─────────────────────────────────────
    with tab4:
        st.subheader("🆕 Tambah Tahun Ajaran Baru")
        st.caption(
            "Buat data tahun ajaran baru (mis. tahun setelah 2026) dengan menyalin "
            "struktur sheet dari tahun yang sudah ada — daftar 75 sekolah beserta "
            "kolom Kuota/Pendaftar/Sheet per-siswa ikut dibuat, tetapi seluruh "
            "angkanya dikosongkan (0 / tanpa baris pendaftar) sehingga siap diisi dari awal."
        )

        tahun_terakhir_pendaftar = max(TAHUN_TERSEDIA)
        with st.form("form_tambah_tahun_pendaftar"):
            c1, c2 = st.columns(2)
            tahun_baru_pendaftar = c1.number_input(
                "Tahun Ajaran Baru (mulai)", min_value=tahun_terakhir_pendaftar + 1,
                max_value=tahun_terakhir_pendaftar + 10, value=tahun_terakhir_pendaftar + 1, step=1,
            )
            salin_dari_pendaftar = c2.selectbox(
                "Salin struktur dari tahun", TAHUN_TERSEDIA,
                index=len(TAHUN_TERSEDIA) - 1, format_func=format_tahun_ajaran,
                help="Tahun ajaran baru akan punya struktur sheet yang sama persis "
                     "dengan tahun ini (disarankan pilih tahun terbaru yang sudah punya "
                     "data per-siswa, seperti 2025/2026 atau 2026/2027).",
                key="salin_dari_pendaftar",
            )
            st.info(f"Tahun ajaran baru akan tampil sebagai **{format_tahun_ajaran(int(tahun_baru_pendaftar))}**.")
            submit_tahun_pendaftar = st.form_submit_button("🆕 Buat Tahun Ajaran", type="primary")

        if submit_tahun_pendaftar:
            try:
                path_baru = tambah_tahun_ajaran(int(tahun_baru_pendaftar), int(salin_dari_pendaftar))
                st.success(
                    f"✅ Tahun ajaran **{format_tahun_ajaran(int(tahun_baru_pendaftar))}** berhasil dibuat "
                    f"({os.path.basename(path_baru)}). Silakan pilih tahun ini di dropdown "
                    "Tahun Ajaran di atas untuk mulai mengisi data pendaftar."
                )
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Gagal membuat tahun ajaran baru: {e}")

else:
    tab_ringkas_pdftr, tab_viz_pdftr, tab_tahun_pdftr2 = st.tabs(
        ["📋 Ringkasan", "📊 Visualisasi", "🆕 Tambah Tahun Ajaran"]
    )

    with tab_ringkas_pdftr:
        st.warning(
            f"⚠️ Data pendaftar per-siswa **tidak tersedia** untuk tahun {tahun} "
            "(sumber data tahun ini tidak memiliki sheet per sekolah), sehingga Tambah/Edit/Hapus "
            "per-siswa tidak tersedia untuk tahun ini. Berikut ditampilkan ringkasan jarak/nilai "
            "min-max per sekolah. Kuota dapat diubah lewat menu **Kelola Kuota**."
        )
        df_ringkas = load_ringkasan_sekolah(tahun)
        if df_ringkas.empty:
            st.error("Data ringkasan tidak ditemukan untuk tahun ini.")
        else:
            # cocokkan nomor sekolah secara presisi (hindari 1 vs 11, 12, dst)
            nomor_ekstrak = df_ringkas["nama"].str.extract(r"(\d+)")[0]
            row_sekolah = df_ringkas[nomor_ekstrak.astype(float) == nomor_sekolah] \
                if nomor_sekolah else pd.DataFrame()

            if zona_pilih != "Semua":
                nomor_valid = {int(n.split()[-1]) for n in nama_sekolah_list if n.split()[-1].isdigit()}
                df_ringkas = df_ringkas[nomor_ekstrak.astype(float).isin(nomor_valid)]

            if not row_sekolah.empty:
                row = row_sekolah.iloc[0]
                st.subheader(f"📋 Ringkasan – {sekolah_pilih} ({tahun})")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("🎓 Kuota Dalam", f"{row['kuota_dalam']:,.0f}" if pd.notna(row["kuota_dalam"]) else "-")
                c2.metric("📝 Pendaftar Dalam", f"{row['pendaftar_dalam']:,.0f}" if pd.notna(row["pendaftar_dalam"]) else "-")
                label_min = "Jarak Min" if tahun == 2022 else "Nilai Min"
                label_max = "Jarak Max" if tahun == 2022 else "Nilai Max"
                c3.metric(f"📏 {label_min}", f"{row['jarak_min']:,.2f}" if pd.notna(row["jarak_min"]) else "-")
                c4.metric(f"📏 {label_max}", f"{row['jarak_max']:,.2f}" if pd.notna(row["jarak_max"]) else "-")
                st.caption(f"ℹ️ {row['keterangan_batas']}")
            else:
                st.info("Data untuk sekolah ini tidak ditemukan pada ringkasan tahun tersebut.")

            st.divider()

            st.subheader(f"📋 Tabel Ringkasan Semua Sekolah ({tahun})")
            label_min = "Jarak Min" if tahun == 2022 else "Nilai Min"
            label_max = "Jarak Max" if tahun == 2022 else "Nilai Max"
            df_tampil = df_ringkas.rename(columns={
                "nama": "Nama Sekolah", "kuota_dalam": "Kuota Dalam",
                "kuota_luar": "Kuota Luar", "pendaftar_dalam": "Pendaftar Dalam",
                "pendaftar_luar": "Pendaftar Luar", "jarak_min": label_min,
                "jarak_max": label_max, "keterangan_batas": "Keterangan",
            })
            df_tampil = _bersihkan_kolom(df_tampil)
            st.dataframe(df_tampil, use_container_width=True, hide_index=True, height=360)
            st.download_button(
                "⬇️ Unduh CSV Ringkasan",
                data=df_tampil.to_csv(index=False),
                file_name=f"ringkasan_pendaftar_{tahun}.csv",
                mime="text/csv",
            )

    # ── Tab Visualisasi ───────────────────────────────────────────────────────
    with tab_viz_pdftr:
        st.subheader(f"📊 Visualisasi Ringkasan Pendaftar ({tahun})")
        st.markdown("##### 📊 Kuota vs Pendaftar (Top 15)")
        df_chart = df_ringkas.dropna(subset=["kuota_dalam"]).sort_values(
            "pendaftar_dalam", ascending=False).head(15) if not df_ringkas.empty else df_ringkas
        if not df_chart.empty:
            fig_bar = px.bar(
                df_chart, x="nama", y=["kuota_dalam", "pendaftar_dalam"], barmode="group",
                labels={"value": "Jumlah", "nama": "Sekolah", "variable": "Kategori"},
                color_discrete_sequence=["#3f51b5", "#f44336"],
            )
            fig_bar.update_layout(
                height=420, xaxis_tickangle=-45, xaxis_tickfont_size=7,
                margin=dict(t=10, b=100, l=10, r=10), legend=dict(orientation="h", y=-0.5),
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.caption("Data tidak tersedia.")

    with tab_tahun_pdftr2:
        st.subheader("🆕 Tambah Tahun Ajaran Baru")
        st.caption(
            "Buat data tahun ajaran baru (mis. tahun setelah 2026) dengan menyalin "
            "struktur sheet dari tahun yang sudah ada — daftar 75 sekolah beserta "
            "kolom Kuota/Pendaftar/Sheet per-siswa ikut dibuat, tetapi seluruh "
            "angkanya dikosongkan (0 / tanpa baris pendaftar) sehingga siap diisi dari awal."
        )

        tahun_terakhir_pendaftar = max(TAHUN_TERSEDIA)
        with st.form("form_tambah_tahun_pendaftar"):
            c1, c2 = st.columns(2)
            tahun_baru_pendaftar = c1.number_input(
                "Tahun Ajaran Baru (mulai)", min_value=tahun_terakhir_pendaftar + 1,
                max_value=tahun_terakhir_pendaftar + 10, value=tahun_terakhir_pendaftar + 1, step=1,
            )
            salin_dari_pendaftar = c2.selectbox(
                "Salin struktur dari tahun", TAHUN_TERSEDIA,
                index=len(TAHUN_TERSEDIA) - 1, format_func=format_tahun_ajaran,
                help="Tahun ajaran baru akan punya struktur sheet yang sama persis "
                     "dengan tahun ini (disarankan pilih tahun terbaru yang sudah punya "
                     "data per-siswa, seperti 2025/2026 atau 2026/2027).",
                key="salin_dari_pendaftar",
            )
            st.info(f"Tahun ajaran baru akan tampil sebagai **{format_tahun_ajaran(int(tahun_baru_pendaftar))}**.")
            submit_tahun_pendaftar = st.form_submit_button("🆕 Buat Tahun Ajaran", type="primary")

        if submit_tahun_pendaftar:
            try:
                path_baru = tambah_tahun_ajaran(int(tahun_baru_pendaftar), int(salin_dari_pendaftar))
                st.success(
                    f"✅ Tahun ajaran **{format_tahun_ajaran(int(tahun_baru_pendaftar))}** berhasil dibuat "
                    f"({os.path.basename(path_baru)}). Silakan pilih tahun ini di dropdown "
                    "Tahun Ajaran di atas untuk mulai mengisi data pendaftar."
                )
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Gagal membuat tahun ajaran baru: {e}")
