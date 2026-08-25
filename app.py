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
st.sidebar.title(f"Hoşgeldin, {st.session_state.rol}")
menu = st.sidebar.radio("Menü", [
    "1. Fiziksel Ciro Girişi", 
    "2. Yemek Sepeti", 
    "3. Trendyol", 
    "4. Masraf Girişi", 
    "5. Kasa & Virman (Detaylı)", 
    "6. Ayarlar ve Raporlar"
])

if st.sidebar.button("Çıkış Yap"):
    st.session_state.giris_yapildi = False
    st.rerun()

# --- 1. FİZİKSEL CİRO ---
if menu == "1. Fiziksel Ciro Girişi":
    st.header("Günlük Dükkan Cirosu")
    with st.form("ciro_form"):
        col1, col2 = st.columns(2)
        with col1:
            tarih = st.date_input("Tarih", datetime.date.today())
            kasa = st.selectbox("Nakit ve Pavo Nakit Hangi Kasaya Girecek?", ["Kasa 1", "Kasa 2"])
            nakit = st.number_input("Nakit (₺)", min_value=0.0)
            kredi = st.number_input("Kredi Kartı (₺)", min_value=0.0)
        with col2:
            pavo_n = st.number_input("Pavo Nakit (₺)", min_value=0.0)
            pavo_k = st.number_input("Pavo Kredi (₺)", min_value=0.0)
            odenmez = st.number_input("Ödenmez (İkram) (₺)", min_value=0.0)
        
        if st.form_submit_button("Ciro Kaydet"):
            veri = {"tarih": str(tarih), "kasa": kasa, "nakit": nakit, "kredi_karti": kredi, "pavo_nakit": pavo_n, "pavo_kredi": pavo_k, "odenmez": odenmez}
            supabase.table("ciro").insert(veri).execute()
            st.success("Dükkan Cirosu Kaydedildi!")

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
                
                veri = {"tarih": str(tarih), "platform": "Yemek Sepeti", "odeme_tipi": odeme_tipi, "brut": tutar, "kesinti": kesinti, "net": net, "durum": "Bekliyor"}
                supabase.table("platform_satis").insert(veri).execute()
                st.success(f"Kaydedildi! (Kesinti: {kesinti} ₺, Net: {net} ₺)")
            else:
                st.error("Lütfen önce Ayarlar sayfasından Yemek Sepeti komisyon oranlarını kaydedin!")

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
                
                veri = {"tarih": str(tarih), "platform": "Trendyol", "odeme_tipi": odeme_tipi, "brut": tutar, "kesinti": kesinti, "net": net, "durum": "Bekliyor"}
                supabase.table("platform_satis").insert(veri).execute()
                st.success(f"Kaydedildi! (Kesinti: {kesinti} ₺, Net: {net} ₺)")
            else:
                st.error("Lütfen önce Ayarlar sayfasından Trendyol komisyon oranlarını kaydedin!")

# --- 4. MASRAF GİRİŞİ ---
elif menu == "4. Masraf Girişi":
    st.header("Masraf Girişi")
    with st.form("masraf_form"):
        tarih = st.date_input("Tarih", datetime.date.today())
        aciklama = st.text_input("Masraf Açıklaması (Örn: Manav, Elektrik)")
        tutar = st.number_input("Tutar (₺)", min_value=0.0)
        odeme_yontemi = st.selectbox("Nereden Ödendi?", ["Nakit - Kasa 1", "Nakit - Kasa 2", "Banka/Kredi Kartı"])
        
        if st.form_submit_button("Masrafı Kaydet"):
            veri = {"tarih": str(tarih), "aciklama": aciklama, "tutar": tutar, "odeme_tipi": odeme_yontemi}
            supabase.table("masraf").insert(veri).execute()
            st.success("Masraf Kaydedildi!")

