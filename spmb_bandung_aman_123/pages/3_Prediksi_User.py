"""
pages/3_Prediksi_User.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import math
import streamlit as st
from utils.ui_theme import apply_custom_theme
apply_custom_theme()
import pandas as pd
from streamlit_folium import st_folium

from utils.zona import ZONA_INFO, ZONA_MAP, geocode_alamat, get_info_wilayah_kecamatan
from utils.map_utils import haversine_meter
from utils.peta_zona import buat_peta_zona_kecamatan
from models.predict import prediksi_peluang, get_df_sekolah_clustered
from data.sekolah_data import SEKOLAH_NEGERI, SEKOLAH_SWASTA

if not st.session_state.get("logged_in"):
    st.warning("⛔ Silakan login terlebih dahulu.")
    st.stop()

st.markdown("## 🎯 Cek Peluang Penerimaan Jalur Domisili")
st.caption("Isi data diri dan pilih kecamatan sesuai Kartu Keluarga (KK).")
st.divider()


PROB_THRESHOLD = 60.0

KECAMATAN_LIST = {
    "A": ["Sukasari", "Cidadap", "Coblong", "Cibeunying Kaler",
          "Bandung Wetan", "Sumur Bandung", "Cibeunying Kidul", "Sukajadi"],
    "B": ["Mandalajati", "Antapani", "Arcamanik", "Cinambo",
          "Panyileukan", "Cibiru", "Gedebage", "Rancasari",
          "Ujungberung", "Buahbatu"],
    "C": ["Kiaracondong", "Batununggal", "Lengkong", "Regol", "Bandung Kidul"],
    "D": ["Cicendo", "Andir", "Bandung Kulon", "Babakan Ciparay",
          "Bojongloa Kaler", "Bojongloa Kidul", "Astana Anyar"],
}

all_kecamatan = []
kec_to_zona = {}
for zona, kec_list in KECAMATAN_LIST.items():
    for kec in kec_list:
        all_kecamatan.append(kec)
        kec_to_zona[kec] = zona

KOORDINAT_KECAMATAN = {
    "Sukasari":         (-6.8720, 107.5991),
    "Cidadap":          (-6.8780, 107.6013),
    "Coblong":          (-6.8864, 107.6193),
    "Cibeunying Kaler": (-6.8950, 107.6342),
    "Bandung Wetan":    (-6.9070, 107.6189),
    "Sumur Bandung":    (-6.9139, 107.6077),
    "Cibeunying Kidul": (-6.9006, 107.6453),
    "Sukajadi":         (-6.8913, 107.5967),
    "Mandalajati":      (-6.8900, 107.6968),
    "Antapani":         (-6.9218, 107.6695),
    "Arcamanik":        (-6.9066, 107.6695),
    "Cinambo":          (-6.9270, 107.6968),
    "Panyileukan":      (-6.9419, 107.7049),
    "Cibiru":           (-6.9156, 107.7103),
    "Gedebage":         (-6.9428, 107.6776),
    "Rancasari":        (-6.9518, 107.6832),
    "Ujungberung":      (-6.9073, 107.7049),
    "Buahbatu":         (-6.9503, 107.6631),
    "Kiaracondong":     (-6.9262, 107.6453),
    "Batununggal":      (-6.9385, 107.6453),
    "Lengkong":         (-6.9377, 107.6268),
    "Regol":            (-6.9348, 107.6138),
    "Bandung Kidul":    (-6.9595, 107.6268),
    "Cicendo":          (-6.9148, 107.5967),
    "Andir":            (-6.9187, 107.5826),
    "Bandung Kulon":    (-6.9300, 107.5745),
    "Babakan Ciparay":  (-6.9456, 107.5882),
    "Bojongloa Kaler":  (-6.9283, 107.5799),
    "Bojongloa Kidul":  (-6.9575, 107.5826),
    "Astana Anyar":     (-6.9255, 107.6033),
}


def hitung_jarak_dan_filter(home_lat, home_lon, zona_user):
    # Zona bebas: tidak lagi dibatasi hanya sekolah di zona domisili user
    # (zona_user), semua SMP Negeri se-Kota Bandung ikut dihitung FCM +
    # prediksi RF-nya. Status "dalam_zona" tetap dihitung apa adanya
    # (True hanya kalau zona sekolah == zona domisili user) supaya
    # peluang yang diprediksi RF tetap realistis, lalu sekolah dari zona
    # lain yang punya peluang baik ditampilkan sebagai rekomendasi antar
    # zona di bagian output.
    results = []
    for s in SEKOLAH_NEGERI:
        jarak_m = haversine_meter(home_lat, home_lon, s["lat"], s["lon"])
        zona_sama = (s.get("zona") == zona_user)
        pred = prediksi_peluang(jarak_m, zona_sama, s["nama"])
        if "error" in pred:
            cluster = "Sedang"
            prob = max(0, min(100, (s["jarak_batas"] / max(jarak_m, 1)) * 60))
        else:
            cluster = pred["cluster_label"]
            prob = pred["prob_diterima"]
        results.append({
            "nama": s.get("nama", ""),
            "zona": s.get("zona", ""),
            "zona_sama": zona_sama,
            "jarak_m": round(jarak_m, 1),
            "kuota": s.get("kuota", 0),
            "pendaftar": s.get("pendaftar", 0),
            "jarak_batas": s.get("jarak_batas", 0),
            "cluster": cluster,
            "prob": round(prob, 1),
            "alamat": s.get("alamat", ""),
            "lat": s.get("lat", 0),
            "lon": s.get("lon", 0),
        })
    return sorted(results, key=lambda x: x["prob"], reverse=True)


def rekomendasi_swasta(home_lat, home_lon, zona_user, top_n=5):
    swasta_zona = [s for s in SEKOLAH_SWASTA if s["zona"] == zona_user]
    if not swasta_zona:
        swasta_zona = SEKOLAH_SWASTA
    hasil = []
    for s in swasta_zona:
        item = s.copy()
        item["jarak_m"] = round(haversine_meter(home_lat, home_lon, s["lat"], s["lon"]), 1)
        hasil.append(item)
    return sorted(hasil, key=lambda x: x["jarak_m"])[:top_n]


def titik_radius(lat, lon, radius_m, bearing_deg):
    R = 6371000
    br = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(math.sin(lat1)*math.cos(radius_m/R) +
                     math.cos(lat1)*math.sin(radius_m/R)*math.cos(br))
    lon2 = lon1 + math.atan2(
        math.sin(br)*math.sin(radius_m/R)*math.cos(lat1),
        math.cos(radius_m/R)-math.sin(lat1)*math.sin(lat2)
    )
    return math.degrees(lat2), math.degrees(lon2)


@st.cache_data(show_spinner=False, ttl=86400)
def cek_wilayah_sekolah(sk_lat, sk_lon, jarak_batas_sk):
    """Reverse-geocode 8 titik (N, TL, T, TG, S, BD, B, BL) di sekeliling
    radius batas sekolah. Hasil di-cache 24 jam agar tidak berulang setiap
    kali halaman dibuka. Mengembalikan list detail per titik (arah,
    kelurahan, kecamatan, koordinat) dan daftar kelurahan unik."""
    from geopy.geocoders import Nominatim
    from geopy.extra.rate_limiter import RateLimiter

    geolocator = Nominatim(user_agent="spmb_bandung_cakupan_user_v1")
    reverse = RateLimiter(geolocator.reverse, min_delay_seconds=1.1)

    arah_label = ["Utara", "Timur Laut", "Timur", "Tenggara",
                  "Selatan", "Barat Daya", "Barat", "Barat Laut"]
    wilayah_list = []

    for i, arah in enumerate(arah_label):
        bearing = i * 45
        plat, plon = titik_radius(sk_lat, sk_lon, jarak_batas_sk, bearing)
        try:
            loc = reverse((plat, plon), language="id", addressdetails=True)
            if loc:
                addr = loc.raw.get("address", {})
                kelurahan = (addr.get("village") or addr.get("suburb") or
                            addr.get("neighbourhood") or addr.get("hamlet") or "?")
                kecamatan = (addr.get("city_district") or addr.get("suburb") or "?")
            else:
                kelurahan, kecamatan = "Tidak ditemukan", "-"
        except Exception as e:
            kelurahan, kecamatan = f"Error: {str(e)[:30]}", "-"

        wilayah_list.append({
            "Arah": arah,
            "Kelurahan/Desa": kelurahan,
            "Kecamatan": kecamatan,
            "Koordinat": f"{plat:.5f}, {plon:.5f}",
        })

    kelurahan_unik = sorted(set(
        w["Kelurahan/Desa"] for w in wilayah_list
        if w["Kelurahan/Desa"] not in ["?", "Tidak ditemukan"] and "Error" not in w["Kelurahan/Desa"]
    ))
    return wilayah_list, kelurahan_unik


st.divider()

# ── Form Input ────────────────────────────────────────────────────────────────
st.subheader("📝 Isi Data")
with st.form("form_prediksi"):
    col1, col2 = st.columns(2)
    nama_siswa = col1.text_input("👤 Nama Lengkap Siswa *",
                                  placeholder="Cth: Muhammad Iqbal Fauzi")
    asal_sd    = col2.text_input("🏫 Asal SD *",
                                  placeholder="Cth: SDN Coblong 1")

    col3, col4 = st.columns([2, 1])
    alamat_input     = col3.text_input("📍 Alamat Lengkap (sesuai KK) *",
                                        placeholder="Cth: Jl. Merdeka No.10 RT 01/02")
    kecamatan_input  = col4.selectbox("🏘️ Kecamatan (sesuai KK) *",
                                       options=all_kecamatan)

    submitted = st.form_submit_button("🔍 Cari & Prediksi Peluang",
                                      type="primary", use_container_width=True)

if submitted:
    if not nama_siswa:
        st.error("⚠️ Nama siswa wajib diisi.")
        st.stop()
    if not asal_sd:
        st.error("⚠️ Asal SD wajib diisi.")
        st.stop()
    if not alamat_input:
        st.error("⚠️ Alamat wajib diisi.")
        st.stop()

    zona_user = kec_to_zona.get(kecamatan_input, "A")

    # Geocode alamat asli dulu (sumber koordinat yg sama dgn "Cek Wilayah Cakupan
    # Sekolah") supaya jarak yang dihasilkan konsisten/sinkron di semua bagian.
    # Kalau alamat gagal di-geocode, baru fallback ke titik tengah kecamatan.
    home_display = None
    with st.spinner("📍 Mencari koordinat alamat kamu..."):
        geo_result = geocode_alamat(alamat_input.strip())

    # Map nama kecamatan (lowercase, sesuai ZONA_MAP) -> label baku sesuai
    # KECAMATAN_LIST, dipakai untuk mencocokkan kecamatan hasil deteksi
    # alamat dengan daftar kecamatan resmi di dropdown.
    kec_label_by_lower = {kec.lower(): kec for kec in all_kecamatan}

    if geo_result and "error" not in geo_result:
        # Alamat berhasil ditemukan di peta -> koordinat hasil geocoding ini
        # yang dipakai apa adanya (harus sesuai dengan lokasi di map).
        # Kecamatan & Zona yang ditampilkan/dipakai disamakan dengan
        # kecamatan hasil deteksi alamat (bukan pilihan dropdown), supaya
        # tidak ada info yang berbeda-beda antara alamat dan kecamatan.
        # Kalau kecamatan tidak terdeteksi dari alamat, baru fallback ke
        # kecamatan yang dipilih user di dropdown.
        zona_terdeteksi = geo_result.get("zona")
        kecamatan_terdeteksi = kec_label_by_lower.get(
            (geo_result.get("kecamatan") or "").lower().strip()
        )
        home_lat = geo_result["lat"]
        home_lon = geo_result["lon"]
        home_display = geo_result["display_name"]

        if kecamatan_terdeteksi and kecamatan_terdeteksi != kecamatan_input:
            st.info(
                f"ℹ️ Alamat yang ditemukan ('{home_display}') terdeteksi di "
                f"Kecamatan **{kecamatan_terdeteksi}**, berbeda dari Kecamatan "
                f"**{kecamatan_input}** yang kamu pilih di form. Kecamatan & "
                f"Zona yang dipakai disesuaikan mengikuti alamat, yaitu "
                f"**{kecamatan_terdeteksi}** (Zona {kec_to_zona.get(kecamatan_terdeteksi, zona_terdeteksi)})."
            )
            kecamatan_input = kecamatan_terdeteksi
            zona_user = kec_to_zona.get(kecamatan_terdeteksi, zona_terdeteksi or zona_user)
        elif zona_terdeteksi and zona_terdeteksi != "Tidak Diketahui" and zona_terdeteksi != zona_user:
            st.info(
                f"ℹ️ Alamat yang ditemukan ('{home_display}') terdeteksi di "
                f"**Zona {zona_terdeteksi}**, sedikit berbeda dari Kecamatan "
                f"**{kecamatan_input}** (Zona {zona_user}) yang kamu pilih. "
                "Koordinat tetap mengikuti lokasi di peta (sesuai alamat yang "
                "kamu tulis), dan pencarian sekolah tetap memakai Zona "
                f"**{zona_user}** sesuai Kecamatan pilihanmu."
            )
    else:
        home_lat, home_lon = KOORDINAT_KECAMATAN.get(
            kecamatan_input, (-6.9175, 107.6191)
        )
        st.warning(
            "⚠️ Alamat lengkap tidak ditemukan di peta, jarak dihitung dari "
            f"titik tengah Kecamatan **{kecamatan_input}** (perkiraan)."
        )

    with st.spinner("🤖 Menghitung prediksi Machine Learning..."):
        sekolah_results = hitung_jarak_dan_filter(home_lat, home_lon, zona_user)

    if not sekolah_results:
        st.warning("⚠️ Tidak ada sekolah negeri ditemukan di zona ini.")
        st.stop()

    st.session_state["hasil_prediksi"] = {
        "nama_siswa": nama_siswa,
        "asal_sd": asal_sd,
        "alamat_input": alamat_input,
        "kecamatan_input": kecamatan_input,
        "zona_user": zona_user,
        "home_lat": home_lat,
        "home_lon": home_lon,
        "home_display": home_display,
        "sekolah_results": sekolah_results,
    }

if "hasil_prediksi" in st.session_state:
    data = st.session_state["hasil_prediksi"]
    nama_siswa      = data["nama_siswa"]
    asal_sd         = data["asal_sd"]
    alamat_input    = data["alamat_input"]
    kecamatan_input = data["kecamatan_input"]
    zona_user       = data["zona_user"]
    home_lat        = data["home_lat"]
    home_lon        = data["home_lon"]
    home_display    = data.get("home_display")
    sekolah_results = data["sekolah_results"]

    # ── Info pendaftar ────────────────────────────────────────────────────────
    st.divider()
    st.subheader(f"📋 Hasil Prediksi untuk: **{nama_siswa}**")

    info1, info2 = st.columns(2)
    with info1:
        st.markdown(f"""
        | Data | Keterangan |
        |------|-----------|
        | 👤 Nama | **{nama_siswa}** |
        | 🏫 Asal SD | **{asal_sd}** |
        | 📍 Alamat | {alamat_input} |
        | 🏘️ Kecamatan | **{kecamatan_input}** |
        | 🗺️ Zona Domisili | **Zona {zona_user}** |
        """)
        if home_display:
            st.caption(f"📌 Titik koordinat terdeteksi: {home_display}")
    with info2:
        zi = ZONA_INFO.get(zona_user, {})
        warna = zi.get("warna", "#333")
        kec_list = ", ".join(KECAMATAN_LIST.get(zona_user, []))
        st.markdown(f"""
        <div style='background:{warna}22;border:2px solid {warna};
                    border-radius:12px;padding:16px;text-align:center'>
          <div style='font-size:2.5rem;font-weight:800;color:{warna}'>
            Zona {zona_user}
          </div>
          <div style='font-size:.8rem;color:#444;margin-top:6px'>
            {zi.get("label","")}
          </div>
          <div style='font-size:.75rem;color:#666;margin-top:4px'>
            {kec_list}
          </div>
        </div>""", unsafe_allow_html=True)

    info_wilayah_user = get_info_wilayah_kecamatan(kecamatan_input)
    if info_wilayah_user:
        st.caption(
            f"📊 Kecamatan **{kecamatan_input}**: rasio aksesibilitas 2SFCA "
            f"rata-rata **{info_wilayah_user['rasio_pendaftar_avg']:.2f}** "
            f"(kuota÷pendaftar, akumulasi data 2022/2024/2025/2026 pada "
            f"{info_wilayah_user['jumlah_sekolah']} SMP Negeri di kecamatan "
            f"ini), jarak batas rata-rata "
            f"**{info_wilayah_user['jarak_batas_m_avg']:,.0f} m**."
        )

    st.divider()

    # ── Peta Batas Kecamatan & Zona SPMB ──────────────────────────────────────
    st.subheader("🗺️ Peta Interaktif – Lokasi & Sekolah Terdekat")
    st.caption(
        "🟢 Lingkaran hijau = dalam batas penerimaan | 🔴 Merah = di luar batas | "
        "🔵 Biru putus = radius 3km domisili. Setiap kecamatan diwarnai sesuai Zona "
        "SPMB-nya; zona domisili Anda disorot dengan garis tebal. Hover pada "
        "kecamatan/sekolah untuk detail."
    )
    peta_zona = buat_peta_zona_kecamatan(
        home_lat=home_lat,
        home_lon=home_lon,
        zona_user=zona_user,
        sekolah_list=sekolah_results[:15],
        radius_meter=3000,
    )
    st_folium(peta_zona, width=None, height=520, returned_objects=[])
    # ─────────────────────────────────────────────────────────────────────────

    st.divider()

    # ── Ranking ───────────────────────────────────────────────────────────────
    st.subheader("🏆 Ranking Sekolah Negeri (Zona Bebas – Termasuk Rekomendasi Antar Zona)")
    st.caption(
        "Diurutkan berdasarkan peluang penerimaan tertinggi dari **seluruh zona** "
        "(tidak dibatasi hanya Zona " + zona_user + "), supaya sekolah dari zona "
        "lain yang punya peluang bagus tetap bisa direkomendasikan."
    )
    st.caption(
        "ℹ️ Kolom **Kategori Cluster** (Tinggi/Sedang/Rendah) menunjukkan tingkat "
        "keketatan tiap sekolah, dari rasio aksesibilitas **2SFCA** "
        "(kuota÷pendaftar) yang di-**log-transform** lalu dikategorikan pakai "
        "**rumus M ± 1 SD**: log(rasio) < M−1SD → *Tinggi* (ketat), "
        "M−1SD s/d M+1SD → *Sedang*, log(rasio) ≥ M+1SD → *Rendah* (longgar) "
        "(M = rata-rata, SD = standar deviasi log-rasio 2SFCA seluruh sekolah)."
    )

    df_rank = pd.DataFrame(sekolah_results)[
        ["nama", "zona", "zona_sama", "jarak_m", "kuota", "pendaftar",
         "jarak_batas", "cluster", "prob", "alamat"]
    ].copy()
    df_rank.insert(0, "Rank", range(1, len(df_rank) + 1))
    df_rank.columns = ["Rank", "Nama Sekolah", "Zona", "Zona Sama dengan Anda",
                       "Jarak (m)", "Kuota", "Pendaftar", "Jarak Batas (m)",
                       "Kategori Cluster", "Peluang (%)", "Alamat"]

    st.dataframe(
        df_rank, use_container_width=True, hide_index=True,
        column_config={
            "Peluang (%)": st.column_config.ProgressColumn(
                "Peluang (%)", min_value=0, max_value=100, format="%.1f%%"),
            "Jarak (m)": st.column_config.NumberColumn(
                "Jarak (m)", format="%.0f m"),
            "Jarak Batas (m)": None,
            "Kuota": None,
            "Pendaftar": None,
        }
    )

    # ── Rekomendasi Antar Zona ───────────────────────────────────────────────
    rekomendasi_lintas_zona = [s for s in sekolah_results if not s["zona_sama"]][:5]
    if rekomendasi_lintas_zona:
        st.markdown("**🔁 Rekomendasi Sekolah dari Zona Lain**")
        st.caption(
            "Sekolah di luar Zona " + zona_user + " dengan peluang penerimaan "
            "terbaik, sebagai alternatif lintas zona (tetap perhatikan syarat "
            "domisili resmi SPMB sebelum mendaftar)."
        )
        df_lintas = pd.DataFrame(rekomendasi_lintas_zona)[
            ["nama", "zona", "jarak_m", "cluster", "prob"]
        ].copy()
        df_lintas.columns = ["Nama Sekolah", "Zona", "Jarak (m)", "Kategori Cluster", "Peluang (%)"]
        st.dataframe(
            df_lintas, use_container_width=True, hide_index=True,
            column_config={
                "Peluang (%)": st.column_config.ProgressColumn(
                    "Peluang (%)", min_value=0, max_value=100, format="%.1f%%"),
                "Jarak (m)": st.column_config.NumberColumn(
                    "Jarak (m)", format="%.0f m"),
            }
        )

    st.divider()

    # ── Wilayah Cakupan per Sekolah ───────────────────────────────────────────
    st.subheader("🌍 Wilayah Cakupan Tiap Sekolah (Top 5 Peluang Tertinggi)")
    st.caption(
        "Menampilkan kelurahan/wilayah di sekitar radius batas penerimaan "
        "untuk 5 sekolah dengan peluang penerimaan tertinggi di Zona " + zona_user + ". "
        "Jika alamat KK kamu berada di salah satu wilayah ini dan masih dalam Zona "
        + zona_user + ", besar kemungkinan kamu memenuhi syarat domisili untuk sekolah tersebut."
    )

    st.markdown("""
    <style>
      [data-testid="stExpander"] summary p { font-size: 1.25rem !important; font-weight: 700 !important; }
    </style>
    """, unsafe_allow_html=True)

    if st.button("🔍 Tampilkan Wilayah Cakupan (5 Sekolah Peluang Tertinggi)", type="secondary"):
        st.session_state["tampilkan_wilayah"] = True

    if st.session_state.get("tampilkan_wilayah"):
        top5 = sekolah_results[:5]
        progress = st.progress(0, text="Memulai pengecekan wilayah...")

        for idx, s in enumerate(top5):
            progress.progress((idx+1)/len(top5),
                             text=f"Mengecek wilayah untuk {s['nama']}... ({idx+1}/{len(top5)})")

            wilayah_list, kelurahan_unik = cek_wilayah_sekolah(
                s["lat"], s["lon"], s["jarak_batas"]
            )

            with st.expander(
                f"🏫 **{s['nama']}** — Jarak {s['jarak_m']:,.0f}m | "
                f"Batas {s['jarak_batas']:,.0f}m | Peluang {s['prob']:.1f}%",
                expanded=(idx == 0)
            ):
                c1, c2 = st.columns([1, 2])
                with c1:
                    st.metric("Jarak Anda ke Sekolah", f"{s['jarak_m']:,.0f} m")
                    st.metric("Batas Penerimaan", f"{s['jarak_batas']:,.0f} m")
                    st.metric("Peluang Diterima", f"{s['prob']:.1f}%")
                    if s["jarak_m"] <= s["jarak_batas"]:
                        st.success(f"✅ **MASUK** radius batas penerimaan.")
                    else:
                        selisih = s["jarak_m"] - s["jarak_batas"]
                        st.error(f"❌ **DI LUAR** radius, selisih {selisih:,.0f} m.")
                with c2:
                    if kelurahan_unik:
                        st.markdown("**📍 Wilayah/Kelurahan dalam radius batas penerimaan:**")
                        for k in kelurahan_unik:
                            st.markdown(f"- {k}")
                    else:
                        st.info("Wilayah belum dapat diidentifikasi (coba lagi nanti).")
                    st.caption(f"📌 Alamat sekolah: {s['alamat']}")

                st.markdown("**📋 Detail Titik Batas Radius (8 Arah Mata Angin):**")
                df_wilayah = pd.DataFrame(wilayah_list)
                st.dataframe(df_wilayah, use_container_width=True, hide_index=True)

                st.markdown("**🗺️ Visualisasi Radius**")
                import folium
                m_cakupan = folium.Map(location=[s["lat"], s["lon"]], zoom_start=14)
                folium.Marker(
                    [s["lat"], s["lon"]], tooltip=s["nama"],
                    icon=folium.Icon(color="red", icon="graduation-cap", prefix="fa")
                ).add_to(m_cakupan)
                folium.Circle(
                    [s["lat"], s["lon"]], radius=s["jarak_batas"], color="#3498db",
                    fill=True, fill_opacity=0.1,
                    tooltip=f"Radius {s['jarak_batas']:,.0f}m"
                ).add_to(m_cakupan)
                for w in wilayah_list:
                    plat, plon = map(float, w["Koordinat"].split(", "))
                    folium.CircleMarker(
                        [plat, plon], radius=6, color="#e74c3c", fill=True,
                        fill_opacity=0.8,
                        tooltip=f"{w['Arah']}: {w['Kelurahan/Desa']}"
                    ).add_to(m_cakupan)
                folium.Marker(
                    [home_lat, home_lon],
                    tooltip=f"🏠 Lokasi kamu: {home_display or alamat_input}",
                    icon=folium.Icon(color="green", icon="home", prefix="fa")
                ).add_to(m_cakupan)
                folium.PolyLine(
                    [[home_lat, home_lon], [s["lat"], s["lon"]]],
                    color="#2ecc71", weight=2, dash_array="5"
                ).add_to(m_cakupan)
                st_folium(m_cakupan, width=None, height=420,
                         returned_objects=[], key=f"peta_cakupan_{idx}")

        progress.empty()
        st.success("✅ Pengecekan wilayah selesai!")

    st.divider()

    # ── Detail Sekolah ────────────────────────────────────────────────────────
    st.subheader("🔍 Detail Prediksi Sekolah Tertentu")
    nama_pilihan = st.selectbox(
        "Pilih sekolah untuk melihat detail:",
        [s["nama"] for s in sekolah_results]
    )
    if nama_pilihan:
        s_detail = next(s for s in sekolah_results if s["nama"] == nama_pilihan)

        kec_sekolah = None
        m_alamat = pd.Series([s_detail.get("alamat", "")]).str.extract(
            r"Kec\.\s*([A-Za-z .]+)"
        )[0]
        if not m_alamat.empty and pd.notna(m_alamat.iloc[0]):
            kec_sekolah = m_alamat.iloc[0].strip().rstrip(".").strip()

        info_wilayah = get_info_wilayah_kecamatan(kec_sekolah) if kec_sekolah else None
        if info_wilayah:
            rasio_tampil = f"{info_wilayah['rasio_pendaftar_avg']:.2f}"
        else:
            rasio_tampil = f"Zona {s_detail['zona']}"

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("📏 Jarak",          f"{s_detail['jarak_m']:,.0f} m")
        d2.metric("🧭 Rasio Aksesibilitas Wilayah", rasio_tampil)
        d3.metric("🎯 Peluang",        f"{s_detail['prob']:.1f}%")
        d4.metric("📐 Batas Historis", f"{s_detail['jarak_batas']:,.0f} m")

        if info_wilayah:
            st.caption(
                f"ℹ️ Kecamatan {kec_sekolah} (Zona {info_wilayah['zona']}): rasio "
                f"aksesibilitas 2SFCA rata-rata {info_wilayah['rasio_pendaftar_avg']:.2f} "
                f"(kuota÷pendaftar, data 2022/2024/2025/2026 pada "
                f"{info_wilayah['jumlah_sekolah']} SMP Negeri) dengan jarak batas "
                f"rata-rata {info_wilayah['jarak_batas_m_avg']:,.0f} m. Semakin "
                f"besar rasionya, semakin lega daya tampung dibanding jumlah "
                f"pendaftar di wilayah itu."
            )

        if s_detail["jarak_m"] <= s_detail["jarak_batas"]:
            st.success(f"✅ Lokasi kamu **dalam batas penerimaan** sekolah ini ({s_detail['jarak_m']:,.0f}m ≤ {s_detail['jarak_batas']:,.0f}m)")
        else:
            st.warning(f"⚠️ Lokasi kamu **di luar batas penerimaan** sekolah ini ({s_detail['jarak_m']:,.0f}m > {s_detail['jarak_batas']:,.0f}m) — namun masih bisa masuk jika dalam radius 3.000m")

        import plotly.graph_objects as go
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=s_detail["prob"],
            title={"text": f"Peluang Masuk – {nama_pilihan}"},
            delta={"reference": 50},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#3f51b5"},
                "steps": [
                    {"range": [0,  40], "color": "#fde8e8"},
                    {"range": [40, 70], "color": "#fef3e2"},
                    {"range": [70,100], "color": "#e8f8f0"},
                ],
                "threshold": {"line": {"color": "red", "width": 3},
                              "thickness": 0.85, "value": PROB_THRESHOLD},
            }
        ))
        fig_gauge.update_layout(height=280, margin=dict(t=40, b=10, l=20, r=20))
        st.plotly_chart(fig_gauge, use_container_width=True)

        prob = s_detail["prob"]
        if prob >= 75:
            st.success(f"✅ **Peluang Tinggi ({prob:.1f}%)** — Sangat disarankan mendaftar!")
        elif prob >= PROB_THRESHOLD:
            st.info(f"ℹ️ **Peluang Sedang ({prob:.1f}%)** — Memungkinkan, persaingan cukup ketat.")
        else:
            st.warning(f"⚠️ **Peluang Rendah ({prob:.1f}%)** — Pertimbangkan sekolah swasta.")

    st.divider()

    # ── Rekomendasi Swasta ────────────────────────────────────────────────────
    avg_prob = sum(s["prob"] for s in sekolah_results) / max(len(sekolah_results), 1)
    st.subheader("💡 Rekomendasi SMP Swasta Terdekat")

    if avg_prob < PROB_THRESHOLD:
        st.warning(
            f"Rata-rata peluang masuk SMP Negeri di Zona **{zona_user}** "
            f"adalah **{avg_prob:.1f}%**. Berikut alternatif SMP Swasta:"
        )
    else:
        st.success(
            f"✅ Rata-rata peluang **{avg_prob:.1f}%** — Peluang bagus! "
            "Berikut pilihan SMP Swasta jika dibutuhkan:"
        )

    swasta_recs = rekomendasi_swasta(home_lat, home_lon, zona_user,
                                     top_n=5 if avg_prob < PROB_THRESHOLD else 3)
    for i, sw in enumerate(swasta_recs, 1):
        with st.container():
            s1, s2, s3 = st.columns([3, 2, 2])
            s1.markdown(f"**{i}. {sw['nama']}**  \n📌 {sw['alamat']}")
            s2.metric("Jarak", f"{sw['jarak_m']:,.0f} m")
            s3.markdown(f"**Zona:** {sw['zona']}")
        st.divider()