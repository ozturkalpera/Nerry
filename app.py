import streamlit as st
import pandas as pd
import datetime
import io
import calendar
from supabase import create_client, Client

st.set_page_config(page_title="Cafe Yönetim", layout="wide")

# --- SUPABASE BAĞLANTISI ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- ZIRHLI FİNANSAL SAYI ÇÖZÜCÜ (Binlik ayraç hatalarını engeller) ---
def safe_float(val):
    if pd.isna(val): return 0.0
    if isinstance(val, (int, float)): return float(val)
    s = str(val).strip().replace('₺', '').replace('TL', '').replace(' ', '')
    if not s: return 0.0
    
    # Negatif sayıları koru
    is_negative = False
    if s.startswith('-'):
        is_negative = True
        s = s[1:]
        
    if ',' in s and '.' in s:
        last_comma = s.rfind(',')
        last_dot = s.rfind('.')
        if last_comma > last_dot:
            # Örn: 1.250,50 (Virgül ondalık)
            s = s.replace('.', '').replace(',', '.')
        else:
            # Örn: 1,250.50 (Nokta ondalık)
            s = s.replace(',', '')
    elif ',' in s:
        # Örn: 1250,50 veya 1,250
        if len(s.split(',')[-1]) != 3:
            s = s.replace(',', '.')
        else:
            s = s.replace(',', '')
    elif '.' in s:
        # Örn: 1.250 veya 1250.50
        if s.count('.') > 1:
            s = s.replace('.', '')
        elif len(s.split('.')[-1]) == 3:
            s = s.replace('.', '')
            
    try:
        res = float(s)
        return -res if is_negative else res
    except Exception:
        return 0.0

def excel_indir(df):
    output = io.BytesIO()
    try:
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Veriler')
        return output.getvalue(), "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    except ModuleNotFoundError:
        return df.to_csv(index=False).encode('utf-8-sig'), "csv", "text/csv"

# --- ZAMAN DAMGASI (GELİŞTİRİLMİŞ PARSER) ---
def format_single_date(d):
    if pd.isna(d) or str(d).strip() in ["", "NaT", "nan", "None"]: 
        return "-"
    try:
        dt = pd.to_datetime(d)
        if dt.tzinfo is None:
            dt = dt.tz_localize('UTC')
        return dt.tz_convert('Europe/Istanbul').strftime('%d.%m.%Y %H:%M')
    except Exception:
        return "-"

def zaman_sutunlari_ekle(df, mevcut_sutunlar):
    ek_sutunlar = mevcut_sutunlar.copy()
    if 'created_at' in df.columns:
        df['İşlenme Zamanı'] = df['created_at'].apply(format_single_date)
        ek_sutunlar.append('İşlenme Zamanı')
    if 'updated_at' in df.columns:
        df['Düzenleme Zamanı'] = df['updated_at'].apply(format_single_date)
        ek_sutunlar.append('Düzenleme Zamanı')
    return df, ek_sutunlar

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

# --- MERKEZİ BİLDİRİM SİSTEMİ ---
def bildirim_goster():
    if "genel_mesaj" in st.session_state:
        tur, metin = st.session_state["genel_mesaj"]
        if tur == "success":
            st.success(metin)
            st.toast(metin, icon="✅")
        elif tur == "error":
            st.error(metin)
            st.toast(metin, icon="❌")
        elif tur == "warning":
            st.warning(metin)
            st.toast(metin, icon="⚠️")
        elif tur == "info":
            st.info(metin)
            st.toast(metin, icon="ℹ️")
        del st.session_state["genel_mesaj"]

# --- CALLBACK FONKSİYONLARI ---
def platform_kaydet_cb(plat_adi):
    tarih = st.session_state[f"{plat_adi}_tarih"]
    online = st.session_state[f"{plat_adi}_on"]
    kapida = st.session_state[f"{plat_adi}_kap"]
    
    if online <= 0 and kapida <= 0:
        st.session_state["genel_mesaj"] = ("warning", "Lütfen en az bir tutar girin.")
        return

    mevcut = db_oku(supabase.table("platform_satis").select("id").eq("platform", plat_adi).eq("tarih", str(tarih)))
    if mevcut:
        st.session_state["genel_mesaj"] = ("error", f"⚠️ {tarih} tarihi için {plat_adi} satışı zaten girilmiş! Değiştirmek için Düzenle panelini kullanın.")
        return

    hata = False
    for o_tip, tutar in [("Online", online), ("Kapıda Ödeme", kapida)]:
        if tutar > 0:
            ayar_getir = db_oku(supabase.table("ayarlar").select("*").eq("platform", plat_adi).eq("odeme_tipi", o_tip))
            if len(ayar_getir) > 0:
                ayar = ayar_getir[0]
                k_tutari = round(tutar * (float(ayar['komisyon']) / 100), 2)
                s_tutari = round((tutar / 1.10) * (float(ayar['stopaj']) / 100), 2)
                kes = round(k_tutari + s_tutari, 2)
                net_t = round(tutar - kes if o_tip == "Online" else -kes, 2)
                t_tarihi = tarih + datetime.timedelta(days=int(ayar['vade']))
                
                veri = {
                    "tarih": str(tarih), "platform": plat_adi, "odeme_tipi": o_tip, 
                    "brut": round(tutar, 2), "komisyon_tutari": k_tutari, "stopaj_tutari": s_tutari, 
                    "kesinti": kes, "net": net_t, "tahsilat_tarihi": str(t_tarihi), "durum": "Bekliyor"
                }
                if not db_yaz(supabase.table("platform_satis").insert(veri)):
                    hata = True
            else:
                st.session_state["genel_mesaj"] = ("error", f"⚠️ Lütfen önce Ayarlar'dan '{o_tip}' için oranları kaydedin!")
                return
    if not hata:
        st.session_state["genel_mesaj"] = ("success", f"{plat_adi} satışları başarıyla kaydedildi!")
        st.session_state[f"{plat_adi}_on"] = 0.0
        st.session_state[f"{plat_adi}_kap"] = 0.0

def ciro_kaydet_cb():
    tarih = st.session_state["ciro_tarih"]
    kasa = st.session_state["ciro_kasa"]
    nakit = st.session_state["ciro_nakit"]
    kredi = st.session_state["ciro_kredi"]
    pavo_n = st.session_state["ciro_pavo_n"]
    pavo_k = st.session_state["ciro_pavo_k"]
    odenmez = st.session_state["ciro_odenmez"]
    
    mevcut = db_oku(supabase.table("ciro").select("id").eq("tarih", str(tarih)))
    if mevcut:
        st.session_state["genel_mesaj"] = ("error", f"⚠️ {tarih} tarihi için Dükkan Cirosu zaten girilmiş! Düzenlemek için paneli kullanın.")
        return
        
    veri = {"tarih": str(tarih), "kasa": kasa, "nakit": nakit, "kredi_karti": kredi, "pavo_nakit": pavo_n, "pavo_kredi": pavo_k, "odenmez": odenmez}
    if db_yaz(supabase.table("ciro").insert(veri)):
        st.session_state["genel_mesaj"] = ("success", "Dükkan Cirosu başarıyla kaydedildi!")
        st.session_state["ciro_nakit"] = 0.0
        st.session_state["ciro_kredi"] = 0.0
        st.session_state["ciro_pavo_n"] = 0.0
        st.session_state["ciro_pavo_k"] = 0.0
        st.session_state["ciro_odenmez"] = 0.0

def puantaj_kaydet_cb():
    tarih = st.session_state["puantaj_tarih"]
    isim = st.session_state["puantaj_isim"]
    durum = st.session_state["puantaj_durum"]
    mesai = st.session_state["puantaj_mesai"]
    
    mevcut = db_oku(supabase.table("puantaj").select("id").eq("personel_adi", isim).eq("tarih", str(tarih)))
    if mevcut:
        st.session_state["genel_mesaj"] = ("error", f"⚠️ {tarih} tarihinde {isim} için zaten giriş yapılmış!")
        return

    if durum == "Haftalık İzin":
        h_baslangic = tarih - datetime.timedelta(days=tarih.weekday())
        h_bitis = h_baslangic + datetime.timedelta(days=6)
        sorgu = supabase.table("puantaj").select("id").eq("personel_adi", isim).eq("durum", "Haftalık İzin").gte("tarih", str(h_baslangic)).lte("tarih", str(h_bitis))
        if db_oku(sorgu):
            st.session_state["genel_mesaj"] = ("error", f"⚠️ İŞLEM REDDEDİLDİ: {isim} bu hafta içinde zaten Haftalık İzin kullanmış!")
            return

    if durum == "Yıllık İzin":
        personel_bilgi = db_oku(supabase.table("personeller").select("yillik_izin_hakki").eq("isim", isim))
        izin_hakki = float(personel_bilgi[0].get('yillik_izin_hakki', 0)) if personel_bilgi else 0
        kullanilan_izinler = db_oku(supabase.table("puantaj").select("id").eq("personel_adi", isim).eq("durum", "Yıllık İzin"))
        if len(kullanilan_izinler) >= izin_hakki:
            st.session_state["genel_mesaj"] = ("error", f"⚠️ İŞLEM REDDEDİLDİ: Yıllık İzin hakkı kalmamıştır!")
            return
        
    veri = {"tarih": str(tarih), "personel_adi": isim, "durum": durum, "fazla_mesai_saati": mesai}
    if db_yaz(supabase.table("puantaj").insert(veri)):
        st.session_state["genel_mesaj"] = ("success", f"{isim} için puantaj kaydedildi!")
        st.session_state["puantaj_mesai"] = 0.0
        st.session_state["puantaj_durum"] = "Tam Gün"

def masraf_kaydet_cb():
    tarih = st.session_state["masraf_tarih"]
    tip = st.session_state["masraf_tipi"]
    aciklama = st.session_state["masraf_aciklama"]
    tutar = st.session_state["masraf_tutar"]
    odeme = st.session_state["masraf_odeme"]
    
    if not aciklama or tutar <= 0:
        st.session_state["genel_mesaj"] = ("warning", "Lütfen açıklama ve tutar girin.")
        return
        
    veri = {"tarih": str(tarih), "masraf_tipi": tip, "aciklama": aciklama, "tutar": tutar, "odeme_tipi": odeme}
    if db_yaz(supabase.table("masraf").insert(veri)):
        bankalar_db = db_oku(supabase.table("banka_hesaplari").select("*"))
        banka_liste = [b['isim'] for b in bankalar_db] if bankalar_db else []
        
        if odeme.startswith("Cari - "):
            cari_adi = odeme.replace("Cari - ", "")
            db_yaz(supabase.table("cari_islemler").insert({"tarih": str(tarih), "cari_adi": cari_adi, "islem_tipi": "Gelen Fatura (Bize Borç Yazar)", "tutar": tutar, "aciklama": f"Masraf: {aciklama}", "odeme_tipi": "- Yok -"}))
            st.session_state["genel_mesaj"] = ("success", f"Masraf kaydedildi ve {cari_adi} hesabına borç işlendi!")
        elif odeme in banka_liste:
            db_yaz(supabase.table("banka_islemleri").insert({"tarih": str(tarih), "hesap_adi": odeme, "islem_tipi": "Para Çıkışı (Masraf)", "tutar": tutar, "aciklama": f"Masraf: {aciklama}"}))
            st.session_state["genel_mesaj"] = ("success", f"Masraf kaydedildi ve {odeme} hesabından düşüldü!")
        else:
            st.session_state["genel_mesaj"] = ("success", "Masraf başarıyla kaydedildi!")
            
        st.session_state["masraf_aciklama"] = ""
        st.session_state["masraf_tutar"] = 0.0

