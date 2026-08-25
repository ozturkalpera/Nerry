import streamlit as st
import pandas as pd
import datetime
import io
from supabase import create_client, Client

st.set_page_config(page_title="Cafe Yönetim", layout="wide")

# --- SUPABASE BAĞLANTISI ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- EXCEL ÇIKTI FONKSİYONU ---
def excel_indir(df):
    output = io.BytesIO()
    try:
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Veriler')
        return output.getvalue(), "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    except ModuleNotFoundError:
        return df.to_csv(index=False).encode('utf-8-sig'), "csv", "text/csv"

# --- GÜVENLİ VERİTABANI FONKSİYONLARI ---
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
    with st.form("login_form"):
        kullanici = st.text_input("Kullanıcı Adı")
        sifre = st.text_input("Şifre", type="password")
        submit_btn = st.form_submit_button("Giriş Yap")
        if submit_btn:
            k = kullanici.strip().lower()
            s = sifre.strip()
            if (k == "admin" and s == "admin123") or (k == "user" and s == "user123"):
                st.session_state.giris_yapildi = True
                st.session_state.rol = "admin" if k == "admin" else "user"
                st.rerun()
            else:
                st.error("Hatalı Giriş! Şifrenizi kontrol edin.")
    st.stop() 

# --- SOL MENÜ ---
st.sidebar.title(f"Hoşgeldin, {st.session_state.rol}")
menu = st.sidebar.radio("Menü", [
    "Günlük Dükkan Cirosu", 
    "Yemek Sepeti Yönetimi", 
    "Trendyol Yönetimi", 
    "Masraf Girişi", 
    "Kasa Yönetimi (Virman)",
    "Personel & Puantaj",
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
                            
                            komisyon_tutari = tutar * (float(ayar['komisyon']) / 100)
                            kdv_haric_tutar = tutar / 1.10
                            stopaj_tutari = kdv_haric_tutar * (float(ayar['stopaj']) / 100)
                            kesinti = komisyon_tutari + stopaj_tutari
                            
                            if o_tip == "Online":
                                net = tutar - kesinti  
                            else:
                                net = -kesinti  
                                
                            tahsilat_tarihi = tarih + datetime.timedelta(days=int(ayar['vade']))
                            
                            veri = {
                                "tarih": str(tarih), "platform": platform_adi, "odeme_tipi": o_tip, 
                                "brut": tutar, "komisyon_tutari": komisyon_tutari, "stopaj_tutari": stopaj_tutari, 
                                "kesinti": kesinti, "net": net, "tahsilat_tarihi": str(tahsilat_tarihi), "durum": "Bekliyor"
                            }
                            db_yaz(supabase.table("platform_satis").insert(veri))
                        else:
                            st.error(f"Lütfen önce Ayarlar sekmesinden '{o_tip}' için oranları kaydedin!")
                            return
                st.success("Satışlar başarıyla kaydedildi!")

    with tab2:
        st.subheader("⏳ Bankaya Yatması Beklenen Paralar")
        bekleyenler = db_oku(supabase.table("platform_satis").select("*").eq("platform", platform_adi).eq("durum", "Bekliyor"))
        if bekleyenler:
            df = pd.DataFrame(bekleyenler)
            if 'komisyon_tutari' not in df.columns: df['komisyon_tutari'] = 0.0
            if 'stopaj_tutari' not in df.columns: df['stopaj_tutari'] = 0.0
            
            df.insert(0, "Seç", False)
            
            edited_df = st.data_editor(
                df[['Seç', 'id', 'tarih', 'odeme_tipi', 'brut', 'komisyon_tutari', 'stopaj_tutari', 'net', 'tahsilat_tarihi']],
                column_config={
                    "Seç": st.column_config.CheckboxColumn("Tik (Seç)", default=False),
                    "id": None, 
                    "tarih": "Satış Tarihi",
                    "odeme_tipi": "Ödeme Tipi",
                    "brut": st.column_config.NumberColumn("Brüt", format="%.2f ₺"),
                    "komisyon_tutari": st.column_config.NumberColumn("Komisyon", format="%.2f ₺"),
                    "stopaj_tutari": st.column_config.NumberColumn("Stopaj", format="%.2f ₺"),
                    "net": st.column_config.NumberColumn("Net Yatan", format="%.2f ₺"),
                    "tahsilat_tarihi": "Yatacağı Tarih"
                },
                disabled=['tarih', 'odeme_tipi', 'brut', 'komisyon_tutari', 'stopaj_tutari', 'net', 'tahsilat_tarihi'],
                hide_index=True,
                use_container_width=True,
                key=f"{platform_adi}_editor"
            )
            
            secilenler = edited_df[edited_df["Seç"] == True]
            col1, col2 = st.columns(2)
            with col1: st.write(f"Tüm Bekleyenlerin Toplamı: **{df['net'].sum():,.2f} ₺**")
            with col2: st.success(f"✔️ Seçtiklerinin Toplamı: **{secilenler['net'].sum():,.2f} ₺**")
            
            if st.button("✅ Seçili Olanları 'ÖDENDİ' Olarak İşaretle", key=f"{platform_adi}_odeme_btn"):
                if not secilenler.empty:
                    for idx in secilenler["id"]:
                        db_yaz(supabase.table("platform_satis").update({"durum": "Ödendi"}).eq("id", int(idx)))
                    st.success("İşaretlendi!")
                    st.rerun()
                else:
                    st.warning("Lütfen listeden en az bir tane satış seçin.")
        else:
            st.success("Bekleyen alacağınız bulunmuyor.")

        st.divider()

        st.subheader("✅ Tahsil Edilenler (Geçmiş Ödemeler)")
        odenenler = db_oku(supabase.table("platform_satis").select("*").eq("platform", platform_adi).eq("durum", "Ödendi"))
        
        if odenenler:
            df_odenen = pd.DataFrame(odenenler)
            if 'komisyon_tutari' not in df_odenen.columns: df_odenen['komisyon_tutari'] = 0.0
            if 'stopaj_tutari' not in df_odenen.columns: df_odenen['stopaj_tutari'] = 0.0
            
            df_odenen = df_odenen.sort_values(by="tarih", ascending=False)

            st.dataframe(
                df_odenen[['tarih', 'odeme_tipi', 'brut', 'komisyon_tutari', 'stopaj_tutari', 'net', 'tahsilat_tarihi']],
                column_config={
                    "tarih": "Satış Tarihi",
                    "odeme_tipi": "Ödeme Tipi",
                    "brut": st.column_config.NumberColumn("Brüt", format="%.2f ₺"),
                    "komisyon_tutari": st.column_config.NumberColumn("Komisyon", format="%.2f ₺"),
                    "stopaj_tutari": st.column_config.NumberColumn("Stopaj", format="%.2f ₺"),
                    "net": st.column_config.NumberColumn("Net Yatan", format="%.2f ₺"),
                    "tahsilat_tarihi": "Yattığı Tarih"
                },
                hide_index=True,
                use_container_width=True
            )
            st.info(f"💰 **Bugüne Kadar Tahsil Edilen Toplam Tutar:** {df_odenen['net'].sum():,.2f} ₺")
        else:
            st.info("Henüz tahsil edilmiş (Ödendi olarak işaretlenmiş) bir kayıt bulunmuyor.")


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
                st.success("Ayarlar güncellendi!")
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

    st.divider()
    
    st.subheader("📋 Geçmiş Ciro Kayıtları")
    cirolar = db_oku(supabase.table("ciro").select("*"))
    
    if cirolar:
        df_ciro = pd.DataFrame(cirolar)
        df_ciro = df_ciro.sort_values(by="tarih", ascending=False)
        
        st.dataframe(
            df_ciro[['tarih', 'kasa', 'nakit', 'kredi_karti', 'pavo_nakit', 'pavo_kredi', 'odenmez']],
            column_config={
                "tarih": "Tarih",
                "kasa": "Kasa",
                "nakit": st.column_config.NumberColumn("Nakit", format="%.2f ₺"),
                "kredi_karti": st.column_config.NumberColumn("Kredi Kartı", format="%.2f ₺"),
                "pavo_nakit": st.column_config.NumberColumn("Pavo Nakit", format="%.2f ₺"),
                "pavo_kredi": st.column_config.NumberColumn("Pavo Kredi", format="%.2f ₺"),
                "odenmez": st.column_config.NumberColumn("Ödenmez", format="%.2f ₺"),
            },
            hide_index=True,
            use_container_width=True
        )
        
        dosya, uzanti, mime = excel_indir(df_ciro[['tarih', 'kasa', 'nakit', 'kredi_karti', 'pavo_nakit', 'pavo_kredi', 'odenmez']])
        st.download_button(label="📥 Ciro Kayıtlarını Excel'e İndir", data=dosya, file_name=f"Gunluk_Ciro_Gecmisi.{uzanti}", mime=mime)
    else:
        st.info("Sistemde henüz kaydedilmiş bir ciro bulunmuyor.")

# İŞTE BURAYI UNUTMUŞTUM! YEMEK SEPETİ VE TRENDYOL YÖNLENDİRMELERİ EKLENDİ 🚀
elif menu == "Yemek Sepeti Yönetimi":
    platform_sayfasi("Yemek Sepeti")

elif menu == "Trendyol Yönetimi":
    platform_sayfasi("Trendyol")

elif menu == "Masraf Girişi":
    st.header("Masraf Girişi")
    
    # --- MASRAF KAYDETME BÖLÜMÜ ---
    with st.form("masraf_form"):
        tarih = st.date_input("Tarih", datetime.date.today())
        aciklama = st.text_input("Açıklama")
        tutar = st.number_input("Tutar (₺)", min_value=0.0)
        odeme_y = st.selectbox("Nereden Ödendi?", [
            "Nakit - Kasa 1", 
            "Nakit - Kasa 2", 
            "Halkbank Kk", 
            "İşbank Kk", 
            "Havale / Diğer Kartlar"
        ])
        if st.form_submit_button("Masrafı Kaydet"):
            veri = {"tarih": str(tarih), "aciklama": aciklama, "tutar": tutar, "odeme_tipi": odeme_y}
            if db_yaz(supabase.table("masraf").insert(veri)):
                st.success("Masraf Kaydedildi!")

    st.divider()
    
    # --- MASRAF DÜZENLE / SİL BÖLÜMÜ ---
    with st.expander("✏️ Masraf Düzenle veya Sil", expanded=False):
        st.info("Aşağıdan geçmiş bir masrafı seçip silebilir veya bilgilerini güncelleyebilirsiniz.")
        tum_masraflar = db_oku(supabase.table("masraf").select("*").order("tarih", desc=True))
        
        if tum_masraflar:
            secenekler = {f"{m['tarih']} | {m['aciklama']} | {m['tutar']} ₺": m for m in tum_masraflar}
            secilen_masraf_str = st.selectbox("İşlem Yapılacak Masrafı Seçin", ["Lütfen bir masraf seçin..."] + list(secenekler.keys()))
            
            if secilen_masraf_str != "Lütfen bir masraf seçin...":
                secilen_m = secenekler[secilen_masraf_str]
                
                with st.form("masraf_duzenle_form"):
                    try:
                        m_tarih = datetime.datetime.strptime(secilen_m['tarih'], '%Y-%m-%d').date()
                    except:
                        m_tarih = datetime.date.today()
                        
                    y_tarih = st.date_input("Tarih", value=m_tarih, key="duzenle_tarih")
                    y_aciklama = st.text_input("Açıklama", value=secilen_m['aciklama'], key="duzenle_aciklama")
                    y_tutar = st.number_input("Tutar (₺)", min_value=0.0, value=float(secilen_m['tutar']), key="duzenle_tutar")
                    
                    odeme_y_liste = ["Nakit - Kasa 1", "Nakit - Kasa 2", "Halkbank Kk", "İşbank Kk", "Havale / Diğer Kartlar"]
                    try:
                        idx = odeme_y_liste.index(secilen_m['odeme_tipi'])
                    except:
                        idx = 0
                    y_odeme_y = st.selectbox("Nereden Ödendi?", odeme_y_liste, index=idx, key="duzenle_odeme")
                    
                    c_gun, c_sil = st.columns(2)
                    with c_gun:
                        if st.form_submit_button("Masrafı Güncelle"):
                            veri = {"tarih": str(y_tarih), "aciklama": y_aciklama, "tutar": y_tutar, "odeme_tipi": y_odeme_y}
                            if db_yaz(supabase.table("masraf").update(veri).eq("id", secilen_m['id'])):
                                st.success("Masraf başarıyla güncellendi!")
                                st.rerun()
                    with c_sil:
                        if st.form_submit_button("🗑️ Bu Masrafı SİL"):
                            if db_yaz(supabase.table("masraf").delete().eq("id", secilen_m['id'])):
                                st.warning("Masraf sistemden tamamen silindi!")
                                st.rerun()
        else:
            st.write("Sistemde henüz kayıtlı masraf yok.")

    st.divider()

    # --- MASRAF FİLTRELEME VE LİSTELEME ALANI ---
    st.subheader("📋 Geçmiş Masraf Kayıtları ve Filtreleme")
    masraflar = db_oku(supabase.table("masraf").select("*"))
    
    if masraflar:
        df_masraf = pd.DataFrame(masraflar)
        df_masraf['tarih'] = pd.to_datetime(df_masraf['tarih']).dt.date
        
        # Filtreleme Menüsü
        with st.expander("🔍 Filtreleme Seçenekleri", expanded=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                min_date = df_masraf['tarih'].min()
                max_date = df_masraf['tarih'].max()
                tarih_araligi = st.date_input("Tarih Aralığı Seç", [min_date, max_date])
            with c2:
                aranan_kelime = st.text_input("Açıklama İçinde Ara (Örn: Manav)")
            with c3:
                odeme_yerleri = df_masraf['odeme_tipi'].unique().tolist()
                secilen_odeme = st.multiselect("Nereden Ödendi?", odeme_yerleri, default=odeme_yerleri)
        
        # Filtreleri DataFrame'e Uygulama
        if len(tarih_araligi) == 2:
            baslama, bitis = tarih_araligi
            df_masraf = df_masraf[(df_masraf['tarih'] >= baslama) & (df_masraf['tarih'] <= bitis)]
        elif len(tarih_araligi) == 1:
            baslama = tarih_araligi[0]
            df_masraf = df_masraf[df_masraf['tarih'] == baslama]
            
        if aranan_kelime:
            df_masraf = df_masraf[df_masraf['aciklama'].str.contains(aranan_kelime, case=False, na=False)]
            
        if secilen_odeme:
            df_masraf = df_masraf[df_masraf['odeme_tipi'].isin(secilen_odeme)]
            
        # Filtrelenmiş halini en yeniden eskiye sırala
        df_masraf = df_masraf.sort_values(by="tarih", ascending=False)
        
        st.dataframe(
            df_masraf[['tarih', 'aciklama', 'tutar', 'odeme_tipi']],
            column_config={
                "tarih": "Tarih",
                "aciklama": "Açıklama",
                "tutar": st.column_config.NumberColumn("Tutar", format="%.2f ₺"),
                "odeme_tipi": "Nereden Ödendi?"
            },
            hide_index=True,
            use_container_width=True
        )
        
        st.info(f"📊 Tablodaki Masrafların Toplamı: **{df_masraf['tutar'].sum():,.2f} ₺**")
        
        dosya_masraf, uzanti_m, mime_m = excel_indir(df_masraf[['tarih', 'aciklama', 'tutar', 'odeme_tipi']])
        st.download_button(
            label="📥 Ekranda Görünen Masrafları Excel'e İndir", 
            data=dosya_masraf, 
            file_name=f"Filtrelenmis_Masraf_Raporu.{uzanti_m}", 
            mime=mime_m
        )
    else:
        st.info("Sistemde henüz kaydedilmiş bir masraf bulunmuyor.")

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

# --- PERSONEL & PUANTAJ MENÜSÜ ---
elif menu == "Personel & Puantaj":
    st.header("👥 Personel & Puantaj Yönetimi")
    
    tab1, tab2, tab3 = st.tabs(["📝 Puantaj (Mesai) Girişi", "📋 Geçmiş Puantaj Kayıtları", "⚙️ Personel Yönetimi"])
    
    with tab3:
        st.subheader("Sisteme Yeni Personel Ekle")
        with st.form("personel_ekle_form"):
            yeni_personel = st.text_input("Personel Adı Soyadı")
            if st.form_submit_button("Personel Ekle"):
                if yeni_personel.strip():
                    if db_yaz(supabase.table("personeller").insert({"isim": yeni_personel.strip()})):
                        st.success(f"{yeni_personel} sisteme başarıyla eklendi!")
                        st.rerun()
                else:
                    st.error("Lütfen geçerli bir isim girin.")
        
        st.divider()
        st.subheader("Mevcut Personeller")
        personel_listesi = db_oku(supabase.table("personeller").select("*"))
        if personel_listesi:
            for p in personel_listesi:
                st.write(f"- {p['isim']}")
        else:
            st.info("Sistemde henüz kayıtlı personel bulunmuyor.")

    with tab1:
        st.subheader("Günlük Puantaj ve Mesai Girişi")
        personel_listesi = db_oku(supabase.table("personeller").select("*"))
        
        if personel_listesi:
            personel_isimleri = [p['isim'] for p in personel_listesi]
            with st.form("puantaj_form"):
                p_tarih = st.date_input("Tarih", datetime.date.today())
                p_isim = st.selectbox("Personel Seçin", personel_isimleri)
                p_durum = st.selectbox("Günlük Durum", ["Tam Gün", "Yarım Gün", "İzinli", "Raporlu", "Gelmedi"])
                p_mesai = st.number_input("Fazla Mesai Saati (Varsa)", min_value=0.0, step=0.5, help="Sadece o gün yapılan ekstra mesai saati")
                
                if st.form_submit_button("Puantajı Kaydet"):
                    veri = {
                        "tarih": str(p_tarih),
                        "personel_adi": p_isim,
                        "durum": p_durum,
                        "fazla_mesai_saati": p_mesai
                    }
                    if db_yaz(supabase.table("puantaj").insert(veri)):
                        st.success(f"{p_isim} için puantaj başarıyla kaydedildi!")
        else:
            st.warning("Lütfen önce 'Personel Yönetimi' sekmesinden sisteme personel ekleyin.")

    with tab2:
        st.subheader("Geçmiş Puantaj Kayıtları")
        puantajlar = db_oku(supabase.table("puantaj").select("*").order("tarih", desc=True))
        
        if puantajlar:
            df_puantaj = pd.DataFrame(puantajlar)
            
            with st.expander("🔍 Kayıtları Filtrele", expanded=False):
                aranan_isim = st.text_input("Personel İsmi Ara")
            if aranan_isim:
                df_puantaj = df_puantaj[df_puantaj['personel_adi'].str.contains(aranan_isim, case=False, na=False)]
            
            st.dataframe(
                df_puantaj[['tarih', 'personel_adi', 'durum', 'fazla_mesai_saati']],
                column_config={
                    "tarih": "Tarih",
                    "personel_adi": "Personel",
                    "durum": "Çalışma Durumu",
                    "fazla_mesai_saati": st.column_config.NumberColumn("Fazla Mesai (Saat)", format="%.1f")
                },
                hide_index=True,
                use_container_width=True
            )
            
            dosya_p, uzanti_p, mime_p = excel_indir(df_puantaj[['tarih', 'personel_adi', 'durum', 'fazla_mesai_saati']])
            st.download_button(label="📥 Puantajları Excel'e İndir", data=dosya_p, file_name=f"Puantaj_Raporu.{uzanti_p}", mime=mime_p)
        else:
            st.info("Sistemde henüz puantaj kaydı bulunmuyor.")

elif menu == "Raporlar":
    st.header("Sistem Raporları")
    
    st.subheader("Platform Satışları (Tümü)")
    sat = db_oku(supabase.table("platform_satis").select("*"))
    if sat: 
        df_sat = pd.DataFrame(sat)
        if 'komisyon_tutari' not in df_sat.columns: df_sat['komisyon_tutari'] = 0.0
        if 'stopaj_tutari' not in df_sat.columns: df_sat['stopaj_tutari'] = 0.0
        
        df_sat = df_sat.sort_values(by="tarih", ascending=False)
        st.dataframe(df_sat[['tarih', 'platform', 'odeme_tipi', 'brut', 'komisyon_tutari', 'stopaj_tutari', 'net', 'durum']])
        dosya, uzanti, mime = excel_indir(df_sat[['tarih', 'platform', 'odeme_tipi', 'brut', 'komisyon_tutari', 'stopaj_tutari', 'net', 'tahsilat_tarihi', 'durum']])
        st.download_button(label="📥 Platform Satışlarını Excel'e İndir", data=dosya, file_name=f"Platform_Satislar_Raporu.{uzanti}", mime=mime)
    
    st.divider()
    
    st.subheader("Dükkan Cirosu")
    cir = db_oku(supabase.table("ciro").select("*"))
    if cir: 
        df_cir = pd.DataFrame(cir)
        df_cir = df_cir.sort_values(by="tarih", ascending=False)
        st.dataframe(df_cir)
        dosya2, uzanti2, mime2 = excel_indir(df_cir)
        st.download_button(label="📥 Dükkan Cirosunu Excel'e İndir", data=dosya2, file_name=f"Dukkan_Cirosu_Raporu.{uzanti2}", mime=mime2)