# --- 5. KASA VE VİRMAN (DETAYLI) ---
elif menu == "5. Kasa & Virman (Detaylı)":
    st.header("Kasa Yönetimi ve Virman")
    secilen_tarih = st.date_input("İşlem Tarihi", datetime.date.today())
    
    st.divider()
    
    st.subheader("1. Güne Başlangıç (Açılış Bakiyeleri)")
    with st.form("acilis_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            acilis_k1 = st.number_input("Kasa 1 Açılış Bakiyesi (₺)", min_value=0.0)
        with col2:
            acilis_k2 = st.number_input("Kasa 2 Açılış Bakiyesi (₺)", min_value=0.0)
        with col3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.form_submit_button("Açılış Bakiyelerini Kaydet"):
                # Eski açılışı silip yeniyi ekle
                supabase.table("kasa_islemleri").delete().eq("tarih", str(secilen_tarih)).eq("islem_tipi", "Açılış").execute()
                supabase.table("kasa_islemleri").insert([
                    {"tarih": str(secilen_tarih), "islem_tipi": "Açılış", "alan": "Kasa 1", "tutar": acilis_k1},
                    {"tarih": str(secilen_tarih), "islem_tipi": "Açılış", "alan": "Kasa 2", "tutar": acilis_k2}
                ]).execute()
                st.success("Açılışlar Kaydedildi!")

    st.subheader("2. Kasalar Arası Virman (Transfer)")
    with st.form("virman_form"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            gonderen = st.selectbox("Gönderen", ["Kasa 1", "Kasa 2"])
        with col2:
            alan = st.selectbox("Alan", ["Kasa 2", "Kasa 1"])
        with col3:
            tutar_v = st.number_input("Tutar (₺)", min_value=0.0)
        with col4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.form_submit_button("Virman Yap"):
                if gonderen != alan and tutar_v > 0:
                    veri = {"tarih": str(secilen_tarih), "islem_tipi": "Virman", "gonderen": gonderen, "alan": alan, "tutar": tutar_v}
                    supabase.table("kasa_islemleri").insert(veri).execute()
                    st.success("Transfer Kaydedildi!")

    st.divider()
    st.subheader("📊 Günün Kasa Özetleri (Otomatik Hesaplama)")
    
    # Verileri Çek ve Hesapla
    cirolar = supabase.table("ciro").select("*").eq("tarih", str(secilen_tarih)).execute().data
    masraflar = supabase.table("masraf").select("*").eq("tarih", str(secilen_tarih)).execute().data
    islemler = supabase.table("kasa_islemleri").select("*").eq("tarih", str(secilen_tarih)).execute().data

    def hesapla(kasa_adi):
        acilis = sum([k['tutar'] for k in islemler if k['islem_tipi'] == 'Açılış' and k['alan'] == kasa_adi])
        giren = sum([(c['nakit'] + c['pavo_nakit']) for c in cirolar if c['kasa'] == kasa_adi])
        cikan = sum([m['tutar'] for m in masraflar if m['odeme_tipi'] == f"Nakit - {kasa_adi}"])
        v_gelen = sum([k['tutar'] for k in islemler if k['islem_tipi'] == 'Virman' and k['alan'] == kasa_adi])
        v_giden = sum([k['tutar'] for k in islemler if k['islem_tipi'] == 'Virman' and k['gonderen'] == kasa_adi])
        net = acilis + giren + v_gelen - cikan - v_giden
        return acilis, giren, cikan, v_gelen, v_giden, net

    k1_a, k1_g, k1_c, k1_vg, k1_vgi, k1_net = hesapla("Kasa 1")
    k2_a, k2_g, k2_c, k2_vg, k2_vgi, k2_net = hesapla("Kasa 2")

    col1, col2 = st.columns(2)
    with col1:
        st.info("### KASA 1 DURUMU")
        st.write(f"Açılış: {k1_a:,.2f} ₺")
        st.write(f"Nakit Giriş: + {k1_g:,.2f} ₺")
        st.write(f"Nakit Çıkış (Masraf): - {k1_c:,.2f} ₺")
        st.write(f"Virman Dengesi: {(k1_vg - k1_vgi):,.2f} ₺")
        st.metric("KASA 1'DE OLMASI GEREKEN", f"{k1_net:,.2f} ₺")
        
    with col2:
        st.success("### KASA 2 DURUMU")
        st.write(f"Açılış: {k2_a:,.2f} ₺")
        st.write(f"Nakit Giriş: + {k2_g:,.2f} ₺")
        st.write(f"Nakit Çıkış (Masraf): - {k2_c:,.2f} ₺")
        st.write(f"Virman Dengesi: {(k2_vg - k2_vgi):,.2f} ₺")
        st.metric("KASA 2'DE OLMASI GEREKEN", f"{k2_net:,.2f} ₺")

# --- 6. AYARLAR VE RAPORLAR (DETAYLI) ---
# --- 6. AYARLAR VE RAPORLAR (DETAYLI) ---
elif menu == "6. Ayarlar ve Raporlar":
    st.header("Sistem Ayarları")
    
    platform_secim = st.selectbox("Hangi platformun ayarlarını güncellemek istiyorsun?", ["Yemek Sepeti", "Trendyol"])
    
    # Mevcut Ayarları Çek
    ayarlar = supabase.table("ayarlar").select("*").eq("platform", platform_secim).execute().data
    o_kom = o_stop = o_vade = k_kom = k_stop = k_vade = 0.0
    
    for a in ayarlar:
        if a['odeme_tipi'] == 'Online':
            o_kom, o_stop, o_vade = a['komisyon'], a['stopaj'], a['vade']
        elif a['odeme_tipi'] == 'Kapıda Ödeme':
            k_kom, k_stop, k_vade = a['komisyon'], a['stopaj'], a['vade']

    with st.form("ayar_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"### 🌐 {platform_secim} - Online Ödeme")
            y_o_kom = st.number_input("Komisyon (%)", value=float(o_kom), format="%.2f", key="o_kom")
            y_o_stop = st.number_input("Stopaj (%)", value=float(o_stop), format="%.2f", key="o_stop")
            y_o_vade = st.number_input("Kaç Gün Sonra Yatar?", value=int(o_vade), step=1, key="o_vade")
            
        with col2:
            st.markdown(f"### 🛵 {platform_secim} - Kapıda Ödeme")
            y_k_kom = st.number_input("Komisyon (%)", value=float(k_kom), format="%.2f", key="k_kom")
            y_k_stop = st.number_input("Stopaj (%)", value=float(k_stop), format="%.2f", key="k_stop")
            y_k_vade = st.number_input("Kaç Gün Sonra Yatar?", value=int(k_vade), step=1, key="k_vade")
            
        st.markdown("<br>", unsafe_allow_html=True)
        if st.form_submit_button("Ayarları Sisteme Öğret (Kaydet)"):
            # Eski ayarları sil
            supabase.table("ayarlar").delete().eq("platform", platform_secim).execute()
            # Yeni ayarları Online ve Kapıda olarak iki satır halinde ekle
            supabase.table("ayarlar").insert([
                {"platform": platform_secim, "odeme_tipi": "Online", "komisyon": y_o_kom, "stopaj": y_o_stop, "vade": int(y_o_vade)},
                {"platform": platform_secim, "odeme_tipi": "Kapıda Ödeme", "komisyon": y_k_kom, "stopaj": y_k_stop, "vade": int(y_k_vade)}
            ]).execute()
            st.success(f"{platform_secim} ayarları başarıyla güncellendi!")
            st.rerun()

    st.divider()
    st.header("Basit Raporlar (Canlı)")
    st.subheader("Platform Satışları")
    satislar = supabase.table("platform_satis").select("*").execute().data
    if satislar:
        df_satis = pd.DataFrame(satislar)
        st.dataframe(df_satis[["tarih", "platform", "odeme_tipi", "brut", "net", "durum"]])
    
    st.subheader("Dükkan Cirosu")
    cirolar = supabase.table("ciro").select("*").execute().data
    if cirolar:
        st.dataframe(pd.DataFrame(cirolar))