def cari_islem_kaydet_cb():
    tarih = st.session_state["cari_islem_tarih"]
    cari = st.session_state["cari_islem_adi"]
    islem = st.session_state["cari_islem_tipi"]
    tutar = st.session_state["cari_islem_tutar"]
    aciklama = st.session_state["cari_islem_aciklama"]
    odeme = st.session_state.get("cari_islem_odeme", "- Yok -")
    
    if tutar <= 0:
        st.session_state["genel_mesaj"] = ("warning", "Lütfen 0'dan büyük bir tutar girin.")
        return

    if islem == "Ödeme Yaptık (Borç Düşer)" and odeme == "- Yok -":
        st.session_state["genel_mesaj"] = ("warning", "Lütfen ödemenin nereden yapıldığını seçin!")
        return
        
    veri = {"tarih": str(tarih), "cari_adi": cari, "islem_tipi": islem, "tutar": tutar, "aciklama": aciklama, "odeme_tipi": odeme if islem == "Ödeme Yaptık (Borç Düşer)" else "- Yok -"}
    
    if db_yaz(supabase.table("cari_islemler").insert(veri)):
        bankalar_db = db_oku(supabase.table("banka_hesaplari").select("*"))
        banka_liste = [b['isim'] for b in bankalar_db] if bankalar_db else []
        
        if islem == "Ödeme Yaptık (Borç Düşer)" and odeme in banka_liste:
            db_yaz(supabase.table("banka_islemleri").insert({
                "tarih": str(tarih), "hesap_adi": odeme, "islem_tipi": "Para Çıkışı", "karsi_hesap": cari, "tutar": tutar, "aciklama": f"Cari Ödemesi: {aciklama}"
            }))
            
        st.session_state["genel_mesaj"] = ("success", f"{cari} firması için {islem} kaydedildi!")
        st.session_state["cari_islem_tutar"] = 0.0
        st.session_state["cari_islem_aciklama"] = ""

# --- GİRİŞ EKRANI ---
if 'giris_yapildi' not in st.session_state:
    st.session_state.giris_yapildi = False

if not st.session_state.giris_yapildi:
    st.title("☕ Cafe Yönetim Sistemi - Giriş")
    with st.form("login_form"):
        kullanici = st.text_input("Kullanıcı Adı")
        sifre = st.text_input("Şifre", type="password")
        if st.form_submit_button("Giriş Yap"):
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
    "Adisyo (Excel) İçe Aktar",
    "Günlük Dükkan Cirosu", 
    "Yemek Sepeti Yönetimi", 
    "Trendyol Yönetimi", 
    "Banka & Kart Yönetimi",
    "Masraf Girişi", 
    "Cari (Tedarikçi) Yönetimi",
    "Kasa Yönetimi (Virman)",
    "Personel & Puantaj",
    "Raporlar"
])

if st.sidebar.button("Çıkış Yap"):
    st.session_state.giris_yapildi = False
    st.rerun()

# --- PLATFORM FONKSİYONU ---
def platform_sayfasi(platform_adi):
    st.header(f"📦 {platform_adi} Yönetimi")
    bildirim_goster()
    
    alt_menu = st.radio(
        "İşlem Seçin", 
        ["💰 Satış Girişi", "🕒 Tahsilat Takibi", "⚙️ Sisteme Öğret"], 
        horizontal=True, 
        label_visibility="collapsed",
        key=f"{platform_adi}_alt_menu"
    )
    st.markdown("---")
    
    if alt_menu == "💰 Satış Girişi":
        st.subheader("Satışları Gir")
        st.date_input("Satış Tarihi", datetime.date.today(), key=f"{platform_adi}_tarih")
        col1, col2 = st.columns(2)
        with col1: st.number_input("Online Ödeme Cirosu (₺)", min_value=0.0, key=f"{platform_adi}_on")
        with col2: st.number_input("Kapıda Ödeme Cirosu (₺)", min_value=0.0, key=f"{platform_adi}_kap")
        
        st.button("Satışları Kaydet", on_click=platform_kaydet_cb, args=(platform_adi,), type="primary")

        st.divider()
        with st.expander(f"✏️ {platform_adi} Kaydını Düzenle veya Sil", expanded=False):
            satislar_db = db_oku(supabase.table("platform_satis").select("*").eq("platform", platform_adi).order("tarih", desc=True))
            if satislar_db:
                secenekler_ps = {f"{s['tarih']} | {s.get('odeme_tipi','')} | Brüt: {s.get('brut',0)} ₺ | Durum: {s.get('durum','')} (ID: {s['id']})": s for s in satislar_db}
                secilen_ps_str = st.selectbox("İşlem Yapılacak Kaydı Seçin", ["Lütfen bir kayıt seçin..."] + list(secenekler_ps.keys()), key=f"{platform_adi}_duz_select")
                if secilen_ps_str != "Lütfen bir kayıt seçin...":
                    secilen_ps = secenekler_ps[secilen_ps_str]
                    with st.form(f"{platform_adi}_duzenle_form"):
                        try: ps_tarih = datetime.datetime.strptime(secilen_ps['tarih'], '%Y-%m-%d').date()
                        except: ps_tarih = datetime.date.today()
                        y_ps_tarih = st.date_input("Tarih", value=ps_tarih)
                        
                        odm_val = secilen_ps.get('odeme_tipi', 'Online')
                        if odm_val not in ["Online", "Kapıda Ödeme"]: odm_val = "Online"
                        y_ps_odeme = st.selectbox("Ödeme Tipi", ["Online", "Kapıda Ödeme"], index=["Online", "Kapıda Ödeme"].index(odm_val))
                        
                        y_ps_brut = st.number_input("Brüt Tutar (₺)", min_value=0.0, value=float(secilen_ps.get('brut', 0)))
                        
                        c_gun, c_sil = st.columns(2)
                        with c_gun:
                            if st.form_submit_button("Güncelle"):
                                ayar_getir = db_oku(supabase.table("ayarlar").select("*").eq("platform", platform_adi).eq("odeme_tipi", y_ps_odeme))
                                if len(ayar_getir) > 0:
                                    ayar = ayar_getir[0]
                                    k_tutari = round(y_ps_brut * (float(ayar['komisyon']) / 100), 2)
                                    s_tutari = round((y_ps_brut / 1.10) * (float(ayar['stopaj']) / 100), 2)
                                    kes = round(k_tutari + s_tutari, 2)
                                    net_t = round(y_ps_brut - kes if y_ps_odeme == "Online" else -kes, 2)
                                    t_tarihi = y_ps_tarih + datetime.timedelta(days=int(ayar['vade']))
                                    guncel_veri = {"tarih": str(y_ps_tarih), "odeme_tipi": y_ps_odeme, "brut": round(y_ps_brut, 2), "komisyon_tutari": k_tutari, "stopaj_tutari": s_tutari, "kesinti": kes, "net": net_t, "tahsilat_tarihi": str(t_tarihi)}
                                    
                                    if db_yaz(supabase.table("platform_satis").update(guncel_veri).eq("id", secilen_ps['id'])):
                                        st.session_state.genel_mesaj = ("success", "Satış kaydı güncellendi!")
                                        st.rerun()
                                else: st.error("Önce ayarları yapın.")
                        with c_sil:
                            if st.form_submit_button("🗑️ Sil"):
                                if db_yaz(supabase.table("platform_satis").delete().eq("id", secilen_ps['id'])):
                                    st.session_state.genel_mesaj = ("info", "Satış kaydı silindi!")
                                    st.rerun()

    elif alt_menu == "🕒 Tahsilat Takibi":
        bekleyenler = db_oku(supabase.table("platform_satis").select("*").eq("platform", platform_adi).eq("durum", "Bekliyor"))
        if bekleyenler:
            df = pd.DataFrame(bekleyenler)
            for col in ['brut', 'komisyon_tutari', 'stopaj_tutari', 'net', 'odeme_tipi', 'tahsilat_tarihi']:
                if col not in df.columns:
                    if col in ['odeme_tipi', 'tahsilat_tarihi']: df[col] = ""
                    else: df[col] = 0.0

            df['brut'] = pd.to_numeric(df['brut'], errors='coerce').fillna(0).round(2)
            df['komisyon_tutari'] = pd.to_numeric(df['komisyon_tutari'], errors='coerce').fillna(0).round(2)
            df['stopaj_tutari'] = pd.to_numeric(df['stopaj_tutari'], errors='coerce').fillna(0).round(2)
            df['net'] = pd.to_numeric(df['net'], errors='coerce').fillna(0).round(2)
            
            z_goster = st.toggle("⏱️ İşlenme Zamanlarını Göster", key=f"{platform_adi}_bek_zg")
            gosterim_sutunlar = ['id', 'tarih', 'odeme_tipi', 'brut', 'komisyon_tutari', 'stopaj_tutari', 'net', 'tahsilat_tarihi']
            if z_goster: df, gosterim_sutunlar = zaman_sutunlari_ekle(df, gosterim_sutunlar)
            
            df.insert(0, "Seç", False)
            gosterim_sutunlar.insert(0, "Seç")
            
            disabled_cols = ['tarih', 'odeme_tipi', 'brut', 'komisyon_tutari', 'stopaj_tutari', 'net', 'tahsilat_tarihi', 'İşlenme Zamanı', 'Düzenleme Zamanı']
            
            edited_df = st.data_editor(
                df[gosterim_sutunlar],
                column_config={"Seç": st.column_config.CheckboxColumn("Tik (Seç)", default=False), "id": None, "brut": st.column_config.NumberColumn("Brüt", format="%.2f ₺"), "komisyon_tutari": st.column_config.NumberColumn("Komisyon", format="%.2f ₺"), "stopaj_tutari": st.column_config.NumberColumn("Stopaj", format="%.2f ₺"), "net": st.column_config.NumberColumn("Net Yatan", format="%.2f ₺")},
                disabled=disabled_cols,
                hide_index=True, use_container_width=True, key=f"{platform_adi}_editor"
            )
            secilenler = edited_df[edited_df["Seç"] == True]
            col1, col2 = st.columns(2)
            with col1: st.write(f"Tüm Bekleyenlerin Toplamı: **{df['net'].sum():,.2f} ₺**")
            with col2: st.success(f"✔️ Seçtiklerinin Toplamı: **{secilenler['net'].sum():,.2f} ₺**")
            
            if not secilenler.empty:
                st.markdown("---")
                st.subheader("💳 Tahsilat ve Banka Aktarımı")
                bankalar_db = db_oku(supabase.table("banka_hesaplari").select("*"))
                banka_isimleri = [b['isim'] for b in bankalar_db] if bankalar_db else []
                
                if not banka_isimleri:
                    st.warning("⚠️ Lütfen önce 'Banka & Kart Yönetimi' sayfasından en az bir banka hesabı ekleyin.")
                else:
                    c_t1, c_t2 = st.columns(2)
                    with c_t1:
                        tahsilat_tarihi = st.date_input("Paranın Bankaya Yattığı Tarih", datetime.date.today(), key=f"{platform_adi}_tah_tar")
                    with c_t2:
                        secilen_banka = st.selectbox("Paranın Yattığı Banka Hesabı", banka_isimleri, key=f"{platform_adi}_tah_bnk")
                    
                    toplam_net = round(float(secilenler['net'].sum()), 2)
                    if st.button(f"✅ Seçili Satışları 'ÖDENDİ' Yap ve Hesaba Aktar ({toplam_net:,.2f} ₺)", type="primary", key=f"{platform_adi}_odeme_btn"):
                        for idx in secilenler["id"]:
                            db_yaz(supabase.table("platform_satis").update({"durum": "Ödendi"}).eq("id", int(idx)))
                        if toplam_net > 0:
                            db_yaz(supabase.table("banka_islemleri").insert({
                                "tarih": str(tahsilat_tarihi), "hesap_adi": secilen_banka, "islem_tipi": "Para Girişi", "tutar": toplam_net, "aciklama": f"{platform_adi} Tahsilatı"
                            }))
                        st.session_state.genel_mesaj = ("success", "Tahsilat başarıyla aktarıldı!")
                        st.rerun()
        else:
            st.success("Bekleyen alacağınız bulunmuyor.")

        odenenler = db_oku(supabase.table("platform_satis").select("*").eq("platform", platform_adi).eq("durum", "Ödendi"))
        if odenenler:
            st.divider()
            st.subheader("✅ Tahsil Edilenler")
            df_odenen = pd.DataFrame(odenenler).sort_values(by="tarih", ascending=False)
            
            for col in ['brut', 'net', 'odeme_tipi', 'tahsilat_tarihi']:
                if col not in df_odenen.columns:
                    df_odenen[col] = 0.0 if col in ['brut', 'net'] else ""

            df_odenen['net'] = pd.to_numeric(df_odenen['net'], errors='coerce').fillna(0).round(2)
            df_odenen['brut'] = pd.to_numeric(df_odenen['brut'], errors='coerce').fillna(0).round(2)
            
            z_goster2 = st.toggle("⏱️ İşlenme Zamanlarını Göster", key=f"{platform_adi}_tah_zg")
            gosterim_odn = ['tarih', 'odeme_tipi', 'brut', 'net', 'tahsilat_tarihi']
            if z_goster2: df_odenen, gosterim_odn = zaman_sutunlari_ekle(df_odenen, gosterim_odn)
            
            st.dataframe(df_odenen[gosterim_odn], hide_index=True, use_container_width=True)
            
            with st.expander("↩️ Tahsilatı Geri Al (Yanlış Aktarımlar İçin)", expanded=False):
                st.info("💡 Yanlışlıkla 'Ödendi' işaretlediğiniz kayıtları tekrar 'Bekliyor' durumuna alabilirsiniz. (Not: Bankaya yansıyan toplu tutarı 'Banka & Kart Yönetimi' sayfasından da silmeyi veya düzeltmeyi unutmayın.)")
                secenekler_o = {f"{o['tarih']} | {o.get('odeme_tipi','')} | Brüt: {o['brut']} ₺ | Net: {o['net']} ₺ (ID:{o['id']})": o for _, o in df_odenen.iterrows()}
                sec_o_str = st.selectbox("Geri Alınacak Kaydı Seçin", ["Lütfen seçin..."] + list(secenekler_o.keys()), key=f"{platform_adi}_gerial")
                if sec_o_str != "Lütfen seçin...":
                    sec_o = secenekler_o[sec_o_str]
                    if st.button("İşlemi Geri Al (Bekleyenlere Taşı)", key=f"{platform_adi}_gerial_btn"):
                        db_yaz(supabase.table("platform_satis").update({"durum": "Bekliyor"}).eq("id", sec_o['id']))
                        st.session_state.genel_mesaj = ("success", "Tahsilat başarıyla geri alındı, işlem tekrar listeye eklendi!")
                        st.rerun()

    elif alt_menu == "⚙️ Sisteme Öğret":
        st.subheader("Komisyon Ayarları")
        with st.form(f"{platform_adi}_ayar_form"):
            y_o_kom = st.number_input("Online Komisyon (%)", value=10.0)
            y_o_stop = st.number_input("Online Stopaj (%)", value=0.0)
            y_o_vade = st.number_input("Online Vade", value=1, step=1)
            y_k_kom = st.number_input("Kapıda Komisyon (%)", value=10.0)
            y_k_stop = st.number_input("Kapıda Stopaj (%)", value=0.0)
            y_k_vade = st.number_input("Kapıda Vade", value=1, step=1)
            if st.form_submit_button("Ayarları Kaydet"):
                if db_yaz(supabase.table("ayarlar").delete().eq("platform", platform_adi)):
                    db_yaz(supabase.table("ayarlar").insert([
                        {"platform": platform_adi, "odeme_tipi": "Online", "komisyon": y_o_kom, "stopaj": y_o_stop, "vade": y_o_vade},
                        {"platform": platform_adi, "odeme_tipi": "Kapıda Ödeme", "komisyon": y_k_kom, "stopaj": y_k_stop, "vade": y_k_vade}
                    ]))
                    st.session_state.genel_mesaj = ("success", "Ayarlar güncellendi!")
                    st.rerun()

