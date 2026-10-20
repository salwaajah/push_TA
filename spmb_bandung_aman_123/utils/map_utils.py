"""
utils/map_utils.py
Builder peta Folium dengan radius batas per sekolah dari data nyata.
"""

import html
import uuid

import folium
import streamlit as st
from folium.plugins import MarkerCluster
import math

from utils.zona import ZONA_INFO
from utils.peta_zona import _load_geojson, _KECAMATAN_KE_ZONA, _normalisasi

ZONA_COLORS  = {"A": "blue", "B": "green", "C": "beige", "D": "red"}
ZONA_HEX     = {"A": "#3498db", "B": "#2ecc71", "C": "#f1c40f", "D": "#e74c3c"}
CLUSTER_COLORS = {"Tinggi": "#e74c3c", "Sedang": "#f1c40f", "Rendah": "#2ecc71"}
CLUSTER_TAMPIL = {"Tinggi": "Ketat", "Sedang": "Sedang", "Rendah": "Longgar"}


def _tambah_batas_kecamatan(m: folium.Map) -> None:
    """Tambahkan layer batas wilayah kecamatan (diwarnai per Zona SPMB)
    ke peta, supaya tampilannya rapi seperti peta batas zona (gambar
    referensi ke-2 user), tanpa mengubah marker/lingkaran sekolah yang
    sudah ada di peta."""
    geo = _load_geojson()

    def _style(feature):
        nama_kec = feature["properties"].get("nama_kecamatan", "")
        zona_kec = _KECAMATAN_KE_ZONA.get(_normalisasi(nama_kec))
        warna = ZONA_INFO.get(zona_kec, {}).get("warna", "#9aa0a6")
        return {"fillColor": warna, "color": "#1a1a2e", "weight": 1.2, "fillOpacity": 0.22}

    def _highlight(_feature):
        return {"fillOpacity": 0.4, "weight": 2.5}

    folium.GeoJson(
        geo,
        name="Batas Kecamatan & Zona SPMB",
        style_function=_style,
        highlight_function=_highlight,
        tooltip=folium.GeoJsonTooltip(fields=["nama_kecamatan"], aliases=["Kecamatan:"], sticky=True),
    ).add_to(m)


def haversine_meter(lat1, lon1, lat2, lon2) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def buat_peta_user(
    home_lat, home_lon,
    sekolah_list,
    zona_user="",
    radius_meter=3000,
) -> folium.Map:
    m = folium.Map(location=[home_lat, home_lon], zoom_start=14,
                   tiles="OpenStreetMap")

    # Lingkaran radius domisili 3000m dari rumah
    folium.Circle(
        location=[home_lat, home_lon],
        radius=radius_meter,
        color="#3498db",
        fill=True,
        fill_opacity=0.05,
        weight=2,
        dash_array="6",
        tooltip=f"Radius Domisili {radius_meter:,} m",
    ).add_to(m)

    # Marker rumah
    folium.Marker(
        location=[home_lat, home_lon],
        tooltip="📍 Rumah Anda",
        popup=folium.Popup("🏠 <b>Lokasi Rumah Anda</b>", max_width=200),
        icon=folium.Icon(color="lightblue", icon="home", prefix="fa"),
    ).add_to(m)

    # Setiap sekolah: marker + lingkaran radius batas penerimaan
    mc = MarkerCluster(name="Sekolah Negeri").add_to(m)

    for s in sekolah_list:
        warna      = ZONA_COLORS.get(s.get("zona", ""), "gray")
        warna_hex  = ZONA_HEX.get(s.get("zona", ""), "#888")
        cluster    = s.get("cluster", "")
        prob       = s.get("prob", 0)
        jarak      = s.get("jarak_m", 0)
        jarak_batas = s.get("jarak_batas", 800)

        # ── Lingkaran radius batas penerimaan per sekolah ──
        # Warna lingkaran: hijau jika rumah dalam batas, merah jika di luar
        dalam_batas = jarak <= jarak_batas
        warna_circle = "#2ecc71" if dalam_batas else "#e74c3c"
        status_label = "✅ Dalam Batas" if dalam_batas else "❌ Di Luar Batas"

        folium.Circle(
            location=[s["lat"], s["lon"]],
            radius=jarak_batas,
            color=warna_circle,
            fill=True,
            fill_opacity=0.08,
            weight=1.5,
            tooltip=f"{s['nama']} – Batas {jarak_batas:,.0f}m ({status_label})",
        ).add_to(m)

        # ── Popup detail ──
        popup_html = f"""
        <div style='min-width:230px;font-family:sans-serif;font-size:13px'>
          <b>🏫 {s['nama']}</b><br>
          <hr style='margin:4px 0'>
          📍 Zona: <b>{s.get('zona','?')}</b><br>
          📏 Jarak rumah ke sekolah: <b>{jarak:,.0f} m</b><br>
          📐 Batas penerimaan: <b>{jarak_batas:,.0f} m</b><br>
          {status_label}<br>
          🔥 Keketatan: <b style='color:{CLUSTER_COLORS.get(cluster,"#333")}'>{CLUSTER_TAMPIL.get(cluster, cluster)}</b><br>
          🎯 Peluang: <b>{prob:.1f}%</b><br>
          📌 {s.get('alamat','—')}
        </div>"""

        folium.Marker(
            location=[s["lat"], s["lon"]],
            tooltip=f"🏫 {s['nama']} | {jarak:,.0f}m | {status_label}",
            popup=folium.Popup(popup_html, max_width=290),
            icon=folium.Icon(color=warna, icon="graduation-cap", prefix="fa"),
        ).add_to(mc)

    # Legend
    legend_html = f"""
    <div style='position:fixed;bottom:30px;left:30px;z-index:999;
                background:white;padding:12px 16px;border-radius:10px;
                box-shadow:0 2px 10px rgba(0,0,0,.25);font-size:12px'>
      <b>Keterangan Lingkaran</b><br>
      <span style='color:#2ecc71'>●</span> Dalam batas penerimaan<br>
      <span style='color:#e74c3c'>●</span> Di luar batas penerimaan<br>
      <span style='color:#3498db'>- -</span> Radius domisili 3.000 m<br>
      <hr style='margin:6px 0'>
      <b>Zona</b><br>
      <span style='color:#3498db'>●</span> A &nbsp;
      <span style='color:#2ecc71'>●</span> B &nbsp;
      <span style='color:#f1c40f'>●</span> C &nbsp;
      <span style='color:#e74c3c'>●</span> D
    </div>"""
    m.get_root().html.add_child(folium.Element(legend_html))
    folium.LayerControl().add_to(m)
    return m


