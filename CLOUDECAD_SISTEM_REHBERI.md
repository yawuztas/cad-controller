# CloudeCAD v3.0 — Sistem Mimarisi, Kod Haritası ve Çalışma Prensipleri Ana Rehberi (SSOT)

> **Belge Türü:** Tek Doğruluk Kaynağı (Single Source of Truth - SSOT)  
> **Sürüm:** v3.0 Gold Release (Healer Katmanı Dahil)  
> **Tarih:** 01 Kasım 2026  
> **Kapsam:** CAD (DXF/DWG) Çizim Denetimi ve Kontrollü Onarım — Metro İstasyonları ve Bina Tesisat Projeleri (BIM/IFC entegrasyonu yol haritasındadır, aktif değildir)  
> **Microsoft Word Formatı:** `CLOUDECAD_SISTEM_REHBERI.docx`

---

## 1. Giriş ve Belgenin Amacı

Bu doküman, **CloudeCAD v3.0 CAD Odaklı (DXF/DWG) Elektrik ve Raylı Sistem Proje Denetim ve Onarım Platformunun** tüm mimarisini, veri modellerini, harici araç bağımlılıklarını, dosya ve fonksiyon ilişkilerini ve mühendislik algoritmalarını tek bir merkezde toplayan resmi mimari başvuru kaynağıdır.

### 📌 Yapay Zeka ve Geliştiriciler İçin Çalışma Protokolü
Gelecekteki her yeni konuşmada, her yapay zeka (YZ) oturumunda veya projeye dahil olan yeni mühendislerde **binlerce satırlık kod tabanını baştan sona tarama zorunluluğunu ortadan kaldırmak** hedeflenmiştir. Sisteme yeni bir kural, yeni bir CAD filtresi veya yeni bir hesaplama modülü eklendiğinde doğrudan bu rehber açılacak, mevcut durum doğrulanacak ve güncellemeler buraya işlenecektir.

---

## 2. Sistemin Temel Çalışma Mantığı ve 5 Mühendislik Prensibi

### 2.1. Sıfır Varsayım İlkesi (Zero-Assumption Engineering)
Bir elektrik projesinde çizimde açıkça yazmayan bir kablo kesiti (örn: 3x2.5), sigorta değeri (örn: 16A), cihaz gücü veya hat mesafesi **asla varsayılarak kesin hesaba dahil edilmez**. Sistem veri kaynağını (Data Source Provenance) dört seviyede izler:
- `EXPLICIT` (Güven: 1.0): Çizimdeki blok özniteliğinden (ATTRIB), kablo etiketinden veya tablodan birebir okundu.
- `PARTIAL_EXPLICIT` (Güven: 0.85): Sembol adı veya katmandan çıkarıldı (örn: 'LED_36W' bloğundan 36W alınması).
- `ESTIMATED_DEFAULT` (Güven: 0.70): Çizimde güç yazılmadığı için kural paketindeki standart linye gücü kullanıldı. Rapor Güven Seviyesi `MUHTEMEL (TAHMİNİ YÜK)` olarak işaretlenir.
- `MISSING` (Güven: 0.0): Kablo kesiti veya güzergah çizimde hiç yok. Otomatik kesit atanmaz; devre `VERİ_YETERSİZ` statüsüne alınır ve Belirsizlik Listesine (`UncertaintyItem`) eklenir.

### 2.2. Kanıta Dayalı Sembol Triyajı (Evidence-Based Symbol Triage)
AutoCAD projelerindeki anonim bloklar (`A$C...`, `*U...` vb.) doğrudan silinmez. `SymbolTriage` motoru her blok için 4 kanıt katmanını inceler:
1. **Mimari Kanıt:** Blok mimari XREF içinde veya MOBILYA/TEFRIS katmanında ve yakınında hiçbir elektrik sembolü/yazısı yoksa `IGNORED_ARCHITECTURAL` olarak filtrelenir ve raporda sayısal olarak özetlenir.
2. **Elektrik Katmanı Kanıtı:** Blok elektrik katmanındaysa (`E-POWER`, `00-AYDINLATMA` vb.) veya yakın çevresinde (yakın elektrik sembolü için 1000, yakın elektrik yazısı için 600 çizim birimi) elektrik sembolü/etiketi varsa silinmez; `UNCERTAIN_ELECTRICAL` statüsüne alınarak mühendis incelemesine sunulur.
3. **Kanıtsızlık Durumu:** Ne mimari ne de elektrik kanıtı bulunamayan bloklar `UNCLASSIFIED` statüsünde Belirsizlik Listesinde tutulur.
4. **Çelişki Yönetimi:** Bir blok hem mimari katmanda olup hem de bir aydınlatma armatürünün tam yanındaysa elektrik izi ağır basar ve blok asla silinmez.