# --- MENÜ İÇERİKLERİ ---
if menu == "Adisyo (Excel) İçe Aktar":
    st.header("📥 Adisyo Excel İçe Aktar (Günlük Satışlar)")
    bildirim_goster()
    
    st.info("Adisyo'dan indirdiğiniz Excel satış raporunu yükleyin. Sistem, 'Geliş Kanalı' ve belirlediğiniz ödeme yöntemlerini analiz edip Ciro ve Platform kayıtlarınızı otomatik ayırır.")
    
    uploaded_file = st.file_uploader("Adisyo Satış Raporu Yükle (Excel)", type=["xlsx", "xls"])
    
    if uploaded_file is not None:
        try:
            df_ad = pd.read_excel(uploaded_file)
            st.success("Excel başarıyla okundu! Lütfen aşağıdaki sütunları seçin:")
            cols = ["- Yok -"] + df_ad.columns.tolist()
            
            def match_col(keywords, exclude=None):
                for i, c in enumerate(cols):
                    c_lower = str(c).lower()
                    if exclude and exclude in c_lower: continue
                    for kw in keywords:
                        if kw in c_lower: return i
                return 0
                
            st.markdown("### Sütun Eşleştirme (Otomatik Tanınanları Kontrol Edin)")
            c1, c2, c3, c4 = st.columns(4)
            with c1: c_kanal = st.selectbox("Geliş Kanalı Sütunu", cols, index=match_col(["kanal", "gelis"]))
            with c2: c_nakit = st.selectbox("Nakit Ödeme Sütunu", cols, index=match_col(["nakit"], exclude="pavo"))
            with c3: c_kk = st.selectbox("Kredi Kartı Sütunu", cols, index=match_col(["kredi kartı", "kredi", "kart"], exclude="pavo"))
            with c4: c_pavo_nakit = st.selectbox("Pavo Nakit Sütunu", cols, index=match_col(["pavo nakit"]))
            
            c5, c6, c7, c8 = st.columns(4)
            with c5: c_pavo_kk = st.selectbox("Pavo Kredi Kartı Sütunu", cols, index=match_col(["pavo kredi", "pavo kart"]))
            with c6: c_ys_on = st.selectbox("YS Online Sütunu", cols, index=match_col(["ys online", "yemek"]))
            with c7: c_ty_on = st.selectbox("Trendyol Online Sütunu", cols, index=match_col(["trendyol online", "ty online"]))
            
            st.divider()
            d1, d2 = st.columns(2)
            with d1: islem_tarihi = st.date_input("İşlem Tarihi (Bu Satışlar Hangi Güne Ait?)", datetime.date.today())
            with d2: hedef_kasa = st.selectbox("Dükkan Nakitleri Hangi Kasaya Eklensin?", ["Kasa 1", "Kasa 2"])
            
            if st.button("Verileri Analiz Et ve Önizleme Oluştur", type="primary"):
                if c_kanal == "- Yok -":
                    st.error("Lütfen 'Geliş Kanalı' sütununu mutlaka seçin!")
                else:
                    c_n = 0.0; c_k = 0.0; c_pn = 0.0; c_pk = 0.0
                    ys_on = 0.0; ys_kap = 0.0
                    ty_on = 0.0; ty_kap = 0.0
                    
                    for idx, row in df_ad.iterrows():
                        kanal = str(row[c_kanal]).lower() if c_kanal != "- Yok -" else ""
                        n_val = safe_float(row[c_nakit]) if c_nakit != "- Yok -" else 0.0
                        k_val = safe_float(row[c_kk]) if c_kk != "- Yok -" else 0.0
                        pn_val = safe_float(row[c_pavo_nakit]) if c_pavo_nakit != "- Yok -" else 0.0
                        pk_val = safe_float(row[c_pavo_kk]) if c_pavo_kk != "- Yok -" else 0.0
                        ys_o_val = safe_float(row[c_ys_on]) if c_ys_on != "- Yok -" else 0.0
                        ty_o_val = safe_float(row[c_ty_on]) if c_ty_on != "- Yok -" else 0.0
                        
                        ys_on += ys_o_val
                        ty_on += ty_o_val
                        
                        c_n += n_val
                        c_k += k_val
                        c_pn += pn_val
                        c_pk += pk_val
                        
                        if "yemek" in kanal or "delivery" in kanal or "ys" in kanal:
                            ys_kap += (n_val + k_val + pn_val + pk_val)
                        elif "trendyol" in kanal or "ty" in kanal or "go" in kanal:
                            ty_kap += (n_val + k_val + pn_val + pk_val)
                            
                    st.session_state['adisyo_ciro'] = [{"Tarih": str(islem_tarihi), "Kasa": hedef_kasa, "Nakit": round(c_n,2), "Kredi Kartı": round(c_k,2), "Pavo Nakit": round(c_pn,2), "Pavo Kredi": round(c_pk,2), "Ödenmez": 0.0}]
                    st.session_state['adisyo_ys'] = [{"Tarih": str(islem_tarihi), "Online Ödeme": round(ys_on,2), "Kapıda Ödeme": round(ys_kap,2)}]
                    st.session_state['adisyo_ty'] = [{"Tarih": str(islem_tarihi), "Online Ödeme": round(ty_on,2), "Kapıda Ödeme": round(ty_kap,2)}]
                    
        except Exception as e:
            st.error(f"Dosya okuma veya ayrıştırma hatası: {e}")
            
    if 'adisyo_ciro' in st.session_state:
        st.divider()
        st.subheader("📝 İşlem Önizlemesi ve Düzenleme")
        st.info("Aşağıdaki veriler Excel'den ayrıştırıldı. Gerekirse kutuların içindeki rakamlara tıklayarak elle son düzeltmeleri yapabilirsiniz.")
        
        st.write("### 🏠 Günlük Dükkan Cirosu (Platform Ödemeleri Dahil Tüm Nakit/Kartlar)")
        df_ciro_edit = st.data_editor(pd.DataFrame(st.session_state['adisyo_ciro']), hide_index=True, use_container_width=True, key="edit_ciro")
        
        c1, c2 = st.columns(2)
        with c1:
            st.write("### 🍔 Yemek Sepeti Satışları")
            df_ys_edit = st.data_editor(pd.DataFrame(st.session_state['adisyo_ys']), hide_index=True, use_container_width=True, key="edit_ys")
        with c2:
            st.write("### 🛍️ Trendyol Satışları")
            df_ty_edit = st.data_editor(pd.DataFrame(st.session_state['adisyo_ty']), hide_index=True, use_container_width=True, key="edit_ty")
            
        if st.button("✅ Tablolardaki Verileri Onayla ve Sisteme Aktar", type="primary"):
            c_row = df_ciro_edit.iloc[0]
            tar_c = str(c_row['Tarih'])
            
            if db_oku(supabase.table("ciro").select("id").eq("tarih", tar_c)):
                st.error(f"HATA: {tar_c} tarihi için Dükkan Cirosu zaten girilmiş! Eski kaydı silmeden yenisini aktaramazsınız.")
            else:
                db_yaz(supabase.table("ciro").insert({
                    "tarih": tar_c, "kasa": c_row['Kasa'], "nakit": float(c_row['Nakit']), "kredi_karti": float(c_row['Kredi Kartı']),
                    "pavo_nakit": float(c_row['Pavo Nakit']), "pavo_kredi": float(c_row['Pavo Kredi']), "odenmez": float(c_row['Ödenmez'])
                }))
                
                def plat_islet(p_adi, r_data):
                    tar_p = str(r_data['Tarih'])
                    if db_oku(supabase.table("platform_satis").select("id").eq("platform", p_adi).eq("tarih", tar_p)):
                        st.warning(f"Uyarı: {p_adi} için {tar_p} tarihinde zaten satış kaydı var, bu platform atlandı.")
                        return
                        
                    for o_tip, tutar in [("Online", float(r_data['Online Ödeme'])), ("Kapıda Ödeme", float(r_data['Kapıda Ödeme']))]:
                        if tutar > 0:
                            ayarlar = db_oku(supabase.table("ayarlar").select("*").eq("platform", p_adi).eq("odeme_tipi", o_tip))
                            if ayarlar:
                                a = ayarlar[0]
                                k_tut = round(tutar * (float(a['komisyon']) / 100), 2)
                                s_tut = round((tutar / 1.10) * (float(a['stopaj']) / 100), 2)
                                kes = round(k_tut + s_tut, 2)
                                net = round(tutar - kes if o_tip == "Online" else -kes, 2)
                                t_tar = pd.to_datetime(tar_p).date() + datetime.timedelta(days=int(a['vade']))
                                
                                db_yaz(supabase.table("platform_satis").insert({
                                    "tarih": tar_p, "platform": p_adi, "odeme_tipi": o_tip, 
                                    "brut": tutar, "komisyon_tutari": k_tut, "stopaj_tutari": s_tut, 
                                    "kesinti": kes, "net": net, "tahsilat_tarihi": str(t_tar), "durum": "Bekliyor"
                                }))
                            else:
                                st.error(f"HATA: {p_adi} ({o_tip}) için komisyon ayarı bulunamadığından sisteme aktarılamadı!")

                plat_islet("Yemek Sepeti", df_ys_edit.iloc[0])
                plat_islet("Trendyol", df_ty_edit.iloc[0])
                
                st.session_state.genel_mesaj = ("success", "Tüm Adisyo verileri başarıyla sisteme entegre edildi!")
                del st.session_state['adisyo_ciro']
                del st.session_state['adisyo_ys']
                del st.session_state['adisyo_ty']
                st.rerun()

