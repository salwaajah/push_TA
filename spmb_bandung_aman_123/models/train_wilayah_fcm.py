"""
models/train_wilayah_fcm.py
Pipeline FCM TERKUNCI (constrained / semi-supervised) untuk WILAYAH (kecamatan).

⚠️ PERBEDAAN PENTING dari versi FCM bebas (unsupervised) sebelumnya:
Versi ini TIDAK membiarkan FCM menentukan sendiri kecamatan itu masuk zona
mana. Zona A/B/C/D untuk tiap kecamatan SUDAH DITETAPKAN mengikuti peta
zonasi SPMB resmi Disdik/Pemkot Bandung (lihat utils/zona.py -> ZONA_MAP),
dan TIDAK PERNAH berubah / berpindah dari aturan itu berapa pun hasil
hitungannya.

FCM di sini hanya dipakai untuk menghitung DERAJAT KEANGGOTAAN FUZZY
(membership degree, 0-100%) setiap kecamatan terhadap zona resminya
sendiri, berdasarkan seberapa mirip pola datanya (rasio pendaftar, jarak
batas, lokasi sekolah) dengan kecamatan lain di zona yang sama.

Metodologi (semi-supervised fuzzy membership scoring):
  0. Rasio per sekolah TIDAK lagi memakai pendaftar/kuota biasa, melainkan
     rasio aksesibilitas spasial ala Two-Step Floating Catchment Area
     (2SFCA, Luo & Wang) Langkah 1:
         Rj = Sj / Σ_{k∈{dkj≤d0}} Pk
     Sj = kapasitas/kuota sekolah j, Pk = jumlah pendaftar (permintaan) di
     titik k yang berada dalam radius layanan d0 terhadap sekolah j. Karena
     pendaftaran SPMB sudah berbasis zonasi jarak (radius d0 = jarak_batas
     historis sekolah itu sendiri), seluruh pendaftar tercatat sekolah j
     sudah berada dalam radius tsb, sehingga Σ Pk = total pendaftar sekolah
     j. Sj & Pk diakumulasi lintas tahun ajaran 2022, 2024, 2025, 2026 (lihat
     hitung_rasio_2sfca_sekolah()) sebelum dibagi, supaya Rj representatif
     multi-tahun. Rj besar -> daya tampung lega dibanding permintaan (akses
     mudah); Rj kecil -> daya tampung sempit dibanding permintaan (akses sulit).
  1. Hitung 4 fitur per kecamatan: rasio_pendaftar_avg (rata-rata Rj sekolah
     dalam kecamatan itu), jarak_batas_m_avg, lat_centroid, lon_centroid ->
     standardisasi z-score.
  2. Kelompok/label ZONA sudah given (dari ZONA_MAP resmi) -> dipakai sebagai
     partisi awal yang "crisp" (bukan hasil clustering).
  3. Hitung centroid tiap zona = rata-rata fitur (sudah di-scale) dari semua
     kecamatan ANGGOTA zona itu (sesuai aturan resmi).
  4. Hitung jarak Euclidean tiap kecamatan ke SEMUA centroid zona (bukan cuma
     zona resminya), lalu hitung derajat keanggotaan fuzzy standar FCM:
         u_ik = 1 / sum_j [ (d_ik / d_jk) ^ (2/(m-1)) ]
     dengan m = 2.0 (fuzziness, sama seperti FCM biasa).
  5. "membership_zona_resmi" = nilai u kecamatan itu terhadap zona resminya
     sendiri (BUKAN hasil argmax -- zona tidak pernah berubah).
     Kalau nilainya rendah (mis. <55%), itu artinya kecamatan itu "ambigu"
     -- datanya sebenarnya lebih mirip zona lain, tapi tetap ditempatkan di
     zona resmi karena aturan zonasi SPMB, bukan karena kemiripan data.
  6. "zona_paling_mirip_data" = zona dengan nilai u tertinggi (bisa beda dari
     zona resmi) -- ditampilkan sebagai info tambahan/diagnostik saja, TIDAK
     dipakai untuk apapun di aplikasi.

Kelebihan pendekatan ini dibanding FCM bebas atau ZONA_MAP manual biasa:
  - Zona tidak pernah melenceng dari aturan SPMB resmi (aman secara hukum/
    administratif, tidak akan menyesatkan siswa).
  - Tetap "data-driven": sistem bisa menunjukkan kecamatan mana yang datanya
    ambigu/berbatasan (borderline), sesuatu yang tidak bisa didapat dari
    ZONA_MAP hardcoded biasa.

Jalankan sekali (atau ulang tiap ada data baru): python models/train_wilayah_fcm.py
Model tersimpan di models/fcm_wilayah_model.pkl
"""

