"""
utils/peta_zona.py
=====================================================================
MODUL TAMBAHAN (BARU) — tidak mengubah file yang sudah ada.

Tujuan:
  Menampilkan peta batas wilayah KECAMATAN Kota Bandung yang diwarnai
  per ZONA SPMB (A/B/C/D — mengikuti definisi di utils/zona.py),
  dengan gaya tampilan sederhana seperti preview GeoJSON di GitHub
  (gambar ke-3 referensi user), namun tetap dilengkapi:
    - marker rumah pendaftar
    - lingkaran radius domisili (seperti gambar ke-2)
    - sorot (highlight) batas zona tempat siswa berdomisili (gambar ke-1)

Sumber data geometri kecamatan:
  tryfatur/geojson-bandung — 3273-kota-bandung-level-kecamatan.json
  (sudah disederhanakan/disimplifikasi & disimpan lokal di
   data/kecamatan_bandung.geojson agar ringan saat dirender Folium)

Modul ini HANYA membaca ZONA_INFO dari utils/zona.py (read-only import),
tidak mengubah isi file utils/zona.py maupun utils/map_utils.py.
"""

import json
import os
import folium

from utils.zona import ZONA_INFO

GEOJSON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "kecamatan_bandung.geojson"
)


def _normalisasi(nama: str) -> str:
    """Normalisasi nama kecamatan agar pencocokan tidak terganggu
    perbedaan spasi/kapitalisasi antara data GeoJSON & ZONA_INFO."""
    return nama.lower().replace(" ", "").strip()


def _bangun_mapping_kecamatan_ke_zona() -> dict:
    """Bangun mapping {nama_kecamatan_ternormalisasi: kode_zona}
    secara dinamis dari ZONA_INFO yang sudah ada di utils/zona.py."""
    mapping = {}
    for kode_zona, info in ZONA_INFO.items():
        for kec in info.get("kecamatan", []):
            mapping[_normalisasi(kec)] = kode_zona
    return mapping


_KECAMATAN_KE_ZONA = _bangun_mapping_kecamatan_ke_zona()


