"""
models/train_models.py
Pipeline training:
  1. Fuzzy C-Means (FCM) → clustering tingkat keketatan sekolah
  2. Random Forest → prediksi probabilitas diterima

Jalankan sekali: python models/train_models.py
Model tersimpan di models/fcm_model.pkl & models/rf_model.pkl
"""

import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import skfuzzy as fuzz
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report
from data.sekolah_data import SEKOLAH_NEGERI
from utils.dataset_loader import (
    get_tahun_tersedia,
    load_ringkasan_sekolah,
    load_pendaftar_detail,
    get_tahun_punya_sheet_per_sekolah,
)

# ──────────────────────────────────────────────────────────────────────────────
# 1. FUZZY C-MEANS  – Clustering keketatan sekolah
# ──────────────────────────────────────────────────────────────────────────────

def hitung_rasio_multitahun() -> dict:
    """
    Rata-rata rasio aksesibilitas 2SFCA (Luo & Wang), Rj = Sj/Pk =
    kuota-dalam/pendaftar-dalam, tiap sekolah, diagregasi dari SELURUH tahun
    ajaran nyata yang tersedia (2022, 2024, 2025, 2026), bukan hanya snapshot
    satu tahun. Dipakai sebagai fitur FCM yang lebih representatif terhadap
    tren riil multi-tahun. Semakin besar nilainya, semakin lega/mudah akses
    (kuota banyak dibanding pendaftar); semakin kecil, semakin ketat.
    Return: {nomor_sekolah (int): rasio_rata_rata}
    """
    akumulasi: dict = {}
    for tahun in get_tahun_tersedia():
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
            kuota = row.get("kuota_dalam")
            pendaftar = row.get("pendaftar_dalam")
            if pd.isna(kuota) or pd.isna(pendaftar) or not pendaftar:
                continue
            akumulasi.setdefault(nomor, []).append(kuota / pendaftar)
    return {nomor: (sum(v) / len(v)) for nomor, v in akumulasi.items()}


def hitung_batas_riil_multitahun(tahun_list: tuple = (2025, 2026)) -> dict:
    """
    Batas radius RIIL tiap sekolah = jarak domisili siswa TERJAUH yang
    benar-benar diterima, diambil dari sheet '<Sekolah> - DOMISILI' pada
    data/dataset_pendaftar/dataset_<tahun>.xlsx (kolom 'Jarak (m)'),
    dirata-ratakan lintas tahun yang punya data per-siswa.
    Menggantikan nilai statis di data/sekolah_data.py dengan angka hasil
    seleksi SPMB sesungguhnya.
    Return: {nomor_sekolah (int): rata_rata_jarak_batas_meter}
    """
    tahun_valid = [t for t in tahun_list if t in get_tahun_punya_sheet_per_sekolah()]
    akumulasi: dict = {}
    for tahun in tahun_valid:
        for nomor in range(1, 76):
            df_det = load_pendaftar_detail(tahun, nomor)
            if df_det is None or df_det.empty:
                continue
            jarak = df_det["Jarak (m)"].dropna()
            if not jarak.empty:
                akumulasi.setdefault(nomor, []).append(float(jarak.max()))
    return {nomor: sum(v) / len(v) for nomor, v in akumulasi.items()}


def hitung_kuota_pendaftar_multitahun() -> tuple:
    """
    Rata-rata KUOTA dan PENDAFTAR (jalur dalam zona) tiap sekolah, diagregasi
    dari SELURUH tahun ajaran nyata yang tersedia (2022, 2024, 2025, 2026),
    dipakai sebagai fitur FCM tambahan (selain rasio_pendaftar yang memang
    turunan kuota/pendaftar) supaya skala riil kuota & pendaftar ikut jadi
    pembeda tingkat keketatan, bukan cuma rasionya saja.
    Return: (kuota_rata2: dict, pendaftar_rata2: dict) — key = nomor sekolah.
    """
    akumulasi_kuota: dict = {}
    akumulasi_pendaftar: dict = {}
    for tahun in get_tahun_tersedia():
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
            kuota = row.get("kuota_dalam")
            pendaftar = row.get("pendaftar_dalam")
            if pd.isna(kuota) or pd.isna(pendaftar) or not pendaftar:
                continue
            akumulasi_kuota.setdefault(nomor, []).append(kuota)
            akumulasi_pendaftar.setdefault(nomor, []).append(pendaftar)
    rata_kuota = {n: sum(v) / len(v) for n, v in akumulasi_kuota.items()}
    rata_pendaftar = {n: sum(v) / len(v) for n, v in akumulasi_pendaftar.items()}
    return rata_kuota, rata_pendaftar