elif menu == "Günlük Dükkan Cirosu":
    st.header("Günlük Dükkan Cirosu")
    bildirim_goster()
    
    c1, c2 = st.columns(2)
    with c1:
        st.date_input("Tarih", datetime.date.today(), key="ciro_tarih")
        st.selectbox("Hedef Kasa", ["Kasa 1", "Kasa 2"], key="ciro_kasa")
        st.number_input("Nakit (₺)", min_value=0.0, key="ciro_nakit")
        st.number_input("Kredi Kartı (₺)", min_value=0.0, key="ciro_kredi")
    with c2:
        st.number_input("Pavo Nakit (₺)", min_value=0.0, key="ciro_pavo_n")
        st.number_input("Pavo Kredi (₺)", min_value=0.0, key="ciro_pavo_k")
        st.number_input("Ödenmez (₺)", min_value=0.0, key="ciro_odenmez")
        
    st.button("Ciro Kaydet", on_click=ciro_kaydet_cb, type="primary")

    st.divider()
    with st.expander("✏️ Ciro Kaydını Düzenle veya Sil", expanded=False):
        tum_cirolar = db_oku(supabase.table("ciro").select("*").order("tarih", desc=True))
        if tum_cirolar:
            secenekler_c = {f"{c['tarih']} | {c['kasa']} | Nakit: {c.get('nakit',0)} ₺ | KK: {c.get('kredi_karti',0)} ₺ (ID: {c['id']})": c for c in tum_cirolar}
            secilen_c_str = st.selectbox("İşlem Yapılacak Ciroyu Seçin", ["Lütfen seçin..."] + list(secenekler_c.keys()))
            if secilen_c_str != "Lütfen seçin...":
                secilen_c = secenekler_c[secilen_c_str]
                with st.form("c_duz_form"):
                    try: c_tarih = datetime.datetime.strptime(secilen_c['tarih'], '%Y-%m-%d').date()
                    except: c_tarih = datetime.date.today()
                    y_c_tarih = st.date_input("Tarih", value=c_tarih)
                    y_kasa = st.selectbox("Hedef Kasa", ["Kasa 1", "Kasa 2"], index=["Kasa 1", "Kasa 2"].index(secilen_c.get('kasa', 'Kasa 1') if secilen_c.get('kasa') in ["Kasa 1", "Kasa 2"] else "Kasa 1"))
                    y_nakit = st.number_input("Nakit", value=float(secilen_c.get('nakit', 0)))
                    y_kredi = st.number_input("KK", value=float(secilen_c.get('kredi_karti', 0)))
                    y_pavo_n = st.number_input("Pavo Nakit", value=float(secilen_c.get('pavo_nakit', 0)))
                    y_pavo_k = st.number_input("Pavo KK", value=float(secilen_c.get('pavo_kredi', 0)))
                    y_odenmez = st.number_input("Ödenmez", value=float(secilen_c.get('odenmez', 0)))
                    c_gun, c_sil = st.columns(2)
                    with c_gun:
                        if st.form_submit_button("Güncelle"):
                            if db_yaz(supabase.table("ciro").update({"tarih": str(y_c_tarih), "kasa": y_kasa, "nakit": y_nakit, "kredi_karti": y_kredi, "pavo_nakit": y_pavo_n, "pavo_kredi": y_pavo_k, "odenmez": y_odenmez}).eq("id", secilen_c['id'])):
                                st.session_state.genel_mesaj = ("success", "Ciro güncellendi!")
                            st.rerun()
                    with c_sil:
                        if st.form_submit_button("Sil"):
                            if db_yaz(supabase.table("ciro").delete().eq("id", secilen_c['id'])):
                                st.session_state.genel_mesaj = ("info", "Ciro kaydı silindi!")
                            st.rerun()

    st.subheader("📋 Geçmiş Ciro Kayıtları")
    cirolar = db_oku(supabase.table("ciro").select("*").order("tarih", desc=True))
    if cirolar:
        z_goster_c = st.toggle("⏱️ Kayıt (İşlenme) Zamanlarını Göster", key="ciro_zg")
        df_ciro = pd.DataFrame(cirolar)
        for col in ['nakit', 'kredi_karti', 'pavo_nakit', 'pavo_kredi', 'odenmez']:
            if col not in df_ciro.columns: df_ciro[col] = 0.0
            df_ciro[col] = pd.to_numeric(df_ciro[col], errors='coerce').fillna(0).round(2)
            
        gosterim_ciro = ['tarih', 'kasa', 'nakit', 'kredi_karti', 'pavo_nakit', 'pavo_kredi', 'odenmez']
        if z_goster_c: df_ciro, gosterim_ciro = zaman_sutunlari_ekle(df_ciro, gosterim_ciro)
            
        st.dataframe(df_ciro[gosterim_ciro], hide_index=True, use_container_width=True)

elif menu == "Yemek Sepeti Yönetimi":
    platform_sayfasi("Yemek Sepeti")

elif menu == "Trendyol Yönetimi":
    platform_sayfasi("Trendyol")

