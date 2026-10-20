"""
utils/zona.py
"""

import os
import re
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────────
# ZONA_MAP: aturan zonasi SPMB RESMI (Disdik/Pemkot Bandung) -- FIXED, tidak
# pernah berubah/dipengaruhi hasil clustering apapun. Ini satu-satunya sumber
# kebenaran untuk "kecamatan X masuk zona apa".
#
# models/fcm_wilayah_model.pkl (models/train_wilayah_fcm.py) TIDAK mengubah
# mapping ini. Model itu hanya menghitung derajat keanggotaan fuzzy (FCM
# terkunci) tiap kecamatan terhadap zona resminya sendiri, dipakai sebagai
# info tambahan/diagnostik di Dashboard Admin (lihat get_info_wilayah_kecamatan
# di bawah), BUKAN untuk menentukan zona.
# ──────────────────────────────────────────────────────────────────────────────

ZONA_MAP: dict = {
    "sukasari": "A", "cidadap": "A", "coblong": "A",
    "cibeunying kaler": "A", "bandung wetan": "A",
    "sumur bandung": "A", "cibeunying kidul": "A", "sukajadi": "A",
    "mandalajati": "B", "antapani": "B", "arcamanik": "B",
    "cinambo": "B", "panyileukan": "B", "cibiru": "B",
    "gedebage": "B", "rancasari": "B", "ujungberung": "B", "buahbatu": "B",
    "kiaracondong": "C", "batununggal": "C", "lengkong": "C",
    "regol": "C", "bandung kidul": "C",
    "cicendo": "D", "andir": "D", "bandung kulon": "D",
    "babakan ciparay": "D", "bojongloa kaler": "D",
    "bojongloa kidul": "D", "astana anyar": "D",
}

ZONA_INFO = {
    "A": {"warna": "#3498db", "label": "Zona A - Bandung Utara-Tengah",
          "kecamatan": ["Sukasari", "Cidadap", "Coblong", "Cibeunying Kaler",
                        "Bandung Wetan", "Sumur Bandung", "Cibeunying Kidul", "Sukajadi"]},
    "B": {"warna": "#2ecc71", "label": "Zona B - Bandung Timur",
          "kecamatan": ["Mandalajati", "Antapani", "Arcamanik", "Cinambo",
                        "Panyileukan", "Cibiru", "Gedebage", "Rancasari", "Ujungberung", "Buahbatu"]},
    "C": {"warna": "#f1c40f", "label": "Zona C - Bandung Tengah-Selatan",
          "kecamatan": ["Kiaracondong", "Batununggal", "Lengkong", "Regol", "Bandung Kidul"]},
    "D": {"warna": "#e74c3c", "label": "Zona D - Bandung Barat",
          "kecamatan": ["Cicendo", "Andir", "Bandung Kulon", "Babakan Ciparay",
                        "Bojongloa Kaler", "Bojongloa Kidul", "Astana Anyar"]},
}


# ──────────────────────────────────────────────────────────────────────────────
# Derajat keanggotaan fuzzy (FCM terkunci) -- opsional, hanya untuk info
# tambahan di Dashboard Admin. Return None kalau model belum ditraining,
# supaya tidak crash (aplikasi tetap jalan normal pakai ZONA_MAP di atas).
# ──────────────────────────────────────────────────────────────────────────────

_WILAYAH_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models", "fcm_wilayah_model.pkl",
)


@st.cache_data(show_spinner=False)
def _load_wilayah_membership():
    if not os.path.exists(_WILAYAH_MODEL_PATH):
        return None
    try:
        import joblib
        art = joblib.load(_WILAYAH_MODEL_PATH)
        return art["df_wilayah"]
    except Exception:
        return None


def _norm_kec(s: str) -> str:
    return re.sub(r"\s+", "", s.lower().strip())


def get_info_wilayah_kecamatan(kecamatan: str) -> dict | None:
    """Info wilayah (hasil agregasi models/train_wilayah_fcm.py) untuk satu
    kecamatan. Return None kalau model belum ditraining atau kecamatan tidak
    ditemukan. Dict berisi: zona, rasio_pendaftar_avg (rasio aksesibilitas
    2SFCA Sj/Pk, rata-rata SMP Negeri di kecamatan itu, akumulasi data tahun
    2022/2024/2025/2026), jarak_batas_m_avg (meter), jumlah_sekolah."""
    df = _load_wilayah_membership()
    if df is None:
        return None
    target = _norm_kec(kecamatan)
    match = df[df["kecamatan"].apply(_norm_kec) == target]
    if match.empty:
        return None
    row = match.iloc[0]
    return {
        "zona": row["zona"],
        "rasio_pendaftar_avg": float(row["rasio_pendaftar_avg"]),
        "jarak_batas_m_avg": float(row["jarak_batas_m_avg"]),
        "jumlah_sekolah": int(row["jumlah_sekolah"]),
    }


def deteksi_zona(address_raw: dict, display_name: str) -> tuple:
    """Coba semua field alamat untuk deteksi zona."""
    
    # Kumpulkan semua kemungkinan nama kecamatan dari response
    candidates = []
    for field in ["suburb", "city_district", "quarter", "neighbourhood",
                  "hamlet", "village", "town", "county", "district"]:
        val = address_raw.get(field, "")
        if val:
            candidates.append(val.lower().strip())
    
    # Juga cek dari display_name
    for part in display_name.lower().split(","):
        candidates.append(part.strip())

    # Cek satu per satu ke ZONA_MAP
    for candidate in candidates:
        for key, zona in ZONA_MAP.items():
            if key in candidate or candidate in key:
                return zona, candidate.title()
    
    return "Tidak Diketahui", ""


