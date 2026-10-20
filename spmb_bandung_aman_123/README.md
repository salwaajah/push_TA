# 🏫 SPMB Bandung – Sistem Rekomendasi & Prediksi Peluang Penerimaan

**Studi Kasus: SMP Jalur Domisili Kota Bandung 2025**

---

## 📁 Struktur Folder

```
spmb_bandung/
│
├── app.py                        # Entry point – Login & routing
│
├── pages/
│   ├── 1_Dashboard_Admin.py      # Dashboard visualisasi (Admin)
│   ├── 2_Kelola_Sekolah.py       # CRUD data sekolah (Admin)
│   └── 3_Prediksi_User.py        # Prediksi & rekomendasi (User)
│
├── models/
│   ├── train_models.py           # Training FCM + Random Forest
│   ├── predict.py                # Inferensi model
│   ├── fcm_model.pkl             # (digenerate setelah training)
│   └── rf_model.pkl              # (digenerate setelah training)
│
├── utils/
│   ├── supabase_client.py        # Koneksi & helper Supabase
│   ├── zona.py                   # Mapping zona + geocoding
│   └── map_utils.py              # Builder peta Folium/OSM
│
├── data/
│   └── sekolah_data.py           # Data statis 75 SMPN + Swasta Bandung
│
├── requirements.txt
└── .streamlit/config.toml
```

---

## ⚙️ Setup

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Jalankan

```bash
streamlit run app.py
```

Tidak ada API key, secrets, atau database eksternal. Semua data disimpan lokal
(Excel/JSON di folder `data/`).

---

## 🔐 Login

Terbuka untuk siapa saja, tanpa password. Pilih peran di dropdown:

- **Masyarakat / Pendaftar:** hanya menu *Cek Rekomendasi Sekolah*.
- **Admin:** menu Dashboard, Kelola Sekolah/Pendaftar/Kuota/Data Swasta, Hasil Seleksi, Analisis Jarak.

> ⚠️ Karena tanpa password, siapa pun yang punya link bisa memilih Admin dan mengubah data.

---

## 🤖 Arsitektur Machine Learning

### Fuzzy C-Means (FCM)
- **Input:** rasio pendaftar/kuota, jarak batas penerimaan, utilitas kuota
- **Output:** 3 cluster keketatan: **Tinggi / Sedang / Rendah**
- Library: `scikit-fuzzy`

### Random Forest (RF)
- **Input:** jarak rumah ke sekolah, status zona (dalam/luar), rasio pendaftar, cluster FCM
- **Output:** probabilitas diterima (0–100%)
- Library: `scikit-learn`

---

## 🗺️ Zona Domisili SPMB 2025

| Zona | Kecamatan |
|------|-----------|
| **A** | Sukasari, Cidadap, Coblong, Cibeunying Kaler, Bandung Wetan, Sumur Bandung, Cibeunying Kidul, Sukajadi |
| **B** | Mandalajati, Antapani, Arcamanik, Cinambo, Panyileukan, Cibiru, Gedebage, Rancasari, Ujungberung, Buahbatu |
| **C** | Kiaracondong, Batununggal, Lengkong, Regol, Bandung Kidul |
| **D** | Cicendo, Andir, Bandung Kulon, Babakan Ciparay, Bojongloa Kaler, Bojongloa Kidul, Astana Anyar |

---

## 📦 Tech Stack

| Komponen | Library |
|----------|---------|
| Web Framework | Streamlit |
| Penyimpanan | Excel/JSON lokal |
| ML Clustering | scikit-fuzzy (Fuzzy C-Means) |
| ML Prediksi | scikit-learn (Random Forest) |
| Peta Interaktif | Folium + streamlit-folium (OpenStreetMap) |
| Geocoding | Geopy (Nominatim/OSM) |
| Visualisasi | Plotly |

---

## 🐛 Troubleshooting

**Model belum ada:** Jalankan `python models/train_models.py` terlebih dahulu.

**Geocoding gagal:** Pastikan koneksi internet aktif. Geopy menggunakan OpenStreetMap Nominatim.


## ⚠️ Catatan model (.pkl)

Model `.pkl` bergantung pada versi `scikit-learn`/`numpy`/`pandas`. Gunakan versi
persis di `requirements.txt` (Python 3.10/3.11). Jika error saat memuat model,
hapus `.pkl` lalu retrain: `python models/train_models.py`.
