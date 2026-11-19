# Metro / İstasyon Mühendislik Özet Raporu — `M09-S29_Atakoy`

> **İstasyon (Antet):** ATAKÖY İSTASYONU (69 pafta) | **Profil:** `ibb_metro` | **Taranan Pafta:** `99` (Elenen kopya: `4`) | **Bulgular:** Kritik `0`, Uyarı `0`, Uygun `2`

- **4 Disiplin Dağılımı:** Kuvvetli Akım: **28** | Topraklama: **8** | Zayıf Akım: **52** | Sinyal / SCADA: **11**
- **Tespit Edilen Birimler:** `mm`: 91, `m`: 5, `cm`: 3
- **Tekilleştirilmiş Güç Ekipmanları:** Trafo: `6×2000 kVA` | UPS: `3×60 kVA + 7×40 kVA + 2×20 kVA` | Topraklama Ringi: `5` | Tava Tipi: `202`

## 1. Denetim Bulguları
| ID | Önem | Kategori | Konum | Proje Değeri | Mevzuat / Beklenen | Standart |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `M-01` | **UYGUN** | VLD (Gerilim Sınırlama Cihazı) Varlığı | Topraklama Paftaları | 49 VLD referansı | VLD mevcut | EN 50122-1 Md. 6 |
| `M-02` | **UYGUN** | Ana Eşpotansiyel Bara (MEB) | Topraklama Sistemi | 4 MEB referansı | MEB >= 2 adet | EN 50122-1 / Metro Şartnamesi |
| `M-03` | **BILGI** | N-1 Trafo Yedekliliği | Güç Dağıtım / Trafo | 6×2000 kVA | N-1 Kalan=10000 kVA | Metro / Tesis Şartnamesi |

## 2. 4 Disiplin Bazlı Temiz Veri Özeti
| Disiplin | Pafta Sayısı | Toplam Ekipman | Topraklama Ring | Şema Düğümü | Öne Çıkan Veri Özeti |
| :--- | ---: | ---: | ---: | ---: | :--- |
| **Kuvvetli Akım** | 28 | 5,467 | 0 | 0 | Trafo: 6×2000 kVA; UPS: 3×60 kVA + 7×40 kVA + 2×20 kVA; Başlıca Tavalar: LV/100 (162x), WC/100 (118x), LV/500 (71x), LV/200 (68x) |
| **Topraklama** | 8 | 252 | 5 | 2,127 | Ring: 5 adet; VLD/MEB doğrulaması üst bulgularda |
| **Zayıf Akım** | 52 | 17,218 | 0 | 131 | Alt sistemler: AX-02(7), TL-02(6), TL-03(6), TL-04(6), TL-05(6), TL-08(6), TL-06(5), TL-07(4) |
| **Sinyal / SCADA** | 11 | 16,556 | 0 | 9,744 | SCADA / PLC / RTU / Sinyalizasyon paftaları |

## 3. Tespit Edilen Başlıca Kablo Tipleri (İlk 10)
| Kablo Tipi | Etiket Adedi |
| :--- | ---: |
| `UTP CAT6 LSZH` | 306 |
| `16mm² Cu` | 187 |
| `3x4 N2XH` | 162 |
| `3x2,5 N2XH` | 66 |
| `SF/UTP CAT 6 LS0H (HFFR)` | 56 |
| `3x2,5 N2XH FE180` | 52 |
| `120mm² Cu` | 37 |
| `3x1,5 NHXMH FE 180` | 37 |
| `3x2,5mm² N2XH FE180` | 28 |
| `3x1.5 N2XH` | 24 |

> *Tam 99 paftalık liste, tüm ekipman metrajı (`295` kalem) ve `202` tava tipi `M09-S29_Atakoy_denetim.xlsx` ve interaktif `M09-S29_Atakoy_denetim.html` dosyalarında yer almaktadır.*
