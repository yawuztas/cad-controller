# Mühendislik Hesap Denetimi Raporu — `musa demir - Elektrik.dwg`

> **Karar:** **REVİZYON GEREKLİ (KRİTİK İHLAL VAR)** | **Birim:** `cm` | **Profil:** `turkey_bina` | **Pano:** 18 + Ana Pano | **Kritik:** 3 | **Uyarı:** 24 | **Uygun:** 1

## 1. Kritik Bulgular ve Uyarı Özeti
| Önem | Konu | Konum | Projede Yazılı | Bizim Motor / Mevzuat | Standart |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **KRITIK** | Yangın Güvenliği (BYKHY) | Kolon Şeması (KİLİTLİ BÖLME & Ortak Pano) | Yangın pompası hem KİLİTLİ BÖLME'de hem ortak panoda (30mA KAKR arkasında) 2 kez çizilmiş | KİLİTLİ BÖLME (AT girişi önünden bağımsız FE180 hat, 30mA KAKR'sız) | BYKHY Md. 74-84 |
| **KRITIK** | KAKR Akım Koordinasyonu | Kolon Şeması Çıkışları (M_16) | 3 kolda (M_16 kol (616459,4096236), M_16 kol (616639,4096236), O-T): KAKR < Sigorta (25A<32A) | I_n(KAKR) >= I_n(Koruma Sigortası) olmalı (veya KAKR kesiciyle aynı/üst akımda seçilmeli) | TS HD 60364-5-53 Md. 531.3 |
| **KRITIK** | Temel Topraklama Formül/Ölçü Kontrolü | Topraklama (TBL_001) | Ry=12.89 Ω, Rç=3.62 Ω, Re=2.83 Ω | CAD Schwarz Re=5.3689 Ω (Sverak 5.4569 Ω) | ETTMY Ek-N/Ek-P & IEEE Std 80 |
| **UYARI** | Paftalar Arası Kablo Çelişkisi | Kolon Şeması ↔ Gerilim Düşümü | Kolon şeması `3x50+25N2XH` vs GD hesabı `3x50+35NYY` | Tek ve tutarlı kesit/izolasyon tipi | EİTY & Proje Bütünlüğü |
| **UYARI** | Faz Yük Dengesizliği | Yükleme Cetveli (IS-T / TBL_002) | R=400W, S=820W, T=600W (%Δ=69.2%) | %Δ <= %15.0 | EİTY Md. 57 |
| **UYARI** | Faz Yük Dengesizliği | DT-1..DT-12, DT-14, DT-15 (14 pano) | R=4000W, S=3100W, T=2790W (%Δ=36.7%) | %Δ <= %15.0 | EİTY Md. 57 |
| **UYARI** | Faz Yük Dengesizliği | DT-13, DT-16 | R=4600W, S=6500W, T=4030W (%Δ=49.0%) | %Δ <= %15.0 | EİTY Md. 57 |
| **UYARI** | Talep Gücü / Diversite Yöntemi | Yükleme Cetveli (O-T / TBL_022) | Kurulu=22,240W -> Talep=10,496W (8kW 0,6/0,4) | Ortak motor yüklerinde (Asansör+Hidrofor+Pompa) konut 8kW kuralı uygulanmaz | EİTY Md. 57 / TEDAŞ Ortak Yükler |
| **UYARI** | Faz Yük Dengesizliği | Yükleme Cetveli (O-T / TBL_022) | R=1200W, S=1040W, T=2500W (%Δ=19.7%) | %Δ <= %15.0 | EİTY Md. 57 |
| **UYARI** | Kablo Akım Kapasitesi Hatası | Isınma Hesabı Tablosu (O-T) | Kablo `4X16` için Iz_yazılı=54 A | TS HD 60364-5-52 gerçek Iz=76 A | TS HD 60364-5-52 Çizelge B.52.3/5 |
| **UYARI** | Gerilim Düşümü Sınır Aşımı | Gerilim Düşümü Hesabı (Toplam %e) | Pafta Toplam = %2.22 (380/220V) | 400/230V: %2.01 / EİTY Aydınlatma Sınırı: <= %1.50 (Motor <= %3.0) | EİTY Md. 57 |
| **UYARI** | KAKR Zaman Seçiciliği | Ana Pano (AT) | 4x160A 300mA KAKR ('S' ibaresi yok) | Ana pano KAKR mutlaka 'S' (Selektif/Gecikmeli, Δt >= 40 ms) tip olmalı | TS HD 60364-5-53 Md. 536 |
| **UYARI** | Temel Topraklama Formül/Ölçü Kontrolü | Topraklama (TBL_001) | Ry=12.89 Ω, Rç=3.62 Ω, Re=2.83 Ω | CAD Schwarz Re=5.3689 Ω (Sverak 5.4569 Ω) | ETTMY Ek-N/Ek-P & IEEE Std 80 |
| **UYGUN** | Temel Topraklama Sınır Kontrolü | Temel Topraklama (GND_01) | Yazılı Re=2.83 Ω | Motor CAD Hesabı Re=5.37 Ω <= 166.7 Ω | TS HD 60364-4-41 Md. 411.5.3 |

