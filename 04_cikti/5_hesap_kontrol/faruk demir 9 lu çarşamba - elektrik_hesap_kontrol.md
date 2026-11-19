# Mühendislik Hesap Denetimi Raporu — `faruk demir 9 lu çarşamba - elektrik.dxf`

> **Karar:** **REVİZYON GEREKLİ (KRİTİK İHLAL VAR)** | **Birim:** `cm` | **Profil:** `turkey_bina` | **Pano:** 51 + Ana Pano | **Kritik:** 7 | **Uyarı:** 10 | **Uygun:** 1

## 1. Kritik Bulgular ve Uyarı Özeti
| Önem | Konu | Konum | Projede Yazılı | Bizim Motor / Mevzuat | Standart |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **KRITIK** | Isınma / Aşırı Akım Koruması | Ana Besleme (AT) | In=320A (3x320A TMŞ), Iz_yazılı=274A (3x95+35N2XH) | In=320A > Iz=278A (İhlal) | TS HD 60364-4-43 Md. 433.1 |
| **KRITIK** | PE İletken Kesiti | Ana Kablo (AT) | 3x95+35N2XH (PE=35 mm²) | Min S_PE >= 47.5 mm² | TS HD 60364-5-54 Çizelge 54.2 |
| **KRITIK** | Yangın Güvenliği (BYKHY) | Kolon Şeması (KİLİTLİ BÖLME & Ortak Pano) | Yangın pompası hem KİLİTLİ BÖLME'de hem ortak panoda (30mA KAKR arkasında) 2 kez çizilmiş | KİLİTLİ BÖLME (AT girişi önünden bağımsız FE180 hat, 30mA KAKR'sız) | BYKHY Md. 74-84 |
| **KRITIK** | Gerilim Düşümü Formül Hatası | Gerilim Düşümü Tablosu (O-T / P4) | Yazılı %e_linye = %0.694 (Toplam %0.790) | Doğru 3-faz %e_linye = %0.116 (400V: %0.105) | EİTY Md. 57 |
| **KRITIK** | KAKR Akım Koordinasyonu | Kolon Şeması Çıkışları (M_14) | 3 kolda (Yabgın pom., hidrofor): KAKR < Sigorta (25A<32A) | I_n(KAKR) >= I_n(Koruma Sigortası) olmalı (veya KAKR kesiciyle aynı/üst akımda seçilmeli) | TS HD 60364-5-53 Md. 531.3 |
| **KRITIK** | Temel Topraklama Formül/Ölçü Kontrolü | Topraklama (TBL_001) | Rç=1.81 Ω (Re=1.56 Ω) | Dwight Rç=18.91 Ω / CAD Schwarz Re=3.05 Ω | ETTMY Ek-N/Ek-P & IEEE Std 80 |
| **KRITIK** | Temel Topraklama Formül/Ölçü Kontrolü | Topraklama (TBL_001) | Ry=11.67 Ω (formül hatalı) | Laurent-Niemann Ry=3.42 Ω / CAD Re=3.05 Ω | ETTMY Ek-N/Ek-P & IEEE Std 80 |
| **UYARI** | Paftalar Arası Kablo Çelişkisi | Kolon Şeması ↔ Gerilim Düşümü | Kolon şeması `3x95+35N2XH` vs GD hesabı `3x95+50NYY` | Tek ve tutarlı kesit/izolasyon tipi | EİTY & Proje Bütünlüğü |
| **UYARI** | Güç Bütçesi Çelişkisi | Pafta Anteti (TBL_015) ↔ Kolon Şeması | Antet: 553,490 W | Alt Panolar Toplamı: 478,950 W (Fark: +74,540 W) | Proje Tutarlılığı |
| **UYARI** | Talep Gücü / Diversite Yöntemi | Yükleme Cetveli (O-T / TBL_003) | Kurulu=18,820W -> Talep=9,128W (8kW 0,6/0,4) | Ortak motor yüklerinde (Asansör+Hidrofor+Pompa) konut 8kW kuralı uygulanmaz | EİTY Md. 57 / TEDAŞ Ortak Yükler |
| **UYARI** | Eksik Şema Verisi | Kolon Şeması (DT-3, DT-4) | Kesici anma akımı yazısı YOK (yalnız 6kA AOS) | İlgili pano/devre çıkışında anma akımı (örn. 3x20A / 25A) belirtilmeli | Proje Çizim Bütünlüğü |
| **UYARI** | Kablo Akım Kapasitesi Hatası | Isınma Hesabı Tablosu (O-T) | Kablo `4X16` için Iz_yazılı=54 A | TS HD 60364-5-52 gerçek Iz=76 A | TS HD 60364-5-52 Çizelge B.52.3/5 |
| **UYARI** | Eksik Gerilim Düşümü Hesabı | Gerilim Düşümü (Ana Besleme / FRM_001) | Güç / %e boş bırakılmış (--,--) | Motor: 380V %0.87 / 400V %0.78 | EİTY Md. 57 |
| **UYARI** | Gerilim Düşümü Sınır Aşımı | Gerilim Düşümü Hesabı (Toplam %e) | Pafta Toplam = %1.29 (380/220V) | Motor: 380V %2.16 / 400V %1.95 / EİTY Aydınlatma <= %1.50 (Motor <= %3.0) | EİTY Md. 57 |
| **UYARI** | KAKR Zaman Seçiciliği | Ana Pano (AT) | 4x320A 300mA KAKR ('S' ibaresi yok) | Ana pano KAKR mutlaka 'S' (Selektif/Gecikmeli, Δt >= 40 ms) tip olmalı | TS HD 60364-5-53 Md. 536 |
| **UYARI** | Temel Topraklama Formül/Ölçü Kontrolü | Topraklama (TBL_001) | Tablo L=95.0 m, A=351.0 m² | CAD L=121.02 m, A=314.04 m² (Re=3.05 Ω) | ETTMY Ek-N/Ek-P & IEEE Std 80 |
| **UYARI** | Aydınlatma Hesabı | Aydınlatma (MAHAL-4 / TBL_002) | E=51 lx, Yansıtma=80-50-31, Z=0.63 | k=0.77, Z_motor=0.63 (1 adet) | TS EN 12464-1 |
| **UYGUN** | Temel Topraklama Sınır Kontrolü | Temel Topraklama (GND_01) | Yazılı Re=1.56 Ω | Motor CAD Hesabı Re=3.05 Ω <= 166.7 Ω | TS HD 60364-4-41 Md. 411.5.3 |

