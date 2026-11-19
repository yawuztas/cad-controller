# Mühendislik Hesap Denetimi Raporu — `bina_1_osman_yesildemir_elektrik.dxf`

> **Karar:** **REVİZYON GEREKLİ (KRİTİK İHLAL VAR)** | **Birim:** `cm` | **Profil:** `turkey_bina` | **Pano:** 1 + Ana Pano | **Kritik:** 2 | **Uyarı:** 1 | **Uygun:** 1

## 1. Kritik Bulgular ve Uyarı Özeti
| Önem | Konu | Konum | Projede Yazılı | Bizim Motor / Mevzuat | Standart |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **KRITIK** | Temel Topraklama Formül/Ölçü Kontrolü | TBL_001 | Ry=12.79 Ω, Rç=3.48 Ω, Re=2.73 Ω | CAD Schwarz Re=5.4093 Ω (Sverak 5.4993 Ω) | ETTMY Ek-N/Ek-P & IEEE Std 80 |
| **UYARI** | KAKR Zaman Seçiciliği | Ana Pano (AT) | 4x25A 300mA KAKR ('S' ibaresi yok) | Ana pano KAKR mutlaka 'S' (Selektif/Gecikmeli, Δt >= 40 ms) tip olmalı | TS HD 60364-5-53 Md. 536 |
| **UYGUN** | Temel Topraklama Sınır Kontrolü | Temel Topraklama (GND_01) | Yazılı Re=2.73 Ω | Motor CAD Hesabı Re=5.41 Ω <= 166.7 Ω | TS HD 60364-4-41 Md. 411.5.3 |

## 2. Güç Bütçesi ve Yükleme Cetvelleri (Proje ↔ Motor)
| Kalem | Projede Yazılı | Bizim Motor Hesabı | Durum |
| :--- | :--- | :--- | :--- |
| **Toplam Kurulu Güç** | Ana Pano: 12,360 W | Alt Panolar (1 pano): **12,360 W**  | UYGUN |
| **Toplam Talep Gücü** | 6,544 W (T.F.=BELİRSİZ) | Hesap: **BELİRSİZ** (Önerilen eşzamanlılık: 1.0) | UYGUN |

### 2A. Yükleme Cetvelleri Karşılaştırması (1 cetvel → 1 grup)
| Pano / Grup | Proje Toplam (W) | Motor Linye Toplam (W) | R / S / T / RST (W) | Faz Dengesizliği | Proje Talep (W) | Motor EİTY 8kW (W) | Durum |
| :--- | ---: | ---: | :--- | ---: | ---: | ---: | :--- |
| **D-T** | 12,360 | 12,360 | 4120 / 4000 / 4240 / 0 | 5.8% | 6,544 | 6,544 | UYGUN |

## 3. Isınma (Ib ≤ In ≤ Iz), PE Kesiti ve Şalt Koordinasyonu (Proje ↔ Motor)
| Parametre (Ana Pano) | Projede Yazılı | Bizim Motor Hesabı | Durum |
| :--- | :--- | :--- | :--- |
| **Ana Pano / Besleme Kablosu** | `AT` — `4x10NYY` (50 m) | TS HD 60364-5-52 / 5-54 kontrolü | UYGUN |
| **Ana Kesici / KAKR** | `3(25A) AOS` / `4x25A 300mA KAKR` | Ib ≤ In ≤ Iz & KAKR 'S' tip seçicilik | UYGUN |
| **İşletme Akımı (Ib)** | Projede Ayrı Yazılmamış / Tablo | **12.4 A** (380V) / **11.8 A** (400V) | UYGUN |
| **Akım Taşıma Kapasitesi (Iz)** | 74 A | **57 A** (TS HD 60364 YAML) | UYGUN |

### 3A. Alt Pano Özet Tablosu (1 pano → 1 grup; tüm panolar `.xlsx` ekindedir)
| Pano / Grup | Kurulu / Talep (W) | Kablo | Kesici | KAKR | Proje Ib (A) | Motor Ib 400V (A) | Proje / Motor Iz (A) | Bulgu / Not |
| :--- | ---: | :--- | :--- | :--- | ---: | ---: | :--- | :--- |
| **D-T** | 12,360 / 6,544 | `-` | `3(20A) AOS` | `4x25A 30mA` | BELİRSİZ | 11.81 | BELİRSİZ / BELİRSİZ | Üst(25A)->Pano(20A) oran=1.25<1.60; 20A->P1(16A) oran=1.25<1.60; Üst KAKR 'S' tip değil |

