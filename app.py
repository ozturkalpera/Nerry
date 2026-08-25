import streamlit as st
import pandas as pd
import datetime
from supabase import create_client, Client

st.set_page_config(page_title="Cafe Yönetim", layout="wide")

# --- SUPABASE BAĞLANTISI ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- GİRİŞ EKRANI ---
if 'giris_yapildi' not in st.session_state:
    st.session_state.giris_yapildi = False

if not st.session_state.giris_yapildi:
    st.title("☕ Cafe Yönetim Sistemi - Giriş")
    kullanici = st.text_input("Kullanıcı Adı")
    sifre = st.text_input("Şifre", type="password")
    if st.button("Giriş Yap"):
        if (kullanici == "admin" and sifre == "admin123") or (kullanici == "user" and sifre == "user123"):
            st.session_state.giris_yapildi = True
            st.session_state.rol = kullanici
            st.rerun()
        else:
            st.error("Hatalı Giriş!")
    st.stop() 

# --- SOL MENÜ ---
st.sidebar.title("Menü")
menu = st.sidebar.radio("Sayfalar", [
    "1. Fiziksel Ciro Girişi", 
    "2. Yemek Sepeti", 
    "3. Trendyol", 
    "4. Masraf Girişi", 
    "5. Kasa & Virman", 
    "6. Ayarlar ve Raporlar"
])

if st.sidebar.button("Çıkış Yap"):
    st.session_state.giris_yapildi = False
    st.rerun()

# --- 1. FİZİKSEL CİRO ---
if menu == "1. Fiziksel Ciro Girişi":
    st.header("Günlük Dükkan Cirosu")
    with st.form("ciro_form"):
        tarih = st.date_input("Tarih", datetime.date.today())
        kasa = st.selectbox("Hangi Kasaya Girecek?", ["Kasa 1", "Kasa 2"])
        nakit = st.number_input("Nakit", min_value=0.0)
        kredi = st.number_input("Kredi Kartı", min_value=0.0)
        pavo_n = st.number_input("Pavo Nakit", min_value=0.0)
        pavo_k = st.number_input("Pavo Kredi", min_value=0.0)
        odenmez = st.number_input("Ödenmez", min_value=0.0)
        
        if st.form_submit_button("Kaydet"):
            veri = {"tarih": str(tarih), "kasa": kasa, "nakit": nakit, "kredi_karti": kredi, "pavo_nakit": pavo_n, "pavo_kredi": pavo_k, "odenmez": odenmez}
            supabase.table("ciro").insert(veri).execute()
            st.success("Ciro Kaydedildi!")

# --- 2. YEMEK SEPETİ ---
elif menu == "2. Yemek Sepeti":
    st.header("Yemek Sepeti Satışları")
    with st.form("ys_form"):
        tarih = st.date_input("Tarih", datetime.date.today())
        odeme_tipi = st.radio("Ödeme Tipi", ["Online", "Kapıda Ödeme"])
        tutar = st.number_input("Satış Tutarı (₺)", min_value=0.0)
        
        if st.form_submit_button("Satışı Kaydet"):
            ayar_getir = supabase.table("ayarlar").select("*").eq("platform", "Yemek Sepeti").eq("odeme_tipi", odeme_tipi).execute()
            
            if len(ayar_getir.data) > 0:
                ayar = ayar_getir.data[0]
                kesinti = tutar * ((ayar['komisyon'] + ayar['stopaj']) / 100)
                net = tutar - kesinti
                
                veri = {
                    "tarih": str(tarih), "platform": "Yemek Sepeti", "odeme_tipi": odeme_tipi,
                    "brut": tutar, "kesinti": kesinti, "net": net, "durum": "Bekliyor"
                }
                supabase.table("platform_satis").insert(veri).execute()
                st.success(f"Kaydedildi! (Net: {net} ₺)")
            else:
                st.error("Lütfen önce Ayarlar sayfasından komisyon oranlarını kaydedin!")

# --- 3. TRENDYOL ---
elif menu == "3. Trendyol":
    st.header("Trendyol Satışları")
    with st.form("ty_form"):
        tarih = st.date_input("Tarih", datetime.date.today())
        odeme_tipi = st.radio("Ödeme Tipi", ["Online", "Kapıda Ödeme"])
        tutar = st.number_input("Satış Tutarı (₺)", min_value=0.0)
        
        if st.form_submit_button("Satışı Kaydet"):
            ayar_getir = supabase.table("ayarlar").select("*").eq("platform", "Trendyol").eq("odeme_tipi", odeme_tipi).execute()
            
            if len(ayar_getir.data) > 0:
                ayar = ayar_getir.data[0]
                kesinti = tutar * ((ayar['komisyon'] + ayar['stopaj']) / 100)
                net = tutar - kesinti
                
                veri = {
                    "tarih": str(tarih), "platform": "Trendyol", "odeme_tipi": odeme_tipi,
                    "brut": tutar, "kesinti": kesinti, "net": net, "durum": "Bekliyor"
                }
                supabase.table("platform_satis").insert(veri).execute()
                st.success(f"Kaydedildi! (Net: {net} ₺)")
            else:
                st.error("Lütfen önce Ayarlar sayfasından komisyon oranlarını kaydedin!")