def hitung_jarak_minmax_multitahun() -> tuple:
    """
    Rata-rata JARAK MIN dan JARAK MAX (meter) siswa yang diterima tiap
    sekolah, diagregasi dari seluruh tahun ajaran yang punya data:
      - 2025 & 2026: dihitung langsung dari data per-siswa riil (sheet
        '<Sekolah> - DOMISILI', kolom 'Jarak (m)'), jalur Domisili saja.
      - 2022 & 2024: dari ringkasan resmi sumber (kolom jarak_min/jarak_max
        pada berkas dataset tahun tsb; 2022 hanya menyediakan jarak_max).
    Return: (jarak_min_rata2: dict, jarak_max_rata2: dict) — key = nomor
    sekolah, nilai dalam meter.
    """
    akumulasi_min: dict = {}
    akumulasi_max: dict = {}

    for tahun in get_tahun_punya_sheet_per_sekolah():
        for nomor in range(1, 76):
            df_det = load_pendaftar_detail(tahun, nomor)
            if df_det is None or df_det.empty:
                continue
            jarak = df_det["Jarak (m)"].dropna()
            if not jarak.empty:
                akumulasi_min.setdefault(nomor, []).append(float(jarak.min()))
                akumulasi_max.setdefault(nomor, []).append(float(jarak.max()))

    for tahun in get_tahun_tersedia():
        if tahun in get_tahun_punya_sheet_per_sekolah():
            continue  # sudah dihitung dari data per-siswa riil di atas
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
            if pd.notna(row.get("jarak_min")):
                akumulasi_min.setdefault(nomor, []).append(float(row["jarak_min"]))
            if pd.notna(row.get("jarak_max")):
                akumulasi_max.setdefault(nomor, []).append(float(row["jarak_max"]))

    rata_min = {n: sum(v) / len(v) for n, v in akumulasi_min.items()}
    rata_max = {n: sum(v) / len(v) for n, v in akumulasi_max.items()}
    return rata_min, rata_max


def hitung_fitur_fcm(sekolah_list: list[dict]) -> pd.DataFrame:
    """
    Fitur FCM untuk setiap sekolah (dipakai untuk clustering keketatan):
      - kuota            : rata-rata kuota jalur dalam zona, lintas tahun
                           ajaran 2022-2026.
      - pendaftar        : rata-rata jumlah pendaftar jalur dalam zona,
                           lintas tahun ajaran 2022-2026.
      - rasio_pendaftar  : rata-rata rasio aksesibilitas 2SFCA (Rj = Sj/Pk =
                           kuota/pendaftar) lintas tahun ajaran 2022-2026
                           (fallback ke data statis bila sekolah belum punya
                           riwayat data di tahun manapun). Besar = longgar,
                           kecil = ketat. Kolom ini JUGA dipakai (mentah,
                           tidak di-standardisasi) untuk kategorisasi label
                           Tinggi/Sedang/Rendah lewat rumus M±1SD.
      - jarak_min        : rata-rata jarak (meter) siswa TERDEKAT yang
                           diterima, lintas tahun yang tersedia datanya.
      - jarak_max        : rata-rata jarak (meter) siswa TERJAUH yang
                           diterima, lintas tahun yang tersedia datanya.
      - selisih_jarak    : jarak_max - jarak_min (meter) — rentang sebaran
                           domisili siswa yang diterima.

    Kolom `jarak_batas_km` dan `utilitas_kuota` tetap dihitung & disertakan
    (dipakai halaman lain: prediksi RF & Analisis Jarak), namun TIDAK lagi
    dipakai sebagai fitur clustering FCM.
    """
    rasio_multitahun = hitung_rasio_multitahun()
    batas_riil = hitung_batas_riil_multitahun()
    kuota_multitahun, pendaftar_multitahun = hitung_kuota_pendaftar_multitahun()
    jarak_min_multitahun, jarak_max_multitahun = hitung_jarak_minmax_multitahun()

    rows = []
    for s in sekolah_list:
        kuota_statis = s["kuota"] or 1
        pendaftar_statis = s["pendaftar"] or 0
        try:
            nomor = int(s["nama"].split()[-1])
        except (ValueError, IndexError):
            nomor = None
        rasio = rasio_multitahun.get(nomor, kuota_statis / pendaftar_statis if pendaftar_statis else float(kuota_statis))
        jarak_batas_m = batas_riil.get(nomor, s["jarak_batas"])
        utilitas = max(0, 1 - kuota_statis / max(pendaftar_statis, 1))

        kuota = kuota_multitahun.get(nomor, float(kuota_statis))
        pendaftar = pendaftar_multitahun.get(nomor, float(pendaftar_statis))
        jarak_min_m = jarak_min_multitahun.get(nomor, jarak_batas_m * 0.1)
        jarak_max_m = jarak_max_multitahun.get(nomor, jarak_batas_m)
        selisih_m = jarak_max_m - jarak_min_m

        rows.append({
            "id": s["id"],
            "nama": s["nama"],
            "kuota": kuota,
            "pendaftar": pendaftar,
            "rasio_pendaftar": rasio,
            "jarak_min": jarak_min_m,
            "jarak_max": jarak_max_m,
            "selisih_jarak": selisih_m,
            "jarak_batas_km": jarak_batas_m / 1000,
            "utilitas_kuota": utilitas,
        })
    return pd.DataFrame(rows)