elif menu == "Banka & Kart Yönetimi":
    st.header("💳 Banka ve Kredi Kartı Yönetimi")
    bildirim_goster()
    
    alt_menu = st.radio(
        "İşlem Seçin", 
        ["💵 İşlem Girişi", "📊 Bakiyeler ve Hesap Ekstresi", "📂 Excel İçe Aktar", "⚙️ Hesap / Kart Ekle"], 
        horizontal=True, 
        label_visibility="collapsed"
    )
    st.markdown("---")
    
    if alt_menu == "⚙️ Hesap / Kart Ekle":
        st.subheader("Sisteme Yeni Banka veya Kart Ekle")
        with st.form("banka_ekle_form"):
            b_isim = st.text_input("Hesap / Kart Adı")
            b_tip = st.selectbox("Türü", ["Banka Hesabı", "Kredi Kartı"])
            if st.form_submit_button("Ekle"):
                if b_isim.strip():
                    if db_yaz(supabase.table("banka_hesaplari").insert({"isim": b_isim.strip(), "tip": b_tip})):
                        st.session_state.genel_mesaj = ("success", "Hesap başarıyla eklendi!")
                    st.rerun()
        st.divider()
        bankalar_db = db_oku(supabase.table("banka_hesaplari").select("*"))
        if bankalar_db:
            with st.expander("✏️ Hesap Adı Düzenle veya Sil", expanded=False):
                sec_b_str = st.selectbox("İşlem Yapılacak Hesabı Seçin", ["Lütfen seçin..."] + [b['isim'] for b in bankalar_db])
                if sec_b_str != "Lütfen seçin...":
                    sec_b = next(b for b in bankalar_db if b['isim'] == sec_b_str)
                    with st.form("banka_isim_duzenle"):
                        y_isim = st.text_input("Hesap Adı", value=sec_b['isim'])
                        c_g, c_s = st.columns(2)
                        with c_g:
                            if st.form_submit_button("İsmi Güncelle"):
                                db_yaz(supabase.table("banka_hesaplari").update({"isim": y_isim}).eq("id", sec_b['id']))
                                db_yaz(supabase.table("banka_islemleri").update({"hesap_adi": y_isim}).eq("hesap_adi", sec_b['isim']))
                                db_yaz(supabase.table("banka_islemleri").update({"karsi_hesap": y_isim}).eq("karsi_hesap", sec_b['isim']))
                                st.session_state.genel_mesaj = ("success", "Hesap adı güncellendi!")
                                st.rerun()
                        with c_s:
                            if st.form_submit_button("Sil"):
                                if db_yaz(supabase.table("banka_hesaplari").delete().eq("id", sec_b['id'])):
                                    st.session_state.genel_mesaj = ("info", "Hesap sistemden silindi!")
                                st.rerun()

    elif alt_menu == "💵 İşlem Girişi":
        st.subheader("Banka veya Kredi Kartı İşlemi Ekle")
        bankalar_db = db_oku(supabase.table("banka_hesaplari").select("*"))
        if bankalar_db:
            banka_isimleri = [b['isim'] for b in bankalar_db]
            b_tarih = st.date_input("Tarih", datetime.date.today(), key="b_tar")
            c1, c2 = st.columns(2)
            with c1:
                b_hesap = st.selectbox("İşlem Yapılacak Hesap / Kart", banka_isimleri, key="b_hesap")
                b_tip = st.selectbox("İşlem Tipi", ["Açılış", "Para Girişi", "Para Çıkışı", "Bankalar Arası Virman", "Kredi Kartı Borç Ödemesi"], key="b_tip")
            with c2:
                b_tutar = st.number_input("Tutar (₺)", min_value=0.0, key="b_tut")
                b_ack = st.text_input("Açıklama", key="b_ack")
            
            b_karsi = None
            if b_tip in ["Bankalar Arası Virman", "Kredi Kartı Borç Ödemesi"]:
                diger_hesaplar = [b for b in banka_isimleri if b != st.session_state.b_hesap]
                b_karsi = st.selectbox("Karşı Hesap / Ödenen Kart", diger_hesaplar, key="b_karsi")
                
            if st.button("İşlemi Kaydet", type="primary"):
                if b_tutar > 0:
                    veri = {"tarih": str(b_tarih), "hesap_adi": st.session_state.b_hesap, "islem_tipi": b_tip, "tutar": float(b_tutar), "aciklama": b_ack}
                    if b_karsi: veri["karsi_hesap"] = b_karsi
                    if db_yaz(supabase.table("banka_islemleri").insert(veri)):
                        st.session_state.genel_mesaj = ("success", "Banka işlemi başarıyla kaydedildi!")
                    st.rerun()
                else: st.warning("Tutar 0'dan büyük olmalıdır.")
                    
            st.divider()
            with st.expander("✏️ Geçmiş İşlemi Düzenle/Sil", expanded=False):
                islemler_b = db_oku(supabase.table("banka_islemleri").select("*").order("tarih", desc=True))
                if islemler_b:
                    secenekler_bi = {f"{i['tarih']} | {i['hesap_adi']} | {i['islem_tipi']} | {i['tutar']} ₺ (ID: {i['id']})": i for i in islemler_b}
                    sec_bi_str = st.selectbox("İşlem Seçin", ["Seçiniz..."] + list(secenekler_bi.keys()))
                    if sec_bi_str != "Seçiniz...":
                        sec_bi = secenekler_bi[sec_bi_str]
                        with st.form("islem_b_duz"):
                            try: y_b_tarih = datetime.datetime.strptime(sec_bi['tarih'], '%Y-%m-%d').date()
                            except: y_b_tarih = datetime.date.today()
                            y_b_tarih_val = st.date_input("Tarih", value=y_b_tarih)
                            y_b_tutar = st.number_input("Tutar", value=float(sec_bi['tutar']))
                            y_b_ack = st.text_input("Açıklama", value=sec_bi.get('aciklama', ''))
                            cg, cs = st.columns(2)
                            with cg:
                                if st.form_submit_button("Güncelle"):
                                    if db_yaz(supabase.table("banka_islemleri").update({"tarih": str(y_b_tarih_val), "tutar": y_b_tutar, "aciklama": y_b_ack}).eq("id", sec_bi['id'])):
                                        st.session_state.genel_mesaj = ("success", "Banka işlemi güncellendi!")
                                    st.rerun()
                            with cs:
                                if st.form_submit_button("Sil"):
                                    if db_yaz(supabase.table("banka_islemleri").delete().eq("id", sec_bi['id'])):
                                        st.session_state.genel_mesaj = ("info", "Banka işlemi silindi!")
                                    st.rerun()

    elif alt_menu == "📊 Bakiyeler ve Hesap Ekstresi":
        st.subheader("Güncel Hesap Bakiyeleri ve Kart Borçları")
        islemler_b = db_oku(supabase.table("banka_islemleri").select("*"))
        hesaplar_db = db_oku(supabase.table("banka_hesaplari").select("*"))
        
        banka_isimleri_tam = []
        if hesaplar_db and islemler_b:
            banka_isimleri_tam = [b['isim'] for b in hesaplar_db]
            hesap_sozluk = {b['isim']: {'Tip': b['tip'], 'Bakiye (Eksi İse Borç)': 0.0} for b in hesaplar_db}
            for i in islemler_b:
                h = i['hesap_adi']
                tip = i['islem_tipi']
                tut = float(i['tutar'])
                kh = i.get('karsi_hesap')
                if h in hesap_sozluk:
                    if tip in ["Açılış", "Para Girişi"]: hesap_sozluk[h]['Bakiye (Eksi İse Borç)'] += tut
                    elif tip in ["Para Çıkışı", "Para Çıkışı (Masraf)", "Bankalar Arası Virman", "Kredi Kartı Borç Ödemesi"]: hesap_sozluk[h]['Bakiye (Eksi İse Borç)'] -= tut
                if kh and kh in hesap_sozluk:
                    if tip == "Bankalar Arası Virman": hesap_sozluk[kh]['Bakiye (Eksi İse Borç)'] += tut
                    elif tip == "Kredi Kartı Borç Ödemesi": hesap_sozluk[kh]['Bakiye (Eksi İse Borç)'] += tut 
            
            df_bakiye = pd.DataFrame.from_dict(hesap_sozluk, orient='index').reset_index().rename(columns={'index': 'Hesap / Kart Adı'})
            df_bakiye['Bakiye (Eksi İse Borç)'] = df_bakiye['Bakiye (Eksi İse Borç)'].round(2)
            st.dataframe(df_bakiye, hide_index=True, use_container_width=True)
            
            st.divider()
            st.subheader("🧾 Hesap Ekstresi (Bakiyeli Rapor)")
            z_goster_e = st.toggle("⏱️ Kayıt (İşlenme) Zamanlarını Göster", key="banka_eks_zg")
            
            if banka_isimleri_tam:
                secili_ekstre_hesabi = st.selectbox("Ekstresini Görmek İstediğiniz Hesabı Seçin", ["Lütfen seçin..."] + banka_isimleri_tam)
                if secili_ekstre_hesabi != "Lütfen seçin...":
                    hesap_hareketleri = []
                    for i in islemler_b:
                        if i['hesap_adi'] == secili_ekstre_hesabi:
                            if i['islem_tipi'] in ["Açılış", "Para Girişi"]:
                                hesap_hareketleri.append({"id": i['id'], "tarih": i['tarih'], "islem": i['islem_tipi'], "aciklama": i.get('aciklama',''), "karsi_hesap": i.get('karsi_hesap',''), "Giriş": float(i['tutar']), "Çıkış": 0.0, "created_at": i.get('created_at'), "updated_at": i.get('updated_at')})
                            else:
                                hesap_hareketleri.append({"id": i['id'], "tarih": i['tarih'], "islem": i['islem_tipi'], "aciklama": i.get('aciklama',''), "karsi_hesap": i.get('karsi_hesap',''), "Giriş": 0.0, "Çıkış": float(i['tutar']), "created_at": i.get('created_at'), "updated_at": i.get('updated_at')})
                        elif i.get('karsi_hesap') == secili_ekstre_hesabi and i['islem_tipi'] in ["Bankalar Arası Virman", "Kredi Kartı Borç Ödemesi"]:
                            hesap_hareketleri.append({"id": i['id'], "tarih": i['tarih'], "islem": f"{i['islem_tipi']} (Gelen)", "aciklama": i.get('aciklama',''), "karsi_hesap": i['hesap_adi'], "Giriş": float(i['tutar']), "Çıkış": 0.0, "created_at": i.get('created_at'), "updated_at": i.get('updated_at')})
                            
                    if hesap_hareketleri:
                        df_e = pd.DataFrame(hesap_hareketleri)
                        df_e['tarih_dt'] = pd.to_datetime(df_e['tarih'])
                        df_e['is_acilis'] = df_e['islem'].apply(lambda x: 0 if x == 'Açılış' else 1)
                        df_e = df_e.sort_values(by=["tarih_dt", "is_acilis", "id"], ascending=[True, True, True]).reset_index(drop=True)
                        
                        bakiye_list = []
                        bakiye = 0.0
                        for idx, r in df_e.iterrows():
                            bakiye = round(bakiye + r['Giriş'] - r['Çıkış'], 2)
                            bakiye_list.append(bakiye)
                        
                        df_e['Bakiye'] = bakiye_list
                        df_e['tarih'] = df_e['tarih_dt'].dt.date
                        df_e = df_e.sort_values(by=["tarih_dt", "is_acilis", "id"], ascending=[False, False, False]).drop(columns=['tarih_dt', 'is_acilis', 'id'])
                        
                        df_e['Giriş'] = df_e['Giriş'].round(2)
                        df_e['Çıkış'] = df_e['Çıkış'].round(2)
                        
                        gosterim_ekstre = ['tarih', 'islem', 'karsi_hesap', 'aciklama', 'Giriş', 'Çıkış', 'Bakiye']
                        if z_goster_e: df_e, gosterim_ekstre = zaman_sutunlari_ekle(df_e, gosterim_ekstre)
                        
                        st.dataframe(df_e[gosterim_ekstre], hide_index=True, use_container_width=True)
                        dosya_e, uzanti_e, mime_e = excel_indir(df_e[gosterim_ekstre])
                        st.download_button(f"📥 {secili_ekstre_hesabi} Ekstresini İndir", data=dosya_e, file_name=f"{secili_ekstre_hesabi}_Ekstresi.{uzanti_e}", mime=mime_e, key="dl_ekstre")
                    else:
                        st.info("Bu hesaba ait kayıt bulunmuyor.")

            st.divider()
            st.subheader("📋 Tüm Banka ve Kart Hareketleri (Genel Döküm)")
            z_goster_b = st.toggle("⏱️ Kayıt (İşlenme) Zamanlarını Göster", key="banka_genel_zg")
            
            banka_dokum_genel = []
            for i in islemler_b:
                banka_dokum_genel.append({
                    "tarih": i['tarih'], 
                    "hesap_adi": i['hesap_adi'], 
                    "islem_tipi": i['islem_tipi'], 
                    "karsi_hesap": i.get('karsi_hesap', ''), 
                    "tutar": float(i['tutar']), 
                    "aciklama": i.get('aciklama', ''),
                    "created_at": i.get('created_at'),
                    "updated_at": i.get('updated_at')
                })
                    
            df_islem_b = pd.DataFrame(banka_dokum_genel)
            if not df_islem_b.empty:
                df_islem_b['tutar'] = df_islem_b['tutar'].round(2)
                df_islem_b['tarih'] = pd.to_datetime(df_islem_b['tarih']).dt.date
                
                with st.expander("🔍 Genel Dökümü Filtrele", expanded=True):
                    c1, c2, c3, c4 = st.columns(4)
                    with c1: t_aralik_b = st.date_input("Tarih Aralığı", [df_islem_b['tarih'].min(), df_islem_b['tarih'].max()], key="filt_b_tar")
                    with c2: sec_hesap = st.multiselect("Hesap / Kart Seç", df_islem_b['hesap_adi'].unique().tolist(), key="filt_b_hesap")
                    with c3: sec_islem_b = st.multiselect("İşlem Tipi", df_islem_b['islem_tipi'].unique().tolist(), key="filt_b_tip")
                    with c4: ara_b = st.text_input("Açıklama Ara", key="filt_b_ara")
                
                if len(t_aralik_b) == 2: df_islem_b = df_islem_b[(df_islem_b['tarih'] >= t_aralik_b[0]) & (df_islem_b['tarih'] <= t_aralik_b[1])]
                elif len(t_aralik_b) == 1: df_islem_b = df_islem_b[df_islem_b['tarih'] == t_aralik_b[0]]
                
                if sec_hesap: df_islem_b = df_islem_b[df_islem_b['hesap_adi'].isin(sec_hesap)]
                if sec_islem_b: df_islem_b = df_islem_b[df_islem_b['islem_tipi'].isin(sec_islem_b)]
                if ara_b: df_islem_b = df_islem_b[df_islem_b['aciklama'].str.contains(ara_b, case=False, na=False)]

                gosterim_b = ['tarih', 'hesap_adi', 'islem_tipi', 'karsi_hesap', 'tutar', 'aciklama']
                if z_goster_b: df_islem_b, gosterim_b = zaman_sutunlari_ekle(df_islem_b, gosterim_b)

                st.dataframe(df_islem_b[gosterim_b].sort_values("tarih", ascending=False), hide_index=True, use_container_width=True)
                st.info(f"📊 Ekranda filtrelenen toplam işlem sayısı: **{len(df_islem_b)}** | Toplam Tutar: **{df_islem_b['tutar'].sum():,.2f} ₺**")
                
                dosya_b, uzanti_b, mime_b = excel_indir(df_islem_b[gosterim_b])
                st.download_button("📥 Filtrelenmiş Dökümü Excel'e İndir", data=dosya_b, file_name=f"Tum_Banka_Hareketleri.{uzanti_b}", mime=mime_b, key="dl_banka")

    elif alt_menu == "📂 Excel İçe Aktar":
        st.subheader("📂 Banka Ekstresi (Excel) İçe Aktar ve Öğret")
        
        excel_menu = st.radio(
            "İşlem Seçin", 
            ["📤 Excel Yükle ve Aktar", "🧠 Kelime Kuralları (Öğret)"], 
            horizontal=True, 
            label_visibility="collapsed",
            key="banka_excel_menu"
        )
        st.markdown("---")
        
        if excel_menu == "🧠 Kelime Kuralları (Öğret)":
            tipler_db = db_oku(supabase.table("masraf_tipleri").select("*"))
            masraf_tipleri = [t['tip_adi'] for t in tipler_db] if tipler_db else ["Genel Masraf"]
            cariler_db = db_oku(supabase.table("cariler").select("*"))
            cari_liste = [c['isim'] for c in cariler_db] if cariler_db else []
            
            with st.form("kural_ekle_form"):
                k_kelime = st.text_input("Açıklamada Geçen Kelime (Örn: BİM, POS)")
                k_islem = st.selectbox("Bunu Hangi İşlem Olarak Tanısın?", ["Masraf", "Cari Ödeme (Para Çıkışı)", "Para Girişi", "Para Çıkışı"])
                k_hedef = st.selectbox("Hedef / Alt Kategori (Sadece Masraf ve Cari İçin)", ["- Yok -"] + masraf_tipleri + cari_liste)
                if st.form_submit_button("Kuralı Öğret"):
                    if k_kelime.strip():
                        if db_yaz(supabase.table("banka_kurallari").insert({"kelime": k_kelime.strip(), "islem_tipi": k_islem, "hedef": k_hedef})):
                            st.session_state.genel_mesaj = ("success", "Kural başarıyla öğretildi!")
                        st.rerun()
                        
            st.divider()
            kurallar_db = db_oku(supabase.table("banka_kurallari").select("*"))
            if kurallar_db:
                for k in kurallar_db:
                    col1, col2 = st.columns([4, 1])
                    with col1: st.write(f"Kelime: **{k['kelime']}** ➡️ İşlem: **{k['islem_tipi']}** | Hedef: **{k['hedef']}**")
                    with col2:
                        if st.button("Sil", key=f"del_k_{k['id']}"):
                            if db_yaz(supabase.table("banka_kurallari").delete().eq("id", k['id'])):
                                st.session_state.genel_mesaj = ("info", "Kural silindi!")
                            st.rerun()

        elif excel_menu == "📤 Excel Yükle ve Aktar":
            bankalar_db = db_oku(supabase.table("banka_hesaplari").select("*"))
            banka_isimleri = [b['isim'] for b in bankalar_db] if bankalar_db else []
            
            if not banka_isimleri:
                st.warning("Lütfen önce sisteme bir banka hesabı ekleyin.")
            else:
                h_secim = st.selectbox("Hangi Hesaba Aktarılacak?", banka_isimleri)
                uploaded_file = st.file_uploader("Banka Ekstresi Yükle (Excel veya CSV)", type=["xlsx", "xls", "csv"])
                
                if uploaded_file is not None:
                    try:
                        if uploaded_file.name.endswith(".csv"): df_yuk = pd.read_csv(uploaded_file)
                        else: df_yuk = pd.read_excel(uploaded_file)
                        
                        cols = ["Yok"] + df_yuk.columns.tolist()
                        c1, c2, c3, c4 = st.columns(4)
                        with c1: col_tar = st.selectbox("Tarih Sütunu", cols, index=1 if len(cols)>1 else 0)
                        with c2: col_ack = st.selectbox("Açıklama Sütunu", cols, index=2 if len(cols)>2 else 0)
                        with c3: col_cik = st.selectbox("Çıkan Tutar (Borç)", cols)
                        with c4: col_gir = st.selectbox("Giren Tutar (Alacak)", cols)
                        
                        if st.button("Verileri İncele ve Kuralları Uygula"):
                            if col_tar == "Yok" or col_ack == "Yok":
                                st.error("Tarih ve Açıklama sütunları zorunludur!")
                            else:
                                kurallar_db = db_oku(supabase.table("banka_kurallari").select("*"))
                                preview = []
                                for i, row in df_yuk.iterrows():
                                    t_val = row[col_tar]
                                    ack_val = str(row[col_ack])
                                    g_tutar = safe_float(row[col_gir]) if col_gir != "Yok" else 0.0
                                    c_tutar = safe_float(row[col_cik]) if col_cik != "Yok" else 0.0
                                    
                                    if g_tutar > 0:
                                        tutar = g_tutar
                                        i_tip = "Para Girişi"
                                    elif c_tutar > 0:
                                        tutar = c_tutar
                                        i_tip = "Para Çıkışı"
                                    else: continue
                                        
                                    h_def = ""
                                    if kurallar_db:
                                        for kr in kurallar_db:
                                            if str(kr['kelime']).lower() in ack_val.lower():
                                                i_tip = kr['islem_tipi']
                                                h_def = kr['hedef']
                                                break
                                    try: tar_str = str(pd.to_datetime(t_val).date())
                                    except: tar_str = str(datetime.date.today())
                                    
                                    preview.append({"İşle": True, "Tarih": tar_str, "Açıklama": ack_val, "Tutar": tutar, "İşlem Tipi": i_tip, "Hedef Kategori": h_def if h_def != "- Yok -" else ""})
                                st.session_state['excel_preview'] = preview

                    except Exception as e:
                        st.error(f"Dosya okuma hatası: {e}")
                        
                if 'excel_preview' in st.session_state:
                    df_p = pd.DataFrame(st.session_state['excel_preview'])
                    edited_df = st.data_editor(df_p, column_config={"İşle": st.column_config.CheckboxColumn("İşle", default=True), "İşlem Tipi": st.column_config.SelectboxColumn("İşlem Tipi", options=["Para Girişi", "Para Çıkışı", "Masraf", "Cari Ödeme (Para Çıkışı)"])}, hide_index=True, use_container_width=True)
                    
                    if st.button("✅ Seçili İşlemleri Sisteme Kaydet", type="primary"):
                        secilen_rows = edited_df[edited_df['İşle'] == True]
                        basarili = 0
                        for idx, r in secilen_rows.iterrows():
                            tip = r['İşlem Tipi']
                            tar = r['Tarih']
                            tut = float(r['Tutar'])
                            ack = r['Açıklama']
                            hedef = r['Hedef Kategori']
                            
                            if tip == "Masraf":
                                db_yaz(supabase.table("masraf").insert({"tarih": tar, "masraf_tipi": hedef, "aciklama": ack, "tutar": tut, "odeme_tipi": h_secim}))
                                db_yaz(supabase.table("banka_islemleri").insert({"tarih": tar, "hesap_adi": h_secim, "islem_tipi": "Para Çıkışı (Masraf)", "tutar": tut, "aciklama": f"Masraf: {ack}"}))
                            elif tip == "Cari Ödeme (Para Çıkışı)":
                                db_yaz(supabase.table("cari_islemler").insert({"tarih": tar, "cari_adi": hedef, "islem_tipi": "Ödeme Yaptık (Borç Düşer)", "tutar": tut, "aciklama": f"Banka: {ack}", "odeme_tipi": h_secim}))
                                db_yaz(supabase.table("banka_islemleri").insert({"tarih": tar, "hesap_adi": h_secim, "islem_tipi": "Para Çıkışı", "karsi_hesap": hedef, "tutar": tut, "aciklama": f"Cari Ödemesi: {ack}"}))
                            else:
                                db_yaz(supabase.table("banka_islemleri").insert({"tarih": tar, "hesap_adi": h_secim, "islem_tipi": tip, "tutar": tut, "aciklama": ack}))
                            
                            basarili += 1
                                
                        del st.session_state['excel_preview']
                        st.session_state.genel_mesaj = ("success", f"{basarili} işlem başarıyla kaydedildi!")
                        st.rerun()