import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import joblib

from data.sekolah_data import SEKOLAH_NEGERI
from utils.dataset_loader import load_ringkasan_sekolah
from utils.zona import ZONA_MAP as _ZONA_MAP_RESMI

MODEL_DIR = os.path.dirname(__file__)
M_FUZZY = 2.0  # fuzziness FCM standar, sama seperti train_models.py

# Tahun ajaran nyata yang dipakai untuk menghitung rasio 2SFCA & fitur
# wilayah (kecamatan). Data 2027 (jika ada) TIDAK diikutkan karena baru
# proyeksi/belum jadi riwayat penuh.
TAHUN_WILAYAH = [2022, 2024, 2025, 2026]


# ──────────────────────────────────────────────────────────────────────────────
# 1. EKSTRAKSI KECAMATAN & FITUR PER WILAYAH
# ──────────────────────────────────────────────────────────────────────────────

def parse_kecamatan(alamat: str) -> str | None:
    """Ambil nama kecamatan dari field alamat sekolah, mis.
    '...Kec. Cicendo' -> 'Cicendo'."""
    m = re.search(r"Kec\.\s*([A-Za-z .]+)", alamat)
    if not m:
        return None
    return m.group(1).strip().rstrip(".").strip()


def hitung_rasio_2sfca_sekolah(tahun_list: list[int] = TAHUN_WILAYAH) -> dict:
    """
    2SFCA Langkah 1 (Luo & Wang): Rj = Sj / Σ_{k∈{dkj≤d0}} Pk

    Sj (kuota_dalam) & Pk (pendaftar_dalam) tiap sekolah diakumulasikan
    (dijumlah) lintas tahun ajaran nyata di `tahun_list` (2022, 2024, 2025,
    2026) sebelum dibagi, supaya Rj mencerminkan daya tampung vs permintaan
    multi-tahun -- bukan snapshot satu tahun saja.

    d0 (radius layanan) di sini adalah jarak_batas historis sekolah itu
    sendiri: karena SPMB berbasis zonasi jarak, seluruh pendaftar yang
    tercatat pada sekolah j sudah berada dalam radius d0 tsb, sehingga
    Σ Pk = total pendaftar_dalam sekolah j pada tahun terkait.

    Return: {nomor_sekolah (int): Rj}
    """
    akumulasi_sj: dict = {}
    akumulasi_pk: dict = {}
    for tahun in tahun_list:
        try:
            df_r = load_ringkasan_sekolah(tahun)
        except Exception:
            continue
        if df_r.empty:
            continue
        nomor_series = df_r["nama"].str.extract(r"(\d+)")[0]
        for nomor_raw, (_, row) in zip(nomor_series, df_r.iterrows()):
            if pd.isna(nomor_raw):
                continue
            nomor = int(float(nomor_raw))
            sj = row.get("kuota_dalam")
            pk = row.get("pendaftar_dalam")
            if pd.isna(sj) or pd.isna(pk):
                continue
            akumulasi_sj[nomor] = akumulasi_sj.get(nomor, 0) + sj
            akumulasi_pk[nomor] = akumulasi_pk.get(nomor, 0) + pk

    hasil = {}
    for nomor, sj_total in akumulasi_sj.items():
        pk_total = akumulasi_pk.get(nomor, 0)
        if pk_total > 0:
            hasil[nomor] = sj_total / pk_total
    return hasil


