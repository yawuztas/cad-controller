# Mühendislik Hesap Denetimi Raporu — `bina_2_faruk_demir_10lu_elektrik.dxf`

> **Karar:** **REVİZYON GEREKLİ (KRİTİK İHLAL VAR)** | **Birim:** `cm` | **Profil:** `turkey_bina` | **Pano:** 57 + Ana Pano | **Kritik:** 7 | **Uyarı:** 12 | **Uygun:** 1

## 1. Kritik Bulgular ve Uyarı Özeti
| Önem | Konu | Konum | Projede Yazılı | Bizim Motor / Mevzuat | Standart |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **KRITIK** | Isınma / Aşırı Akım Koruması | Ana Besleme (AT) | In=320A (3x320A TMŞ), Iz_yazılı=274A (3x95+35N2XH) | In=320A > Iz=278A (İhlal) | TS HD 60364-4-43 Md. 433.1 |
| **KRITIK** | PE İletken Kesiti | Ana Kablo (AT) | 3x95+35N2XH (PE=35 mm²) | Min S_PE >= 47.5 mm² | TS HD 60364-5-54 Çizelge 54.2 |
| **KRITIK** | Yangın Güvenliği (BYKHY) | Kolon Şeması (KİLİTLİ BÖLME & Ortak Pano) | Yangın pompası hem KİLİTLİ BÖLME'de hem ortak panoda (30mA KAKR arkasında) 2 kez çizilmiş | KİLİTLİ BÖLME (AT girişi önünden bağımsız FE180 hat, 30mA KAKR'sız) | BYKHY Md. 74-84 |
| **KRITIK** | Gerilim Düşümü Formül Hatası | Gerilim Düşümü Tablosu (O-T / P4) | Yazılı %e_linye = %0.694 (Toplam %0.789) | Doğru 3-faz %e_linye = %0.116 (400V: %0.105) | EİTY Md. 57 |
| **KRITIK** | KAKR Akım Koordinasyonu | Kolon Şeması Çıkışları (M_14) | 3 kolda (Yabgın pom., hidrofor): KAKR < Sigorta (25A<32A) | I_n(KAKR) >= I_n(Koruma Sigortası) olmalı (veya KAKR kesiciyle aynı/üst akımda seçilmeli) | TS HD 60364-5-53 Md. 531.3 |
| **KRITIK** | Temel Topraklama Formül/Ölçü Kontrolü | TBL_001 | Ry=11.57 Ω, Rç=1.65 Ω, Re=1.44 Ω | CAD Schwarz Re=2.9319 Ω (Sverak 2.9321 Ω) | ETTMY Ek-N/Ek-P & IEEE Std 80 |
| **UYARI** | Paftalar Arası Kablo Çelişkisi | Kolon Şeması ↔ Gerilim Düşümü | Kolon şeması `3x95+35N2XH` vs GD hesabı `3x95+50NYY` | Tek ve tutarlı kesit/izolasyon tipi | EİTY & Proje Bütünlüğü |
| **UYARI** | Güç Bütçesi Çelişkisi | Pafta Anteti (TBL_017) ↔ Kolon Şeması | Antet: 553,490 W | Alt Panolar Toplamı: 533,490 W (Fark: +20,000 W) | Proje Tutarlılığı |
| **UYARI** | Talep Gücü / Diversite Yöntemi | Yükleme Cetveli (O-T / TBL_003) | Kurulu=18,560W -> Talep=9,024W (8kW 0,6/0,4) | Ortak motor yüklerinde (Asansör+Hidrofor+Pompa) konut 8kW kuralı uygulanmaz | EİTY Md. 57 / TEDAŞ Ortak Yükler |
| **UYARI** | Faz Yük Dengesizliği | Yükleme Cetveli (DT-55 / TBL_004) | R=4300W, S=4540W, T=5000W (%Δ=15.2%) | %Δ <= %15.0 | EİTY Md. 57 |
| **UYARI** | Eksik Şema Verisi | Kolon Şeması (DT-3, DT-4) | Kesici anma akımı yazısı YOK (yalnız 6kA AOS) | İlgili pano/devre çıkışında anma akımı (örn. 3x20A / 25A) belirtilmeli | Proje Çizim Bütünlüğü |
| **UYARI** | Kablo Akım Kapasitesi Hatası | Isınma Hesabı Tablosu (O-T) | Kablo `4X16` için Iz_yazılı=54 A | TS HD 60364-5-52 gerçek Iz=76 A | TS HD 60364-5-52 Çizelge B.52.3/5 |
| **UYARI** | Gerilim Düşümü Sınır Aşımı | Gerilim Düşümü Hesabı (Toplam %e) | Pafta Toplam = %2.36 (380/220V) | 400/230V: %2.14 / EİTY Aydınlatma Sınırı: <= %1.50 (Motor <= %3.0) | EİTY Md. 57 |
| **UYARI** | KAKR Zaman Seçiciliği | Ana Pano (AT) | 4x320A 300mA KAKR ('S' ibaresi yok) | Ana pano KAKR mutlaka 'S' (Selektif/Gecikmeli, Δt >= 40 ms) tip olmalı | TS HD 60364-5-53 Md. 536 |
| **UYARI** | Temel Topraklama Formül/Ölçü Kontrolü | Topraklama (TBL_001) | Ry=11.57 Ω, Rç=1.65 Ω, Re=1.44 Ω | CAD Schwarz Re=2.9319 Ω (Sverak 2.9321 Ω) | ETTMY Ek-N/Ek-P & IEEE Std 80 |
| **UYARI** | Aydınlatma Hesabı | Aydınlatma (İŞYERİ / TBL_002) | E=125 lx, Yansıtma=80-50-30, Z=14.26 | k=3.21, Z_motor=14.26 (15 adet), Önerilen E>=300 lx | TS EN 12464-1 |
| **UYARI** | Aydınlatma Hesabı | Aydınlatma (YATAK ODASI #1 / TBL_002) | E=50 lx, Yansıtma=80-50-30, Z=0.67 | k=0.80, Z_motor=0.67 (1 adet), Önerilen E>=100 lx | TS EN 12464-1 |
| **UYARI** | Aydınlatma Hesabı | Aydınlatma (YATAK ODASI #2 / TBL_002) | E=51 lx, Yansıtma=80-50-31, Z=0.69 | k=0.80, Z_motor=0.69 (1 adet), Önerilen E>=100 lx | TS EN 12464-1 |
| **UYGUN** | Temel Topraklama Sınır Kontrolü | Temel Topraklama (GND_01) | Yazılı Re=1.44 Ω | Motor CAD Hesabı Re=2.93 Ω <= 166.7 Ω | TS HD 60364-4-41 Md. 411.5.3 |

## 2. Güç Bütçesi ve Yükleme Cetvelleri (Proje ↔ Motor)
| Kalem | Projede Yazılı | Bizim Motor Hesabı | Durum |
| :--- | :--- | :--- | :--- |
| **Toplam Kurulu Güç** | Ana Pano: 533,490 W / Antet: 553,490 W | Alt Panolar (57 pano): **533,490 W** (Antet Farkı: 20,000 W) | ÇELİŞKİ / HATA VAR |
| **Toplam Talep Gücü** | 133,373 W (T.F.=0.25) | Hesap: **133,372 W** (Önerilen eşzamanlılık: 0.25) | ÇELİŞKİ / HATA VAR |

### 2A. Yükleme Cetvelleri Karşılaştırması (2 cetvel → 2 grup)
| Pano / Grup | Proje Toplam (W) | Motor Linye Toplam (W) | R / S / T / RST (W) | Faz Dengesizliği | Proje Talep (W) | Motor EİTY 8kW (W) | Durum |
| :--- | ---: | ---: | :--- | ---: | ---: | ---: | :--- |
| **O-T** | 18,560 | 18,560 | 280 / 540 / 240 / 17500 | 4.8% | 9,024 | 9,024 | KRİTİK İHLAL (BYKHY) |
| **DT-55** | 13,840 | 13,840 | 4300 / 4540 / 5000 / 0 | 15.2% | 7,136 | 7,136 | UYARI / İNCELEME GEREKLİ |

## 3. Isınma (Ib ≤ In ≤ Iz), PE Kesiti ve Şalt Koordinasyonu (Proje ↔ Motor)
| Parametre (Ana Pano) | Projede Yazılı | Bizim Motor Hesabı | Durum |
| :--- | :--- | :--- | :--- |
| **Ana Pano / Besleme Kablosu** | `AT` — `3x95+35N2XH` (50 m) | TS HD 60364-5-52 / 5-54 kontrolü | KRİTİK İHLAL |
| **Ana Kesici / KAKR** | `3x320A TMŞ` / `4x320A 300mA KAKR` | Ib ≤ In ≤ Iz & KAKR 'S' tip seçicilik | KRİTİK İHLAL |
| **İşletme Akımı (Ib)** | Projede Ayrı Yazılmamış / Tablo | **253.3 A** (380V) / **240.6 A** (400V) | KRİTİK İHLAL |
| **Akım Taşıma Kapasitesi (Iz)** | 274 A | **278 A** (TS HD 60364 YAML) | KRİTİK İHLAL |

### 3A. Alt Pano Özet Tablosu (57 pano → 31 grup; tüm panolar `.xlsx` ekindedir)
| Pano / Grup | Kurulu / Talep (W) | Kablo | Kesici | KAKR | Proje Ib (A) | Motor Ib 400V (A) | Proje / Motor Iz (A) | Bulgu / Not |
| :--- | ---: | :--- | :--- | :--- | ---: | ---: | :--- | :--- |
| **O-T** | 18,560 / 9,024 | `4X16` | `YOK` | `4x40A 30mA` | 22.85 | 16.28 | 54 / 76 | TABLO Iz HATALI (54A vs 76A); DÜŞÜK cosφ (0.6); LİNYE %e FORMÜL HATASI (Yazılı %0.694 vs Doğru %0.116); 40A->P2(32A) oran=1.25<1.60 |
| **IS-T** | 3,660 / 3,660 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 5.56 | 6.60 | 54 / 52 | Üst KAKR 'S' tip değil |
| **DT-1, DT-9** | 9,190 / 5,276 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 13.36 | 9.52 | 54 / 52 | DÜŞÜK cosφ (0.6); ANA BESLEME DAHİL %e>1.5% (1.52%); Üst KAKR 'S' tip değil |
| **DT-2, DT-5, DT-14** | 9,190 / 5,276 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 13.36 | 9.52 | 54 / 52 | DÜŞÜK cosφ (0.6); ANA BESLEME DAHİL %e>1.5% (1.51%); Üst KAKR 'S' tip değil |
| **DT-3, DT-4** | 9,190 / 5,276 | `4x6N2XH/6mm2 07Z1` | `YOK` | `4x25A 30mA` | 13.36 | 9.52 | 54 / 52 | ŞEMADA KESİCİ YAZISI EKSİK; DÜŞÜK cosφ (0.6) |
| **DT-6** | 9,190 / 5,276 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 13.36 | 9.52 | 54 / 52 | DÜŞÜK cosφ (0.6); ANA BESLEME DAHİL %e>1.5% (1.55%); Üst KAKR 'S' tip değil |
| **DT-7, DT-12, DT-15** | 9,190 / 5,276 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 13.36 | 9.52 | 54 / 52 | DÜŞÜK cosφ (0.6); ANA BESLEME DAHİL %e>1.5% (1.54%); Üst KAKR 'S' tip değil |
| **DT-8, DT-13** | 9,190 / 5,276 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 13.36 | 9.52 | 54 / 52 | DÜŞÜK cosφ (0.6); Üst KAKR 'S' tip değil |
| **DT-10** | 9,190 / 5,276 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 13.36 | 9.52 | 54 / 52 | DÜŞÜK cosφ (0.6); ANA BESLEME DAHİL %e>1.5% (1.57%); Üst KAKR 'S' tip değil |
| **DT-11** | 9,190 / 5,276 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 13.36 | 9.52 | 54 / 52 | DÜŞÜK cosφ (0.6); ANA BESLEME DAHİL %e>1.5% (1.59%); Üst KAKR 'S' tip değil |
| **DT-16** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 13.39 | 9.54 | 54 / 52 | DÜŞÜK cosφ (0.6); ANA BESLEME DAHİL %e>1.5% (1.58%); Üst KAKR 'S' tip değil |
| **DT-17, DT-22, DT-25, DT-34, DT-38 (5 pano)** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.57%); Üst KAKR 'S' tip değil |
| **DT-18** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.51%); Üst KAKR 'S' tip değil |
| **DT-19** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.55%); Üst KAKR 'S' tip değil |
| **DT-20, DT-27, DT-32, DT-35, DT-44, DT-48 (6 pano)** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.60%); Üst KAKR 'S' tip değil |
| **DT-21, DT-53** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.63%); Üst KAKR 'S' tip değil |
| **DT-23** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.53%); Üst KAKR 'S' tip değil |
| **DT-24, DT-28** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.54%); Üst KAKR 'S' tip değil |
| **DT-26, DT-39** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.62%); Üst KAKR 'S' tip değil |
| **DT-29** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.58%); Üst KAKR 'S' tip değil |
| **DT-30, DT-37, DT-42, DT-45, DT-54 (5 pano)** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.64%); Üst KAKR 'S' tip değil |
| **DT-31** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.66%); Üst KAKR 'S' tip değil |
| **DT-33** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.56%); Üst KAKR 'S' tip değil |
| **DT-36, DT-49** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.65%); Üst KAKR 'S' tip değil |
| **DT-40, DT-47, DT-52** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.67%); Üst KAKR 'S' tip değil |
| **DT-41** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.69%); Üst KAKR 'S' tip değil |
| **DT-43** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.59%); Üst KAKR 'S' tip değil |
| **DT-46** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.68%); Üst KAKR 'S' tip değil |
| **DT-50** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.70%); Üst KAKR 'S' tip değil |
| **DT-51** | 9,220 / 5,288 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 10.04 | 9.54 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (1.73%); Üst KAKR 'S' tip değil |
| **DT-55** | 13,840 / 7,136 | `4x6N2XH/6mm2 07Z1` | `3(20A)` | `4x25A 30mA` | 13.55 | 12.87 | 54 / 52 | ANA BESLEME DAHİL %e>1.5% (2.29%); 20A->P1(16A) oran=1.25<1.60; Üst KAKR 'S' tip değil |