### 2.3. Kademeli Eşleştirme (Graduated / Tiered Matching)
Raylı sistem ve büyük bina projelerinde kuvvetli akım dağıtım panoları ile topraklama paftaları, kablo kanalları ve kolon şemaları arasında üç kademeli eşleştirme uygulanır:
- **Tier 1 (Birebir & Normalize Eşleşme):** Pano etiketinin normalize hali topraklama etiketleri veya parçalarıyla birebir eşleşir (örn: `S19MCC301 == S19MCC301`). Güven: 1.0 (KESİN).
- **Tier 2 (Çekirdek Kod & Alt Parça Ayrıştırma):** Topraklama paftasındaki kompozit bağlantı etiketleri (örn: `TS19LVS401/S19MCC301/01`) alt bileşenlerine parçalanır; panonun çekirdek kodu (`MCC301`, `LVS401`, `İAP-E/301`) ile eşleştirilir. Güven: 0.85-0.90 (YÜKSEK).
- **Tier 3 (Kat / Mahal ECB İrtibatı):** Pano kodunun mahal numarası ile o katın Eşpotansiyel Barası (örn: `S19/ECB/051`) mahal bazında eşleştirilir. Güven: 0.80.

### 2.4. Şiddetin Kanıta Bağlanması (Evidence-Based Severity & Scope Handling)
Denetim motoru girdi kapsamı sınırlılığı ile gerçek mühendislik hatalarını birbirinden ayırır:
- **Durum A (Kısmi Set Koruması):** Kullanıcı 5 paftalık kısmi bir set yüklediğinde, kuvvetli akım panosunun bulunduğu katın `PS-17` topraklama paftası analiz setine hiç verilmemişse bu bir tasarım hatası değil, girdi kapsamı sınırlılığıdır. Asla `CRITICAL` veya `WARNING` üretilmez; `UncertaintyItem` (`UNC-GRND-SHEET-MISSING-...`) üretilerek durum `İNCELEME_GEREKLİ` (%50 güven) olarak işaretlenir.
- **Durum B (Mevcut Paftada Bulunamama):** O kata ait topraklama paftası analiz setinde mevcut olmasına rağmen panonun topraklama irtibat kodu bulunamıyorsa; isimlendirme varyasyonu ihtimali nedeniyle bulgu `CRITICAL` değil, `WARNING` (Güven: %70, MUHTEMEL) olarak üretilir.
- **Durum C (Doğrudan Standart İhlali):** Açıkça çizilmiş ve kanıtlanmış kural ihlallerinde (örn: TS HD 60364-4-43 Madde 433.1 uyarınca 4x4 mm² kabloya 32A sigorta ve 25A KAK takılması) bulgu `CRITICAL` (%100 KESİN) olarak raporlanır.

### 2.5. İstasyon Kodu ve Antet Hiyerarşisi
Öncelik Sırası: `1. Klasör Adı (M09-S24) > 2. Pafta Dosya Adı (AG-...-S24-...) > 3. DWG İçi Blok/Antet Metinleri`. Dosya adı S24 olduğu halde antette S28 Mimar Sinan yazıyorsa istasyon S24 kabul edilir ve `REC-STATION-TITLE-MISMATCH` mühendislik uyarısı üretilir.

---

## 3. Kullanılan Harici Programlar ve Sistem Bağımlılıkları