elif menu == "Masraf Girişi":
    st.header("Masraf Girişi")
    bildirim_goster()
    tipler_db = db_oku(supabase.table("masraf_tipleri").select("*"))
    tipler = [t['tip_adi'] for t in tipler_db] if tipler_db else ["Genel Masraf"]

    with st.expander("⚙️ Yeni Masraf Tipi Tanımla", expanded=False):
        with st.form("masraf_tipi_form"):
            yeni_tip = st.text_input("Masraf Tipi Adı")
            if st.form_submit_button("Ekle"):
                if yeni_tip.strip():
                    if db_yaz(supabase.table("masraf_tipleri").insert({"tip_adi": yeni_tip.strip()})):
                        st.session_state.genel_mesaj = ("success", "Masraf Tipi eklendi!")
                    st.rerun()
    st.divider()
        
    bankalar_db = db_oku(supabase.table("banka_hesaplari").select("*"))
    banka_liste = [b['isim'] for b in bankalar_db] if bankalar_db else []
    cariler_db = db_oku(supabase.table("cariler").select("*"))
    cari_liste = [f"Cari - {c['isim']}" for c in cariler_db] if cariler_db else []
    odeme_yontemleri = ["Nakit - Kasa 1", "Nakit - Kasa 2"] + banka_liste + cari_liste

    c1, c2 = st.columns(2)
    with c1:
        st.date_input("Tarih", datetime.date.today(), key="masraf_tarih")
        st.selectbox("Masraf Tipi", tipler, key="masraf_tipi")
        st.text_input("Açıklama", key="masraf_aciklama")
    with c2:
        st.number_input("Tutar (₺)", min_value=0.0, key="masraf_tutar")
        st.selectbox("Nereden Ödendi?", odeme_yontemleri, key="masraf_odeme")
    st.button("Masrafı Kaydet", on_click=masraf_kaydet_cb, type="primary")

    st.divider()
    with st.expander("✏️ Masraf Düzenle veya Sil", expanded=False):
        tum_masraflar = db_oku(supabase.table("masraf").select("*").order("tarih", desc=True))
        if tum_masraflar:
            secenekler = {f"{m['tarih']} | {m.get('masraf_tipi','Genel')} | {m.get('aciklama','')} | {m['tutar']} ₺ (ID: {m['id']})": m for m in tum_masraflar}
            secilen_m_str = st.selectbox("İşlem Yapılacak Masrafı Seçin", ["Lütfen seçin..."] + list(secenekler.keys()))
            if secilen_m_str != "Lütfen seçin...":
                secilen_m = secenekler[secilen_m_str]
                with st.form("masraf_duz_form"):
                    try: m_tarih = datetime.datetime.strptime(secilen_m['tarih'], '%Y-%m-%d').date()
                    except: m_tarih = datetime.date.today()
                    y_tarih = st.date_input("Tarih", value=m_tarih)
                    try: t_idx = tipler.index(secilen_m.get('masraf_tipi', 'Genel Masraf'))
                    except: t_idx = 0
                    y_tip = st.selectbox("Masraf Tipi", tipler, index=t_idx)
                    y_aciklama = st.text_input("Açıklama", value=secilen_m.get('aciklama',''))
                    y_tutar = st.number_input("Tutar (₺)", value=float(secilen_m.get('tutar', 0)))
                    
                    o_val = secilen_m.get('odeme_tipi', 'Nakit - Kasa 1')
                    if o_val not in odeme_yontemleri: o_val = odeme_yontemleri[0]
                    y_odeme_y = st.selectbox("Nereden Ödendi?", odeme_yontemleri, index=odeme_yontemleri.index(o_val))
                    
                    c_gun, c_sil = st.columns(2)
                    with c_gun:
                        if st.form_submit_button("Güncelle"):
                            if str(secilen_m.get('odeme_tipi','')).startswith("Cari - "):
                                eski_c_adi = str(secilen_m.get('odeme_tipi')).replace("Cari - ", "")
                                db_yaz(supabase.table("cari_islemler").delete().eq("cari_adi", eski_c_adi).eq("tarih", str(secilen_m['tarih'])).ilike("aciklama", f"Masraf: {secilen_m.get('aciklama','')}%"))
                            elif str(secilen_m.get('odeme_tipi','')) in banka_liste:
                                db_yaz(supabase.table("banka_islemleri").delete().eq("hesap_adi", secilen_m['odeme_tipi']).eq("tarih", str(secilen_m['tarih'])).eq("islem_tipi", "Para Çıkışı (Masraf)").ilike("aciklama", f"Masraf: {secilen_m.get('aciklama','')}%"))
                            
                            db_yaz(supabase.table("masraf").update({"tarih": str(y_tarih), "masraf_tipi": y_tip, "aciklama": y_aciklama, "tutar": y_tutar, "odeme_tipi": y_odeme_y}).eq("id", secilen_m['id']))
                            
                            if str(y_odeme_y).startswith("Cari - "):
                                yeni_c_adi = y_odeme_y.replace("Cari - ", "")
                                db_yaz(supabase.table("cari_islemler").insert({"tarih": str(y_tarih), "cari_adi": yeni_c_adi, "islem_tipi": "Gelen Fatura (Bize Borç Yazar)", "tutar": y_tutar, "aciklama": f"Masraf: {y_aciklama}"}))
                            elif y_odeme_y in banka_liste:
                                db_yaz(supabase.table("banka_islemleri").insert({"tarih": str(y_tarih), "hesap_adi": y_odeme_y, "islem_tipi": "Para Çıkışı (Masraf)", "tutar": y_tutar, "aciklama": f"Masraf: {y_aciklama}"}))
                            
                            st.session_state.genel_mesaj = ("success", "Masraf güncellendi!")
                            st.rerun()
                    with c_sil:
                        if st.form_submit_button("Sil"):
                            if db_yaz(supabase.table("masraf").delete().eq("id", secilen_m['id'])):
                                if str(secilen_m.get('odeme_tipi','')).startswith("Cari - "):
                                    sil_c_adi = str(secilen_m.get('odeme_tipi')).replace("Cari - ", "")
                                    db_yaz(supabase.table("cari_islemler").delete().eq("cari_adi", sil_c_adi).eq("tarih", str(secilen_m['tarih'])).ilike("aciklama", f"Masraf: {secilen_m.get('aciklama','')}%"))
                                elif str(secilen_m.get('odeme_tipi','')) in banka_liste:
                                    db_yaz(supabase.table("banka_islemleri").delete().eq("hesap_adi", secilen_m['odeme_tipi']).eq("tarih", str(secilen_m['tarih'])).eq("islem_tipi", "Para Çıkışı (Masraf)").ilike("aciklama", f"Masraf: {secilen_m.get('aciklama','')}%"))
                                st.session_state.genel_mesaj = ("info", "Masraf tamamen silindi!")
                                st.rerun()

    st.subheader("📋 Masraf Kayıtları ve Filtreleme")
    masraflar = db_oku(supabase.table("masraf").select("*").order("tarih", desc=True))
    if masraflar:
        z_goster_m = st.toggle("⏱️ Kayıt (İşlenme) Zamanlarını Göster", key="masraf_zg")
        df_masraf = pd.DataFrame(masraflar)
        if 'tutar' not in df_masraf.columns: df_masraf['tutar'] = 0.0
        if 'odeme_tipi' not in df_masraf.columns: df_masraf['odeme_tipi'] = ""
        if 'aciklama' not in df_masraf.columns: df_masraf['aciklama'] = ""
        
        df_masraf['tutar'] = pd.to_numeric(df_masraf['tutar'], errors='coerce').fillna(0).round(2)
        df_masraf['masraf_tipi'] = df_masraf.get('masraf_tipi', 'Genel').fillna('Genel Masraf')
        df_masraf['tarih'] = pd.to_datetime(df_masraf['tarih']).dt.date
        with st.expander("🔍 Filtreleme Seçenekleri", expanded=True):
            c1, c2, c3, c4 = st.columns(4)
            with c1: tarih_araligi = st.date_input("Tarih Aralığı", [df_masraf['tarih'].min(), df_masraf['tarih'].max()])
            with c2: sec_tip = st.multiselect("Masraf Tipi", df_masraf['masraf_tipi'].unique().tolist())
            with c3: sec_odeme = st.multiselect("Nereden Ödendi?", df_masraf['odeme_tipi'].unique().tolist())
            with c4: aranan = st.text_input("Açıklama Ara")
        if len(tarih_araligi) == 2: df_masraf = df_masraf[(df_masraf['tarih'] >= tarih_araligi[0]) & (df_masraf['tarih'] <= tarih_araligi[1])]
        elif len(tarih_araligi) == 1: df_masraf = df_masraf[df_masraf['tarih'] == tarih_araligi[0]]
        if sec_tip: df_masraf = df_masraf[df_masraf['masraf_tipi'].isin(sec_tip)]
        if sec_odeme: df_masraf = df_masraf[df_masraf['odeme_tipi'].isin(sec_odeme)]
        if aranan: df_masraf = df_masraf[df_masraf['aciklama'].str.contains(aranan, case=False, na=False)]
        
        gosterim_mas = ['tarih', 'masraf_tipi', 'aciklama', 'tutar', 'odeme_tipi']
        if z_goster_m: df_masraf, gosterim_mas = zaman_sutunlari_ekle(df_masraf, gosterim_mas)
        
        st.dataframe(df_masraf[gosterim_mas], hide_index=True, use_container_width=True)
        st.info(f"📊 Toplam Tutar: **{df_masraf['tutar'].sum():,.2f} ₺**")