## 2. Güç Bütçesi ve Yükleme Cetvelleri (Proje ↔ Motor)
| Kalem | Projede Yazılı | Bizim Motor Hesabı | Durum |
| :--- | :--- | :--- | :--- |
| **Toplam Kurulu Güç** | Ana Pano: 478,950 W / Antet: 553,490 W | Alt Panolar (51 pano): **478,950 W** (Antet Farkı: 74,540 W) | ÇELİŞKİ / HATA VAR |
| **Toplam Talep Gücü** | BELİRSİZ (T.F.=BELİRSİZ) / Antet: 133,373 W | Hesap: **BELİRSİZ** (Önerilen eşzamanlılık: 0.27) | ÇELİŞKİ / HATA VAR |

### 2A. Yükleme Cetvelleri Karşılaştırması (1 cetvel → 1 grup)
| Pano / Grup | Proje Toplam (W) | Motor Linye Toplam (W) | R / S / T / RST (W) | Faz Dengesizliği | Proje Talep (W) | Motor EİTY 8kW (W) | Durum |
| :--- | ---: | ---: | :--- | ---: | ---: | ---: | :--- |
| **O-T** | BELİRSİZ | 18,820 | 0 / 0 / 0 / 0 | BELİRSİZ | 9,128 | 9,128 | KRİTİK İHLAL (BYKHY) |

