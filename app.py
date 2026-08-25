import streamlit as st
import pandas as pd
import datetime
from supabase import create_client, Client

st.set_page_config(page_title="Cafe Yönetim", layout="wide")

# --- SUPABASE BAĞLANTISI ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- GÜVENLİ (ÇÖKMEYİ ENGELLEYEN) VERİTABANI FONKSİYONLARI ---
def db_oku(sorgu):
    try:
        sonuc = sorgu.execute()
        return sonuc.data if sonuc.data else []
    except Exception as e:
        st.error(f"⚠️ Veri Okuma Hatası: {e}")
        return []

def db_yaz(sorgu):
    try:
        sorgu.execute()
        return True
    except Exception as e:
        st.error(f"⚠️ İşlem Başarısız Oldu. Hata Detayı: {e}")
        return False

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
    "Günlük Dükkan Cirosu", 
    "Yemek Sepeti Yönetimi", 
    "Trendyol Yönetimi", 
    "Masraf Girişi", 
    "Kasa Yönetimi (Virman)",
    "Raporlar"
])

if st.sidebar.button("Çıkış Yap"):
    st.session_state.giris_yapildi = False
    st.rerun()

# --- PLATFORM (YS / TRENDYOL) FONKSİYONU ---
def platform_sayfasi(platform_adi):
    st.header(f"📦 {platform_adi} Yönetimi")
    tab1, tab2, tab3 = st.tabs(["💰 Satış Girişi", "🕒 Tahsilat Takibi (Toplu Ödeme)", "⚙️ Sisteme Öğret (Ayarlar)"])
    
    with tab1:
        st.subheader("Satışları Gir")
        with st.form(f"{platform_adi}_satis_form"):
            tarih = st.date_input("Satış Tarihi", datetime.date.today())
            col1, col2 = st.columns(2)
            with col1: online = st.number_input("Online Ödeme Cirosu (₺)", min_value=0.0, key=f"{platform_adi}_satis_online")
            with col2: kapida = st.number_input("Kapıda Ödeme Cirosu (₺)", min_value=0.0, key=f"{platform_adi}_satis_kapida")
            
            if st.form_submit_button("Satışları Kaydet"):
                for o_tip, tutar in [("Online", online), ("Kapıda Ödeme", kapida)]:
                    if tutar > 0:
                        ayar_getir = db_oku(supabase.table("ayarlar").select("*").eq("platform", platform_adi).eq("odeme_tipi", o_tip))
                        if len(ayar_getir) > 0:
                            ayar = ayar_getir[0]
                            kesinti = tutar * ((float(ayar['komisyon']) + float(ayar['stopaj'])) / 100)
                            net = tutar - kesinti
                            tahsilat_tarihi = tarih + datetime.timedelta(days=int(ayar['vade']))
                            
                            veri = {"tarih": str(tarih), "platform": platform_adi, "odeme_tipi": o_tip, "brut": tutar, "kesinti": kesinti, "net": net, "tahsilat_tarihi": str(tahsilat_tarihi), "durum": "Bekliyor"}
                            db_yaz(supabase.table("platform_satis").insert(veri))
                        else:
                            st.error(f"Lütfen önce Ayarlar sekmesinden '{o_tip}' için oranları kaydedin!")
                            return
                st.success("Satışlar başarıyla kaydedildi!")

    with tab2:
        st.subheader("Bankaya Yatması Beklenen Paralar")
        bekleyenler = db_oku(supabase.table("platform_satis").select("*").eq("platform", platform_adi).eq("durum", "Bekliyor"))
        if bekleyenler:
            df = pd.DataFrame(bekleyenler)
            
            # --- YENİ EKLENEN TOPLU SEÇİM ÖZELLİĞİ ---
            # Seçim yapabilmen için tabloya "Seç" adında bir tik kutusu sütunu ekliyoruz
            df.insert(0, "Seç", False)
            st.info("💡 **İpucu:** Hesabınıza yatan ödemeleri soldaki kutucuklardan işaretleyin. Seçtiklerinizin toplamı aşağıda otomatik hesaplanacaktır.")
            
            # Tabloyu düzenlenebilir (tiklenebilir) olarak ekrana bas
            edited_df = st.data_editor(
                df[['Seç', 'id', 'tarih', 'odeme_tipi', 'net', 'tahsilat_tarihi']],
                column_config={
                    "Seç": st.column_config.CheckboxColumn("Tik (Seç)", default=False),
                    "id": None, # ID sütununu gizliyoruz ki kafa karıştırmasın
                    "tarih": "Satış Tarihi",
                    "odeme_tipi": "Ödeme Tipi",
                    "net": st.column_config.NumberColumn("Net Tutar (₺)", format="%.2f ₺"),
                    "tahsilat_tarihi": "Beklenen Ödeme Tarihi"
                },
                disabled=['tarih', 'odeme_tipi', 'net', 'tahsilat_tarihi'], # Sadece "Seç" kutusu tıklanabilsin
                hide_index=True,
                use_container_width=True,
                key=f"{platform_adi}_editor"
            )
            
            # Seçilenleri hesapla
            secilenler = edited_df[edited_df["Seç"] == True]
            secilen_toplam = secilenler["net"].sum()
            
            # Toplam Durumlarını Göster
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"Tüm Bekleyenlerin Toplamı: **{df['net'].sum():,.2f} ₺**")
            with col2:
                st.success(f"✔️ Seçtiklerinin Toplamı: **{secilen_toplam:,.2f} ₺**")
            
            # Toplu Ödeme Butonu
            if st.button("✅ Seçili Olanları 'ÖDENDİ' Olarak İşaretle", key=f"{platform_adi}_odeme_btn"):
                if not secilenler.empty:
                    for idx in secilenler["id"]:
                        db_yaz(supabase.table("platform_satis").update({"durum": "Ödendi"}).eq("id", int(idx)))
                    st.success("Seçilen tüm satışlar 'Ödendi' olarak başarıyla güncellendi!")
                    st.rerun()
                else:
                    st.warning("Lütfen listeden en az bir tane satış seçin.")
        else:
            st.success("Bekleyen alacağınız bulunmuyor.")

    with tab3:
        st.subheader("Komisyon ve Kesinti Oranlarını Öğret")
        ayarlar = db_oku(supabase.table("ayarlar").select("*").eq("platform", platform_adi))
        o_kom = o_stop = o_vade = k_kom = k_stop = k_vade = 0
        for a in ayarlar:
            if a['odeme_tipi'] == 'Online': o_kom, o_stop, o_vade = a['komisyon'], a['stopaj'], a['vade']
            if a['odeme_tipi'] == 'Kapıda Ödeme': k_kom, k_stop, k_vade = a['komisyon'], a['stopaj'], a['vade']

        with st.form(f"{platform_adi}_ayar_form"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("### 🌐 Online Ödeme")
                y_o_kom = st.number_input("Komisyon (%)", value=float(o_kom), key=f"{platform_adi}_o_kom")
                y_o_stop = st.number_input("Stopaj (%)", value=float(o_stop), key=f"{platform_adi}_o_stop")
                y_o_vade = st.number_input("Vade (Gün)", value=int(o_vade), step=1, key=f"{platform_adi}_o_vade")
            with c2:
                st.markdown("### 🛵 Kapıda Ödeme")
                y_k_kom = st.number_input("Komisyon (%)", value=float(k_kom), key=f"{platform_adi}_k_kom")
                y_k_stop = st.number_input("Stopaj (%)", value=float(k_stop), key=f"{platform_adi}_k_stop")
                y_k_vade = st.number_input("Vade (Gün)", value=int(k_vade), step=1, key=f"{platform_adi}_k_vade")
            
            if st.form_submit_button("Ayarları Güncelle"):
                db_yaz(supabase.table("ayarlar").delete().eq("platform", platform_adi))
                db_yaz(supabase.table("ayarlar").insert([
                    {"platform": platform_adi, "odeme_tipi": "Online", "komisyon": y_o_kom, "stopaj": y_o_stop, "vade": y_o_vade},
                    {"platform": platform_adi, "odeme_tipi": "Kapıda Ödeme", "komisyon": y_k_kom, "stopaj": y_k_stop, "vade": y_k_vade}
                ]))
                st.success("Ayarlar başarıyla kaydedildi!")
                st.rerun()

# --- MENÜ YÖNLENDİRMELERİ ---
if menu == "Günlük Dükkan Cirosu":
    st.header("Günlük Dükkan Cirosu")
    with st.form("ciro_form"):
        c1, c2 = st.columns(2)
        with c1:
            tarih = st.date_input("Tarih", datetime.date.today())
            kasa = st.selectbox("Hedef Kasa", ["Kasa 1", "Kasa 2"])
            nakit = st.number_input("Nakit (₺)", min_value=0.0)
            kredi = st.number_input("Kredi Kartı (₺)", min_value=0.0)
        with c2:
            pavo_n = st.number_input("Pavo Nakit (₺)", min_value=0.0)
            pavo_k = st.number_input("Pavo Kredi (₺)", min_value=0.0)
            odenmez = st.number_input("Ödenmez (₺)", min_value=0.0)
        
        if st.form_submit_button("Ciro Kaydet"):
            veri = {"tarih": str(tarih), "kasa": kasa, "nakit": nakit, "kredi_karti": kredi, "pavo_nakit": pavo_n, "pavo_kredi": pavo_k, "odenmez": odenmez}
            if db_yaz(supabase.table("ciro").insert(veri)):
                st.success("Dükkan Cirosu Kaydedildi!")

elif menu == "Yemek Sepeti Yönetimi":
    platform_sayfasi("Yemek Sepeti")

elif menu == "Trendyol Yönetimi":
    platform_sayfasi("Trendyol")

elif menu == "Masraf Girişi":
    st.header("Masraf Girişi")
    with st.form("masraf_form"):
        tarih = st.date_input("Tarih", datetime.date.today())
        aciklama = st.text_input("Açıklama")
        tutar = st.number_input("Tutar (₺)", min_value=0.0)
        odeme_y = st.selectbox("Nereden Ödendi?", ["Nakit - Kasa 1", "Nakit - Kasa 2", "Havale / Kredi Kartı"])
        if st.form_submit_button("Masrafı Kaydet"):
            veri = {"tarih": str(tarih), "aciklama": aciklama, "tutar": tutar, "odeme_tipi": odeme_y}
            if db_yaz(supabase.table("masraf").insert(veri)):
                st.success("Masraf Kaydedildi!")

elif menu == "Kasa Yönetimi (Virman)":
    st.header("Kasa Yönetimi ve Virman")
    secilen = st.date_input("İşlem Tarihi", datetime.date.today())
    
    st.subheader("Güne Başlangıç")
    with st.form("acilis_form"):
        c1, c2, c3 = st.columns(3)
        with c1: k1_acilis = st.number_input("Kasa 1 Açılış (₺)", min_value=0.0)
        with c2: k2_acilis = st.number_input("Kasa 2 Açılış (₺)", min_value=0.0)
        with c3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.form_submit_button("Kaydet"):
                db_yaz(supabase.table("kasa_islemleri").delete().eq("tarih", str(secilen)).eq("islem_tipi", "Açılış"))
                if db_yaz(supabase.table("kasa_islemleri").insert([
                    {"tarih": str(secilen), "islem_tipi": "Açılış", "alan": "Kasa 1", "tutar": k1_acilis},
                    {"tarih": str(secilen), "islem_tipi": "Açılış", "alan": "Kasa 2", "tutar": k2_acilis}
                ])):
                    st.success("Açılışlar Kaydedildi!")

    st.subheader("Kasalar Arası Virman")
    with st.form("virman_form"):
        c1, c2, c3, c4 = st.columns(4)
        with c1: gonderen = st.selectbox("Gönderen", ["Kasa 1", "Kasa 2"])
        with c2: alan = st.selectbox("Alan", ["Kasa 2", "Kasa 1"])
        with c3: tutar_v = st.number_input("Tutar (₺)", min_value=0.0)
        with c4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.form_submit_button("Virman Yap"):
                if gonderen != alan and tutar_v > 0:
                    if db_yaz(supabase.table("kasa_islemleri").insert({"tarih": str(secilen), "islem_tipi": "Virman", "gonderen": gonderen, "alan": alan, "tutar": tutar_v})):
                        st.success("Transfer Kaydedildi!")

    st.divider()
    st.subheader("📊 Günün Kasa Özetleri")
    
    cirolar = db_oku(supabase.table("ciro").select("*").eq("tarih", str(secilen)))
    masraflar = db_oku(supabase.table("masraf").select("*").eq("tarih", str(secilen)))
    islemler = db_oku(supabase.table("kasa_islemleri").select("*").eq("tarih", str(secilen)))

    def hesapla(k_adi):
        a = sum([i['tutar'] for i in islemler if i.get('islem_tipi') == 'Açılış' and i.get('alan') == k_adi])
        g = sum([(c.get('nakit', 0) + c.get('pavo_nakit', 0)) for c in cirolar if c.get('kasa') == k_adi])
        c = sum([m['tutar'] for m in masraflar if m.get('odeme_tipi') == f"Nakit - {k_adi}"])
        vg = sum([i['tutar'] for i in islemler if i.get('islem_tipi') == 'Virman' and i.get('alan') == k_adi])
        vgi = sum([i['tutar'] for i in islemler if i.get('islem_tipi') == 'Virman' and i.get('gonderen') == k_adi])
        return a, g, c, vg, vgi, (a + g + vg - c - vgi)

    k1_a, k1_g, k1_c, k1_vg, k1_vgi, k1_net = hesapla("Kasa 1")
    k2_a, k2_g, k2_c, k2_vg, k2_vgi, k2_net = hesapla("Kasa 2")

    c1, c2 = st.columns(2)
    with c1:
        st.info("### KASA 1 DURUMU")
        st.write(f"Açılış: {k1_a:,.2f} ₺\n\nNakit Giriş: + {k1_g:,.2f} ₺\n\nNakit Çıkış: - {k1_c:,.2f} ₺\n\nVirman Dengesi: {(k1_vg - k1_vgi):,.2f} ₺")
        st.metric("KASA 1'DE OLMASI GEREKEN", f"{k1_net:,.2f} ₺")
    with c2:
        st.success("### KASA 2 DURUMU")
        st.write(f"Açılış: {k2_a:,.2f} ₺\n\nNakit Giriş: + {k2_g:,.2f} ₺\n\nNakit Çıkış: - {k2_c:,.2f} ₺\n\nVirman Dengesi: {(k2_vg - k2_vgi):,.2f} ₺")
        st.metric("KASA 2'DE OLMASI GEREKEN", f"{k2_net:,.2f} ₺")

elif menu == "Raporlar":
    st.header("Sistem Raporları")
    st.subheader("Platform Satışları (Tümü)")
    sat = db_oku(supabase.table("platform_satis").select("*"))
    if sat: st.dataframe(pd.DataFrame(sat)[['tarih', 'platform', 'odeme_tipi', 'brut', 'net', 'durum']])
    
    st.subheader("Dükkan Cirosu")
    cir = db_oku(supabase.table("ciro").select("*"))
    if cir: st.dataframe(pd.DataFrame(cir))
