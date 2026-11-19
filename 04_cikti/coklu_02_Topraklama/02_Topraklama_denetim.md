# Çoklu Pafta / İstasyon Mühendislik Raporu (`02_Topraklama`)

- **Kural Profili:** `ibb_metro`
- **Taranan Dosya:** `8` (Atlanan yedek/kopya: `0`)
- **Antet İstasyon/Proje Adları:** `{'29 EKİM CUMHURİYET İSTASYONU': 6, 'İHLAS YUVA İSTASYONU': 2}`
- **Topraklama Ringi Sayısı:** `3` | **Tava Tipi:** `7` | **Trafo (kVA):** `[2000.0, 2000.0, 1600.0, 1600.0, 1600.0, 1600.0]` | **UPS (kVA):** `[60.0, 60.0, 40.0, 40.0, 10.0, 10.0, 10.0, 10.0]`

## Denetim Bulguları
| ID | Şiddet | Kategori | Konum | Proje Değeri | Mevzuat / Beklenen | Standart |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| M-01 | UYARI | Pafta Antet Tutarlılığı | İstasyon Genel | 29 EKİM CUMHURİYET İSTASYONU (6 pafta), İHLAS YUVA İSTASYONU (2 pafta) | Tek ve tutarlı istasyon adı | CAD Pafta Standardı |
| M-02 | UYGUN | VLD (Gerilim Sınırlama Cihazı) Varlığı | Topraklama Paftaları | 5 VLD referansı | VLD mevcut | EN 50122-1 Md. 6 |
| M-03 | UYGUN | Ana Eşpotansiyel Bara (MEB) | Topraklama Sistemi | 4 MEB referansı | MEB >= 2 adet | EN 50122-1 / Metro Şartnamesi |
| M-04 | BILGI | N-1 Trafo Yedekliliği | Güç Dağıtım / Trafo | 2000 kVA + 2000 kVA + 1600 kVA + 1600 kVA + 1600 kVA + 1600 kVA | N-1 Kalan=8400 kVA | Metro / Tesis Şartnamesi |

## Pafta & Antet Özeti
| Dosya | Alt Klasör | Tespit Edilen Disiplin | Birim | İstasyon (Antet) | Sembol | Topraklama Ring | Kapalı Mahal (`momepy`) | Şema Düğümü |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: |
| AG-PRT-M09-S26-000-99-PS-17-A-T-2I-001-A.dwg |  | TOPRAKLAMA | m | İHLAS YUVA İSTASYONU | 4 | 1 | 13 | 0 |
| AG-PRT-M09-S26-000-99-PS-17-A-T-2I-002~008-A.dwg |  | TOPRAKLAMA | m | İHLAS YUVA İSTASYONU | 17 | 1 | 31 | 0 |
| AG-PRT-M09-S26-000-99-PS-17-A-T-2I-011-A.dwg |  | TOPRAKLAMA | cm | 29 EKİM CUMHURİYET İSTASYONU | 2 | 0 | 0 | 2094 |
| AG-PRT-M09-S26-BT0-00-PS-17-A-T-2I-001-A.dwg |  | TOPRAKLAMA | mm | 29 EKİM CUMHURİYET İSTASYONU | 0 | 0 | 8 | 0 |
| AG-PRT-M09-S26-BT0-01-PS-17-A-T-2I-001-A.dwg |  | TOPRAKLAMA | mm | 29 EKİM CUMHURİYET İSTASYONU | 42 | 0 | 20 | 0 |
| AG-PRT-M09-S26-CT0-03-PS-17-A-T-2I-001-A.dwg |  | TOPRAKLAMA | mm | 29 EKİM CUMHURİYET İSTASYONU | 73 | 0 | 18 | 0 |
| AG-PRT-M09-S26-CT0-2A-PS-17-A-T-2I-001-A.dwg |  | TOPRAKLAMA | mm | 29 EKİM CUMHURİYET İSTASYONU | 2 | 0 | 18 | 0 |
| AG-PRT-M09-S26-CT0-2B-PS-17-A-T-2I-001-A.dwg |  | TOPRAKLAMA | mm | 29 EKİM CUMHURİYET İSTASYONU | 130 | 1 | 13 | 0 |