## 4. Gerilim Düşümü (%e) Karşılaştırması (Proje ↔ Motor)
| Bölüm | Kablo | L (m) | P (W) | S (mm²) | Projede Yazılı %e | Motor 380/220V | Motor 400/230V | IEC Ek-G %e |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Ana Besleme (`FRM_001`) | `3x95+50NYY` | 50.0 | 133,373 | 95.0 | **0.87%** | 0.87% | 0.78% | 1.16% |
| Kolon Hattı (`FRM_002`) | `4x6N2XH/6mm2 07Z1` | 26.0 | 7,136 | 6.0 | **0.38%** | 0.38% | 0.35% | 0.46% |
| Linye Hattı (`FRM_003`) | `3x2,5NHXMH` | 15.0 | 2,500 | 2.5 | **1.11%** | 1.11% | 1.01% | 1.26% |
| **TOPLAM %e** | - | - | - | - | **2.36%** | **2.36%** | **2.14%** | - |

## 5. Temel Topraklama (R_E) Karşılaştırması (Proje ↔ Motor)
| Parametre | Projede Yazılı | Motor (Tablo Girdisi) | Motor (Gerçek CAD Geometrisi) |
| :--- | ---: | ---: | ---: |
| Temel Alanı A (m²) | 336.00 | 336.00 | **332.59** |
| Şerit Boyu L (m) | 105.00 | 105.00 | **131.63** (+filiz 8.91) |
| Eşdeğer Çap D (m) | 20.69 | 20.68 | **20.58** |
| Çubuk Direnci Rç (Ω) | 1.65 *(formül uyumsuz)* | 18.91 | **16.65** |
| Yatay / Temel Ry (Ω) | 11.57 *(formül uyumsuz)* | 3.37 | **3.19** |
| Bileşke Schwarz Re (Ω) | 1.44 | 3.12 | **2.93** |
| IEEE 80 Sverak Rg (Ω) | Projede Yok | 3.10 | **2.93** |
| TT Sınır (50V / IΔn) | <= 166.0 Ω | - | <= **166.67 Ω** (UYGUN) |

