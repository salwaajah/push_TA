"""
pages/6_Kelola_Data_Swasta.py
Kelola Data Swasta (Admin only).
Menampilkan data SMP Swasta (rujukan/rekomendasi) beserta filter Zona,
dan menyediakan CRUD (Tambah / Edit / Hapus).

Catatan: data SMP Swasta bersumber dari data/sekolah_data.py (SEKOLAH_SWASTA)
dan bersifat statis (referensi alamat & lokasi), berbeda dengan dataset SMP
Negeri (2022/2024/2025/2026) yang memang berbasis tahun ajaran. Sumber data
Excel yang tersedia untuk proyek ini tidak berisi rincian kuota/pendaftar per
tahun untuk sekolah swasta, sehingga filter tahun tidak ditampilkan di sini.
Perubahan (tambah/edit/hapus) disimpan permanen ke data/sekolah_swasta_custom.json.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from utils.ui_theme import apply_custom_theme
apply_custom_theme()
import pandas as pd
import plotly.express as px
from streamlit_folium import st_folium

from utils.swasta_store import load_swasta, insert_swasta, update_swasta, delete_swasta
from utils.zona import geocode_alamat
from utils.map_utils import buat_peta_wilayah, fix_map_tab_render
from utils.dataset_loader import bersihkan_kolom_kosong

if not st.session_state.get("logged_in") or st.session_state.get("user_role") != "admin":
    st.warning("⛔ Halaman ini hanya untuk Admin.")
    st.stop()

st.markdown("## 🏢 Kelola Data Swasta – SPMB Kota Bandung")
st.caption("Data referensi SMP Swasta di Kota Bandung untuk rekomendasi alternatif jalur domisili.")
st.info(
    "ℹ️ Data sekolah swasta bersifat statis (referensi lokasi & alamat) dan tidak "
    "memiliki dimensi tahun ajaran pada berkas sumber, sehingga tidak ada filter tahun di sini.",
    icon="ℹ️",
)
st.divider()

df = pd.DataFrame(load_swasta())

tab1, tab2, tab3, tab4 = st.tabs(
    ["📋 Tabel Data", "📊 Visualisasi", "➕ Tambah Sekolah", "✏️ Edit / Hapus"]
)

# ── Tab 1: Lihat & Filter ────────────────────────────────────────────────────
with tab1:
    col_zona, col_cari = st.columns([1, 2])
    zona_pilih = col_zona.multiselect("Filter Zona", ["A", "B", "C", "D"],
                                       default=["A", "B", "C", "D"], key="zona_view")
    cari = col_cari.text_input("🔎 Cari nama sekolah / alamat", "", key="cari_view")

    df_f = df[df["zona"].isin(zona_pilih)] if zona_pilih else df
    if cari:
        mask = (
            df_f["nama"].str.contains(cari, case=False, na=False) |
            df_f["alamat"].str.contains(cari, case=False, na=False)
        )
        df_f = df_f[mask]

    m1, m2 = st.columns(2)
    m1.metric("🏫 Total SMP Swasta", len(df))
    m2.metric("🔎 Hasil Filter", len(df_f))

    st.subheader("📋 Daftar SMP Swasta")
    df_swasta_tampil = df_f.rename(columns={
        "nama": "Nama Sekolah", "zona": "Zona",
        "lat": "Latitude", "lon": "Longitude", "alamat": "Alamat",
    })[["Nama Sekolah", "Zona", "Latitude", "Longitude", "Alamat"]]
    st.dataframe(
        bersihkan_kolom_kosong(df_swasta_tampil),
        use_container_width=True, hide_index=True,
    )
    st.download_button(
        "⬇️ Unduh CSV",
        data=df_f.to_csv(index=False),
        file_name="data_smp_swasta.csv",
        mime="text/csv",
    )

# ── Tab 2: Per Zona / Visualisasi ───────────────────────────────────────────
with tab2:
    st.subheader("📊 Visualisasi Data SMP Swasta")

    if "zona" in df.columns:
        st.markdown("##### Jumlah SMP Swasta per Zona")
        ringkas_zona = df.groupby("zona").size().reset_index(name="Jumlah")
        fig_zona = px.bar(ringkas_zona, x="zona", y="Jumlah", color="zona",
                           labels={"zona": "Zona"}, color_discrete_sequence=px.colors.qualitative.Set2)
        fig_zona.update_layout(height=340, showlegend=False)
        st.plotly_chart(fig_zona, use_container_width=True)

    if "lat" in df.columns and "lon" in df.columns:
        st.markdown("##### Sebaran Lokasi SMP Swasta per Wilayah")
        st.caption("Peta diwarnai mengikuti batas kecamatan & Zona SPMB, sama seperti peta di menu Dashboard Admin.")
        daftar_peta_swasta = []
        for _, r in df.dropna(subset=["lat", "lon"]).iterrows():
            daftar_peta_swasta.append({
                "nama": r.get("nama", "-"),
                "zona": r.get("zona", ""),
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "alamat": r.get("alamat", ""),
            })
        peta_swasta_wilayah = buat_peta_wilayah(daftar_peta_swasta, label_layer="SMP Swasta")

        _reload_key_swa = "peta_reload_sekolah_swasta"
        _reload_n_swa = st.session_state.get(_reload_key_swa, 0)
        col_info_swa, col_btn_swa = st.columns([5, 1.4])
        with col_info_swa:
            st.caption(
                "⏳ Peta memuat komponen (Leaflet/marker) dari internet setiap "
                "kali halaman dibuka. Jika area di bawah tampak kosong/putih "
                "lebih dari beberapa detik, klik **Muat Ulang Peta**."
            )
        with col_btn_swa:
            if st.button("🔄 Muat Ulang Peta", key="btn_reload_peta_sekolah_swasta"):
                st.session_state[_reload_key_swa] = _reload_n_swa + 1
                _reload_n_swa += 1
        with st.spinner("🗺️ Menyiapkan peta..."):
            st_folium(
                peta_swasta_wilayah, width=None, height=520, returned_objects=[],
                key=f"peta_sekolah_swasta_{_reload_n_swa}",
            )
        fix_map_tab_render()

# ── Tab 3: Tambah ──────────────────────────────────────────────────────────────
with tab3:
    st.subheader("➕ Tambah Data SMP Swasta")
    st.caption(
        "Isi alamat lebih dulu lalu klik **Cari Koordinat**, latitude & "
        "longitude akan terisi otomatis (bisa disesuaikan manual sebelum disimpan)."
    )

    alamat_cari = st.text_input("📍 Alamat Lengkap *", key="tambah_swasta_alamat",
                                 placeholder="Jl. ..., Kec. ...")
    if st.button("🔍 Cari Koordinat dari Alamat", key="btn_geocode_tambah_swasta"):
        if not alamat_cari:
            st.warning("Isi alamat terlebih dahulu.")
        else:
            with st.spinner("Mencari koordinat..."):
                hasil_geo = geocode_alamat(alamat_cari)
            if not hasil_geo or hasil_geo.get("error"):
                st.error(f"Alamat tidak ditemukan: {hasil_geo.get('error') if hasil_geo else 'tidak ada hasil'}")
            else:
                st.session_state["tambah_swasta_lat"] = hasil_geo["lat"]
                st.session_state["tambah_swasta_lon"] = hasil_geo["lon"]
                st.success(
                    f"✅ Koordinat ditemukan: {hasil_geo['lat']:.6f}, {hasil_geo['lon']:.6f} "
                    f"(Zona terdeteksi: {hasil_geo.get('zona', '-')})"
                )

    with st.form("form_tambah_swasta"):
        c1, c2 = st.columns(2)
        nama   = c1.text_input("Nama Sekolah *", placeholder="SMP ...")
        zona   = c2.selectbox("Zona *", ["A", "B", "C", "D"])
        lat    = c1.number_input("Latitude",  value=float(st.session_state.get("tambah_swasta_lat", -6.9175)), format="%.6f")
        lon    = c2.number_input("Longitude", value=float(st.session_state.get("tambah_swasta_lon", 107.6191)), format="%.6f")
        submit = st.form_submit_button("💾 Simpan", type="primary")

    if submit:
        if not nama:
            st.error("Nama sekolah wajib diisi.")
        else:
            try:
                insert_swasta({
                    "nama": nama, "zona": zona,
                    "lat": lat, "lon": lon, "alamat": alamat_cari,
                })
                st.success(f"✅ '{nama}' berhasil ditambahkan!")
                st.session_state.pop("tambah_swasta_lat", None)
                st.session_state.pop("tambah_swasta_lon", None)
                st.rerun()
            except Exception as e:
                st.error(f"Gagal menyimpan: {e}")

# ── Tab 4: Edit / Hapus ─────────────────────────────────────────────────────
with tab4:
    st.subheader("✏️ Edit atau Hapus Data SMP Swasta")
    if df.empty:
        st.info("Belum ada data SMP Swasta.")
    else:
        opsi = {f"{row['nama']} (Zona {row['zona']})": row["id"] for _, row in df.iterrows()}
        pilihan = st.selectbox("Pilih Sekolah:", list(opsi.keys()))
        selected_id = opsi[pilihan]
        row = df[df["id"] == selected_id].iloc[0]

        new_alamat = st.text_area("📍 Alamat", value=str(row["alamat"]), key="edit_swasta_alamat")
        if st.button("🔍 Cari Ulang Koordinat dari Alamat", key="btn_geocode_edit_swasta"):
            if not new_alamat:
                st.warning("Isi alamat terlebih dahulu.")
            else:
                with st.spinner("Mencari koordinat..."):
                    hasil_geo = geocode_alamat(new_alamat)
                if not hasil_geo or hasil_geo.get("error"):
                    st.error(f"Alamat tidak ditemukan: {hasil_geo.get('error') if hasil_geo else 'tidak ada hasil'}")
                else:
                    st.session_state["edit_swasta_lat"] = hasil_geo["lat"]
                    st.session_state["edit_swasta_lon"] = hasil_geo["lon"]
                    st.success(
                        f"✅ Koordinat ditemukan: {hasil_geo['lat']:.6f}, {hasil_geo['lon']:.6f} "
                        f"(Zona terdeteksi: {hasil_geo.get('zona', '-')})"
                    )

        with st.form("form_edit_swasta"):
            c1, c2 = st.columns(2)
            new_nama   = c1.text_input("Nama Sekolah", value=str(row["nama"]))
            new_zona   = c2.selectbox("Zona", ["A", "B", "C", "D"],
                                       index=["A", "B", "C", "D"].index(str(row["zona"])))
            new_lat    = c1.number_input(
                "Latitude", value=float(st.session_state.get("edit_swasta_lat", row["lat"])), format="%.6f")
            new_lon    = c2.number_input(
                "Longitude", value=float(st.session_state.get("edit_swasta_lon", row["lon"])), format="%.6f")

            col_btn1, col_btn2, _ = st.columns([1, 1, 3])
            simpan = col_btn1.form_submit_button("💾 Update", type="primary")
            hapus  = col_btn2.form_submit_button("🗑️ Hapus", type="secondary")

        if simpan:
            try:
                update_swasta(int(selected_id), {
                    "nama": new_nama, "zona": new_zona,
                    "lat": new_lat, "lon": new_lon, "alamat": new_alamat,
                })
                st.success(f"✅ Data '{new_nama}' diperbarui.")
                st.session_state.pop("edit_swasta_lat", None)
                st.session_state.pop("edit_swasta_lon", None)
                st.rerun()
            except Exception as e:
                st.error(f"Gagal update: {e}")

        if hapus:
            try:
                delete_swasta(int(selected_id))
                st.success(f"🗑️ '{row['nama']}' dihapus.")
                st.rerun()
            except Exception as e:
                st.error(f"Gagal hapus: {e}")