def buat_peta_wilayah(daftar_lokasi, label_layer="Sekolah") -> folium.Map:
    """Peta sebaran lokasi (sekolah negeri/swasta) dengan layer batas
    wilayah kecamatan yang diwarnai per Zona SPMB (sama seperti peta di
    menu Dashboard Admin), supaya persebaran lokasi terlihat per-wilayah
    dan tidak cuma titik polos seperti st.map biasa.

    daftar_lokasi: list of dict dengan minimal key 'nama', 'zona', 'lat', 'lon'
    (key 'alamat' opsional, ditampilkan di popup bila ada)."""
    if not daftar_lokasi:
        return folium.Map(location=[-6.9175, 107.6191], zoom_start=12, tiles="OpenStreetMap")

    center_lat = sum(s["lat"] for s in daftar_lokasi) / len(daftar_lokasi)
    center_lon = sum(s["lon"] for s in daftar_lokasi) / len(daftar_lokasi)

    m = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles="OpenStreetMap")

    _tambah_batas_kecamatan(m)

    mc = MarkerCluster(name=label_layer).add_to(m)
    for s in daftar_lokasi:
        zona = s.get("zona", "")
        warna_hex = ZONA_HEX.get(zona, "#888888")
        alamat = s.get("alamat", "")
        popup_html = f"""
        <div style='min-width:220px;font-family:sans-serif;font-size:13px'>
          <b>🏫 {s.get('nama', '-')}</b><br><hr style='margin:4px 0'>
          📍 Zona: <b style='color:{warna_hex}'>{zona or '-'}</b><br>
          {"📌 " + alamat + "<br>" if alamat else ""}
        </div>"""

        folium.CircleMarker(
            location=[s["lat"], s["lon"]],
            radius=9,
            color=warna_hex,
            fill=True,
            fill_color=warna_hex,
            fill_opacity=0.85,
            weight=2,
            tooltip=f"{s.get('nama', '-')} (Zona {zona or '-'})",
            popup=folium.Popup(popup_html, max_width=280),
        ).add_to(mc)

    legend_html = """
    <div style='position:fixed;bottom:30px;left:30px;z-index:999;
                background:white;padding:10px 16px;border-radius:8px;
                box-shadow:0 2px 8px rgba(0,0,0,.3);font-size:12px'>
      <b>Zona SPMB (mengikuti batas kecamatan)</b><br>
      <span style='color:#3498db'>●</span> A &nbsp;
      <span style='color:#2ecc71'>●</span> B &nbsp;
      <span style='color:#f1c40f'>●</span> C &nbsp;
      <span style='color:#e74c3c'>●</span> D
    </div>"""
    m.get_root().html.add_child(folium.Element(legend_html))
    folium.LayerControl().add_to(m)
    return m