def train_fcm(df_fcm: pd.DataFrame, n_clusters: int = 3, m: float = 2.0,
              kolom_fitur: tuple = ("kuota", "pendaftar", "rasio_pendaftar",
                                     "jarak_min", "jarak_max", "selisih_jarak"),
              kolom_rasio_asli: str = "rasio_pendaftar"):
    """
    Jalankan Fuzzy C-Means.
    `kolom_fitur`     : kolom dipakai sebagai fitur clustering FCM (boleh sudah
                        distandarisasi/z-score oleh caller, mis. per tahun).
    `kolom_rasio_asli`: kolom rasio 2SFCA MENTAH (kuota/pendaftar, selalu > 0,
                        BELUM di-z-score) dipakai khusus untuk kategorisasi
                        label Tinggi/Sedang/Rendah. Wajib beda dari kolom
                        fitur clustering kalau kolom itu sudah di-z-score,
                        supaya log-transform di bawah tidak menerima nilai
                        negatif.
    Return: (cntr, u, cluster_labels_array, df_fcm_with_labels)
    """
    data = df_fcm[list(kolom_fitur)].values.T
    # FCM
    cntr, u, u0, d, jm, p, fpc = fuzz.cluster.cmeans(
        data, c=n_clusters, m=m, error=0.005, maxiter=1000, init=None
    )
    cluster_idx = np.argmax(u, axis=0)  # hard assignment

    # ── Kategorisasi Tinggi/Sedang/Rendah pakai rumus M ± 1 SD ──────────────
    # Mengikuti Tabel Kategori Jenjang (kriteria: >= M+1SD -> Tinggi,
    # M-1SD s/d M+1SD -> Sedang, < M-1SD -> Rendah), TAPI dengan 2 penyesuaian
    # supaya kategori "Tinggi" (Ketat) benar-benar bisa muncul:
    #
    #   1) Dihitung LANGSUNG per sekolah (bukan rata-rata tiap cluster FCM
    #      lagi) - merata-ratakan dulu per cluster meredam nilai ekstrem
    #      individual sehingga nyaris tidak pernah menembus ambang M±1SD.
    #
    #   2) Rasio 2SFCA (kuota/pendaftar) di-LOG-TRANSFORM dulu sebelum
    #      dihitung M & SD-nya. Rasio ini distribusinya condong (skewed) ke
    #      kanan - ada segelintir sekolah sangat longgar (rasio 3-6x rata-
    #      rata) yang membuat SD mentah jadi sangat besar, sehingga ambang
    #      M-1SD mentah jadi terlalu rendah dan tidak ada sekolah manapun
    #      yang cukup ketat untuk melewatinya. Log-transform adalah teknik
    #      statistik standar untuk data rasio yang skewed: menyimetriskan
    #      distribusinya supaya M±1SD bisa membagi ketiga kategori secara
    #      proporsional.
    #
    # rasio 2SFCA asli (Rj = Sj/Pk = kuota/pendaftar, Luo & Wang): semakin
    # BESAR nilainya, semakin LONGGAR/mudah akses; semakin KECIL, semakin
    # KETAT. Karena arah nilainya terbalik dari "tingkat keketatan" yang mau
    # dikategorikan, arah threshold Tabel Kategori Jenjang ikut dibalik
    # supaya makna label tetap benar (Tinggi = keketatan tinggi/Ketat,
    # Rendah = keketatan rendah/Longgar):
    #   log(Rj) <  M - 1SD  -> Tinggi  (rasio jauh di bawah rata-rata -> ketat)
    #   M-1SD..M+1SD        -> Sedang
    #   log(Rj) >= M + 1SD  -> Rendah  (rasio jauh di atas rata-rata  -> longgar)
    rasio_asli = df_fcm[kolom_rasio_asli].clip(lower=1e-6)
    log_rasio = np.log(rasio_asli)
    M = log_rasio.mean()
    SD = log_rasio.std(ddof=0)

    def _kategori_msd(log_nilai: float) -> str:
        if log_nilai < M - SD:
            return "Tinggi"
        elif log_nilai >= M + SD:
            return "Rendah"
        else:
            return "Sedang"

    df_fcm = df_fcm.copy()
    df_fcm["cluster_idx"] = cluster_idx
    df_fcm["cluster_label"] = log_rasio.map(_kategori_msd)
    df_fcm["membership_max"] = u.max(axis=0)

    # label_map di sini hanya referensi kategori MAYORITAS tiap cluster FCM
    # (mis. untuk keperluan tampilan ringkasan), TIDAK lagi dipakai untuk
    # menentukan cluster_label tiap sekolah (sudah per-individu di atas).
    label_map = {}
    for c in range(n_clusters):
        sub = df_fcm.loc[df_fcm["cluster_idx"] == c, "cluster_label"]
        label_map[c] = sub.mode().iloc[0] if not sub.empty else "Sedang"

    return cntr, u, label_map, df_fcm