elif menu == "Cari (Tedarikçi) Yönetimi":
    st.header("🏢 Cari (Tedarikçi) Yönetimi")
    bildirim_goster()
    
    alt_menu = st.radio(
        "İşlem Seçin", 
        ["📈 Fatura & Ödeme Girişi", "📋 Cari Ekstre", "⚙️ Tedarikçi Ekle"], 
        horizontal=True, 
        label_visibility="collapsed"
    )
    st.markdown("---")
    
    if alt_menu == "⚙️ Tedarikçi Ekle":
        with st.form("cari_ekle_form"):
            yeni_cari = st.text_input("Tedarikçi Firma / Kişi Adı")
            if st.form_submit_button("Ekle"):
                if yeni_cari.strip():
                    if db_yaz(supabase.table("cariler").insert({"isim": yeni_cari.strip()})):
                        st.session_state.genel_mesaj = ("success", "Cari eklendi!")
                    st.rerun()
        st.divider()
        cariler_db = db_oku(supabase.table("cariler").select("*"))
        if cariler_db:
            with st.expander("✏️ Cari Adı Düzenle veya Sil", expanded=False):
                sec_c_str = st.selectbox("İşlem Yapılacak Cariyi Seçin", ["Lütfen seçin..."] + [c['isim'] for c in cariler_db])
                if sec_c_str != "Lütfen seçin...":
                    sec_c = next(c for c in cariler_db if c['isim'] == sec_c_str)
                    with st.form("cari_isim_duzenle"):
                        y_isim = st.text_input("Firma Adı", value=sec_c['isim'])
                        c_g, c_s = st.columns(2)
                        with c_g:
                            if st.form_submit_button("Güncelle"):
                                db_yaz(supabase.table("cariler").update({"isim": y_isim}).eq("id", sec_c['id']))
                                db_yaz(supabase.table("cari_islemler").update({"cari_adi": y_isim}).eq("cari_adi", sec_c['isim']))
                                st.session_state.genel_mesaj = ("success", "Cari güncellendi!")
                                st.rerun()
                        with c_s:
                            if st.form_submit_button("Sil"):
                                if db_yaz(supabase.table("cariler").delete().eq("id", sec_c['id'])):
                                    st.session_state.genel_mesaj = ("info", "Cari silindi!")
                                st.rerun()

    elif alt_menu == "📈 Fatura & Ödeme Girişi":
        cariler_db = db_oku(supabase.table("cariler").select("*"))
        if cariler_db:
            c1, c2 = st.columns(2)
            with c1:
                st.date_input("İşlem Tarihi", datetime.date.today(), key="cari_islem_tarih")
                st.selectbox("Cari (Firma) Seçin", [c['isim'] for c in cariler_db], key="cari_islem_adi")
                st.selectbox("İşlem Tipi", ["Gelen Fatura (Bize Borç Yazar)", "Ödeme Yaptık (Borç Düşer)"], key="cari_islem_tipi")
            with c2:
                st.number_input("Tutar (₺)", min_value=0.0, key="cari_islem_tutar")
                
                bankalar_db = db_oku(supabase.table("banka_hesaplari").select("*"))
                b_liste = [b['isim'] for b in bankalar_db] if bankalar_db else []
                odeme_yontemleri = ["- Yok -", "Nakit - Kasa 1", "Nakit - Kasa 2"] + b_liste
                st.selectbox("Nereden Ödendi? (Sadece Ödeme Yaptıysanız Seçin)", odeme_yontemleri, key="cari_islem_odeme")
                
                st.text_input("Açıklama / Fatura No", key="cari_islem_aciklama")
                st.button("İşlemi Kaydet", on_click=cari_islem_kaydet_cb, type="primary")
            st.divider()
            with st.expander("✏️ Geçmiş İşlemi Düzenle/Sil", expanded=False):
                islemler = db_oku(supabase.table("cari_islemler").select("*").order("tarih", desc=True))
                if islemler:
                    secenekler_i = {f"{i['tarih']} | {i['cari_adi']} | {i['islem_tipi']} | {i['tutar']} ₺ (ID: {i['id']})": i for i in islemler}
                    sec_i_str = st.selectbox("İşlem Seçin", ["Seçiniz..."] + list(secenekler_i.keys()))
                    if sec_i_str != "Seçiniz...":
                        sec_i = secenekler_i[sec_i_str]
                        with st.form("islem_duz"):
                            y_tarih = st.date_input("Tarih", value=datetime.datetime.strptime(sec_i['tarih'], '%Y-%m-%d').date())
                            
                            islem_tipi_val = sec_i.get('islem_tipi', 'Gelen Fatura (Bize Borç Yazar)')
                            if islem_tipi_val not in ["Gelen Fatura (Bize Borç Yazar)", "Ödeme Yaptık (Borç Düşer)"]: islem_tipi_val = "Gelen Fatura (Bize Borç Yazar)"
                            y_tip = st.selectbox("İşlem Tipi", ["Gelen Fatura (Bize Borç Yazar)", "Ödeme Yaptık (Borç Düşer)"], index=["Gelen Fatura (Bize Borç Yazar)", "Ödeme Yaptık (Borç Düşer)"].index(islem_tipi_val))
                            
                            y_tutar = st.number_input("Tutar", value=float(sec_i.get('tutar', 0)))
                            
                            odm_val = sec_i.get('odeme_tipi', '- Yok -')
                            if odm_val not in odeme_yontemleri: odm_val = "- Yok -"
                            y_odeme = st.selectbox("Nereden Ödendi?", odeme_yontemleri, index=odeme_yontemleri.index(odm_val))
                            
                            y_ack = st.text_input("Açıklama", value=sec_i.get('aciklama', ''))
                            cg, cs = st.columns(2)
                            with cg:
                                if st.form_submit_button("Güncelle"):
                                    if str(sec_i.get('islem_tipi')) == "Ödeme Yaptık (Borç Düşer)" and str(sec_i.get('odeme_tipi')) in b_liste:
                                        db_yaz(supabase.table("banka_islemleri").delete().eq("hesap_adi", sec_i['odeme_tipi']).eq("tarih", str(sec_i['tarih'])).eq("islem_tipi", "Para Çıkışı").ilike("aciklama", f"Cari Ödemesi: {sec_i.get('aciklama', '')}%"))
                                    
                                    db_yaz(supabase.table("cari_islemler").update({"tarih": str(y_tarih), "islem_tipi": y_tip, "tutar": y_tutar, "aciklama": y_ack, "odeme_tipi": y_odeme if y_tip == "Ödeme Yaptık (Borç Düşer)" else "- Yok -"}).eq("id", sec_i['id']))
                                    
                                    if y_tip == "Ödeme Yaptık (Borç Düşer)" and y_odeme in b_liste:
                                        db_yaz(supabase.table("banka_islemleri").insert({"tarih": str(y_tarih), "hesap_adi": y_odeme, "islem_tipi": "Para Çıkışı", "karsi_hesap": sec_i['cari_adi'], "tutar": y_tutar, "aciklama": f"Cari Ödemesi: {y_ack}"}))
                                    st.session_state.genel_mesaj = ("success", "İşlem güncellendi!")
                                    st.rerun()
                            with cs:
                                if st.form_submit_button("Sil"):
                                    if str(sec_i.get('islem_tipi')) == "Ödeme Yaptık (Borç Düşer)" and str(sec_i.get('odeme_tipi')) in b_liste:
                                        db_yaz(supabase.table("banka_islemleri").delete().eq("hesap_adi", sec_i['odeme_tipi']).eq("tarih", str(sec_i['tarih'])).eq("islem_tipi", "Para Çıkışı").ilike("aciklama", f"Cari Ödemesi: {sec_i.get('aciklama', '')}%"))
                                    
                                    if db_yaz(supabase.table("cari_islemler").delete().eq("id", sec_i['id'])):
                                        st.session_state.genel_mesaj = ("info", "İşlem tamamen silindi!")
                                    st.rerun()

    elif alt_menu == "📋 Cari Ekstre":
        islemler = db_oku(supabase.table("cari_islemler").select("*"))
        if islemler:
            df_i = pd.DataFrame(islemler)
            if 'tutar' not in df_i.columns: df_i['tutar'] = 0.0
            if 'odeme_tipi' not in df_i.columns: df_i['odeme_tipi'] = ""
            if 'aciklama' not in df_i.columns: df_i['aciklama'] = ""
            
            df_i['tutar'] = pd.to_numeric(df_i['tutar'], errors='coerce').fillna(0).round(2)
            
            fatura_toplam = df_i[df_i['islem_tipi'] == 'Gelen Fatura (Bize Borç Yazar)'].groupby('cari_adi')['tutar'].sum()
            odeme_toplam = df_i[df_i['islem_tipi'] == 'Ödeme Yaptık (Borç Düşer)'].groupby('cari_adi')['tutar'].sum()
            bakiye_df = pd.DataFrame({'Toplam Fatura Tutarı': fatura_toplam, 'Ödenen Tutar': odeme_toplam}).fillna(0)
            
            bakiye_df['Toplam Fatura Tutarı'] = bakiye_df['Toplam Fatura Tutarı'].round(2)
            bakiye_df['Ödenen Tutar'] = bakiye_df['Ödenen Tutar'].round(2)
            bakiye_df['KALAN BORCUMUZ'] = (bakiye_df['Toplam Fatura Tutarı'] - bakiye_df['Ödenen Tutar']).round(2)
            st.dataframe(bakiye_df.reset_index(), hide_index=True, use_container_width=True)
            
            st.divider()
            st.subheader("Tüm Cari Hareketler Dökümü")
            z_goster_c2 = st.toggle("⏱️ Kayıt (İşlenme) Zamanlarını Göster", key="cari_zg")
            df_i['odeme_tipi'] = df_i.get('odeme_tipi', '- Yok -')
            df_i['tarih'] = pd.to_datetime(df_i['tarih']).dt.date
            
            with st.expander("🔍 Cari Filtreleme Paneli", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                with c1: t_aralik_c = st.date_input("Tarih Aralığı", [df_i['tarih'].min(), df_i['tarih'].max()], key="filt_c_tar")
                with c2: sec_cari = st.multiselect("Cari (Firma) Seç", df_i['cari_adi'].unique().tolist(), key="filt_c_cari")
                with c3: sec_tip_c = st.multiselect("İşlem Tipi", df_i['islem_tipi'].unique().tolist(), key="filt_c_tip")
                with c4: ara_c = st.text_input("Açıklama Ara", key="filt_c_ara")
                
            if len(t_aralik_c) == 2: df_i = df_i[(df_i['tarih'] >= t_aralik_c[0]) & (df_i['tarih'] <= t_aralik_c[1])]
            elif len(t_aralik_c) == 1: df_i = df_i[df_i['tarih'] == t_aralik_c[0]]
            if sec_cari: df_i = df_i[df_i['cari_adi'].isin(sec_cari)]
            if sec_tip_c: df_i = df_i[df_i['islem_tipi'].isin(sec_tip_c)]
            if ara_c: df_i = df_i[df_i['aciklama'].str.contains(ara_c, case=False, na=False)]
            
            gosterim_cari = ['tarih', 'cari_adi', 'islem_tipi', 'tutar', 'odeme_tipi', 'aciklama']
            if z_goster_c2: df_i, gosterim_cari = zaman_sutunlari_ekle(df_i, gosterim_cari)
            
            st.dataframe(df_i[gosterim_cari].sort_values("tarih", ascending=False), hide_index=True, use_container_width=True)
            
            dosya_c, uzanti_c, mime_c = excel_indir(df_i[gosterim_cari])
            st.download_button("📥 Filtrelenmiş Dökümü Excel'e İndir", data=dosya_c, file_name=f"Cari_Hareketleri.{uzanti_c}", mime=mime_c, key="dl_cari")