def buat_peta_admin(sekolah_list) -> folium.Map:
    if not sekolah_list:
        return folium.Map(location=[-6.9175, 107.6191], zoom_start=13)

    center_lat = sum(s["lat"] for s in sekolah_list) / len(sekolah_list)
    center_lon = sum(s["lon"] for s in sekolah_list) / len(sekolah_list)

    m = folium.Map(location=[center_lat, center_lon], zoom_start=13,
                   tiles="OpenStreetMap")

    _tambah_batas_kecamatan(m)

    for s in sekolah_list:
        cluster     = s.get("cluster", "Sedang")
        warna_hex   = CLUSTER_COLORS.get(cluster, "#888888")
        jarak_batas = s.get("jarak_batas", 800)
        rasio       = s.get("rasio_pendaftar", 1.0)

        # Lingkaran radius batas per sekolah
        folium.Circle(
            location=[s["lat"], s["lon"]],
            radius=jarak_batas,
            color=warna_hex,
            fill=True,
            fill_opacity=0.10,
            weight=1.5,
            tooltip=f"{s['nama']} – Batas {jarak_batas:,.0f}m",
        ).add_to(m)

        popup_html = f"""
        <div style='min-width:200px;font-family:sans-serif;font-size:13px'>
          <b>{s['nama']}</b><br><hr style='margin:4px 0'>
          Zona: <b>{s.get('zona','?')}</b><br>
          Kuota: <b>{s.get('kuota',0)}</b><br>
          Pendaftar: <b>{s.get('pendaftar',0)}</b><br>
          Rasio Aksesibilitas 2SFCA: <b>{rasio:.2f}</b><br>
          Batas Jarak: <b>{jarak_batas:,.0f} m</b><br>
          Cluster: <span style='color:{warna_hex}'><b>{CLUSTER_TAMPIL.get(cluster, cluster)}</b></span>
        </div>"""

        folium.CircleMarker(
            location=[s["lat"], s["lon"]],
            radius=10,
            color=warna_hex,
            fill=True,
            fill_color=warna_hex,
            fill_opacity=0.8,
            tooltip=f"{s['nama']} – {cluster}",
            popup=folium.Popup(popup_html, max_width=260),
        ).add_to(m)

    # Legend
    legend_html = """
    <div style='position:fixed;bottom:30px;left:30px;z-index:999;
                background:white;padding:10px 16px;border-radius:8px;
                box-shadow:0 2px 8px rgba(0,0,0,.3);font-size:12px'>
      <b>Tingkat Keketatan</b><br>
      <span style='color:#e74c3c'>●</span> Ketat<br>
      <span style='color:#f1c40f'>●</span> Sedang<br>
      <span style='color:#2ecc71'>●</span> Longgar<br>
      <hr style='margin:4px 0'>
      <small>Lingkaran = radius batas penerimaan</small>
    </div>"""
    m.get_root().html.add_child(folium.Element(legend_html))
    folium.LayerControl().add_to(m)
    return m


def _inject_iframe_js_code(source: str) -> None:
    """Sisipkan kode JS supaya jalan di context dokumen PARENT (bukan di
    dalam tab yang sedang disembunyikan), lewat trik iframe javascript: URL.
    Referensi: https://github.com/randyzwitch/streamlit-folium/issues/128
    """
    div_id = uuid.uuid4()
    st.markdown(
        f"""
        <div style="height:0;width:0;overflow:hidden;" id="{div_id}">
        <iframe src="javascript: \
        var script = document.createElement('script'); \
        script.type = 'text/javascript'; \
        script.text = {html.escape(repr(source))}; \
        var div = window.parent.document.getElementById('{div_id}'); \
        div.appendChild(script); \
        "></iframe>
        </div>
        """,
        unsafe_allow_html=True,
    )


def fix_map_tab_render() -> None:
    """Perbaikan supaya peta Folium (st_folium) tidak blank/kosong ketika
    halaman di-refresh, karena peta ditempatkan di dalam st.tabs yang bukan
    tab aktif pertama. Streamlit merender konten semua tab ke DOM, tapi tab
    yang tidak aktif sempat mendapat tinggi 0px saat komponen iframe peta
    pertama kali dimuat, sehingga ukuran peta Leaflet "terkunci" ke 0 dan
    tetap kosong walau tab dibuka (baru muncul lagi setelah ada interaksi
    apapun di halaman). Fungsi ini memaksa iframe peta yang tingginya
    kepatok 0 untuk diset ulang ke tinggi sebenarnya, dicek berkala dan juga
    setiap ada klik di halaman. Panggil fungsi ini tepat setelah pemanggilan
    st_folium(...).
    """
    source = """
    (function() {
        var attempts = 0;
        var maxAttempts = 20;
        var intervalMs = 250;

        function perbaikiTinggiIframe() {
            var intervalId = setInterval(function() {
                var iframes = document.querySelectorAll('iframe[title*="folium"]');
                if (iframes.length > 0 || attempts > maxAttempts) {
                    iframes.forEach(function(iframe) {
                        if (!iframe.style.height || iframe.style.height === "0px" || iframe.height === "0") {
                            iframe.style.height = "100%";
                            iframe.style.minHeight = "400px";
                        }
                    });
                    clearInterval(intervalId);
                }
                attempts++;
            }, intervalMs);
        }

        function saatInteraksi() { perbaikiTinggiIframe(); }

        perbaikiTinggiIframe();
        document.addEventListener('click', saatInteraksi);
    })();
    """
    _inject_iframe_js_code(source)