# ──────────────────────────────────────────────────────────────────────────────
# 2. RANDOM FOREST  – Prediksi probabilitas diterima
# ──────────────────────────────────────────────────────────────────────────────

def generate_training_data(df_fcm: pd.DataFrame, n_samples: int = 5000,
                            seed: int = 42,
                            tahun_list: tuple = (2022, 2024, 2025, 2026)) -> pd.DataFrame:
    """
    Bangun data latih dari data pendaftar RIIL di data/dataset_pendaftar/.
    Fitur: [jarak_m, status_zona, rasio_pendaftar_sekolah, cluster_label]
    Target: diterima (1) / tidak (0)

    Tahun 2025 & 2026 (punya sheet per-siswa):
    - Kelas "diterima" (1): 100% DATA RIIL — jarak domisili sesungguhnya
      tiap siswa yang lolos, dibaca langsung dari sheet
      '<Sekolah> - DOMISILI' (load_pendaftar_detail()).
    - Kelas "tidak diterima" (0): data sumber SPMB tidak mencatat domisili
      siswa yang ditolak (hanya jumlah totalnya), sehingga baris kelas ini
      tetap disimulasikan — namun jumlahnya DIKALIBRASI ke jumlah penolakan
      RIIL tiap sekolah tiap tahun (pendaftar_dalam - diterima_dalam), dan
      jaraknya disebar di ATAS batas radius riil sekolah tsb.

    Tahun 2022 & 2024 (HANYA data ringkasan per sekolah, TIDAK ada data
    per-siswa individual):
    - Kelas "diterima" (1) DISIMULASIKAN dengan linspace dari jarak_min ke
      jarak_max RIIL sekolah tsb — metode yang sama dengan "Fungsi Linspace"
      pada BAB 4 (lihat Gambar 4.9) — sejumlah siswa diterima riil
      (diterima_dalam; fallback ke min(kuota_dalam, pendaftar_dalam) untuk
      tahun 2024 karena sumber datanya tidak mencantumkan diterima_dalam).
    - Kelas "tidak diterima" (0): sama seperti tahun 2025/2026, dikalibrasi
      ke jumlah penolakan riil dan disebar di atas jarak_max.

    CATATAN SUMBER DATA (2024): kolom "jarak_min"/"jarak_max" tahun 2024
    diambil dari kolom Excel bernama "Nilai Min" / "Nilai max" pada sheet
    "Hasil seleksi" — BUKAN kolom "Jarak" — sehingga belum bisa dipastikan
    itu betul jarak dalam meter atau metrik seleksi lain (lihat
    keterangan_batas pada load_ringkasan_sekolah()). Untuk tahun 2022,
    kolom sumbernya memang "Jarak max" (meter) sehingga lebih aman
    dipakai; jarak_min 2022 tidak tersedia di sumber sehingga diasumsikan
    0 (sama seperti titik awal linspace pada Gambar 4.9).

    Parameter n_samples dipertahankan untuk kompatibilitas signature, namun
    tidak lagi dipakai sebagai jumlah baris pasti karena jumlah data kini
    mengikuti volume data riil yang tersedia (silakan lihat log jumlah baris
    aktual yang dicetak main()).
    """
    df_fcm_idx = df_fcm.copy()
    df_fcm_idx["nomor"] = df_fcm_idx["nama"].str.extract(r"(\d+)")[0].astype(float).astype("Int64")
    info_sekolah = {
        int(r["nomor"]): {"rasio_pendaftar": r["rasio_pendaftar"], "cluster_label": r["cluster_label"]}
        for _, r in df_fcm_idx.iterrows() if pd.notna(r["nomor"])
    }

    tahun_sheet = [t for t in tahun_list if t in get_tahun_punya_sheet_per_sekolah()]
    tahun_ringkasan = [t for t in tahun_list if t not in get_tahun_punya_sheet_per_sekolah()]
    records = []

    # === Tahun dengan data per-siswa riil (2025, 2026) ===
    for tahun in tahun_sheet:
        ring = load_ringkasan_sekolah(tahun)
        for _, srow in ring.iterrows():
            m = re.search(r"(\d+)", str(srow["nama"]))
            if not m:
                continue
            nomor = int(m.group(1))
            info = info_sekolah.get(nomor)
            if info is None:
                continue
            pendaftar = srow.get("pendaftar_dalam")
            diterima_n = srow.get("diterima_dalam")
            if pd.isna(pendaftar):
                continue

            df_det = load_pendaftar_detail(tahun, nomor)
            if df_det is None or df_det.empty:
                continue
            jarak_riil = df_det["Jarak (m)"].dropna()
            if jarak_riil.empty:
                continue
            cutoff = float(jarak_riil.max())

            # === kelas "diterima" (1) — 100% data riil ===
            for j in jarak_riil:
                records.append({
                    "jarak_m": round(float(j), 2),
                    "dalam_zona": 1,
                    "rasio_pendaftar": round(info["rasio_pendaftar"], 4),
                    "cluster_label": info["cluster_label"],
                    "diterima": 1,
                })

            # === kelas "tidak diterima" (0) — jumlah dikalibrasi ke data riil ===
            n_tolak = int(pendaftar) - int(diterima_n if not pd.isna(diterima_n) else len(jarak_riil))
            n_tolak = max(0, n_tolak)
            if n_tolak > 0:
                rng = np.random.default_rng(1000 * tahun + nomor + seed)
                jarak_tolak = cutoff + rng.lognormal(
                    mean=np.log(max(cutoff * 0.3, 50)), sigma=0.9, size=n_tolak
                )
                jarak_tolak = np.clip(jarak_tolak, cutoff + 1, cutoff + 8000)
                for j in jarak_tolak:
                    records.append({
                        "jarak_m": round(float(j), 2),
                        "dalam_zona": 1,
                        "rasio_pendaftar": round(info["rasio_pendaftar"], 4),
                        "cluster_label": info["cluster_label"],
                        "diterima": 0,
                    })

    # === Tahun ringkasan saja (2022, 2024) — simulasi linspace jarak_min-jarak_max riil ===
    for tahun in tahun_ringkasan:
        ring = load_ringkasan_sekolah(tahun)
        for _, srow in ring.iterrows():
            m = re.search(r"(\d+)", str(srow["nama"]))
            if not m:
                continue
            nomor = int(m.group(1))
            info = info_sekolah.get(nomor)
            if info is None:
                continue

            pendaftar = srow.get("pendaftar_dalam")
            jarak_max_riil = srow.get("jarak_max")
            if pd.isna(pendaftar) or pd.isna(jarak_max_riil):
                continue
            jarak_max_riil = float(jarak_max_riil)

            diterima_n = srow.get("diterima_dalam")
            kuota = srow.get("kuota_dalam")
            if pd.isna(diterima_n):
                diterima_n = min(kuota, pendaftar) if pd.notna(kuota) else pendaftar
            n_diterima = int(diterima_n)
            if n_diterima <= 0:
                continue

            jarak_min_riil = srow.get("jarak_min")
            jarak_min_pakai = float(jarak_min_riil) if pd.notna(jarak_min_riil) else 0.0

            # === kelas "diterima" (1) — simulasi linspace antar batas riil ===
            jarak_diterima = np.linspace(jarak_min_pakai, jarak_max_riil, n_diterima)
            for j in jarak_diterima:
                records.append({
                    "jarak_m": round(float(j), 2),
                    "dalam_zona": 1,
                    "rasio_pendaftar": round(info["rasio_pendaftar"], 4),
                    "cluster_label": info["cluster_label"],
                    "diterima": 1,
                })

            # === kelas "tidak diterima" (0) — jumlah dikalibrasi ke data riil ===
            n_tolak = max(0, int(pendaftar) - n_diterima)
            if n_tolak > 0:
                rng = np.random.default_rng(1000 * tahun + nomor + seed)
                jarak_tolak = jarak_max_riil + rng.lognormal(
                    mean=np.log(max(jarak_max_riil * 0.3, 50)), sigma=0.9, size=n_tolak
                )
                jarak_tolak = np.clip(jarak_tolak, jarak_max_riil + 1, jarak_max_riil + 8000)
                for j in jarak_tolak:
                    records.append({
                        "jarak_m": round(float(j), 2),
                        "dalam_zona": 1,
                        "rasio_pendaftar": round(info["rasio_pendaftar"], 4),
                        "cluster_label": info["cluster_label"],
                        "diterima": 0,
                    })

    return pd.DataFrame(records)