## 2. Güç Bütçesi ve Yükleme Cetvelleri (Proje ↔ Motor)
| Kalem | Projede Yazılı | Bizim Motor Hesabı | Durum |
| :--- | :--- | :--- | :--- |
| **Toplam Kurulu Güç** | Ana Pano: 192,780 W / Antet: 192,780 W | Alt Panolar (18 pano): **192,780 W** (Antet Farkı: 0 W) | UYGUN |
| **Toplam Talep Gücü** | 75,184 W (T.F.=0.39) | Hesap: **75,184 W** (Önerilen eşzamanlılık: 0.37) | UYGUN |

### 2A. Yükleme Cetvelleri Karşılaştırması (18 cetvel → 4 grup)
| Pano / Grup | Proje Toplam (W) | Motor Linye Toplam (W) | R / S / T / RST (W) | Faz Dengesizliği | Proje Talep (W) | Motor EİTY 8kW (W) | Durum |
| :--- | ---: | ---: | :--- | ---: | ---: | ---: | :--- |
| **IS-T** | 1,820 | 1,820 | 400 / 820 / 600 / 0 | 69.2% | BELİRSİZ | 1,092 | UYARI / İNCELEME GEREKLİ |
| **DT-1..DT-12, DT-14, DT-15 (14 pano)** | 9,890 | 9,890 | 4000 / 3100 / 2790 / 0 | 36.7% | 5,556 | 5,556 | UYARI / İNCELEME GEREKLİ |
| **DT-13, DT-16** | 15,130 | 15,130 | 4600 / 6500 / 4030 / 0 | 49.0% | 7,652 | 7,652 | UYARI / İNCELEME GEREKLİ |
| **O-T** | 22,240 | 22,240 | 1200 / 1040 / 2500 / 17500 | 19.7% | 10,496 | 10,496 | KRİTİK İHLAL (BYKHY) |

## 3. Isınma (Ib ≤ In ≤ Iz), PE Kesiti ve Şalt Koordinasyonu (Proje ↔ Motor)
| Parametre (Ana Pano) | Projede Yazılı | Bizim Motor Hesabı | Durum |
| :--- | :--- | :--- | :--- |
| **Ana Pano / Besleme Kablosu** | `AT` — `3x50+25N2XH` (50 m) | TS HD 60364-5-52 / 5-54 kontrolü | UYGUN |
| **Ana Kesici / KAKR** | `3x160A TMŞ` / `4x160A 300mA KAKR` | Ib ≤ In ≤ Iz & KAKR 'S' tip seçicilik | UYGUN |
| **İşletme Akımı (Ib)** | Projede Ayrı Yazılmamış / Tablo | **142.8 A** (380V) / **135.7 A** (400V) | UYGUN |
| **Akım Taşıma Kapasitesi (Iz)** | 184 A | **179 A** (TS HD 60364 YAML) | UYGUN |

### 3A. Alt Pano Özet Tablosu (18 pano → 4 grup; tüm panolar `.xlsx` ekindedir)
| Pano / Grup | Kurulu / Talep (W) | Kablo | Kesici | KAKR | Proje Ib (A) | Motor Ib 400V (A) | Proje / Motor Iz (A) | Bulgu / Not |
| :--- | ---: | :--- | :--- | :--- | ---: | ---: | :--- | :--- |
| **O-T** | 22,240 / 8,880 | `4X16` | `YOK` | `4x25A 30mA` | 22.49 | 16.02 | 54 / 76 | TABLO Iz HATALI (54A vs 76A); DÜŞÜK cosφ (0.6); 25A->P1(16A) oran=1.56<1.60 |
| **IS-T** | 1,820 / 1,820 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 2.77 | 3.28 | 54 / 52 | Üst KAKR 'S' tip değil |
| **DT-1..DT-12, DT-14, DT-15 (14 pano)** | 9,890 / 5,556 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 14.07 | 10.02 | 54 / 52 | DÜŞÜK cosφ (0.6); 20A->P1(16A) oran=1.25<1.60; Üst KAKR 'S' tip değil |
| **DT-13, DT-16** | 15,130 / 7,652 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 19.38 | 13.81 | 54 / 52 | DÜŞÜK cosφ (0.6); 20A->P1(16A) oran=1.25<1.60; Üst KAKR 'S' tip değil |