## 3. Isınma (Ib ≤ In ≤ Iz), PE Kesiti ve Şalt Koordinasyonu (Proje ↔ Motor)
| Parametre (Ana Pano) | Projede Yazılı | Bizim Motor Hesabı | Durum |
| :--- | :--- | :--- | :--- |
| **Ana Pano / Besleme Kablosu** | `AT` — `3x95+35N2XH` (50 m) | TS HD 60364-5-52 / 5-54 kontrolü | KRİTİK İHLAL |
| **Ana Kesici / KAKR** | `3x320A TMŞ` / `4x320A 300mA KAKR` | Ib ≤ In ≤ Iz & KAKR 'S' tip seçicilik | KRİTİK İHLAL |
| **İşletme Akımı (Ib)** | 254.0 A | **253.3 A** (380V) / **240.6 A** (400V) | KRİTİK İHLAL |
| **Akım Taşıma Kapasitesi (Iz)** | 274 A | **278 A** (TS HD 60364 YAML) | KRİTİK İHLAL |

### 3A. Alt Pano Özet Tablosu (51 pano → 8 grup; tüm panolar `.xlsx` ekindedir)
| Pano / Grup | Kurulu / Talep (W) | Kablo | Kesici | KAKR | Proje Ib (A) | Motor Ib 400V (A) | Proje / Motor Iz (A) | Bulgu / Not |
| :--- | ---: | :--- | :--- | :--- | ---: | ---: | :--- | :--- |
| **O-T** | 18,820 / 9,128 | `4X16` | `YOK` | `4x40A 30mA` | 23.11 | 16.47 | 54 / 76 | TABLO Iz HATALI (54A vs 76A); DÜŞÜK cosφ (0.6); LİNYE %e FORMÜL HATASI (Yazılı %0.694 vs Doğru %0.116); 40A->P2(32A) oran=1.25<1.60 |
| **IS-T** | 4,320 / 4,320 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 6.56 | 7.79 | 54 / 52 | Üst KAKR 'S' tip değil |
| **DT-1, DT-2, DT-5..DT-12 (10 pano)** | 9,190 / 5,276 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 13.36 | 9.52 | 54 / 52 | DÜŞÜK cosφ (0.6); Üst KAKR 'S' tip değil |
| **DT-3, DT-4** | 9,190 / 5,276 | `4x6N2XH/6mm2 07Z1` | `YOK` | `4x25A 30mA` | 13.36 | 9.52 | 54 / 52 | ŞEMADA KESİCİ YAZISI EKSİK; DÜŞÜK cosφ (0.6) |
| **DT-13..DT-16 (4 pano)** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 13.39 | 9.54 | 54 / 52 | DÜŞÜK cosφ (0.6); Üst KAKR 'S' tip değil |
| **DT-17..DT-42 (26 pano)** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | Üst KAKR 'S' tip değil |
| **DT-43..DT-48 (6 pano)** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | BELİRSİZ | 9.54 | BELİRSİZ / 52 | Üst KAKR 'S' tip değil |
| **DT-49** | 13,870 / 7,148 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | BELİRSİZ | 12.90 | BELİRSİZ / 52 | Üst KAKR 'S' tip değil |

## 4. Gerilim Düşümü (%e) Karşılaştırması (Proje ↔ Motor)
| Bölüm | Kablo | L (m) | P (W) | S (mm²) | Projede Yazılı %e | Motor 380/220V | Motor 400/230V | IEC Ek-G %e |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Ana Besleme (`FRM_001`) | `3x95+50NYY` | 50.0 | BELİRSİZ | 95.0 | **BELİRSİZ** | 0.87% | 0.78% | 1.16% |
| Kolon Hattı (`FRM_002`) | `4x6N2XH/6mm2 07Z1` | 27.0 | 7,148 | 6.0 | **0.40%** | 0.40% | 0.36% | 0.48% |
| Linye Hattı (`FRM_003`) | `3x2,5NHXMH` | 12.0 | 2,500 | 2.5 | **0.89%** | 0.89% | 0.81% | 1.01% |
| **TOPLAM %e** | - | - | - | - | **1.29%** | **2.16%** | **1.95%** | - |