# --- 4. MASRAF GİRİŞİ ---
elif menu == "4. Masraf Girişi":
    st.header("Masraf Girişi")
    with st.form("masraf_form"):
        tarih = st.date_input("Tarih", datetime.date.today())
        aciklama = st.text_input("Açıklama")
        tutar = st.number_input("Tutar (₺)", min_value=0.0)
        odeme_yontemi = st.selectbox("Nereden Ödendi?", ["Nakit - Kasa 1", "Nakit - Kasa 2", "Banka/Kredi Kartı"])
        
        if st.form_submit_button("Masrafı Kaydet"):
            veri = {"tarih": str(tarih), "aciklama": aciklama, "tutar": tutar, "odeme_tipi": odeme_yontemi}
            supabase.table("masraf").insert(veri).execute()
            st.success("Masraf Kaydedildi!")

# --- 5. KASA VE VİRMAN ---
elif menu == "5. Kasa & Virman":
    st.header("Kasa Açılışı ve Virman")
    st.subheader("Güne Başlarken Kasa Açılışı")
    with st.form("acilis_form"):
        tarih = st.date_input("Tarih", datetime.date.today())
        kasa_secim = st.selectbox("Kasa", ["Kasa 1", "Kasa 2"])
        tutar = st.number_input("Açılış Bakiyesi", min_value=0.0)
        if st.form_submit_button("Açılışı Kaydet"):
            veri = {"tarih": str(tarih), "islem_tipi": "Açılış", "alan": kasa_secim, "tutar": tutar}
            supabase.table("kasa_islemleri").insert(veri).execute()
            st.success("Açılış Kaydedildi!")

    st.subheader("Kasalar Arası Virman (Transfer)")
    with st.form("virman_form"):
        tarih_v = st.date_input("Transfer Tarihi", datetime.date.today())
        gonderen = st.selectbox("Gönderen Kasa", ["Kasa 1", "Kasa 2"])
        alan = st.selectbox("Alan Kasa", ["Kasa 2", "Kasa 1"])
        tutar_v = st.number_input("Transfer Tutarı", min_value=0.0)
        if st.form_submit_button("Transfer Yap"):
            if gonderen != alan:
                veri = {"tarih": str(tarih_v), "islem_tipi": "Virman", "gonderen": gonderen, "alan": alan, "tutar": tutar_v}
                supabase.table("kasa_islemleri").insert(veri).execute()
                st.success("Transfer Kaydedildi!")

# --- 6. AYARLAR VE RAPORLAR ---
elif menu == "6. Ayarlar ve Raporlar":
    st.header("Sistem Ayarları")
    with st.form("ayar_form"):
        platform = st.selectbox("Platform", ["Yemek Sepeti", "Trendyol"])
        odeme_t = st.selectbox("Ödeme Tipi", ["Online", "Kapıda Ödeme"])
        komisyon = st.number_input("Komisyon (%)", min_value=0.0)
        stopaj = st.number_input("Stopaj (%)", min_value=0.0)
        vade = st.number_input("Kaç Gün Sonra Yatar? (Vade)", min_value=0)
        
        if st.form_submit_button("Ayarı Kaydet"):
            supabase.table("ayarlar").delete().eq("platform", platform).eq("odeme_tipi", odeme_t).execute()
            veri = {"platform": platform, "odeme_tipi": odeme_t, "komisyon": komisyon, "stopaj": stopaj, "vade": vade}
            supabase.table("ayarlar").insert(veri).execute()
            st.success(f"{platform} - {odeme_t} ayarı güncellendi!")

    st.divider()
    st.header("Basit Raporlar (Canlı)")
    st.subheader("Platform Satışları")
    satislar = supabase.table("platform_satis").select("*").execute().data
    if satislar:
        st.dataframe(pd.DataFrame(satislar)[["tarih", "platform", "odeme_tipi", "brut", "net", "durum"]])
    
    st.subheader("Dükkan Cirosu")
    cirolar = supabase.table("ciro").select("*").execute().data
    if cirolar:
        st.dataframe(pd.DataFrame(cirolar))
