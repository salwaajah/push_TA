"""
utils/dataset_loader.py
Loader untuk dataset Excel multi-tahun (2022, 2024, 2025, 2026) yang dipakai oleh
menu admin: Kelola Pendaftar, Kelola Kuota, dan Kelola Data Swasta.

Catatan struktur sumber data (tidak seragam antar tahun):
- 2025 & 2026 : punya sheet per sekolah "SMP NEGERI n - DOMISILI" (n = 1..75)
                berisi data pendaftar per siswa (termasuk kolom jarak/skor jarak).
- 2024        : TIDAK punya sheet per sekolah. Data ringkas ada di sheet
                "Kuota Sekolah" (kuota & pendaftar) dan "Hasil seleksi"
                (Nilai Min / Nilai Max per sekolah - bukan jarak dalam meter).
- 2022        : TIDAK punya sheet per sekolah. Data ringkas ada di "Sheet1"
                (kuota dalam/luar, pendaftar dalam/luar, hasil, dan "Jarak max"
                saja - tidak ada jarak minimum).

Karena itu, untuk tahun 2022 & 2024 halaman "Kelola Pendaftar" menampilkan
ringkasan (jarak/nilai min-max) alih-alih daftar pendaftar per-siswa.
"""

import os
import re
import json
import shutil
import pandas as pd
import streamlit as st
import openpyxl

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(BASE_DIR, "data", "dataset_pendaftar")
TAHUN_CONFIG_PATH = os.path.join(BASE_DIR, "data", "tahun_config.json")


def bersihkan_kolom_kosong(df: "pd.DataFrame") -> "pd.DataFrame":
    """Hapus kolom yang seluruh isinya kosong (NaN / None / string kosong)
    dari sebuah tabel, supaya tabel tidak menampilkan kolom berisi 'None'
    di semua barisnya. Dipakai sebelum menampilkan tabel (st.dataframe) di
    berbagai menu (Kelola Kuota, Hasil Seleksi, dll)."""
    if df is None or df.empty:
        return df
    kolom_kosong = [
        c for c in df.columns
        if df[c].isna().all()
        or df[c].astype(str).str.strip().str.lower().isin(["", "none", "nan", "nat"]).all()
    ]
    return df.drop(columns=kolom_kosong) if kolom_kosong else df

# ── Registry tahun ajaran (dinamis, tersimpan di data/tahun_config.json) ──────
# Struktur tiap entri: {"file": "dataset_2025.xlsx", "sheet_per_sekolah": true}
_DEFAULT_TAHUN_CONFIG = {
    "2022": {"file": "dataset_2022.xlsx", "sheet_per_sekolah": False},
    "2024": {"file": "dataset_2024.xlsx", "sheet_per_sekolah": False},
    "2025": {"file": "dataset_2025.xlsx", "sheet_per_sekolah": True},
    "2026": {"file": "dataset_2026.xlsx", "sheet_per_sekolah": True},
}