## 6. Aydınlatma Hesabı — Lümen Yöntemi (Proje ↔ Motor)
| Mahal | Boyut (m) | Proje (E / k / Z) | Motor (k / Z / Gerçekleşen lx) | Seçilen | Durum |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **İŞYERİ** | 11.4×11.1 (hm=1.75m) | 125 lx / 3.21 / 14.26 | 3.21 / 14.26 (15 ad.) / **131.5 lx** | `P 14x36 W` | TS EN 12464-1 tavsiyesi (300 lx) için E=125 lx düşük |
| **MUTFAK** | 4.0×2.0 (hm=1.75m) | 125 lx / 0.76 / 1.72 | 0.76 / 1.72 (2 ad.) / **145.7 lx** | `P 2x36 W` | UYGUN |
| **YATAK ODASI #1** | 2.7×2.9 (hm=1.75m) | 50 lx / 0.80 / 0.67 | 0.80 / 0.67 (1 ad.) / **74.4 lx** | `P 1x36 W` | TS EN 12464-1 tavsiyesi (100 lx) için E=50 lx düşük |
| **YATAK ODASI #2** | 2.7×2.9 (hm=1.75m) | 51 lx / 0.80 / 0.69 | 0.80 / 0.69 (1 ad.) / **74.4 lx** | `P 1x36 W` | TS EN 12464-1 tavsiyesi (100 lx) için E=51 lx düşük; Excel sağa sürükleme hatası: E=50->51 lx; Excel sağa sürükleme hatası: yansıtma 80-50-30->80-50-31 |

## 7. Şebeke Yük Akışı & IEC 60909 Kısa Devre (`pandapower`)
- **Özet:** 58 bara yakınsadı | **Maks. Bağıl %e:** `%0.47` | **3-Faz Kısa Devre Ik'' Aralığı:** `2.07 – 72.17 kA`
- **Not:** Trafo bilgisi çizimde yok; ana bara AG kaynak olarak modellenmiştir.
| Bara / Pano (Öncelikli) | Gerilim (p.u.) | Bağıl Düşüm (%e) | 3-Faz Kısa Devre Ik'' (kA) |
| :--- | ---: | ---: | ---: |
| **AT** | 1.0000 | %0.00 | 72.169 kA |
| **DT-55** | 0.9953 | %0.47 | 2.462 kA |
| **DT-51** | 0.9959 | %0.41 | 2.068 kA |
| **DT-50** | 0.9962 | %0.38 | 2.210 kA |
| **DT-41** | 0.9963 | %0.37 | 2.288 kA |
| **DT-46** | 0.9964 | %0.36 | 2.372 kA |
| **DT-40** | 0.9966 | %0.34 | 2.462 kA |
*Not: Toplam 58 baranın tamamı `.xlsx` rapor ekinde yer almaktadır.*