| Harici Araç / Çevre | Sistemdeki Yolu / Türü | Çalışma Mantığı ve Entegrasyonu |
| :--- | :--- | :--- |
| **AutoCAD Core Console** (`accoreconsole.exe`) | `C:\Program Files\Autodesk\AutoCAD 20XX\accoreconsole.exe` | Autodesk'in GUI'siz konsol motorudur. Script üzerinden `FILEDIA 0 -> _AUDIT _Y -> _DXFOUT dosya 16 -> _QUIT _Y` komut dizisini çalıştırır. Bozuk nesneleri onararak temiz ASCII DXF üretir. |
| **AutoCAD COM Automation** (`win32com.client`) | `AutoCAD.Application` ActiveX / COM | Core Console bulunamadığında arka planda görünmez (`Visible=False`) bir AutoCAD açarak Audit ve DXFOUT uygular. |
| **Merkezi DXF Önbelleği** (`.dxf_cache/`) | `D:\autocad projesi\.dxf_cache` | `{safe_stem}_{st_size}_{st_mtime}.dxf` hash formatında çalışır. Dosya sonundaki `EOF` ve `ENDSEC` kontrolleri ile yarım kalmış dosyalar otomatik tespit edilip baştan onarılır. |
| **Python 3.11 Sanal Ortamı** (`venv`) | `D:\autocad projesi\venv` | İzole çalışma ortamı. Tüm CLI komutları ve pytest testleri bu sanal ortamda koşar. |

---

## 4. Kullanılan Python Kütüphaneleri ve Fonksiyonları

| Kütüphane | Sürüm | İçe Aktarıldığı Modüller | Mühendislik Fonksiyonu ve Rolü |
| :--- | :--- | :--- | :--- |
| `ezdxf` | >=1.3.0 | `core/cad/reader.py`, `core/topology/route_builder.py` | AutoCAD DXF parsing; INSERT, LINE, LWPOLYLINE, TEXT, MTEXT, ATTRIB nesnelerini okuma. Not: `dxf_converter.py` ezdxf kullanmaz; accoreconsole/COM subprocess çalıştırır. |
| `shapely` | >=2.0.0 | `core/cad/geometry.py`, `core/cad/frame_detector.py`, `core/cad/triage.py` | 2D poligon kesişimleri, Bounding Box, iç içe pafta sınırları ve semboller arası mesafe ölçümü. |
| `networkx` | >=3.3 | `core/topology/route_builder.py`, `core/topology/circuit_resolver.py` | Devre topolojisi ve kablo güzergahları için graf teorisi. Minimum Spanning Tree (MST) kablo boyu hesabı. |
| `python-docx` | >=1.2.0 | `tools/generate_system_guide.py`, `legacy/*/docx_reporter.py` | Microsoft Word (.docx) formatında resmi denetim raporları ve kılavuz dokümantasyon üretimi. |
| `openpyxl` & `xlrd` | >=3.1.0, >=2.0.1 | `legacy/yukleme_cetveli`, `legacy/topraklama_motoru` | Excel yükleme cetvelleri (.xlsx/.xls) okuma — yalnızca v1.0 legacy modüller. **v2.0 çekirdek motoru Excel okumaz; tüm linye verisi çizimden alınır.** |
| `numpy` | >=1.26.0 | `legacy/superpose_motoru` | Süperpoze çakışma analizinde sayısal matrisler (legacy). `electrical_calc.py` saf Python'dır. |
| `matplotlib` | >=3.9.0 | `legacy/superpose_motoru`, `legacy/topraklama_motoru` | Koordinasyon planları, süperpoze çakışma haritaları ve redline PNG görselleştirmeleri (legacy). |
| `PyYAML` | >=6.0 | `core/rules/rule_engine.py` | YAML kural paketlerinin (turkey_bina/ibb_metro) yüklenmesi; yönetmelik eşikleri koddan ayrı tutulur. |
| `pywin32` | >=306 | `common/dxf_converter.py` | Windows ActiveX ve AutoCAD COM Automation arayüzü kontrolü. |
| `pytest` | >=9.1.0 | `tests/test_reference_projects.py` | 13 Altın Referans Testinin deterministik ve otomatik doğrulanması (denetim + healer + regresyon). |

---

## 5. Mimari Kod Haritası (Hangi Dosya Nerede, Neye Bağlı?)