## 4. Gerilim Düşümü (%e) Karşılaştırması (Proje ↔ Motor)
| Bölüm | Kablo | L (m) | P (W) | S (mm²) | Projede Yazılı %e | Motor 380/220V | Motor 400/230V | IEC Ek-G %e |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Ana Besleme (`FRM_001`) | `4x10NYY` | 30.0 | 6,544 | 10.0 | **0.25%** | 0.24% | 0.22% | 0.27% |
| Linye Hattı (`FRM_002`) | `3x2,5NHXMH` | 6.0 | 2,500 | 2.5 | **0.45%** | 0.44% | 0.41% | 0.51% |
| **TOPLAM %e** | - | - | - | - | **0.70%** | **0.68%** | **0.63%** | - |

## 5. Temel Topraklama (R_E) Karşılaştırması (Proje ↔ Motor)
| Parametre | Projede Yazılı | Motor (Tablo Girdisi) | Motor (Gerçek CAD Geometrisi) |
| :--- | ---: | ---: | ---: |
| Temel Alanı A (m²) | 126.00 | 126.00 | **114.57** |
| Şerit Boyu L (m) | 46.00 | 46.00 | **44.63** (+filiz 6.64) |
| Eşdeğer Çap D (m) | 12.67 | 12.67 | **12.08** |
| Çubuk Direnci Rç (Ω) | 3.48 *(formül uyumsuz)* | 18.91 | **16.65** |
| Yatay / Temel Ry (Ω) | 12.79 *(formül uyumsuz)* | 6.12 | **6.38** |
| Bileşke Schwarz Re (Ω) | 2.73 | 5.32 | **5.41** |
| IEEE 80 Sverak Rg (Ω) | Projede Yok | 5.34 | **5.50** |
| TT Sınır (50V / IΔn) | <= 166.0 Ω | - | <= **166.67 Ω** (UYGUN) |

## 6. Aydınlatma Hesabı — Lümen Yöntemi (Proje ↔ Motor)
| Mahal | Boyut (m) | Proje (E / k / Z) | Motor (k / Z / Gerçekleşen lx) | Seçilen | Durum |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **MAHAL-1** | 4.0×3.2 (hm=1.75m) | 125 lx / 1.01 / 2.35 | 1.01 / 2.35 (3 ad.) / **159.4 lx** | `P 2x40 W` | UYGUN |
| **MAHAL-2** | 4.7×5.5 (hm=1.75m) | 100 lx / 1.45 / 4.79 | 1.45 / 4.79 (5 ad.) / **104.4 lx** | `N 5x40 W` | UYGUN |
| **MAHAL-3** | 4.0×4.5 (hm=1.75m) | 100 lx / 1.21 / 3.66 | 1.21 / 3.66 (4 ad.) / **109.3 lx** | `N 4x40 W` | UYGUN |
| **MAHAL-4** | 3.3×3.1 (hm=2.95m) | 50 lx / 0.55 / 1.15 | 0.55 / 1.15 (2 ad.) / **86.8 lx** | `P 1x40 W` | UYGUN |
| **MAHAL-5** | 4.1×4.0 (hm=1.75m) | 100 lx / 1.15 / 3.30 | 1.15 / 3.30 (4 ad.) / **121.2 lx** | `N 3x40 W` | UYGUN |

## 7. Şebeke Yük Akışı & IEC 60909 Kısa Devre (`pandapower`)
- **Özet:** 3 bara yakınsadı | **Maks. Bağıl %e:** `%0.49` | **3-Faz Kısa Devre Ik'' Aralığı:** `1.99 – 72.17 kA`
- **Not:** Trafo bilgisi çizimde yok; ana bara AG kaynak olarak modellenmiştir.
| Bara / Pano (Öncelikli) | Gerilim (p.u.) | Bağıl Düşüm (%e) | 3-Faz Kısa Devre Ik'' (kA) |
| :--- | ---: | ---: | ---: |
| **AT** | 1.0000 | %0.00 | 72.169 kA |
| **Linye Hattı** | 0.9951 | %0.49 | 1.991 kA |
| **Ana Besleme** | 0.9960 | %0.40 | 3.578 kA |

