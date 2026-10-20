"""
pages/2_Kelola_Sekolah.py
CRUD data sekolah (Admin only).
Data utama dari Supabase; fallback ke data statis jika Supabase belum dikonfigurasi.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from utils.ui_theme import apply_custom_theme
apply_custom_theme()
import pandas as pd
import plotly.express as px
from streamlit_folium import st_folium
from utils.supabase_client import (
    get_supabase_client, get_all_sekolah,
    insert_sekolah, update_sekolah, delete_sekolah
)
from utils.negeri_store import load_negeri, insert_negeri, update_negeri, delete_negeri
from data.sekolah_data import SEKOLAH_NEGERI
from utils.zona import geocode_alamat
from utils.map_utils import buat_peta_wilayah, fix_map_tab_render
from utils.dataset_loader import bersihkan_kolom_kosong

if not st.session_state.get("logged_in") or st.session_state.get("user_role") != "admin":
    st.warning("⛔ Halaman ini hanya untuk Admin.")
    st.stop()

st.markdown("## 🏫 Kelola Data Sekolah – Admin SPMB Bandung")
st.caption("Tambah, edit, atau hapus data sekolah, kuota, dan radius domisili.")
st.divider()


# ── Load data (Supabase atau fallback statis) ──────────────────────────────────
@st.cache_data(ttl=30)
def load_data():
    try:
        data = get_all_sekolah()
        if data:
            return pd.DataFrame(data), "supabase"
    except Exception:
        pass
    # Fallback ke penyimpanan lokal (JSON) — data tetap tersimpan permanen
    return pd.DataFrame(load_negeri()), "local"


df, sumber = load_data()


# ── Tab ────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(
    ["📋 Lihat Data", "➕ Tambah Sekolah", "✏️ Edit / Hapus", "📊 Visualisasi"]
)

with tab1:
    st.subheader(f"Data Sekolah ({len(df)} record)")
    zona_sel = st.multiselect("Filter Zona:", ["A", "B", "C", "D"],
                               default=["A", "B", "C", "D"])
    df_show = df[df["zona"].isin(zona_sel)] if "zona" in df.columns else df
    st.dataframe(bersihkan_kolom_kosong(df_show), use_container_width=True, hide_index=True)

with tab2:
    st.subheader("➕ Tambah Data Sekolah Baru")
    st.caption(
        "Isi alamat lebih dulu lalu klik **Cari Koordinat**, latitude & "
        "longitude akan terisi otomatis (bisa disesuaikan manual sebelum disimpan)."
    )

    alamat_cari = st.text_input("📍 Alamat Lengkap *", key="tambah_sekolah_alamat",
                                 placeholder="Jl. ..., Kec. ...")
    if st.button("🔍 Cari Koordinat dari Alamat", key="btn_geocode_tambah"):
        if not alamat_cari:
            st.warning("Isi alamat terlebih dahulu.")
        else:
            with st.spinner("Mencari koordinat..."):
                hasil_geo = geocode_alamat(alamat_cari)
            if not hasil_geo or hasil_geo.get("error"):
                st.error(f"Alamat tidak ditemukan: {hasil_geo.get('error') if hasil_geo else 'tidak ada hasil'}")
            else:
                st.session_state["tambah_sekolah_lat"] = hasil_geo["lat"]
                st.session_state["tambah_sekolah_lon"] = hasil_geo["lon"]
                st.success(
                    f"✅ Koordinat ditemukan: {hasil_geo['lat']:.6f}, {hasil_geo['lon']:.6f} "
                    f"(Zona terdeteksi: {hasil_geo.get('zona', '-')})"
                )

    with st.form("form_tambah"):
        c1, c2 = st.columns(2)
        nama    = c1.text_input("Nama Sekolah *", placeholder="SMP Negeri XX")
        zona    = c2.selectbox("Zona *", ["A", "B", "C", "D"])
        kuota   = c1.number_input("Kuota", min_value=0, value=120)
        pendaftar = c2.number_input("Jumlah Pendaftar (historis)", min_value=0, value=120)
        jarak_batas = c1.number_input("Jarak Batas Penerimaan (meter)", min_value=0.0, value=800.0)
        lat     = c1.number_input("Latitude",  value=float(st.session_state.get("tambah_sekolah_lat", -6.9175)), format="%.6f")
        lon     = c2.number_input("Longitude", value=float(st.session_state.get("tambah_sekolah_lon", 107.6191)), format="%.6f")
        submit  = st.form_submit_button("💾 Simpan", type="primary")

    if submit:
        if not nama:
            st.error("Nama sekolah wajib diisi.")
        else:
            try:
                if sumber == "supabase":
                    data_baru = {
                        "nama_sekolah": nama, "zona": zona,
                        "kuota": kuota, "pendaftar": pendaftar,
                        "jarak_batas": jarak_batas,
                        "lat": lat, "lon": lon, "alamat": alamat_cari,
                    }
                    insert_sekolah(data_baru)
                else:
                    data_baru = {
                        "nama": nama, "zona": zona,
                        "kuota": kuota, "pendaftar": pendaftar,
                        "jarak_batas": jarak_batas,
                        "lat": lat, "lon": lon, "alamat": alamat_cari,
                    }
                    insert_negeri(data_baru)
                st.success(f"✅ Sekolah '{nama}' berhasil ditambahkan!")
                st.session_state.pop("tambah_sekolah_lat", None)
                st.session_state.pop("tambah_sekolah_lon", None)
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Gagal menyimpan: {e}")

with tab3:
    st.subheader("✏️ Edit atau Hapus Data Sekolah")
    nama_list = df["nama"].tolist() if "nama" in df.columns else df.get("nama_sekolah", pd.Series()).tolist()

    selected_nama = st.selectbox("Pilih Sekolah:", nama_list)
    if selected_nama:
        col_nama = "nama" if "nama" in df.columns else "nama_sekolah"
        row = df[df[col_nama] == selected_nama].iloc[0]

        alamat_edit = st.text_area("📍 Alamat", value=str(row.get("alamat", "")), key="edit_sekolah_alamat")
        if st.button("🔍 Cari Ulang Koordinat dari Alamat", key="btn_geocode_edit"):
            if not alamat_edit:
                st.warning("Isi alamat terlebih dahulu.")
            else:
                with st.spinner("Mencari koordinat..."):
                    hasil_geo = geocode_alamat(alamat_edit)
                if not hasil_geo or hasil_geo.get("error"):
                    st.error(f"Alamat tidak ditemukan: {hasil_geo.get('error') if hasil_geo else 'tidak ada hasil'}")
                else:
                    st.session_state["edit_sekolah_lat"] = hasil_geo["lat"]
                    st.session_state["edit_sekolah_lon"] = hasil_geo["lon"]
                    st.success(
                        f"✅ Koordinat ditemukan: {hasil_geo['lat']:.6f}, {hasil_geo['lon']:.6f} "
                        f"(Zona terdeteksi: {hasil_geo.get('zona', '-')})"
                    )

        with st.form("form_edit"):
            c1, c2 = st.columns(2)
            new_zona        = c1.selectbox("Zona", ["A","B","C","D"],
                                            index=["A","B","C","D"].index(str(row.get("zona","A"))))
            new_kuota       = c2.number_input("Kuota", value=int(row.get("kuota", 120)))
            new_pendaftar   = c1.number_input("Pendaftar", value=int(row.get("pendaftar", 120)))
            new_jarak_batas = c2.number_input("Jarak Batas (m)", value=float(row.get("jarak_batas", 800)))
            new_lat         = c1.number_input(
                "Latitude",
                value=float(st.session_state.get("edit_sekolah_lat", row.get("lat", -6.9175))),
                format="%.6f",
            )
            new_lon         = c2.number_input(
                "Longitude",
                value=float(st.session_state.get("edit_sekolah_lon", row.get("lon", 107.6191))),
                format="%.6f",
            )

            col_btn1, col_btn2, _ = st.columns([1, 1, 3])
            simpan = col_btn1.form_submit_button("💾 Update", type="primary")
            hapus  = col_btn2.form_submit_button("🗑️ Hapus", type="secondary")
        new_alamat = alamat_edit

        if simpan:
            data_update = {
                "zona": new_zona, "kuota": new_kuota,
                "pendaftar": new_pendaftar, "jarak_batas": new_jarak_batas,
                "lat": new_lat, "lon": new_lon, "alamat": new_alamat,
            }
            try:
                if sumber == "supabase":
                    update_sekolah(int(row.get("id", 0)), data_update)
                else:
                    update_negeri(int(row.get("id", 0)), data_update)
                st.success(f"✅ Data '{selected_nama}' diperbarui.")
                st.session_state.pop("edit_sekolah_lat", None)
                st.session_state.pop("edit_sekolah_lon", None)
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Gagal update: {e}")

        if hapus:
            try:
                if sumber == "supabase":
                    delete_sekolah(int(row.get("id", 0)))
                else:
                    delete_negeri(int(row.get("id", 0)))
                st.success(f"🗑️ '{selected_nama}' dihapus.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Gagal hapus: {e}")

with tab4:
    st.subheader("📊 Visualisasi Data Sekolah")
    col_zona = "zona" if "zona" in df.columns else None
    col_kuota = "kuota" if "kuota" in df.columns else None
    col_pendaftar = "pendaftar" if "pendaftar" in df.columns else None

    if col_zona:
        st.markdown("##### Jumlah Sekolah per Zona")
        ringkas_zona = df.groupby(col_zona).size().reset_index(name="Jumlah")
        fig_zona = px.bar(ringkas_zona, x=col_zona, y="Jumlah", color=col_zona,
                           labels={col_zona: "Zona"}, color_discrete_sequence=px.colors.qualitative.Set2)
        fig_zona.update_layout(height=340, showlegend=False)
        st.plotly_chart(fig_zona, use_container_width=True)

    if col_kuota and col_pendaftar:
        st.markdown("##### Kuota vs Pendaftar per Sekolah (Top 20 Pendaftar Terbanyak)")
        df_top = df.sort_values(col_pendaftar, ascending=False).head(20)
        nama_col = "nama" if "nama" in df.columns else "nama_sekolah"
        fig_kp = px.bar(
            df_top, x=nama_col, y=[col_kuota, col_pendaftar], barmode="group",
            labels={"value": "Jumlah", nama_col: "Sekolah", "variable": "Kategori"},
            color_discrete_sequence=["#3f51b5", "#f44336"],
        )
        fig_kp.update_layout(height=420, xaxis_tickangle=-45, xaxis_tickfont_size=9, margin=dict(b=150))
        st.plotly_chart(fig_kp, use_container_width=True)

    if "lat" in df.columns and "lon" in df.columns:
        st.markdown("##### Sebaran Lokasi Sekolah per Wilayah")
        st.caption("Peta diwarnai mengikuti batas kecamatan & Zona SPMB, sama seperti peta di menu Dashboard Admin.")
        nama_col_peta = "nama" if "nama" in df.columns else "nama_sekolah"
        alamat_col_peta = "alamat" if "alamat" in df.columns else None
        daftar_peta = []
        for _, r in df.dropna(subset=["lat", "lon"]).iterrows():
            daftar_peta.append({
                "nama": r.get(nama_col_peta, "-"),
                "zona": r.get("zona", ""),
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "alamat": r.get(alamat_col_peta, "") if alamat_col_peta else "",
            })
        peta_sekolah_wilayah = buat_peta_wilayah(daftar_peta, label_layer="Sekolah Negeri")

        _reload_key_neg = "peta_reload_sekolah_negeri"
        _reload_n_neg = st.session_state.get(_reload_key_neg, 0)
        col_info_neg, col_btn_neg = st.columns([5, 1.4])
        with col_info_neg:
            st.caption(
                "⏳ Peta memuat komponen (Leaflet/marker) dari internet setiap "
                "kali halaman dibuka. Jika area di bawah tampak kosong/putih "
                "lebih dari beberapa detik, klik **Muat Ulang Peta**."
            )
        with col_btn_neg:
            if st.button("🔄 Muat Ulang Peta", key="btn_reload_peta_sekolah_negeri"):
                st.session_state[_reload_key_neg] = _reload_n_neg + 1
                _reload_n_neg += 1
        with st.spinner("🗺️ Menyiapkan peta..."):
            st_folium(
                peta_sekolah_wilayah, width=None, height=520, returned_objects=[],
                key=f"peta_sekolah_negeri_{_reload_n_neg}",
            )
        fix_map_tab_render()