```text
D:\autocad projesi\
├── cloudecad.py                      <- MERKEZİ GİRİŞ NOKTASI (Unified CLI, Interactive Menu, Watch Mode)
├── batch_inspector.py                <- Toplu Proje Denetim Köprüsü (Klasör İzleme & Tarama)
├── cloudecad.bat                     <- Hızlı Başlatıcı (UTF-8 güvenli venv sarmalayıcısı)
├── otomatik_denetim.bat              <- Tek Tıkla Toplu Denetim / Watch Servisi Menüsü
├── tools/
│   ├── generate_system_guide.py      <- BU REHBERİ DERLEYEN BETİK (docx + md tek komutla yenilenir)
│   ├── field_run_healer.py           <- SAHA İNDİRİM: gerçek paftalarda Healer zinciri (v3.0)
│   ├── review_station.py             <- ONAY İSTASYONU: FastAPI + kural bazlı toplu triyaj (v3.0)
│   └── compose_delivery.py           <- COMPOSER: DXF→DWG + teslim paketi; başarısız olursa COM ile orijinal DWG üzerinden onarır (v3.0)
├── jobs/                             <- İş kabul/üretim klasörü (JOB-YYYY-*; plans/output/redline/delivery)
├── CLOUDECAD_SISTEM_REHBERI.docx     <- RESMİ SİSTEM MİMARİSİ VE ÇALIŞMA PRENSİPLERİ REHBERİ (WORD)
├── CLOUDECAD_SISTEM_REHBERI.md       <- SİSTEM REHBERİ (MARKDOWN KOPYASI)
├── tests/
│   └── test_reference_projects.py    <- 13 ADET GOLD-STANDARD BİRİM, DENETİM VE HEALER TESTİ
├── lispkodlar/                       <- AutoCAD Üretim Hızlandırma LISP Araçları (kullanıcı aracı)
├── ornekprojeler/                    <- Tekil Örnek DWG Girdileri (--file modu)
├── incelenecek projeler/             <- Toplu Denetim Girdi Klasörü (--scan / --watch)
├── projelerin inceleme sonuçları/    <- Üretilen Denetim Raporları (varsayılan çıktı klasörü)
├── raporlar/                         <- Proje Onay Evrakları & Yükleme Cetvelleri (arşiv)
├── ErrorReports/                     <- Çökme tanılama kayıtları
├── cloudecadprogramı/
│   ├── requirements.txt              <- Python Paket Bağımlılıkları
│   ├── kur.bat                       <- Sanal Ortam + Paket Kurulum Betiği
│   ├── common/
│   │   ├── dxf_converter.py          <- accoreconsole / COM DWG->DXF Dönüştürücü ve .dxf_cache Yöneticisi
│   │   ├── com_dwgs.py               <- COM tabanlı DWG Düzeltici (ezdxf yazımı AutoCAD'i çökertirse yedek yol)
│   │   ├── universal_cad_reader.py   <- Geriye Dönük Uyumluluk Sarmalayıcısı (-> core/cad/reader.py)
│   │   └── station_audit_engine.py   <- Geriye Dönük Uyumluluk Sarmalayıcısı (-> core/engine.py)
│   ├── core/
│   │   ├── engine.py                 <- ORKESTRASYON MOTORU (UnifiedAuditEngine; StationAuditEngine takma adı)
│   │   ├── cad/
│   │   │   ├── reader.py             <- UniversalCADReader (DXF -> DrawingSceneGraph + Handle Provenance)
│   │   │   ├── cad_safety.py         <- CADSafetyGuard & UnitScaleResolver (XREF, Block Def, CTB, INSUNITS, MTEXT)
│   │   │   ├── frame_detector.py     <- FrameDetector (İç İçe Paftalar, Antetler, Kat Planı Bölgeleri)
│   │   │   ├── triage.py             <- SymbolTriage (Kanıta Dayalı Anonim Blok ve Sembol Triyajı)
│   │   │   ├── classifier.py         <- Sembol Sınıflandırıcı ve Lejant Analizi
│   │   │   └── geometry.py           <- Shapely 2D Geometri ve Uzaysal İndeksleme Yardımcıları
│   │   ├── healer/                   <- v3.0 OTOMATİK ONARIM, OPTİMİZASYON VE YENİDEN ÜRETİM MOTORU
│   │   │   ├── layer_doctor.py       <- Modül 1: LayerAndBlockDoctor (Katman Standardizasyonu & Mimari Kilit)
│   │   │   ├── wire_healer.py        <- Modül 2: TopologicalWireHealer (4 Şartlı Stitch, Snap & Overkill)
│   │   │   ├── electrical_optimizer.py <- Modül 3: ElectricalAutoOptimizer (ASBUILT/DESIGN & Re-Verify)
│   │   │   └── table_generator.py    <- Modül 4: CADTableGenerator (DWG Yükleme Cetveli & .xlsx Üretici)
│   │   ├── calculators/
│   │   │   └── electrical_calc.py    <- Elektrik Mühendisliği Hesaplayıcıları (Iz, e%, Faz Dengesi, PE Kesit)
│   │   ├── model/
│   │   │   ├── entities.py           <- CAD Varlık Modelleri (DrawingSceneGraph, PlacedSymbol, TextToken...)
│   │   │   └── audit.py              <- Denetim & Rapor Modelleri (StationAuditReport, AuditFinding...)
│   │   ├── reconciliation/
│   │   │   └── cross_sheet_engine.py <- ÇAPRAZ MUTABAKAT MOTORU (Plan vs Tablo, Pano vs Topraklama PS-17)
│   │   ├── rules/
│   │   │   ├── rule_engine.py        <- Dinamik Kural Paketi Yöneticisi ve TS HD 60364-5-52 Tabloları
│   │   │   └── packs/
│   │   │       ├── turkey_bina.yaml  <- Türkiye Bina & Tesis Elektrik Yönetmeliği Kural Paketi
│   │   │       └── ibb_metro.yaml    <- İBB Raylı Sistemler As-Built Elektrik Şartnamesi Paketi
│   │   ├── topology/
│   │   │   ├── circuit_resolver.py   <- Mantıksal Linye ve Devre Çözümleyici
│   │   │   └── route_builder.py      <- Fiziksel Kablo Güzergahı ve Ağaç Oluşturucu
│   │   └── reporters/
│   │       ├── markdown_reporter.py  <- Markdown (.md) Formatında Mühendislik Raporu Üreteci
│   │       └── json_reporter.py      <- JSON Formatında Tam Yapılandırılmış Denetim Verisi Üreteci
│   └── legacy/                       <- v1.0 Eski İzole Modüller (Referans & Arşiv Amaçlı)
└── .dxf_cache/                       <- Dönüştürülmüş ve Onarılmış DXF Dosyaları Önbelleği
```

