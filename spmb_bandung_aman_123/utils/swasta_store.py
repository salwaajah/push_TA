"""
utils/swasta_store.py
Penyimpanan CRUD untuk data SMP Swasta (Kelola Data Swasta).

Data sumber asli (data/sekolah_data.py -> SEKOLAH_SWASTA) bersifat statis
(hardcoded di kode). Agar Tambah/Edit/Hapus dari halaman admin bisa
tersimpan permanen tanpa perlu database, data disalin sekali ke berkas
JSON lokal (data/sekolah_swasta_custom.json) yang menjadi sumber data
sesungguhnya sejak saat itu.
"""

import json
import os

from data.sekolah_data import SEKOLAH_SWASTA

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_PATH = os.path.join(BASE_DIR, "data", "sekolah_swasta_custom.json")


def _seed() -> list[dict]:
    data = []
    for i, d in enumerate(SEKOLAH_SWASTA, start=1):
        item = dict(d)
        item["id"] = i
        data.append(item)
    return data


def load_swasta() -> list[dict]:
    """Ambil seluruh data SMP Swasta. Membuat berkas JSON dari data statis
    bawaan jika belum pernah ada (hanya terjadi sekali)."""
    if os.path.exists(STORE_PATH):
        try:
            with open(STORE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    data = _seed()
    save_swasta(data)
    return data


def save_swasta(data: list[dict]) -> None:
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def insert_swasta(item: dict) -> int:
    data = load_swasta()
    new_id = max([d.get("id", 0) for d in data], default=0) + 1
    item = dict(item)
    item["id"] = new_id
    data.append(item)
    save_swasta(data)
    return new_id


def update_swasta(item_id: int, updates: dict) -> None:
    data = load_swasta()
    for d in data:
        if d.get("id") == item_id:
            d.update(updates)
            break
    else:
        raise ValueError("Data SMP Swasta tidak ditemukan.")
    save_swasta(data)


def delete_swasta(item_id: int) -> None:
    data = load_swasta()
    data_baru = [d for d in data if d.get("id") != item_id]
    if len(data_baru) == len(data):
        raise ValueError("Data SMP Swasta tidak ditemukan.")
    save_swasta(data_baru)