def hitung_fitur_wilayah(sekolah_list: list[dict]) -> pd.DataFrame:
    """Agregasi fitur dari level sekolah -> level kecamatan. Rasio memakai
    2SFCA (hitung_rasio_2sfca_sekolah), jarak batas dalam METER (tanpa
    konversi ke km)."""
    rasio_2sfca = hitung_rasio_2sfca_sekolah()

    rows = []
    for s in sekolah_list:
        kecamatan = parse_kecamatan(s["alamat"])
        if not kecamatan:
            continue
        try:
            nomor = int(s["nama"].split()[-1])
        except (ValueError, IndexError):
            nomor = None
        kuota = s["kuota"] or 1
        pendaftar = s["pendaftar"] or 0
        # Fallback ke rasio statis Sj/Pk (kuota/pendaftar) sekolah itu kalau
        # sekolah tidak punya riwayat data tahun 2022/2024/2025/2026.
        rasio = rasio_2sfca.get(nomor, kuota / max(pendaftar, 1))
        rows.append({
            "kecamatan": kecamatan,
            "rasio_pendaftar": rasio,
            "jarak_batas_m": s["jarak_batas"],
            "lat": s["lat"],
            "lon": s["lon"],
        })

    df = pd.DataFrame(rows)
    df_wilayah = (
        df.groupby("kecamatan")
        .agg(
            rasio_pendaftar_avg=("rasio_pendaftar", "mean"),
            jarak_batas_m_avg=("jarak_batas_m", "mean"),
            lat_centroid=("lat", "mean"),
            lon_centroid=("lon", "mean"),
            jumlah_sekolah=("kecamatan", "count"),
        )
        .reset_index()
    )
    return df_wilayah


# ──────────────────────────────────────────────────────────────────────────────
# 2. FCM TERKUNCI – hitung membership terhadap zona resmi (bukan clustering)
# ──────────────────────────────────────────────────────────────────────────────

def hitung_membership_terkunci(df_wilayah: pd.DataFrame, zona_map: dict, m: float = M_FUZZY):
    """
    Zona SUDAH DITENTUKAN dari zona_map (aturan resmi) -- fungsi ini TIDAK
    melakukan clustering/penentuan zona, hanya menghitung derajat
    keanggotaan fuzzy (u) tiap kecamatan terhadap centroid tiap zona resmi.
    """
    fitur_cols = ["rasio_pendaftar_avg", "jarak_batas_m_avg", "lat_centroid", "lon_centroid"]

    def _norm(s: str) -> str:
        """Normalisasi nama kecamatan: lowercase, hilangkan spasi berlebih
        DAN semua spasi (supaya 'astana anyar' == 'astanaanyar', dua ejaan
        yang sama-sama dipakai di berbagai sumber data)."""
        return re.sub(r"\s+", "", s.lower().strip())

    zona_map_norm = {_norm(k): v for k, v in zona_map.items()}

    df_wilayah = df_wilayah.copy()
    df_wilayah["zona"] = df_wilayah["kecamatan"].apply(
        lambda k: zona_map_norm.get(_norm(k))
    )

    tak_dikenal = df_wilayah[df_wilayah["zona"].isna()]
    if not tak_dikenal.empty:
        print(f"⚠️  {len(tak_dikenal)} kecamatan tidak ada di ZONA_MAP resmi, "
              f"dilewati: {tak_dikenal['kecamatan'].tolist()}")
        df_wilayah = df_wilayah.dropna(subset=["zona"])

    X = df_wilayah[fitur_cols].values
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std == 0] = 1.0
    X_scaled = (X - mean) / std

    zona_list = sorted(df_wilayah["zona"].unique())

    # Centroid tiap zona = rata-rata fitur (scaled) anggota zona itu SESUAI
    # ATURAN RESMI (bukan hasil iterasi clustering).
    centroids = {}
    for z in zona_list:
        mask = (df_wilayah["zona"] == z).values
        centroids[z] = X_scaled[mask].mean(axis=0)
    cntr_matrix = np.array([centroids[z] for z in zona_list])  # (n_zona, n_fitur)

    # Jarak tiap kecamatan ke SEMUA centroid zona.
    dist = np.linalg.norm(
        X_scaled[:, None, :] - cntr_matrix[None, :, :], axis=2
    )  # (n_kecamatan, n_zona)
    dist = np.fmax(dist, 1e-10)  # hindari pembagian nol

    # Rumus keanggotaan fuzzy standar FCM.
    power = 2.0 / (m - 1.0)
    inv = dist ** (-power)
    u = inv / inv.sum(axis=1, keepdims=True)  # (n_kecamatan, n_zona)

    df_wilayah = df_wilayah.reset_index(drop=True)
    for j, z in enumerate(zona_list):
        df_wilayah[f"u_{z}"] = u[:, j]

    zona_idx = {z: j for j, z in enumerate(zona_list)}
    df_wilayah["membership_zona_resmi"] = [
        u[i, zona_idx[row.zona]] for i, row in df_wilayah.iterrows()
    ]
    argmax_idx = u.argmax(axis=1)
    df_wilayah["zona_paling_mirip_data"] = [zona_list[i] for i in argmax_idx]
    df_wilayah["ambigu"] = df_wilayah["zona"] != df_wilayah["zona_paling_mirip_data"]

    return df_wilayah, centroids, mean, std, zona_list


