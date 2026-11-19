# Metro / İstasyon Mühendislik Özet Raporu — `M09-S21_Ataturk_Mahallesi`

> **İstasyon (Antet):** ATATÜRK MAHALLESİ İSTASYONU (51 pafta) | **Profil:** `ibb_metro` | **Taranan Pafta:** `83` (Elenen kopya: `0`) | **Bulgular:** Kritik `0`, Uyarı `0`, Uygun `2`

- **4 Disiplin Dağılımı:** Kuvvetli Akım: **22** | Topraklama: **6** | Zayıf Akım: **50** | Sinyal / SCADA: **5**
- **Tespit Edilen Birimler:** `mm`: 77, `cm`: 4, `m`: 2
- **Tekilleştirilmiş Güç Ekipmanları:** Trafo: `2×2500 kVA + 6×2400 kVA + 6×1600 kVA` | UPS: `3×40 kVA + 5×10 kVA` | Topraklama Ringi: `10` | Tava Tipi: `161`

## 1. Denetim Bulguları
| ID | Önem | Kategori | Konum | Proje Değeri | Mevzuat / Beklenen | Standart |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `M-01` | **UYGUN** | VLD (Gerilim Sınırlama Cihazı) Varlığı | Topraklama Paftaları | 51 VLD referansı | VLD mevcut | EN 50122-1 Md. 6 |
| `M-02` | **UYGUN** | Ana Eşpotansiyel Bara (MEB) | Topraklama Sistemi | 5 MEB referansı | MEB >= 2 adet | EN 50122-1 / Metro Şartnamesi |
| `M-03` | **BILGI** | N-1 Trafo Yedekliliği | Güç Dağıtım / Trafo | 2×2500 kVA + 6×2400 kVA + 6×1600 kVA | N-1 Kalan=26500 kVA | Metro / Tesis Şartnamesi |

## 2. 4 Disiplin Bazlı Temiz Veri Özeti
| Disiplin | Pafta Sayısı | Toplam Ekipman | Topraklama Ring | Şema Düğümü | Öne Çıkan Veri Özeti |
| :--- | ---: | ---: | ---: | ---: | :--- |
| **Kuvvetli Akım** | 22 | 5,223 | 0 | 0 | Trafo: 2×2500 kVA + 6×2400 kVA + 6×1600 kVA; UPS: 3×40 kVA + 5×10 kVA; Başlıca Tavalar: LV/100 (1193x), WC/100 (1020x), LV/200 (654x), LV/500 (650x) |
| **Topraklama** | 6 | 214 | 10 | 0 | Ring: 10 adet; VLD/MEB doğrulaması üst bulgularda |
| **Zayıf Akım** | 50 | 16,856 | 0 | 806 | Alt sistemler: TL-11(7), AX-02(6), TL-03(5), TL-04(5), TL-05(5), TL-06(5), TL-08(5), TL-02(4) |
| **Sinyal / SCADA** | 5 | 1,865 | 0 | 722 | SCADA / PLC / RTU / Sinyalizasyon paftaları |

## 3. Tespit Edilen Başlıca Kablo Tipleri (İlk 10)
| Kablo Tipi | Etiket Adedi |
| :--- | ---: |
| `CAT 6` | 1044 |
| `CAT 6 SF/UTP LSOH` | 284 |
| `UTP CAT6 LSZH` | 257 |
| `16mm² Cu` | 188 |
| `2x1.5 NHXMH` | 109 |
| `3x2,5 N2XH FE180` | 96 |
| `3x4 N2XH` | 91 |
| `3x2,5 N2XH-J` | 64 |
| `3x1.5 N2XH` | 32 |
| `1x35mm² H07Z-R` | 23 |

> *Tam 83 paftalık liste, tüm ekipman metrajı (`400` kalem) ve `161` tava tipi `M09-S21_Ataturk_Mahallesi_denetim.xlsx` ve interaktif `M09-S21_Ataturk_Mahallesi_denetim.html` dosyalarında yer almaktadır.*