# Bounding box kasar Kota Bandung (dua sudut berlawanan), dipakai untuk
# membatasi (bounded) pencarian Nominatim supaya tidak "meleset" ke daerah
# lain di luar Bandung saat query yang diberikan kurang spesifik.
_BANDUNG_VIEWBOX = [(-6.80, 107.55), (-7.06, 107.76)]


@st.cache_data(show_spinner=False)
def geocode_alamat(alamat: str) -> dict | None:
    """
    Geocode alamat ke lat/lon + zona.
    Nominatim/OSM sering tidak punya data di level nomor rumah untuk alamat
    Indonesia, jadi kalau query lengkap gagal, dicoba query yang makin umum
    (tanpa nomor rumah, lalu segmen kelurahan/kecamatan) sebelum menyerah.

    Untuk menghindari salah-cocok ke lokasi lain (mis. query yang terlalu
    umum ke-geocode ke tempat yang sama sekali tidak berkaitan dengan
    alamat yang diminta), pencarian dibatasi (bounded) ke area Kota
    Bandung, dan setiap hasil divalidasi ulang harus benar-benar berada
    di wilayah Bandung sebelum diterima.
    """
    import re

    geolocator = Nominatim(user_agent="spmb_bandung_app_v2", timeout=10)
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)

    alamat_bersih = alamat.strip()
    parts = [p.strip() for p in alamat_bersih.split(",") if p.strip()]
    sudah_ada_bandung = "bandung" in alamat_bersih.lower()
    sufiks = "" if sudah_ada_bandung else ", Kota Bandung, Jawa Barat, Indonesia"

    queries = [f"{alamat_bersih}{sufiks}"]

    tanpa_no = re.sub(r"\bno\.?\s*\d+\w*", "", alamat_bersih, flags=re.IGNORECASE).strip(", ")
    if tanpa_no and tanpa_no.lower() != alamat_bersih.lower():
        sufiks_tn = "" if "bandung" in tanpa_no.lower() else ", Kota Bandung, Jawa Barat, Indonesia"
        queries.append(f"{tanpa_no}{sufiks_tn}")

    # Fallback paling umum: pakai 1-2 segmen alamat terakhir yang biasanya
    # berisi kelurahan/kecamatan (BUKAN cuma segmen paling akhir literal,
    # mis. "Indonesia" saja, karena itu terlalu umum & rawan salah cocok
    # ke lokasi lain yang tidak berkaitan sama sekali dengan alamat asli).
    if len(parts) > 2:
        segmen = parts[-3:-1] if len(parts) > 3 else parts[-2:-1]
        segmen_akhir = ", ".join(
            s for s in segmen
            if s.lower() not in ("indonesia", "jawa barat")
            and "kota bandung" not in s.lower()
        )
        if segmen_akhir:
            queries.append(f"{segmen_akhir}, Kota Bandung, Jawa Barat, Indonesia")

    # Fallback terakhir: kalau alamat menyebut kecamatan secara eksplisit
    # (mis. "Kec. Sukasari" / "Kecamatan Sukasari"), coba geocode nama
    # kecamatannya saja. Data batas administrasi kecamatan di OSM/Nominatim
    # jauh lebih lengkap dibanding data jalan/nomor rumah untuk alamat
    # Indonesia, jadi query ini hampir selalu berhasil dan dipakai sebagai
    # jaring pengaman supaya alamat tidak langsung dianggap "tidak ditemukan"
    # hanya karena nomor rumah/nama jalannya tidak ada di peta.
    kec_match = re.search(r"\bkec(?:amatan)?\.?\s+([A-Za-z .]+)", alamat_bersih, flags=re.IGNORECASE)
    if kec_match:
        nama_kec = kec_match.group(1).strip(" .,")
        if nama_kec:
            queries.append(f"Kecamatan {nama_kec}, Kota Bandung, Jawa Barat, Indonesia")

    # Hilangkan query duplikat (case-insensitive) tapi tetap jaga urutan,
    # supaya query yang paling spesifik tetap dicoba lebih dulu.
    seen, queries_unik = set(), []
    for q in queries:
        key = q.lower().strip()
        if key not in seen:
            seen.add(key)
            queries_unik.append(q)
    queries = queries_unik

    last_error = None
    any_query_succeeded = False
    for query in queries:
        try:
            location = geocode(
                query, addressdetails=True,
                viewbox=_BANDUNG_VIEWBOX, bounded=True,
            )
            any_query_succeeded = True
        except Exception as e:
            # Jangan langsung menyerah kalau satu query error (mis. timeout
            # sesaat) -- tetap coba query fallback berikutnya dulu.
            last_error = str(e)
            continue
        if location is not None:
            addr = location.raw.get("address", {})
            # Validasi: hasil harus benar-benar di wilayah Bandung, supaya
            # query yang kurang spesifik tidak salah cocok ke tempat lain
            # (mis. landmark/POI populer yang tidak berkaitan dengan alamat
            # yang dicari).
            wilayah = " ".join(str(addr.get(k, "")) for k in
                                ("city", "county", "state_district", "state")).lower()
            if "bandung" not in wilayah:
                continue
            zona, kecamatan_label = deteksi_zona(addr, location.address)
            return {
                "lat": location.latitude,
                "lon": location.longitude,
                "display_name": location.address,
                "kecamatan": kecamatan_label,
                "zona": zona,
            }

    # Kalau semua query gagal karena error (mis. timeout/koneksi), bukan
    # karena memang tidak ketemu, tampilkan error aslinya supaya admin tahu
    # itu masalah koneksi ke layanan peta, bukan alamatnya yang salah.
    if last_error and not any_query_succeeded:
        return {"error": last_error}
    return None


def get_zona_dari_kecamatan(kecamatan: str) -> str:
    return ZONA_MAP.get(kecamatan.lower().strip(), "Tidak Diketahui")