## 4. Gerilim Düşümü (%e) Karşılaştırması (Proje ↔ Motor)
| Bölüm | Kablo | L (m) | P (W) | S (mm²) | Projede Yazılı %e | Motor 380/220V | Motor 400/230V | IEC Ek-G %e |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Ana Besleme (`FRM_001`) | `3x50+35NYY` | 50.0 | 75,184 | 50.0 | **0.93%** | 0.93% | 0.84% | 1.20% |
| Kolon Hattı (`FRM_002`) | `4x6N2XH/6mm2 07Z1` | 25.0 | 7,652 | 6.0 | **0.40%** | 0.39% | 0.36% | 0.48% |
| Linye Hattı (`FRM_003`) | `3x2,5NHXMH` | 12.0 | 2,500 | 2.5 | **0.89%** | 0.89% | 0.81% | 1.01% |
| **TOPLAM %e** | - | - | - | - | **2.22%** | **2.21%** | **2.01%** | - |

## 5. Temel Topraklama (R_E) Karşılaştırması (Proje ↔ Motor)
| Parametre | Projede Yazılı | Motor (Tablo Girdisi) | Motor (Gerçek CAD Geometrisi) |
| :--- | ---: | ---: | ---: |
| Temel Alanı A (m²) | 120.00 | 120.00 | **112.74** |
| Şerit Boyu L (m) | 44.00 | 44.00 | **46.50** (+filiz 8.03) |
| Eşdeğer Çap D (m) | 12.36 | 12.36 | **11.98** |
| Çubuk Direnci Rç (Ω) | 3.62 *(formül uyumsuz)* | 18.91 | **16.65** |
| Yatay / Temel Ry (Ω) | 12.89 *(formül uyumsuz)* | 6.32 | **6.32** |
| Bileşke Schwarz Re (Ω) | 2.83 | 5.47 | **5.37** |
| IEEE 80 Sverak Rg (Ω) | Projede Yok | 5.49 | **5.46** |
| TT Sınır (50V / IΔn) | <= 166.0 Ω | - | <= **166.67 Ω** (UYGUN) |

## 6. Aydınlatma Hesabı — Lümen Yöntemi (Proje ↔ Motor)
| Mahal | Boyut (m) | Proje (E / k / Z) | Motor (k / Z / Gerçekleşen lx) | Seçilen | Durum |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **MAHAL-1** | 9.0×12.0 (hm=1.75m) | 125 lx / 2.94 / 12.17 | 2.94 / 12.17 (13 ad.) / **133.5 lx** | `P 12x36 W` | UYGUN |
| **MAHAL-2** | 3.4×4.0 (hm=1.75m) | 50 lx / 1.05 / 1.00 | 1.05 / 1.00 (2 ad.) / **99.5 lx** | `P 1x36 W` | UYGUN |
| **MAHAL-3** | 2.5×4.0 (hm=1.75m) | 50 lx / 0.88 / 0.86 | 0.88 / 0.86 (1 ad.) / **58.3 lx** | `P 1x36 W` | UYGUN |

## 7. Şebeke Yük Akışı & IEC 60909 Kısa Devre (`pandapower`)
- **Özet:** 19 bara yakınsadı | **Maks. Bağıl %e:** `%0.49` | **3-Faz Kısa Devre Ik'' Aralığı:** `2.56 – 72.17 kA`
- **Not:** Trafo bilgisi çizimde yok; ana bara AG kaynak olarak modellenmiştir.
| Bara / Pano (Öncelikli) | Gerilim (p.u.) | Bağıl Düşüm (%e) | 3-Faz Kısa Devre Ik'' (kA) |
| :--- | ---: | ---: | ---: |
| **AT** | 1.0000 | %0.00 | 72.169 kA |
| **DT-13** | 0.9951 | %0.49 | 2.559 kA |
| **DT-16** | 0.9963 | %0.37 | 3.356 kA |
| **DT-14** | 0.9966 | %0.34 | 2.665 kA |
| **DT-9** | 0.9969 | %0.31 | 2.904 kA |
| **DT-10** | 0.9970 | %0.30 | 3.041 kA |
| **DT-15** | 0.9972 | %0.28 | 3.191 kA |
*Not: Toplam 19 baranın tamamı `.xlsx` rapor ekinde yer almaktadır.*