## 5. Temel Topraklama (R_E) Karşılaştırması (Proje ↔ Motor)
| Parametre | Projede Yazılı | Motor (Tablo Girdisi) | Motor (Gerçek CAD Geometrisi) |
| :--- | ---: | ---: | ---: |
| Temel Alanı A (m²) | 351.00 | 351.00 | **314.04** |
| Şerit Boyu L (m) | 95.00 | 95.00 | **121.02** (+filiz 8.01) |
| Eşdeğer Çap D (m) | 21.15 | 21.14 | **20.00** |
| Çubuk Direnci Rç (Ω) | 1.81 *(formül uyumsuz)* | 18.91 | **16.65** |
| Yatay / Temel Ry (Ω) | 11.67 *(formül uyumsuz)* | 3.42 | **3.33** |
| Bileşke Schwarz Re (Ω) | 1.56 | 3.16 | **3.05** |
| IEEE 80 Sverak Rg (Ω) | Projede Yok | 3.15 | **3.05** |
| TT Sınır (50V / IΔn) | <= 166.0 Ω | - | <= **166.67 Ω** (UYGUN) |

## 6. Aydınlatma Hesabı — Lümen Yöntemi (Proje ↔ Motor)
| Mahal | Boyut (m) | Proje (E / k / Z) | Motor (k / Z / Gerçekleşen lx) | Seçilen | Durum |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **MAHAL-1** | 12.0×10.2 (hm=1.75m) | 125 lx / 3.15 / 13.79 | 3.15 / 13.79 (14 ad.) / **126.9 lx** | `P 14x36 W` | UYGUN |
| **MAHAL-2** | 3.7×2.2 (hm=1.75m) | 125 lx / 0.79 / 1.75 | 0.79 / 1.75 (2 ad.) / **143.2 lx** | `P 2x36 W` | UYGUN |
| **MAHAL-3** | 2.5×2.9 (hm=1.75m) | 50 lx / 0.77 / 0.62 | 0.77 / 0.62 (1 ad.) / **80.4 lx** | `P 1x36 W` | UYGUN |
| **MAHAL-4** | 2.5×2.9 (hm=1.75m) | 51 lx / 0.77 / 0.63 | 0.77 / 0.63 (1 ad.) / **80.4 lx** | `P 1x36 W` | Excel sağa sürükleme hatası: E=50->51 lx; Excel sağa sürükleme hatası: yansıtma 80-50-30->80-50-31 |
| **MAHAL-5** | 5.0×5.0 (hm=1.75m) | 51 lx / 1.43 / 1.51 | 1.43 / 1.51 (2 ad.) / **67.7 lx** | `P 2x36 W` | UYGUN |

## 7. Şebeke Yük Akışı & IEC 60909 Kısa Devre (`pandapower`)
- **Özet:** 45 bara yakınsadı | **Maks. Bağıl %e:** `%0.40` | **3-Faz Kısa Devre Ik'' Aralığı:** `2.14 – 72.17 kA`
- **Not:** Trafo bilgisi çizimde yok; ana bara AG kaynak olarak modellenmiştir.
| Bara / Pano (Öncelikli) | Gerilim (p.u.) | Bağıl Düşüm (%e) | 3-Faz Kısa Devre Ik'' (kA) |
| :--- | ---: | ---: | ---: |
| **AT** | 1.0000 | %0.00 | 72.169 kA |
| **DT-36** | 0.9960 | %0.40 | 2.137 kA |
| **DT-35** | 0.9962 | %0.38 | 2.210 kA |
| **DT-27** | 0.9964 | %0.36 | 2.372 kA |
| **DT-26** | 0.9966 | %0.34 | 2.462 kA |
| **DT-37** | 0.9966 | %0.34 | 2.462 kA |
| **DT-41** | 0.9966 | %0.34 | 2.462 kA |
*Not: Toplam 45 baranın tamamı `.xlsx` rapor ekinde yer almaktadır.*