---

## 6. Beş Çekirdek Denetim Modülünün İşleyişi

1. **Modül 1 — Kuvvetli Akım ve Pano Faz Yük Dengesi:**
   - Kat planlarındaki linyeler çizimden (DXF) toplanır. Not: v2.0 çekirdek motoru Excel okumaz; openpyxl/xlrd yalnız legacy modüllerdedir.
   - Pano bazında faz yük dengesizliği: `Δ% = ((I_max - I_min) / I_max) * 100` formülüyle denetlenir. Sınırlar aktif kural paketinden okunur: İBB metro paketi %15 Uyarı / **%20 Kritik**; bina paketi %15 Uyarı / %25 Kritik.
   - Kablo akım taşıma kapasitesi ($I_z$) ve gerilim düşümü hesaplanır.

2. **Modül 2 — Paftalar Arası Çapraz Mutabakat:**
   - Plan vs Metraj Tablosu: Kuvvetli akım planındaki (PS-11) kablo etiketleri ile tablodaki satırlar karşılaştırılır (`REC-TBL-OMIT`).
   - Pano vs Topraklama: Dağıtım panoları ile topraklama paftaları (PS-17, GN-14) kademeli eşleştirmeye tabi tutulur.

3. **Modül 3 — Zayıf Akım 11 Alt Sistem Analizi:**
   - `AX-02` Yangın Algılama ve `TL-02..TL-11` alt sistemleri pafta dosya adından dinamik tanınır; harita M09 hattı DXF içerik analiziyle doğrulanmıştır: TL-02 LAN/F.O., TL-03 Telefon/SOS, TL-04 TETRA/Anten, TL-05 Anons (PA/VA), TL-06 CCTV, TL-07 Saat, TL-08 Kartlı Geçiş, TL-09 SCADA, TL-10 Yolcu Bilgilendirme (PIS), TL-11 Sistem Odası Rack.
   - Kolon şeması ile kat planı sembol sayıları karşılaştırılır.
   - CAT6 kablolarda 90 metre sınır kontrolü, acil hatlarda FE180 yangına dayanıklı kablo kontrolü yapılır.

4. **Modül 4 — Topraklama ve Tava Kapsamı:**
   - Eşpotansiyel Baralar (`S19/ECB/...`), Trafo/Pano bağlantıları (`TS19...`), Kablo tavaları ve merdiven metrajları özetlenir.

