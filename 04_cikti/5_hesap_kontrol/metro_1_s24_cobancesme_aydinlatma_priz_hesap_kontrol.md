# Mühendislik Hesap Denetimi ve Yeniden Hesaplama Raporu — `metro_1_s24_cobancesme_aydinlatma_priz.dxf`

**Birim:** `mm` | **Mevzuat Kaynağı:** `ibb_metro` | **Denetlenen Pano:** 0 + Ana Pano | **Kritik İhlal:** 0 | **Uyarı:** 4 | **Uygun:** 1

## 1. Kritik Bulgular & Mühendislik Hata Özeti
| Kod | Önem | Kategori | Konum | Projedeki Değer | Motor / Mevzuat Değerlendirmesi | Standart |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `M-01` | **UYGUN** | Yangın Güvenliği / Halojen-Free Kablo | Pafta Genel (4 tip, 22 adet) | 3x95/16mm² XLPE, 3x(1x185/25ş mm2 XLPE), 1x240 mm² XLPE, 3x95/16 mm² XLPE | LSZH / HFFR / XLPE / FE180 — Çizimde tespit edilen tüm güç/sinyal/data kabloları halojensiz (N2XH/N2XRH/XLPE/LS0H) sınıftadır. | NFPA 130 Md. 8.8 & BYKHY Md. 72, 83 |
| `M-02` | **UYARI** | Yangına Dayanıklı (FE180/PH120) Besleme | Acil / Sinyalizasyon / Yangın | FE180/PH120 etiketi tespit edilmedi | FE180 / PH120 Zorunlu — Acil/sinyalizasyon ekipmanları mevcut ancak okunan kablo etiketlerinde açık FE180/PH120 ibaresi görülmedi. | BYKHY Md. 72 & NFPA 130 |
| `M-03` | **BILGI** | Kablo Akım Taşıma Kapasitesi (Yöntem E & B.52.17) | Okunan 4 güç kablosu kesiti | 3x95/16mm² XLPE: Iz(E)=298A -> Gruplama(x0.70)=208.6A; 3x(1x185/25ş mm2 XLPE): Iz(E)=456A -> Gruplama(x0.70)=319.2A; 1x240 mm² XLPE: Iz(E)=641A -> Gruplama(x0.70)=448.7A; 3x95/16 mm² XLPE: Iz(E)=298A -> Gruplama(x0.70)=208.6A | Çizelge B.52.3/B.52.5 x 0.70 — Çizimdeki güç kabloları için delikli tava (Yöntem E) ve 3 devre gruplama katsayısı (0.70) uygulanmış tablo sınırları hesaplandı (kesitlerin gerçek yük akımı Ib bilgisi çizimde mevcutsa pano/şema adımında ayrıca denetlenir). | TS HD 60364-5-52:2014 |
| `M-04` | **UYARI** | PE / Konsantrik Ekran Kesit Oranı | 3x95/16mm² XLPE | S_faz=95 mm², Ekran/PE=16 mm² | Çizelge 54.2 >= 47.5 mm² (S/2) — 3x95/16mm² XLPE kablosundaki 16 mm² ekran/PE kesiti, 95 mm² faz kesiti için basit S/2 oranının (47.5 mm²) altındadır. | TS HD 60364-5-54:2013 Çizelge 54.2 |
| `M-05` | **UYARI** | PE / Konsantrik Ekran Kesit Oranı | 3x(1x185/25ş mm2 XLPE) | S_faz=185 mm², Ekran/PE=25 mm² | Çizelge 54.2 >= 92.5 mm² (S/2) — 3x(1x185/25ş mm2 XLPE) kablosundaki 25 mm² ekran/PE kesiti, 185 mm² faz kesiti için basit S/2 oranının (92.5 mm²) altındadır. | TS HD 60364-5-54:2013 Çizelge 54.2 |
| `M-06` | **UYARI** | PE / Konsantrik Ekran Kesit Oranı | 3x95/16 mm² XLPE | S_faz=95 mm², Ekran/PE=16 mm² | Çizelge 54.2 >= 47.5 mm² (S/2) — 3x95/16 mm² XLPE kablosundaki 16 mm² ekran/PE kesiti, 95 mm² faz kesiti için basit S/2 oranının (47.5 mm²) altındadır. | TS HD 60364-5-54:2013 Çizelge 54.2 |
| `M-07` | **BILGI** | Zayıf Akım / Sinyal Ekipmanı ve Mahal Kapsama | Disiplin=KUVVETLI_AKIM | Ekipman: ZAYIF AKIM: 2, ZAYIF AKIM: 2, ZAYIF AKIM: 2, ZAYIF AKIM: 2 | Kapalı Mahal: 0 (0.0 m²) | momepy / Envanter Doğrulaması — Çizimden ayıklanan zayıf akım/sinyal ekipman sayımı ve momepy kapalı mahal morfolojisi özetidir. | İBB Raylı Sistemler & ISO/IEC 11801 |

## 2. Güç Bütçesi Mutabakatı ve Yükleme Cetvelleri
| Kaynak | Kurulu Güç (W) | Talep Faktörü | Talep Gücü (W) | Durum / Not |
| :--- | ---: | ---: | ---: | :--- |
| Alt Panolar Toplamı (0 pano) | **0** | - | 0 (bireysel toplam) | Daire eşzamanlılık önerisi: - |
| Ana Pano Şeması (`AT`) | BELİRSİZ | BELİRSİZ | BELİRSİZ (Hesap: BELİRSİZ) | UYGUN |

## 3. Isınma Kontrolü (Ib ≤ In ≤ Iz), PE Kesiti ve Seçicilik
- **Ana Pano (`BELİRSİZ`):** Kablo `1.8/3kV, 1x240 mm² XLPE` (BELİRSİZ) | Kesici: `BELİRSİZ` | KAKR: `BELİRSİZ` | Ib (380V / 400V): **BELİRSİZ / BELİRSİZ** | Iz (Proje / TS HD 60364 YAML): **BELİRSİZ / 599 A** | Sonuç: **BELİRSİZ (Veri Eksik)**

## 4. Gerilim Düşümü (%e) Denetimi (Formül Blokları + 0 Pano)
