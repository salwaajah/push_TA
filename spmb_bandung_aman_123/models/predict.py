"""
models/predict.py
Fungsi inferensi: load model → prediksi probabilitas + cluster.
"""

import os
import joblib
import numpy as np
import streamlit as st

MODEL_DIR = os.path.join(os.path.dirname(__file__))


@st.cache_resource
def load_models():
    fcm_path = os.path.join(MODEL_DIR, "fcm_model.pkl")
    rf_path  = os.path.join(MODEL_DIR, "rf_model.pkl")
    if not os.path.exists(fcm_path) or not os.path.exists(rf_path):
        return None, None
    fcm = joblib.load(fcm_path)
    rf  = joblib.load(rf_path)
    return fcm, rf


def prediksi_peluang(
    jarak_m: float,
    dalam_zona: bool,
    nama_sekolah: str,
) -> dict:
    """
    Return dict:
      prob_diterima : float (0-100)
      cluster_label : str ("Tinggi"/"Sedang"/"Rendah")
      rasio_pendaftar: float (rasio aksesibilitas 2SFCA, kuota/pendaftar;
                       besar = longgar, kecil = ketat)
      jarak_batas_m : float
    """
    fcm_art, rf_art = load_models()
    if fcm_art is None or rf_art is None:
        return {"error": "Model belum ditraining. Jalankan: python models/train_models.py"}

    df_cls = fcm_art["df_sekolah_clustered"]
    match = df_cls[df_cls["nama"].str.lower() == nama_sekolah.lower()]
    if match.empty:
        # fallback: cari yang mirip
        match = df_cls[df_cls["nama"].str.contains(
            nama_sekolah.split()[-1], case=False, na=False
        )]
    if match.empty:
        return {"error": f"Sekolah '{nama_sekolah}' tidak ditemukan di model."}

    row = match.iloc[0]
    cluster_label = row["cluster_label"]
    rasio = row["rasio_pendaftar"]
    jarak_batas_m = row["jarak_batas_km"] * 1000

    le   = rf_art["label_encoder"]
    clf  = rf_art["model"]
    try:
        cluster_enc = le.transform([cluster_label])[0]
    except ValueError:
        cluster_enc = 1  # fallback Sedang

    X = np.array([[jarak_m, int(dalam_zona), rasio, cluster_enc]])
    prob = clf.predict_proba(X)[0]
    # class 1 = diterima
    idx_diterima = list(clf.classes_).index(1)
    prob_diterima = float(prob[idx_diterima]) * 100

    return {
        "prob_diterima": round(prob_diterima, 1),
        "cluster_label": cluster_label,
        "rasio_pendaftar": round(rasio, 3),
        "jarak_batas_m": round(jarak_batas_m, 1),
    }


def get_df_sekolah_clustered():
    """Kembalikan DataFrame sekolah dengan hasil clustering FCM."""
    fcm_art, _ = load_models()
    if fcm_art is None:
        return None
    return fcm_art["df_sekolah_clustered"]