def train_rf(df_train: pd.DataFrame):
    """Train Random Forest Classifier. Return (model, label_encoder, feature_names)."""
    le = LabelEncoder()
    df_train = df_train.copy()
    df_train["cluster_enc"] = le.fit_transform(df_train["cluster_label"])

    features = ["jarak_m", "dalam_zona", "rasio_pendaftar", "cluster_enc"]
    X = df_train[features].values
    y = df_train["diterima"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=10,
        min_samples_leaf=5,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)

    print("=== Random Forest Evaluation ===")
    y_pred = clf.predict(X_test)
    print(classification_report(y_test, y_pred, target_names=["Tidak Diterima", "Diterima"]))

    return clf, le, features


# ──────────────────────────────────────────────────────────────────────────────
# 3. SIMPAN MODEL
# ──────────────────────────────────────────────────────────────────────────────

def main():
    print("📊 Menghitung fitur FCM dari data sekolah...")
    df_fcm = hitung_fitur_fcm(SEKOLAH_NEGERI)

    print("🔵 Training Fuzzy C-Means...")
    cntr, u, label_map, df_fcm = train_fcm(df_fcm, n_clusters=3)

    print("\nKategori label Tinggi/Sedang/Rendah dihitung dengan rumus M ± 1 SD "
          "atas rasio aksesibilitas 2SFCA (kuota/pendaftar) seluruh sekolah "
          "(arah threshold dibalik dari Tabel Kategori Jenjang karena rasio "
          "besar = longgar, bukan ketat).")
    print("\nHasil Clustering Sekolah:")
    print(df_fcm[["nama", "rasio_pendaftar", "jarak_batas_km",
                  "cluster_label", "membership_max"]].to_string(index=False))

    print("\n🌳 Membangun data training RF (kelas diterima = data riil, "
          "kelas ditolak = kalibrasi jumlah riil)...")
    df_train = generate_training_data(df_fcm, n_samples=8000)
    print(f"   Total baris: {len(df_train)} "
          f"(diterima riil: {(df_train['diterima']==1).sum()}, "
          f"ditolak kalibrasi: {(df_train['diterima']==0).sum()})")

    print("🌳 Training Random Forest...")
    rf_model, le, feature_names = train_rf(df_train)

    # Simpan semua artefak
    os.makedirs(os.path.dirname(__file__), exist_ok=True)
    joblib.dump({
        "cntr": cntr,
        "u": u,
        "label_map": label_map,
        "df_sekolah_clustered": df_fcm,
    }, os.path.join(os.path.dirname(__file__), "fcm_model.pkl"))

    joblib.dump({
        "model": rf_model,
        "label_encoder": le,
        "feature_names": feature_names,
    }, os.path.join(os.path.dirname(__file__), "rf_model.pkl"))

    print("\n✅ Model disimpan: models/fcm_model.pkl & models/rf_model.pkl")


if __name__ == "__main__":
    main()