def _load_geojson() -> dict:
    with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def buat_peta_zona_kecamatan(
    home_lat: float = None,
    home_lon: float = None,
    zona_user: str = None,
    sekolah_list: list | None = None,
    radius_meter: int = 3000,
) -> folium.Map:
    """
    Membuat peta Folium berisi batas wilayah kecamatan Kota Bandung,
    diwarnai sesuai Zona SPMB (mengikuti warna di ZONA_INFO).

    Parameter:
        home_lat, home_lon : koordinat rumah pendaftar (opsional).
                              Jika diisi, peta dipusatkan ke lokasi ini,
                              ditambah marker rumah + lingkaran radius domisili.
        zona_user          : kode zona ("A"/"B"/"C"/"D") tempat pendaftar
                              berdomisili — kecamatan pada zona ini akan
                              disorot (border lebih tebal & lebih gelap).
        sekolah_list        : daftar dict sekolah [{nama, lat, lon}, ...]
                              opsional, ditampilkan sebagai marker tambahan.
        radius_meter        : radius lingkaran domisili (meter), default 3000.
    """
    geo = _load_geojson()

    if home_lat is not None and home_lon is not None:
        center = [home_lat, home_lon]
        zoom = 13
    else:
        center = [-6.9175, 107.6191]  # titik tengah Kota Bandung
        zoom = 12

    m = folium.Map(location=center, zoom_start=zoom, tiles="cartodbpositron")

    def style_function(feature):
        nama_kec = feature["properties"].get("nama_kecamatan", "")
        zona_kec = _KECAMATAN_KE_ZONA.get(_normalisasi(nama_kec))
        warna = ZONA_INFO.get(zona_kec, {}).get("warna", "#9aa0a6")
        disorot = bool(zona_user) and zona_kec == zona_user
        return {
            "fillColor": warna,
            "color": "#1a1a2e" if not disorot else "#000000",
            "weight": 1.2 if not disorot else 3.5,
            "fillOpacity": 0.55 if disorot else 0.30,
        }

    def highlight_function(_feature):
        return {"fillOpacity": 0.7, "weight": 3}

    tooltip = folium.GeoJsonTooltip(
        fields=["nama_kecamatan"],
        aliases=["Kecamatan:"],
        sticky=True,
    )

    folium.GeoJson(
        geo,
        name="Batas Kecamatan & Zona SPMB",
        style_function=style_function,
        highlight_function=highlight_function,
        tooltip=tooltip,
    ).add_to(m)

    # ── Lingkaran radius domisili + marker rumah (mengikuti gaya gambar ke-2) ──
    if home_lat is not None and home_lon is not None:
        folium.Circle(
            location=[home_lat, home_lon],
            radius=radius_meter,
            color="#3498db",
            fill=True,
            fill_opacity=0.10,
            weight=2,
            dash_array="6,6",
            tooltip=f"Radius domisili {radius_meter:,} m",
        ).add_to(m)

        folium.Marker(
            location=[home_lat, home_lon],
            tooltip="📍 Rumah Anda",
            popup=folium.Popup("🏠 <b>Lokasi Rumah Anda</b>", max_width=200),
            icon=folium.Icon(color="lightblue", icon="home", prefix="fa"),
        ).add_to(m)

    # ── Marker sekolah + lingkaran radius batas penerimaan (hijau/merah) ─────
    if sekolah_list:
        CLUSTER_COLORS = {"Tinggi": "#e74c3c", "Sedang": "#f1c40f", "Rendah": "#2ecc71"}
        CLUSTER_TAMPIL = {"Tinggi": "Ketat", "Sedang": "Sedang", "Rendah": "Longgar"}
        for s in sekolah_list:
            jarak       = s.get("jarak_m")
            jarak_batas = s.get("jarak_batas", 800)
            cluster     = s.get("cluster", "")
            prob        = s.get("prob", 0)

            if jarak is not None:
                dalam_batas   = jarak <= jarak_batas
                warna_circle  = "#2ecc71" if dalam_batas else "#e74c3c"
                warna_marker  = "green" if dalam_batas else "red"
                status_label  = "✅ Dalam Batas" if dalam_batas else "❌ Di Luar Batas"

                folium.Circle(
                    location=[s["lat"], s["lon"]],
                    radius=jarak_batas,
                    color=warna_circle,
                    fill=True,
                    fill_opacity=0.08,
                    weight=1.5,
                    tooltip=f"{s.get('nama','Sekolah')} – Batas {jarak_batas:,.0f}m ({status_label})",
                ).add_to(m)

                popup_html = f"""
                <div style='min-width:230px;font-family:sans-serif;font-size:13px'>
                  <b>🏫 {s.get('nama','Sekolah')}</b><br>
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
                    tooltip=f"🏫 {s.get('nama','Sekolah')} | {jarak:,.0f}m | {status_label}",
                    popup=folium.Popup(popup_html, max_width=290),
                    icon=folium.Icon(color=warna_marker, icon="graduation-cap", prefix="fa"),
                ).add_to(m)
            else:
                folium.Marker(
                    location=[s["lat"], s["lon"]],
                    tooltip=f"🏫 {s.get('nama','Sekolah')}",
                    icon=folium.Icon(color="darkblue", icon="graduation-cap", prefix="fa"),
                ).add_to(m)

    # ── Legenda warna zona + keterangan lingkaran batas penerimaan ───────────
    legend_rows = "".join(
        f"<span style='color:{info['warna']}'>●</span> "
        f"Zona {kode} — {info['label'].split('–')[-1].strip()}<br>"
        for kode, info in ZONA_INFO.items()
    )
    legend_html = f"""
    <div style='position:fixed;bottom:30px;right:30px;z-index:9999;
                background:white;padding:10px 14px;border-radius:10px;
                box-shadow:0 2px 10px rgba(0,0,0,.3);font-size:12px;max-width:230px;
                font-family:sans-serif'>
      <b>🗺️ Zona SPMB Domisili</b><br>{legend_rows}
      <hr style='margin:6px 0'>
      <b>Keterangan Lingkaran</b><br>
      <span style='color:#2ecc71'>●</span> Dalam batas penerimaan<br>
      <span style='color:#e74c3c'>●</span> Di luar batas penerimaan<br>
      <span style='color:#3498db'>- -</span> Radius domisili {radius_meter:,} m
    </div>"""
    m.get_root().html.add_child(folium.Element(legend_html))

    folium.LayerControl().add_to(m)
    return m
