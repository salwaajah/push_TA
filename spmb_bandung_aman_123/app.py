import streamlit as st
from utils.ui_theme import apply_custom_theme

st.set_page_config(
    page_title="SPMB Bandung - Rekomendasi Zonasi",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_custom_theme()

st.markdown("""
<style>
  [data-testid="stSidebar"] { background: linear-gradient(180deg,#eaf4fd 0%,#d3e9fb 100%); }
  [data-testid="stSidebar"] * { color: #1a237e !important; }
  .main-header { font-size: 2rem; font-weight: 700; color: #1a237e; }
  .sub-header  { font-size: 1rem; color: #5c6bc0; margin-bottom: 1.5rem; }
</style>
""", unsafe_allow_html=True)

def logout_user():
    for key in ["session", "user_role", "user_email", "logged_in"]:
        st.session_state.pop(key, None)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_role" not in st.session_state:
    st.session_state.user_role = "user"
if "user_email" not in st.session_state:
    st.session_state.user_email = ""

def halaman_login():
    col_c, col_m, col_r = st.columns([1, 2, 1])
    with col_m:
        st.markdown("""
        <div style='text-align:center;margin-bottom:32px'>
          <span style='font-size:3rem'>🏫</span><br>
          <span style='font-size:1.6rem;font-weight:700;color:#1a237e'>SPMB Kota Bandung</span><br>
          <span style='color:#5c6bc0'>Rekomendasi Sekolah Sekolah Menengah Pertama Kota Bandung</span>
        </div>""", unsafe_allow_html=True)

        with st.form("form_login"):
            nama = st.text_input("👤 Nama / Email (opsional)", placeholder="Nama kamu")
            role_pilih = st.selectbox(
                "🧭 Masuk sebagai",
                ["👤 Masyarakat / Pendaftar", "🛡️ Admin"],
            )
            submitted = st.form_submit_button("Masuk", use_container_width=True, type="primary")

        if submitted:
            is_admin = role_pilih.startswith("🛡️")
            st.session_state.user_role = "admin" if is_admin else "user"
            st.session_state.logged_in = True
            st.session_state.user_email = nama.strip() or ("Admin" if is_admin else "Pengunjung")
            st.rerun()

def halaman_beranda():
    st.markdown('<p class="main-header">🏫 Rekomendasi Sekolah Jalur Domisili</p>', unsafe_allow_html=True)

    if st.session_state.user_role == "admin":
        st.info("Gunakan menu di sidebar → **Dashboard Admin**, **Kelola Sekolah**, **Kelola Pendaftar**, **Kelola Kuota**, **Kelola Data Swasta**, **Hasil Seleksi**, atau **Analisis Jarak**.")
    else:
        st.info("Gunakan menu di sidebar → **Cek Rekomendasi Sekolah**.")

    st.subheader("📍 Pembagian Zona SPMB Kota Bandung")
    z1, z2, z3, z4 = st.columns(4)
    zona_info = {
        "A": ("🔵", "#EBF5FB", "Bandung Utara-Tengah", "Sukasari, Cidadap, Coblong, Cibeunying Kaler, Bandung Wetan, Sumur Bandung, Cibeunying Kidul, Sukajadi"),
        "B": ("🟢", "#EAFAF1", "Bandung Timur", "Mandalajati, Antapani, Arcamanik, Cinambo, Panyileukan, Cibiru, Gedebage, Rancasari, Ujungberung, Buahbatu"),
        "C": ("🟡", "#FEF9E7", "Bandung Tengah-Selatan", "Kiaracondong, Batununggal, Lengkong, Regol, Bandung Kidul"),
        "D": ("🔴", "#FDEDEC", "Bandung Barat", "Cicendo, Andir, Bandung Kulon, Babakan Ciparay, Bojongloa Kaler, Bojongloa Kidul, Astana Anyar"),
    }
    for col, (zona, (icon, bg, label, kec)) in zip([z1, z2, z3, z4], zona_info.items()):
        with col:
            st.markdown(f"""
            <div style='background:{bg};border-radius:10px;padding:14px'>
              <b>{icon} Zona {zona}</b><br>
              <small>{label}</small><br><hr style='margin:6px 0'>
              <small style='color:#555'>{kec}</small>
            </div>""", unsafe_allow_html=True)

# ── Routing ──────────────────────────────────────────────────────────────────
# Menu ADMIN : Beranda, Dashboard Admin, Kelola Sekolah, Kelola Pendaftar,
#              Kelola Kuota, Kelola Data Swasta. (Prediksi User TIDAK tampil di menu Admin)
# Menu USER  : Beranda, Cek Rekomendasi Sekolah. (fitur Admin TIDAK tampil di menu User)
if not st.session_state.logged_in:
    pg = st.navigation([st.Page(halaman_login, title="Login", icon="🔑")], position="hidden")
    pg.run()
else:
    beranda          = st.Page(halaman_beranda, title="Beranda", icon="🏠", default=True)
    dashboard_admin  = st.Page("pages/1_Dashboard_Admin.py",   title="Dashboard Admin",     icon="📊")
    kelola_sekolah   = st.Page("pages/2_Kelola_Sekolah.py",    title="Kelola Sekolah",      icon="🏫")
    prediksi_user    = st.Page("pages/3_Prediksi_User.py",     title="Cek Rekomendasi Sekolah", icon="🎯")
    kelola_pendaftar = st.Page("pages/4_Kelola_Pendaftar.py",  title="Kelola Pendaftar",    icon="📝")
    kelola_kuota     = st.Page("pages/5_Kelola_Kuota.py",      title="Kelola Kuota",        icon="🎓")
    kelola_swasta    = st.Page("pages/6_Kelola_Data_Swasta.py", title="Kelola Data Swasta", icon="🏢")
    hasil_seleksi    = st.Page("pages/7_Hasil_Seleksi.py",     title="Hasil Seleksi",       icon="📑")
    analisis_jarak   = st.Page("pages/8_Analisis_Jarak.py",    title="Analisis Jarak",      icon="📏")

    if st.session_state.user_role == "admin":
        halaman_tersedia = [
            beranda, dashboard_admin, kelola_sekolah,
            kelola_pendaftar, kelola_kuota, kelola_swasta, hasil_seleksi,
            analisis_jarak,
        ]
    else:
        halaman_tersedia = [beranda, prediksi_user]

    pg = st.navigation(halaman_tersedia)

    with st.sidebar:
        st.divider()
        st.markdown(f"### 👤 {st.session_state.user_email}")
        st.markdown(f"**Role:** {'🛡️ Admin' if st.session_state.user_role == 'admin' else '👤 Masyarakat'}")
        if st.button("🚪 Logout", use_container_width=True):
            logout_user()
            st.rerun()

    pg.run()