5. **Modül 5 — Belirsizlik Listesi ve Güven Analizi (Uncertainty Review List):**
   - Fonksiyonu kanıtlanamayan bloklar (`UNC-SYM-...`), kesiti yazılmamış linyeler (`UNC-MISSING-CABLE-...`) ve paftası eksik panolar (`UNC-GRND-SHEET-MISSING-...`) raporda mühendise sunulur.

---

## 6B. v3.0 Onarım ve Üretim Hattı (Healer + Onay İstasyonu + Composer)

Akış: **Saha Koşumu → Onay İstasyonu → Composer.**

1. **Healer Katmanı:** `core/healer/` — LayerAndBlockDoctor, TopologicalWireHealer (4 şartlı stitch), ElectricalAutoOptimizer (ASBUILT/DESIGN frenli), CADTableGenerator (DWG cetveli + .xlsx). Ortak kalkan: `core/cad/cad_safety.py`.
2. **Saha Koşumu:** `tools/field_run_healer.py` — zinciri gerçek paftalarda koşar; temiz DXF + imzalı defter + redline üretir. Saha kanıtı: 7 S19 paftası, 58.000+ korunan varlık, %141,7 dengesizlik reçetesi.
3. **Onay İstasyonu:** `tools/review_station.py` — kural bazlı toplu triyaj, tekil onay/ret, statü koruması, redline; her karar SHA-256 imzalı deftere yazılır (kilit + atomik yazma).
4. **Composer:** `tools/compose_delivery.py` — onaylı DXF → DWG 2018 + teslim paketi. Kademeli dönüşüm: accoreconsole → SPLINE temizliği → **COM onarımı** (`common/com_dwgs.py`; ezdxf yazımının AutoCAD 2027'yi çökerttiği paftalar için kalıcı çözüm, düzenlemeler orijinal DWG üzerinde AutoCAD API ile uygulanır).
5. **İş Klasörü:** `jobs/JOB-*/` — intake.yaml, output/, plans/, applied/, redline/, delivery/, RESPONSIBILITE_DEFTERI.json, canlı RAPOR.md.

### 6B.1 Modül Olgunluk Tablosu

| Katman | Konum | Durum | Not |
| :--- | :--- | :--- | :--- |
| Denetim motoru (engine, cross_sheet, rules, reporters) | `core/` | AKTİF-ÜRETİM | 13 test; İBB saha raporlarıyla doğrulanmış |
| CAD okuma + triyaj + pafta tespiti | `core/cad/` | AKTİF-ÜRETİM | 388 DXF önbelleğinde gerçek paftalarla çalışıyor |
| Healer 4 modülü + güvenlik kalkanı | `core/healer/` + `core/cad/cad_safety.py` | AKTİF-PROTOTİP | 7 pafta saha koşumu + 13 test |
| Onay İstasyonu | `tools/review_station.py` | AKTİF-PROTOTİP | Tek kullanıcılı; onay akışı doğrulandı |
| Composer + COM onarımı | `tools/compose_delivery.py` + `common/com_dwgs.py` | AKTİF-PROTOTİP | 7/7 DWG üretildi; COM AutoCAD GUI başlatır |
| CAT6 90 m fiziksel ölçüm | `core/topology/` | YARIM | Gerçek M09 setinde CAT6/UTP yalnızca antet notlarında geçiyor (devre bazlı etiket yok) → çoğu paftada ölçülemez, UNC-CAT6-SPAN belirsizliği beklenir |
| Metro pafta kodu tanıma | `core/engine.py` | AKTİF (M09 odaklı) | AX/TL/PS/GN/ELM/USK/PRT doğrulandı; diğer hatlar genişletme ister |
| Excel yükleme cetveli okuma | `legacy/` | LEGACY-ARŞİV | v2.0 çekirdeği Excel okumaz |
| Süperpoze / topraklama motoru (v1) | `legacy/` | LEGACY-ARŞİV | Referans |
| BIM/IFC/Revit parser | — | YOK (yol haritası) | Çekirdek DXF/DWG odaklı |
| LLM/vision çizim anlama | — | YOK | Heuristik + geometri + kanıt zinciri yaklaşımı |

> **Sıfır Varsayım istisnası (belgelenmiş):** CADTableGenerator, fazı okunamayan linyeleri tabloda üç faza
> eşit paylaştırır ve bunu **(faz belirsiz — TAHMİNİ eşit dağıtım)** etiketiyle ESTIMATED_DEFAULT olarak
> raporlar. Denetim motorunda belirsiz faz asla varsayılmaz; belirsizlik maddesi açılır.

---

## 7. Mevzuat, Standartlar ve Kabul Kriterleri

- **TS HD 60364-5-52:2014 (Çizelge B.52.2 - B.52.5):** XLPE 90°C ve PVC 70°C, B1/C/E döşeme yöntemleri, sıcaklık ve gruplama katsayıları.
- **TS HD 60364-4-43 Madde 433.1:** $I_b \le I_n \le I_z$ ve $I_n \le I_{n,KAK}$ aşırı akım koordinasyonu.
- **BYKHY Madde 72 & 83:** Yangın pompası beslemesinde FE180 kablo zorunludur; 30mA KAK kullanımı kesinlikle yasaktır.
- **İBB Raylı Sistemler As-Built Elektrik Şartnamesi:** Faz dengesizliği $\le \%15$ (Uyarı) / $\%20$ (Kritik — metro paketi; bina paketinde $\%25$); CAT6 kanal mesafesi maks. 90m.
- **EN 50122-1 & ETTY:** İstasyon dağıtım panolarının ana topraklama ağına irtibat kodu zorunluluğu.
- **IEC 60364-5-54 Madde 543.1:** Faz kesitine göre PE iletkeni minimum kesit kontrolü ($S \le 16 \to S$, $16 < S \le 35 \to 16$, $S > 35 \to S/2$).

---

## 8. Doğrulama ve Test Mimarisi (Gold-Standard Test Paketi)

| Test Adı | Kapsam ve Denetlenen Kural | Beklenen Deterministik Sonuç |
| :--- | :--- | :--- |
| `test_ref01_clean_pass_metro_station` | Eksiksiz metro istasyonu modeli. | 0 Kritik Hata, 0 Uyarı, PASS. |
| `test_ref02_known_violations_project` | Gerilim düşümü ihlali, sigorta koordinasyon hatası ve yangın pompası 30mA KAK ihlali. | Tüm ihlallerin CRITICAL olarak %100 KESİN yakalanması. |
| `test_ref03_missing_data_and_uncertainties` | Kesiti yazılmamış eksik projeler. | Otomatik 25A atanmaz; `UNC-MISSING-CABLE-SPEC` üretilir. |
| `test_ref04_tshd60364_ampacity_table_accuracy` | TS HD 60364-5-52 akım taşıma tablosu doğruluğu. | PVC/XLPE, B1/C/E akım değerleri birebir uyuşur; 999mm² None döner. |
| `test_ref05_station_code_priority_and_markdown_reporter` | S24 dosyasında S28 antet metni bulunması. | İstasyon S24 seçilir, antet uyumsuzluğu raporlanır. |
| `test_ref06_symbol_triage_evidence_based` | Anonim blokların 4 kanıt süzgeciyle triyajı. | Mimari elenir, elektrik korunur, armatür yanındakiler silinmez. |
| `test_ref07_metro_sheet_codes_and_station_grounding_are_dynamic` | PS-08 ve GN-14 dinamik pafta tanıma. | Dinamik istasyon kodları ve ECB/TS bağlantıları özetlenir. |
| `test_ref08_graduated_grounding_reconciliation` | Kademeli topraklama eşleştirme ve kanıta bağlı şiddet. | Kompozit etiketler Tier 2 ile UYGUN eşleşir; kat paftası eksikse hata değil belirsizlik açılır; paftada bulunamayan pano WARNING olur. |
| `test_ref09_layer_doctor_and_cad_safety` | Modül 1 (`LayerAndBlockDoctor`) ve `cad_safety.py` 3 tuzak koruması. | XREF ve Blok Tanımı korunur; `IGNORED_ARCHITECTURAL` elemanlar `A-MIMARI-ALTYAPI` (Color 8, 0.09mm, Kilitli) katmanına taşınır; imzalı `applied_changes.json` üretilir. |
| `test_ref10_topological_wire_healer_4_conditions` | Modül 2 (`TopologicalWireHealer`) 4 şartlı doğrusal birleştirme, yan yana paralel hat mayın koruması, OVERKILL ve Snap. | 4/4 koşulu sağlayan kopukluk köprülenir; yan yana paralel hatlar (~90° köprü) ve `W1` vs `W2` farklı devreler `REQUIRES_APPROVAL` olarak durdurulur. |
| `test_ref11_electrical_optimizer_asbuilt_vs_design_and_reverify` | Modül 3 (`ElectricalAutoOptimizer`) `ASBUILT` vs `DESIGN` iş tipi freni ve Öner -> Yeniden Doğrula -> Onayla -> Uygula zinciri. | `ASBUILT` faz değişimi DWG'ye uygulanamaz; `DESIGN` modunda Greedy LPT dengesizliği %0'a indirir; FE180 ve koruma koordinasyonu bellekte yeniden doğrulanıp MTEXT formatı korunarak işlenir. |
| `test_ref12_cad_table_generator_dwg_and_xlsx` | Modül 4 (`CADTableGenerator`) DWG içi LINE+TEXT yükleme cetveli çizimi, mevcut tablo hücresi güncelleme ve `.xlsx` üretimi. | `E-ETIKET-TABLO` katmanında ölçekli cetvel ızgarası çizilir, mevcut hücre handle'ı onay kapısından geçerek güncellenir ve kurumsal Excel (`.xlsx`) dosyası oluşturulur. |
| `test_ref13_all_11_audit_fixes_regression` | Canlı denetimde yakalanan 11 kritik/orta/küçük bulgunun regresyon doğrulaması. | Faz token Değişmezlik Kalkanı (`L2-01 3x2.5 NYY` korunur), dinamik kural paketi sınırları, `STRtree` hızlandırması, Duplicate devre çelişki koruması, kademeli Snap ve Unitless `cm` tespiti doğrulanır. |

**Test Çalıştırma:**
```powershell
& "D:\autocad projesi\venv\Scripts\python.exe" -m pytest "D:\autocad projesi\tests" -v
```

---

## 9. Kullanım Kılavuzu (CLI & İzleme Servisi)

```powershell
# İnteraktif Menü
python cloudecad.py

# Tekil Pafta İncelemesi
python cloudecad.py --file "D:\autocad projesi\ornekprojeler\faruk demir 10 lu - Elektrik.dwg"

# İstasyon Klasörü Denetimi
python cloudecad.py "D:\autocad projesi\incelenecek projeler\işsonları_duzenlenmis\M09-S19_Masko"

# Toplu Tarama (Batch Scan)
python cloudecad.py --scan

# Sürekli İzleme Servisi (Watch Mode - Klasöre dosya atıldıkça otomatik denetim)
python cloudecad.py --watch

# v3.0 SAHA İNDİRİM: Healer zinciri (temiz DXF + mesuliyet defteri + redline)
python tools/field_run_healer.py

# v3.0 ONAY İSTASYONU: kural bazlı toplu triyaj + tekil onay/ret (yerel web arayüzü)
python tools/review_station.py --job jobs/JOB-2026-S19-SAHA-01 --port 8765

# v3.0 COMPOSER: temiz DXF -> DWG 2018 + teslim paketi (delivery/)
python tools/compose_delivery.py --job jobs/JOB-2026-S19-SAHA-01
```

---

## 10. Gelecekteki Geliştiriciler ve Yapay Zeka İçin Bakım Protokolü

1. **Kod Değişikliği Öncesi Bu Belgeyi Kontrol Edin:** Değişiklik yapılacak modülün bu rehberdeki bağımlılıklarını inceleyin.
2. **Sıfır Varsayım İlkesini Asla İhlal Etmeyin:** Çizimde yazmayan hiçbir veriyi koda sabit olarak gömmeyin. Veri eksikse `UncertaintyItem` açın.
3. **Kural Değişikliklerini YAML Dosyalarında Yapın:** Yönetmelik parametrelerini `turkey_bina.yaml` veya `ibb_metro.yaml` dosyalarında yönetin.
4. **Test Paketini Çalıştırın:** Yapılan her değişiklikten sonra `pytest tests/test_reference_projects.py -v` komutu ile 13 testin tümünün yeşil olduğunu doğrulayın.
5. **Bu Rehberi Güncelleyin:** Yeni bir kural, CAD filtresi veya modül eklendiğinde bu dokümanı (`CLOUDECAD_SISTEM_REHBERI.docx` ve `.md`) güncel tutun.