def _muat_tahun_config() -> dict:
    if not os.path.exists(TAHUN_CONFIG_PATH):
        os.makedirs(os.path.dirname(TAHUN_CONFIG_PATH), exist_ok=True)
        with open(TAHUN_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(_DEFAULT_TAHUN_CONFIG, f, indent=2, ensure_ascii=False)
        return dict(_DEFAULT_TAHUN_CONFIG)
    with open(TAHUN_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _simpan_tahun_config(cfg: dict):
    with open(TAHUN_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def _file_per_tahun() -> dict:
    cfg = _muat_tahun_config()
    return {int(t): os.path.join(DATASET_DIR, v["file"]) for t, v in cfg.items()}


def get_tahun_tersedia() -> list:
    """Daftar tahun (angka) yang tersedia, terurut naik."""
    return sorted(int(t) for t in _muat_tahun_config().keys())


def get_tahun_punya_sheet_per_sekolah() -> list:
    cfg = _muat_tahun_config()
    return sorted(int(t) for t, v in cfg.items() if v.get("sheet_per_sekolah"))


def format_tahun_ajaran(tahun: int) -> str:
    """Format tampilan tahun ajaran, contoh: 2025 -> '2025/2026'."""
    try:
        tahun = int(tahun)
        return f"{tahun}/{tahun + 1}"
    except (TypeError, ValueError):
        return str(tahun)


# Kompatibilitas dengan kode lama yang memakai konstanta langsung.
# (Dievaluasi sekali saat modul di-import; halaman yang butuh nilai selalu
# terbaru sebaiknya memanggil get_tahun_tersedia()/get_tahun_punya_sheet_per_sekolah().)
FILE_PER_TAHUN = _file_per_tahun()
TAHUN_TERSEDIA = get_tahun_tersedia()
TAHUN_PUNYA_SHEET_PER_SEKOLAH = get_tahun_punya_sheet_per_sekolah()


def _to_float(v):
    try:
        if v is None:
            return None
        return float(str(v).replace(",", "."))
    except (ValueError, TypeError):
        return None


@st.cache_resource(show_spinner=False)
def _load_workbook(tahun: int):
    path = _file_per_tahun().get(tahun)
    if not path or not os.path.exists(path):
        return None
    return openpyxl.load_workbook(path, read_only=True, data_only=True)


def _cari_sheet_sekolah(wb, nomor: int):
    """Cari sheet 'SMP NEGERI n - DOMISILI', mengakomodasi spasi ganda pada
    beberapa nomor sekolah (16-75) di file sumber."""
    kandidat = [
        f"SMP NEGERI {nomor} - DOMISILI",
        f"SMP  NEGERI {nomor} - DOMISILI",
    ]
    for nama in kandidat:
        if nama in wb.sheetnames:
            return wb[nama]
    # fallback: cocokkan dengan regex, jaga-jaga ada variasi spasi lain
    pola = re.compile(rf"SMP\s+NEGERI\s+{nomor}\s*-\s*DOMISILI", re.IGNORECASE)
    for nama in wb.sheetnames:
        if pola.match(nama.strip()):
            return wb[nama]
    return None


@st.cache_data(show_spinner=False, ttl=3600)
def load_pendaftar_detail(tahun: int, nomor_sekolah: int) -> pd.DataFrame | None:
    """Mengambil daftar pendaftar per-siswa untuk 1 sekolah (hanya tersedia
    untuk tahun 2025 & 2026). Mengembalikan None jika sheet tidak ditemukan
    atau tahun tidak punya data per-siswa."""
    if tahun not in get_tahun_punya_sheet_per_sekolah():
        return None

    wb = _load_workbook(tahun)
    if wb is None:
        return None

    ws = _cari_sheet_sekolah(wb, nomor_sekolah)
    if ws is None:
        return None

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return None

    data_rows = rows[1:]  # baris pertama = header
    hasil = []
    for r in data_rows:
        if r is None or r[0] is None:
            continue
        no, kode, nama, luar_daerah, daftar_ulang, asal_sd, tgl_lahir = (
            r[0], r[1], r[2], r[3], r[4], r[5], r[6]
        )
        jarak = _to_float(r[7]) if len(r) > 7 else None
        hasil.append({
            "No": int(no) if no is not None else None,
            "Kode Pendaftar": kode,
            "Nama": nama,
            "Luar Daerah": luar_daerah,
            "Daftar Ulang": daftar_ulang,
            "Asal Sekolah Dasar": asal_sd,
            "Tanggal Lahir": tgl_lahir,
            "Jarak (m)": jarak,
        })

    if not hasil:
        return None
    df = pd.DataFrame(hasil)
    for kol in ["Kode Pendaftar", "Nama", "Luar Daerah", "Daftar Ulang", "Asal Sekolah Dasar"]:
        df[kol] = df[kol].astype(str).replace("None", "")
    return df


@st.cache_data(show_spinner=False, ttl=3600)
def load_ringkasan_sekolah(tahun: int) -> pd.DataFrame:
    """Mengambil ringkasan per-sekolah (kuota, pendaftar, jarak/nilai min-max
    jika tersedia) untuk tahun berapa pun. Mengembalikan DataFrame dengan
    kolom standar:
    nama, kuota_dalam, kuota_luar, pendaftar_dalam, pendaftar_luar,
    diterima_dalam, diterima_luar, jarak_min, jarak_max, keterangan_batas
    """
    wb = _load_workbook(tahun)
    if wb is None:
        return pd.DataFrame()

    if tahun == 2022:
        ws = wb["Sheet1"]
        rows = list(ws.iter_rows(values_only=True))[1:]
        hasil = []
        for r in rows:
            if not r or r[0] is None:
                continue
            nama = str(r[0]).replace("-ZONASI", "").replace("- ZONASI", "").replace(" - ZONASI", "").strip()
            hasil.append({
                "nama": nama,
                "kuota_dalam": _to_float(r[2]),
                "kuota_luar": _to_float(r[3]),
                "pendaftar_dalam": _to_float(r[4]),
                "pendaftar_luar": _to_float(r[5]),
                "diterima_dalam": _to_float(r[6]),
                "diterima_luar": _to_float(r[7]),
                "jarak_min": None,
                "jarak_max": _to_float(r[8]) if len(r) > 8 else None,
                "keterangan_batas": "Jarak Max saja (data sumber 2022 tidak menyediakan jarak minimum)",
            })
        return pd.DataFrame(hasil)

    if tahun == 2024:
        ws_kuota = wb["Kuota Sekolah"]
        rows_kuota = list(ws_kuota.iter_rows(values_only=True))[1:]
        kuota_map = {}
        for r in rows_kuota:
            if not r or r[2] is None:
                continue
            kuota_map[str(r[2]).strip()] = {
                "kuota_dalam": _to_float(r[4]),
                "pendaftar_dalam": _to_float(r[5]),
                "alamat": r[3],
            }

        ws_hasil = wb["Hasil seleksi"]
        rows_hasil = list(ws_hasil.iter_rows(values_only=True))[1:]
        hasil = []
        for r in rows_hasil:
            if not r or r[3] is None:
                continue
            # Beberapa sekolah punya 2 baris (jalur dalam & luar daerah).
            # Ambil baris "dalam daerah" (kolom Luar daerah == 'Tidak') saja
            # agar konsisten 1 baris per sekolah.
            luar_daerah = str(r[1]).strip().lower() if r[1] is not None else ""
            if luar_daerah == "ya":
                continue
            nama = str(r[3]).strip()
            base = kuota_map.get(nama, {})
            hasil.append({
                "nama": nama,
                "kuota_dalam": base.get("kuota_dalam"),
                "kuota_luar": None,
                "pendaftar_dalam": base.get("pendaftar_dalam"),
                "pendaftar_luar": None,
                "diterima_dalam": None,
                "diterima_luar": None,
                "jarak_min": _to_float(r[6]),
                "jarak_max": _to_float(r[7]),
                "keterangan_batas": "Nilai Min/Max (bukan jarak meter - data sumber 2024 tidak menyediakan sheet per sekolah)",
            })
        return pd.DataFrame(hasil)

    sheet_name = f"Kuota Sekolah_{tahun}"
    if sheet_name in wb.sheetnames:
        # Struktur "Kuota Sekolah_{tahun}" dipakai 2025, 2026, dan setiap
        # tahun ajaran baru yang dibuat lewat menu "Tambah Tahun Ajaran".
        # Deteksi kolom dari header (bukan hardcode tahun) supaya tahun baru
        # dengan struktur ringkas (mis. seperti 2026: Nama, Jalur, Kuota,
        # Pendaftar, Hasil) tetap terbaca benar.
        ws = wb[sheet_name]
        semua_baris = list(ws.iter_rows(values_only=True))
        if not semua_baris:
            return pd.DataFrame()
        header = [str(h).strip().lower() if h else "" for h in semua_baris[0]]
        punya_kolom_luar = any("luar" in h for h in header)

        # Untuk tahun yang punya sheet per sekolah (mis. 2026 dst.) tapi
        # sheet ringkasannya TIDAK punya kolom Kuota/Pendaftar Luar terpisah
        # (punya_kolom_luar == False), Jalur Domisili Batasan tetap bisa
        # dihitung dari kolom 'Luar Daerah' pada sheet per-siswa untuk 8 SMP
        # Negeri resmi (SEKOLAH_DOMISILI_BATASAN) -- supaya menu Hasil Seleksi
        # tidak menampilkan "data belum tersedia" padahal datanya ada di
        # sheet per-siswa (lihat menu Kelola Pendaftar).
        from data.sekolah_data import SEKOLAH_DOMISILI_BATASAN
        tahun_punya_sheet = tahun in get_tahun_punya_sheet_per_sekolah()

        hasil = []
        for r in semua_baris[1:]:
            if not r or r[0] is None:
                continue
            nama = str(r[0]).strip()
            if punya_kolom_luar:
                hasil.append({
                    "nama": nama,
                    "kuota_dalam": _to_float(r[2]) if len(r) > 2 else None,
                    "kuota_luar": _to_float(r[3]) if len(r) > 3 else None,
                    "pendaftar_dalam": _to_float(r[4]) if len(r) > 4 else None,
                    "pendaftar_luar": _to_float(r[5]) if len(r) > 5 else None,
                    "diterima_dalam": _to_float(r[6]) if len(r) > 6 else None,
                    "diterima_luar": _to_float(r[7]) if len(r) > 7 else None,
                    "jarak_min": None,
                    "jarak_max": None,
                    "keterangan_batas": "Lihat detail per-siswa di menu Kelola Pendaftar",
                })
            else:  # struktur ringkas: Nama, Jalur, Kuota, Pendaftar, Hasil
                kuota_luar_v = None
                pendaftar_luar_v = None
                diterima_luar_v = None
                keterangan = "Lihat detail per-siswa di menu Kelola Pendaftar"

                if tahun_punya_sheet:
                    m_nomor = re.search(r"(\d+)", nama)
                    nomor_sek = int(m_nomor.group(1)) if m_nomor else None
                    if nomor_sek in SEKOLAH_DOMISILI_BATASAN:
                        df_det_sek = load_pendaftar_detail(tahun, nomor_sek)
                        if df_det_sek is not None and not df_det_sek.empty:
                            jumlah_luar = int(
                                df_det_sek["Luar Daerah"].astype(str).str.strip()
                                .str.lower().eq("ya").sum()
                            )
                            if jumlah_luar > 0:
                                # Berkas sumber tahun ini tidak mencatat kuota
                                # Domisili Batasan terpisah; disamakan dengan
                                # jumlah pendaftar Luar Daerah tercatat (pola
                                # yang sama seperti data tahun 2025, di mana
                                # kuota luar == pendaftar luar untuk 8 SMP
                                # Negeri Jalur Domisili Batasan resmi ini).
                                pendaftar_luar_v = float(jumlah_luar)
                                kuota_luar_v = pendaftar_luar_v
                                diterima_luar_v = pendaftar_luar_v
                                keterangan = (
                                    "Kuota/Pendaftar Domisili Batasan dihitung dari "
                                    "kolom 'Luar Daerah' pada sheet per-siswa (berkas "
                                    "sumber tahun ini tidak memiliki kolom Kuota/"
                                    "Pendaftar Batasan terpisah di sheet ringkasan)."
                                )

                hasil.append({
                    "nama": nama,
                    "kuota_dalam": _to_float(r[2]) if len(r) > 2 else None,
                    "kuota_luar": kuota_luar_v,
                    "pendaftar_dalam": _to_float(r[3]) if len(r) > 3 else None,
                    "pendaftar_luar": pendaftar_luar_v,
                    "diterima_dalam": _to_float(r[4]) if len(r) > 4 else None,
                    "diterima_luar": diterima_luar_v,
                    "jarak_min": None,
                    "jarak_max": None,
                    "keterangan_batas": keterangan,
                })
        return pd.DataFrame(hasil)

    return pd.DataFrame()


def _invalidate_cache():
    """Bersihkan cache loader supaya perubahan langsung terlihat."""
    _load_workbook.clear()
    load_pendaftar_detail.clear()
    load_ringkasan_sekolah.clear()
    load_hasil_seleksi.clear()
    load_jarak_minmax_jalur.clear()


def _load_workbook_writable(tahun: int):
    path = _file_per_tahun().get(tahun)
    if not path or not os.path.exists(path):
        return None, path
    wb = openpyxl.load_workbook(path, data_only=False)
    return wb, path


def save_pendaftar_row(tahun: int, nomor_sekolah: int, data: dict, no_existing=None):
    """Tambah (no_existing=None) atau ubah (no_existing=nomor 'No' baris)
    satu baris pendaftar pada sheet per-sekolah. Hanya berlaku untuk tahun
    yang punya sheet per sekolah (2025, 2026)."""
    if tahun not in get_tahun_punya_sheet_per_sekolah():
        raise ValueError(f"Tahun {tahun} tidak memiliki data pendaftar per-siswa.")

    wb, path = _load_workbook_writable(tahun)
    if wb is None:
        raise FileNotFoundError(f"Berkas dataset tahun {tahun} tidak ditemukan.")

    ws = _cari_sheet_sekolah(wb, nomor_sekolah)
    if ws is None:
        raise ValueError(f"Sheet untuk sekolah nomor {nomor_sekolah} tidak ditemukan.")

    if no_existing is not None:
        target_row = None
        for r in range(2, ws.max_row + 1):
            if ws.cell(row=r, column=1).value == no_existing:
                target_row = r
                break
        if target_row is None:
            raise ValueError("Baris pendaftar yang akan diubah tidak ditemukan.")
    else:
        max_no = 0
        for r in range(2, ws.max_row + 1):
            v = ws.cell(row=r, column=1).value
            if isinstance(v, (int, float)):
                max_no = max(max_no, int(v))
        target_row = ws.max_row + 1
        ws.cell(row=target_row, column=1, value=max_no + 1)
        ws.cell(row=target_row, column=2, value=f"SMPN{nomor_sekolah}-{max_no + 1:04d}")

    ws.cell(row=target_row, column=3, value=data.get("nama", ""))
    ws.cell(row=target_row, column=4, value=data.get("luar_daerah", ""))
    ws.cell(row=target_row, column=6, value=data.get("asal_sd", ""))
    ws.cell(row=target_row, column=7, value=data.get("tgl_lahir", ""))
    ws.cell(row=target_row, column=8, value=data.get("jarak"))

    wb.save(path)
    _invalidate_cache()


def delete_pendaftar_row(tahun: int, nomor_sekolah: int, no_existing):
    if tahun not in get_tahun_punya_sheet_per_sekolah():
        raise ValueError(f"Tahun {tahun} tidak memiliki data pendaftar per-siswa.")

    wb, path = _load_workbook_writable(tahun)
    if wb is None:
        raise FileNotFoundError(f"Berkas dataset tahun {tahun} tidak ditemukan.")

    ws = _cari_sheet_sekolah(wb, nomor_sekolah)
    if ws is None:
        raise ValueError(f"Sheet untuk sekolah nomor {nomor_sekolah} tidak ditemukan.")

    target_row = None
    for r in range(2, ws.max_row + 1):
        if ws.cell(row=r, column=1).value == no_existing:
            target_row = r
            break
    if target_row is None:
        raise ValueError("Baris pendaftar yang akan dihapus tidak ditemukan.")

    ws.delete_rows(target_row, 1)
    wb.save(path)
    _invalidate_cache()


def update_kuota_sekolah(tahun: int, nama_sekolah: str, kuota_dalam=None, kuota_luar=None):
    """Ubah kuota (dalam/luar) satu sekolah pada sheet ringkasan tahun
    tersebut. Struktur sheet berbeda-beda tiap tahun, ditangani per kasus."""
    wb, path = _load_workbook_writable(tahun)
    if wb is None:
        raise FileNotFoundError(f"Berkas dataset tahun {tahun} tidak ditemukan.")

    ditemukan = False

    if tahun == 2022:
        ws = wb["Sheet1"]
        for r in range(2, ws.max_row + 1):
            raw_nama = ws.cell(row=r, column=1).value
            if raw_nama is None:
                continue
            nm = str(raw_nama).replace("-ZONASI", "").replace("- ZONASI", "").replace(" - ZONASI", "").strip()
            if nm == nama_sekolah:
                if kuota_dalam is not None:
                    ws.cell(row=r, column=3, value=kuota_dalam)
                if kuota_luar is not None:
                    ws.cell(row=r, column=4, value=kuota_luar)
                ditemukan = True
                break

    elif tahun == 2024:
        ws = wb["Kuota Sekolah"]
        for r in range(2, ws.max_row + 1):
            nm = ws.cell(row=r, column=3).value
            if nm is not None and str(nm).strip() == nama_sekolah:
                if kuota_dalam is not None:
                    ws.cell(row=r, column=5, value=kuota_dalam)
                ditemukan = True
                break

    else:
        # 2025, 2026, dan setiap tahun ajaran baru yang ditambahkan lewat
        # menu "Tambah Tahun Ajaran" memakai struktur sheet yang sama:
        # "Kuota Sekolah_{tahun}" dengan kolom Kuota dalam/Kuota luar.
        sheet_name = f"Kuota Sekolah_{tahun}"
        if sheet_name not in wb.sheetnames:
            raise ValueError(f"Sheet '{sheet_name}' tidak ditemukan pada berkas tahun {tahun}.")
        ws = wb[sheet_name]
        for r in range(2, ws.max_row + 1):
            nm = ws.cell(row=r, column=1).value
            if nm is not None and str(nm).strip() == nama_sekolah:
                if kuota_dalam is not None:
                    ws.cell(row=r, column=3, value=kuota_dalam)
                if kuota_luar is not None:
                    ws.cell(row=r, column=4, value=kuota_luar)
                ditemukan = True
                break

    if not ditemukan:
        raise ValueError(f"Sekolah '{nama_sekolah}' tidak ditemukan pada data tahun {tahun}.")

    wb.save(path)
    _invalidate_cache()


def insert_kuota_sekolah(tahun: int, nama_sekolah: str, kuota_dalam=0, kuota_luar=None,
                          pendaftar_dalam=0, pendaftar_luar=None):
    """Tambah baris kuota/pendaftar sekolah baru pada sheet ringkasan tahun
    tersebut (dipakai oleh menu Kelola Kuota & Hasil Seleksi, mirip CRUD
    Tambah pada Kelola Sekolah)."""
    if not nama_sekolah:
        raise ValueError("Nama sekolah wajib diisi.")

    wb, path = _load_workbook_writable(tahun)
    if wb is None:
        raise FileNotFoundError(f"Berkas dataset tahun {tahun} tidak ditemukan.")

    if tahun == 2022:
        ws = wb["Sheet1"]
        for r in range(2, ws.max_row + 1):
            raw = ws.cell(row=r, column=1).value
            if raw is None:
                continue
            nm = str(raw).replace("-ZONASI", "").replace("- ZONASI", "").replace(" - ZONASI", "").strip()
            if nm == nama_sekolah:
                raise ValueError(f"Sekolah '{nama_sekolah}' sudah ada pada data tahun {tahun}.")
        target_row = ws.max_row + 1
        ws.cell(row=target_row, column=1, value=nama_sekolah)
        ws.cell(row=target_row, column=3, value=kuota_dalam)
        ws.cell(row=target_row, column=4, value=kuota_luar or 0)
        ws.cell(row=target_row, column=5, value=pendaftar_dalam)
        ws.cell(row=target_row, column=6, value=pendaftar_luar or 0)

    elif tahun == 2024:
        ws = wb["Kuota Sekolah"]
        for r in range(2, ws.max_row + 1):
            nm = ws.cell(row=r, column=3).value
            if nm is not None and str(nm).strip() == nama_sekolah:
                raise ValueError(f"Sekolah '{nama_sekolah}' sudah ada pada data tahun {tahun}.")
        target_row = ws.max_row + 1
        ws.cell(row=target_row, column=3, value=nama_sekolah)
        ws.cell(row=target_row, column=5, value=kuota_dalam)
        ws.cell(row=target_row, column=6, value=pendaftar_dalam)

        # Ringkasan tahun 2024 dibaca dari sheet "Hasil seleksi" (bukan
        # "Kuota Sekolah"), jadi baris baru juga perlu ditambahkan di sana
        # supaya langsung tampil di menu Kelola Kuota/Hasil Seleksi.
        ws_hasil = wb["Hasil seleksi"]
        target_row_hasil = ws_hasil.max_row + 1
        ws_hasil.cell(row=target_row_hasil, column=1, value=2024)
        ws_hasil.cell(row=target_row_hasil, column=2, value="Tidak")
        ws_hasil.cell(row=target_row_hasil, column=4, value=nama_sekolah)
        ws_hasil.cell(row=target_row_hasil, column=5, value="SMP")
        ws_hasil.cell(row=target_row_hasil, column=6, value="ZONASI")

    else:
        sheet_name = f"Kuota Sekolah_{tahun}"
        if sheet_name not in wb.sheetnames:
            raise ValueError(f"Sheet '{sheet_name}' tidak ditemukan pada berkas tahun {tahun}.")
        ws = wb[sheet_name]
        semua_baris = list(ws.iter_rows(values_only=True))
        header = [str(h).strip().lower() if h else "" for h in semua_baris[0]] if semua_baris else []
        punya_kolom_luar = any("luar" in h for h in header)

        for r in range(2, ws.max_row + 1):
            nm = ws.cell(row=r, column=1).value
            if nm is not None and str(nm).strip() == nama_sekolah:
                raise ValueError(f"Sekolah '{nama_sekolah}' sudah ada pada data tahun {tahun}.")

        target_row = ws.max_row + 1
        ws.cell(row=target_row, column=1, value=nama_sekolah)
        if punya_kolom_luar:
            ws.cell(row=target_row, column=3, value=kuota_dalam)
            ws.cell(row=target_row, column=4, value=kuota_luar or 0)
            ws.cell(row=target_row, column=5, value=pendaftar_dalam)
            ws.cell(row=target_row, column=6, value=pendaftar_luar or 0)
        else:
            ws.cell(row=target_row, column=2, value="Domisili")
            ws.cell(row=target_row, column=3, value=kuota_dalam)
            ws.cell(row=target_row, column=4, value=pendaftar_dalam)
            ws.cell(row=target_row, column=5, value=0)

    wb.save(path)
    _invalidate_cache()


def delete_kuota_sekolah(tahun: int, nama_sekolah: str):
    """Hapus baris kuota/pendaftar satu sekolah dari sheet ringkasan tahun
    tersebut (dipakai oleh menu Kelola Kuota & Hasil Seleksi)."""
    wb, path = _load_workbook_writable(tahun)
    if wb is None:
        raise FileNotFoundError(f"Berkas dataset tahun {tahun} tidak ditemukan.")

    ditemukan = False

    if tahun == 2022:
        ws = wb["Sheet1"]
        for r in range(2, ws.max_row + 1):
            raw = ws.cell(row=r, column=1).value
            if raw is None:
                continue
            nm = str(raw).replace("-ZONASI", "").replace("- ZONASI", "").replace(" - ZONASI", "").strip()
            if nm == nama_sekolah:
                ws.delete_rows(r, 1)
                ditemukan = True
                break

    elif tahun == 2024:
        ws = wb["Kuota Sekolah"]
        for r in range(2, ws.max_row + 1):
            nm = ws.cell(row=r, column=3).value
            if nm is not None and str(nm).strip() == nama_sekolah:
                ws.delete_rows(r, 1)
                ditemukan = True
                break

        # Hapus juga baris terkait di "Hasil seleksi" (sumber ringkasan
        # tahun 2024), bisa lebih dari satu baris (jalur dalam & luar daerah).
        ws_hasil = wb["Hasil seleksi"]
        for r in range(ws_hasil.max_row, 1, -1):
            nm = ws_hasil.cell(row=r, column=4).value
            if nm is not None and str(nm).strip() == nama_sekolah:
                ws_hasil.delete_rows(r, 1)
                ditemukan = True

    else:
        sheet_name = f"Kuota Sekolah_{tahun}"
        if sheet_name not in wb.sheetnames:
            raise ValueError(f"Sheet '{sheet_name}' tidak ditemukan pada berkas tahun {tahun}.")
        ws = wb[sheet_name]
        for r in range(2, ws.max_row + 1):
            nm = ws.cell(row=r, column=1).value
            if nm is not None and str(nm).strip() == nama_sekolah:
                ws.delete_rows(r, 1)
                ditemukan = True
                break

    if not ditemukan:
        raise ValueError(f"Sekolah '{nama_sekolah}' tidak ditemukan pada data tahun {tahun}.")

    wb.save(path)
    _invalidate_cache()


# ──────────────────────────────────────────────────────────────────────────
# Hasil Seleksi: ringkasan diterima/ditolak per sekolah, dipisah jalur
# Domisili (dalam daerah) dan Domisili Batasan (luar daerah / radius
# perluasan), untuk tahun 2022-2026. Aturan: jumlah diterima = min(kuota,
# pendaftar) — konsisten dengan aturan seleksi SPMB jalur domisili.
# ──────────────────────────────────────────────────────────────────────────

JALUR_LABEL = {"dalam": "Domisili", "luar": "Domisili Batasan"}


@st.cache_data(show_spinner=False, ttl=3600)
def load_hasil_seleksi(tahun: int) -> pd.DataFrame:
    """Ringkasan hasil seleksi per sekolah & jalur untuk satu tahun.
    Kolom: tahun, nama, jalur, kuota, pendaftar, diterima, ditolak,
    jarak_min, jarak_max, keterangan_jarak."""
    df = load_ringkasan_sekolah(tahun)
    if df.empty:
        return df

    rows = []
    for _, r in df.iterrows():
        for suffix, jalur in JALUR_LABEL.items():
            kuota = r.get(f"kuota_{suffix}")
            pendaftar = r.get(f"pendaftar_{suffix}")
            if pd.isna(kuota) and pd.isna(pendaftar):
                continue
            kuota_v = float(kuota) if pd.notna(kuota) else 0.0
            pendaftar_v = float(pendaftar) if pd.notna(pendaftar) else 0.0
            diterima = min(kuota_v, pendaftar_v)
            ditolak = max(0.0, pendaftar_v - kuota_v)
            rows.append({
                "tahun": tahun,
                "nama": r["nama"],
                "jalur": jalur,
                "kuota": kuota_v,
                "pendaftar": pendaftar_v,
                "diterima": diterima,
                "ditolak": ditolak,
                # jarak_min/jarak_max sumber sudah menggambarkan rentang
                # jalur dalam (Domisili); untuk jalur luar belum tersedia
                # rincian jarak terpisah pada berkas sumber.
                "jarak_min": r.get("jarak_min") if suffix == "dalam" else None,
                "jarak_max": r.get("jarak_max") if suffix == "dalam" else None,
                "keterangan_jarak": r.get("keterangan_batas"),
            })
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=3600)
def load_jarak_minmax_jalur(tahun: int, nomor_batasan: tuple) -> pd.DataFrame:
    """Tabel jarak (m) min-max per sekolah, dipisah Jalur Domisili & Jalur
    Domisili Batasan.

    - Tahun dengan data per-siswa (2025, 2026, dan tahun ajaran baru yang
      punya sheet per sekolah): dihitung langsung dari kolom 'Jarak (m)'
      & 'Luar Daerah' pada sheet per-sekolah. Jalur Domisili Batasan hanya
      dihitung untuk sekolah yang terdaftar di `nomor_batasan` (SMP dengan
      Jalur Domisili Batasan resmi).
    - Tahun tanpa data per-siswa (2022, 2024): memakai ringkasan jarak/nilai
      min-max yang sudah tersedia di sumber (hanya Jalur Domisili; Jalur
      Domisili Batasan tidak tersedia rinciannya pada berkas sumber tahun
      tersebut).

    Kolom hasil: nama, jalur, jumlah, jarak_min, jarak_max.
    """
    from data.sekolah_data import SEKOLAH_NEGERI

    hasil = []
    if tahun in get_tahun_punya_sheet_per_sekolah():
        for s in SEKOLAH_NEGERI:
            try:
                nomor = int(s["nama"].split()[-1])
            except (ValueError, IndexError):
                continue
            try:
                df_det = load_pendaftar_detail(tahun, nomor)
            except (ValueError, TypeError):
                # Sebagian sheet sumber (mis. struktur kolom yang tidak
                # konsisten) bisa gagal di-parse; lewati saja sekolah itu
                # agar tabel jarak keseluruhan tetap tampil.
                continue
            if df_det is None or df_det.empty:
                continue
            df_det = df_det.copy()
            df_det["_luar"] = df_det["Luar Daerah"].astype(str).str.strip().str.lower().eq("ya")

            # SMP dengan Jalur Domisili Batasan resmi dipisah sepenuhnya dari
            # Jalur Domisili biasa: tidak lagi tampil pada baris Domisili.
            if nomor not in nomor_batasan:
                df_dom = df_det[~df_det["_luar"]]
                hasil.append({
                    "nama": s["nama"], "zona": s["zona"], "jalur": "Domisili",
                    "jumlah": len(df_dom),
                    "jarak_min": df_dom["Jarak (m)"].min() if df_dom["Jarak (m)"].notna().any() else None,
                    "jarak_max": df_dom["Jarak (m)"].max() if df_dom["Jarak (m)"].notna().any() else None,
                })

            if nomor in nomor_batasan:
                df_bat = df_det[df_det["_luar"]]
                hasil.append({
                    "nama": s["nama"], "zona": s["zona"], "jalur": "Domisili Batasan",
                    "jumlah": len(df_bat),
                    "jarak_min": df_bat["Jarak (m)"].min() if df_bat["Jarak (m)"].notna().any() else None,
                    "jarak_max": df_bat["Jarak (m)"].max() if df_bat["Jarak (m)"].notna().any() else None,
                })
    else:
        zona_by_nomor = {}
        for s in SEKOLAH_NEGERI:
            try:
                zona_by_nomor[int(s["nama"].split()[-1])] = s["zona"]
            except (ValueError, IndexError):
                pass
        df_ring = load_ringkasan_sekolah(tahun)
        for _, r in df_ring.iterrows():
            m = re.search(r"(\d+)", str(r["nama"]))
            nomor = int(m.group(1)) if m else None
            if nomor not in nomor_batasan:
                hasil.append({
                    "nama": r["nama"], "zona": zona_by_nomor.get(nomor, "-"), "jalur": "Domisili",
                    "jumlah": r.get("pendaftar_dalam"),
                    "jarak_min": r.get("jarak_min"), "jarak_max": r.get("jarak_max"),
                })
            if nomor in nomor_batasan:
                hasil.append({
                    "nama": r["nama"], "zona": zona_by_nomor.get(nomor, "-"), "jalur": "Domisili Batasan",
                    "jumlah": r.get("pendaftar_luar"),
                    "jarak_min": None, "jarak_max": None,
                })
    return pd.DataFrame(hasil)


@st.cache_data(show_spinner=False, ttl=3600)
def load_diterima_detail(tahun: int, nomor_sekolah: int, kuota_dalam: int) -> pd.DataFrame | None:
    """Daftar nama pendaftar jalur Domisili (dalam daerah) yang diterima,
    yaitu `kuota_dalam` pendaftar dengan jarak terpendek. Hanya tersedia
    untuk tahun yang punya data per-siswa (sheet per sekolah)."""
    df = load_pendaftar_detail(tahun, nomor_sekolah)
    if df is None or df.empty or not kuota_dalam:
        return None
    df_dalam = df[df["Luar Daerah"].astype(str).str.strip().str.lower() != "ya"].copy()
    df_dalam = df_dalam.sort_values("Jarak (m)", na_position="last")
    return df_dalam.head(int(kuota_dalam))


# ──────────────────────────────────────────────────────────────────────────
# Tambah Tahun Ajaran Baru
# ──────────────────────────────────────────────────────────────────────────

def tambah_tahun_ajaran(tahun_baru: int, salin_struktur_dari: int) -> str:
    """Buat berkas dataset tahun ajaran baru dengan menyalin STRUKTUR sheet
    dari tahun yang sudah ada (header + daftar sekolah), tapi mengosongkan
    baris pendaftar/kuota (kuota & pendaftar diset 0, sheet per-siswa
    dikosongkan) supaya admin bisa mulai mengisi data dari nol.
    Mendaftarkan tahun baru ke data/tahun_config.json.
    Mengembalikan path file yang dibuat."""
    cfg = _muat_tahun_config()
    if str(tahun_baru) in cfg:
        raise ValueError(f"Tahun ajaran {tahun_baru} sudah ada.")

    file_sumber = _file_per_tahun().get(salin_struktur_dari)
    if not file_sumber or not os.path.exists(file_sumber):
        raise FileNotFoundError(f"Berkas sumber tahun {salin_struktur_dari} tidak ditemukan.")

    nama_file_baru = f"dataset_{tahun_baru}.xlsx"
    path_baru = os.path.join(DATASET_DIR, nama_file_baru)
    if os.path.exists(path_baru):
        raise FileExistsError(f"Berkas '{nama_file_baru}' sudah ada.")

    shutil.copyfile(file_sumber, path_baru)

    wb = openpyxl.load_workbook(path_baru, data_only=False)
    punya_sheet_per_sekolah = str(salin_struktur_dari) in cfg and cfg[str(salin_struktur_dari)].get("sheet_per_sekolah")

    sheet_kuota_lama = f"Kuota Sekolah_{salin_struktur_dari}"
    sheet_kuota_baru = f"Kuota Sekolah_{tahun_baru}"
    if sheet_kuota_lama in wb.sheetnames:
        ws = wb[sheet_kuota_lama]
        ws.title = sheet_kuota_baru
        # Kosongkan kolom kuota & pendaftar (biarkan nama sekolah & jalur)
        for r in range(2, ws.max_row + 1):
            if ws.cell(row=r, column=1).value is None:
                continue
            for c in range(3, ws.max_column + 1):
                ws.cell(row=r, column=c, value=0)

    if punya_sheet_per_sekolah:
        for sheet_name in list(wb.sheetnames):
            if sheet_name == sheet_kuota_baru:
                continue
            if re.match(r"SMP\s+NEGERI\s+\d+\s*-\s*DOMISILI", sheet_name, re.IGNORECASE):
                ws = wb[sheet_name]
                # Hapus semua baris data pendaftar, sisakan header saja
                if ws.max_row > 1:
                    ws.delete_rows(2, ws.max_row - 1)

    wb.save(path_baru)

    cfg[str(tahun_baru)] = {"file": nama_file_baru, "sheet_per_sekolah": bool(punya_sheet_per_sekolah)}
    _simpan_tahun_config(cfg)
    _invalidate_cache()

    return path_baru