# ──────────────────────────────────────────────────────────────────────────────
# 3. SIMPAN MODEL
# ──────────────────────────────────────────────────────────────────────────────

def main():
    print("📊 Menghitung fitur per kecamatan dari data sekolah...")
    df_wilayah = hitung_fitur_wilayah(SEKOLAH_NEGERI)
    print(f"   {len(df_wilayah)} kecamatan terdeteksi.")

    print("\n🔒 Menghitung derajat keanggotaan fuzzy (zona TERKUNCI ke aturan resmi)...")
    df_wilayah, centroids, mean, std, zona_list = hitung_membership_terkunci(
        df_wilayah, _ZONA_MAP_RESMI, m=M_FUZZY
    )

    print("\nHasil (zona TIDAK PERNAH berubah dari aturan resmi):")
    tampil = df_wilayah[[
        "kecamatan", "rasio_pendaftar_avg", "jarak_batas_m_avg",
        "jumlah_sekolah", "zona", "membership_zona_resmi",
        "zona_paling_mirip_data", "ambigu",
    ]].sort_values(["zona", "membership_zona_resmi"], ascending=[True, False])
    print(tampil.to_string(index=False))

    n_ambigu = int(df_wilayah["ambigu"].sum())
    print(f"\n⚠️  {n_ambigu} dari {len(df_wilayah)} kecamatan datanya lebih mirip "
          f"zona lain (borderline), tapi TETAP di zona resmi sesuai aturan SPMB.")

    joblib.dump({
        "zona_map_resmi": _ZONA_MAP_RESMI,
        "df_wilayah": df_wilayah,
        "centroids": centroids,
        "scaler_mean": mean,
        "scaler_std": std,
        "zona_list": zona_list,
        "m_fuzzy": M_FUZZY,
        "metode": "FCM_terkunci_zona_resmi",
    }, os.path.join(MODEL_DIR, "fcm_wilayah_model.pkl"))

    print("\n✅ Model disimpan: models/fcm_wilayah_model.pkl")
    print("   Zona A/B/C/D mengikuti aturan resmi SPMB -- FCM hanya menghitung")
    print("   derajat keyakinan (confidence), bukan menentukan zona.")


if __name__ == "__main__":
    main()
