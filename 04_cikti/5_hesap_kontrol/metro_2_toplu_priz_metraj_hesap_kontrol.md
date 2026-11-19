# Mühendislik Hesap Denetimi ve Yeniden Hesaplama Raporu — `metro_2_toplu_priz_metraj.dxf`

**Birim:** `mm` | **Mevzuat Kaynağı:** `ibb_metro` | **Denetlenen Pano:** 1 + Ana Pano | **Kritik İhlal:** 0 | **Uyarı:** 0 | **Uygun:** 2

## 1. Kritik Bulgular & Mühendislik Hata Özeti
| Kod | Önem | Kategori | Konum | Projedeki Değer | Motor / Mevzuat Değerlendirmesi | Standart |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `M-01` | **UYGUN** | Yangın Güvenliği / Halojen-Free Kablo | Pafta Genel (7 tip, 46 adet) | 3x2,5 N2XH, 4x10 N2XH, 3x4 N2XH, 5x6 N2XH | LSZH / HFFR / XLPE / FE180 — Çizimde tespit edilen tüm güç/sinyal/data kabloları halojensiz (N2XH/N2XRH/XLPE/LS0H) sınıftadır. | NFPA 130 Md. 8.8 & BYKHY Md. 72, 83 |
| `M-02` | **UYGUN** | Yangına Dayanıklı (FE180/PH120) Besleme | Acil / Sinyalizasyon / Yangın | 3x2,5 N2XH FE180, 3x6 N2XH FE180 | FE180 / PH120 Zorunlu — Acil durum / sinyalizasyon / yangın hatlarında yangına dayanıklı (FE180) kablo kullanıldığı doğrulandı. | BYKHY Md. 72 & NFPA 130 |
| `M-03` | **BILGI** | Kablo Akım Taşıma Kapasitesi (Yöntem E & B.52.17) | Okunan 7 güç kablosu kesiti | 3x2,5 N2XH: Iz(E)=36A -> Gruplama(x0.70)=25.2A; 4x10 N2XH: Iz(E)=75A -> Gruplama(x0.70)=52.5A; 3x4 N2XH: Iz(E)=49A -> Gruplama(x0.70)=34.3A; 5x6 N2XH: Iz(E)=54A -> Gruplama(x0.70)=37.8A | Çizelge B.52.3/B.52.5 x 0.70 — Çizimdeki güç kabloları için delikli tava (Yöntem E) ve 3 devre gruplama katsayısı (0.70) uygulanmış tablo sınırları hesaplandı (kesitlerin gerçek yük akımı Ib bilgisi çizimde mevcutsa pano/şema adımında ayrıca denetlenir). | TS HD 60364-5-52:2014 |
| `M-04` | **BILGI** | Zayıf Akım / Sinyal Ekipmanı ve Mahal Kapsama | Disiplin=KUVVETLI_AKIM | Ekipman: ZAYIF AKIM: 2, ZAYIF AKIM: 2, ZAYIF AKIM: 2, GEÇİŞ / BİLET SİSTEMİ: 1 | Kapalı Mahal: 0 (0.0 m²) | momepy / Envanter Doğrulaması — Çizimden ayıklanan zayıf akım/sinyal ekipman sayımı ve momepy kapalı mahal morfolojisi özetidir. | İBB Raylı Sistemler & ISO/IEC 11801 |

## 2. Güç Bütçesi Mutabakatı ve Yükleme Cetvelleri
| Kaynak | Kurulu Güç (W) | Talep Faktörü | Talep Gücü (W) | Durum / Not |
| :--- | ---: | ---: | ---: | :--- |
| Alt Panolar Toplamı (1 pano) | **0** | - | 0 (bireysel toplam) | Daire eşzamanlılık önerisi: - |
| Ana Pano Şeması (`AT`) | BELİRSİZ | BELİRSİZ | BELİRSİZ (Hesap: BELİRSİZ) | UYGUN |

## 3. Isınma Kontrolü (Ib ≤ In ≤ Iz), PE Kesiti ve Seçicilik
- **Ana Pano (`BELİRSİZ`):** Kablo `4x10 N2XH` (BELİRSİZ) | Kesici: `BELİRSİZ` | KAKR: `BELİRSİZ` | Ib (380V / 400V): **BELİRSİZ / BELİRSİZ** | Iz (Proje / TS HD 60364 YAML): **BELİRSİZ / 71 A** | Sonuç: **BELİRSİZ (Veri Eksik)**

### 3A. Pano Bazlı Akım Taşıma, Kesici ve Koruma Tablosu (1 pano)
| Pano | Kurulu (W) | Talep (W) | Kablo | Kesici | KAKR | Ib Yazılı (A) | Ib Motor 400V (A) | Iz Yazılı / YAML (A) | Bulgu / Not |
| :--- | ---: | ---: | :--- | :--- | :--- | ---: | ---: | :--- | :--- |
| **-** | BELİRSİZ | BELİRSİZ | `-` | `YOK` | `-` | BELİRSİZ | BELİRSİZ | BELİRSİZ / BELİRSİZ | UYGUN |

## 4. Gerilim Düşümü (%e) Denetimi (Formül Blokları + 1 Pano)
