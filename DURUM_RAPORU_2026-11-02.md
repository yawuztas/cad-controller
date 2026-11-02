# CLOUDECAD v3.0 — DURUM RAPORU (2 Kasım 2026)

> Bu belge, projenin bugünkü halini, bu oturumda yapılan tüm değişiklikleri ve
> açık kalan işleri tek yerde toplar. Yeni oturumlar için başlangıç noktasıdır.

---

## 1. Nerede Duruyoruz (Tek Cümlelik Özet)

Sistem artık **uçtan uca çalışan bir üretim hattı**: batmış DWG gelir → okunur ve
denetlenir → kanıtlı düzeltmeler önerilir → **mühendis onaylar** → temizlenmiş
DWG + rapor + imzalı değişiklik defteri teslim edilir.

**Bu oturumda 3 büyük iş başarıldı:** (a) v2.0 rehber/motor hataları kapatıldı,
(b) v3.0 "Auto-Healer" katmanı senin tarafın yazıldı, ben denetledim ve 11 bulguyu
kapatılan hâle getirdim, (c) saha üretim hattı (saha koşumu → onay ekranı → DWG
teslimatı) kuruldu ve **7/7 gerçek S19 paftasında** kanıtlandı.

---

## 2. Bu Oturumda Yapılan İşler (Sırayla)

### 2.1 Faz A — Mevcut Sistemin (v2.0) Denetimi ve Düzeltilmesi
*Ne yaptım:* Rehber dokümanı, motor modülleri, kurulum ve çıktıları satır satır inceledim.

| Bulgu | Düzeltme | Durum |
|---|---|---|
| `.md` rehberinde **15 kontrol karakteri** (8×BEL, 2×VT, 4×TAB, 1×FF) — `\a`,`\v`,`\t`,`\f` kaçışları yorumlanıyordu | `md_content` **ham string**'e çevrildi (`r"""..."""`) | ✅ 0 karakter |
| Kütüphane tablosu gerçeği yansıtmıyordu (ezdxf `dxf_converter`'da yok; openpyxl/xlrd core'da yok; numpy `electrical_calc`'ta yok; `superpoze`→`superpose_motoru`; **PyYAML hiç yok**) | Tablo gerçek import taramasıyla yeniden yazıldı, PyYAML satırı eklendi | ✅ |
| `requirements.txt` **eksik**: python-docx, pytest, PyYAML · **fazlalık**: click | Eksikler eklendi, click çıkarıldı | ✅ |
| `engine.py` faz dengesizliği sınır metni **sabit** `%15/%25` yazıyordu (paket %20 diyordu) | `RuleEngine.get_phase_limits_text()` eklendi, iki satır pakete bağlandı | ✅ |
| Kod ağacı eksikti (`tools/`, `lispkodlar/`, `jobs/`, `.bat` dosyaları, `requirements.txt` konumu) | Ağaç güncellendi | ✅ |
| DOCX ile MD uyumsuzdu (ref13 DOCX'te yoktu — kontrolüm sadece paragraflara bakıyordu) | Jeneratör güncellendi, ikisi birlikte yeniden derlendi | ✅ |

**Sonuç:** 12/12 test yeşil, rehber v2.0.1 (sonra v3.0) olarak senkron.

---

### 2.2 Faz B — v3.0 "Auto-Healer" Katmanı (SEN yazdın, BEN denetledim)
Senin yazdığın 5 modül: `cad_safety.py` (güvenlik kalkanı), `layer_doctor.py`,
`wire_healer.py`, `electrical_optimizer.py`, `table_generator.py`.

Benim denetimimde **11 bulgu** çıktı; **11'inin tamamı senin tarafından kapatıldı**
ve senin eklediğin `test_ref13` ile doğrulandı. Ben de bağımsız 33 + 27 senaryoluk
duman testleri yazarak doğruladım:

| # | Bulgu | Çözüm |
|---|---|---|
| 🔴1 | Faz etiketi değiştirme **metni yok ediyordu** ("L2-01 3x2.5 NYY" → "L2") | `safe_replace_phase_token` + bağımsız token regex'i + metin ezilmezlik kalkanı |
| 🔴2 | Optimizatör **sabit sınırlar** kullanıyordu (paket %20 iken %15) | `phase_imbalance_limits` + `get_vd_limit()` pakete bağlandı |
| 🟠3 | Duplicate temizleyicide devre bağlamı kontrolü yoktu | Farklı etiketli üst üste çizgiler → onay kuyruğu |
| 🟠4 | O(n²) performans | STRtree uzamsal indeksleme |
| 🟠5 | Snap "sessiz" uygulanıyordu + çift müdahale | Kademeli snap (≤5cm auto) + `stitched_endpoints` koruması |
| 🟠6 | Onaylanmayanlar "REJECTED" görünüyordu | `NOT_SELECTED` + ayrı `rejected_proposal_ids` |
| 🟡7 | Unitless cm tespiti fiilen ölüydü | Çizim yayılımıyla çapraz doğrulama |
| 🟡8 | "E-KAPI-GUVENLIK" gibi elektrik katmanları mimariye taşınıyordu | `_is_protected_electrical_layer` |
| 🟡9 | `table_generator` mutlak import + onaysız hücre güncelleme | Relative import + `approved_cell_handles` kapısı |
| 🟡10 | vd hesabı motorla uyuşmuyordu | `calc_effective_circuit_length` ortak kullanımı |
| 🟡11 | Yangın pompasında KAK metni güncellenmiyordu + bayat sayaçlar | `BYKHY_FIRE_PUMP_RCD_REMOVAL` + `_refresh_summary_counts` |

**Ayrıca senin 23:06 düzenlemen** (`wire_healer.py`'ye katman uygunluk filtresi) 4.733
şüpheli otomatik stitch'i 0'a indirdi — benim "çok fazla otomatik uygulama" uyarımın
tam karşılığıydı. 13/13 test yeşil.

---

### 2.3 Faz C — Saha Koşumu (ben yazdım: `tools/field_run_healer.py`)
Gerçek M09-S19_Masko paftalarında tam zincir: **Okuma → Triyaj → LayerDoctor →
WireHealer → ASBUILT Optimizasyonu**, ardından mesuliyet defteri + redline + temiz DXF.

| Koşum | Pafta | Sonuç | Süre |
|---|---|---|---|
| 1 (ilk) | 4 zayıf akım | 6.190 uygulanan değişiklik | 52,5 sn |
| 2 (senin filtre düzeltmen sonrası) | 4 | 698 değişiklik (TL-03'te 4.733→0 otomatik stitch) | 21 sn |
| 3 (nihai) | **7** (4 zayıf akım + 3 kuvvetli akım) | 701 değişiklik, **19 devre çözüldü** | 42 sn |

**Saha verisinin kanıtladıkları:**
- **58.413 varlık** blok tanımı/XREF gerekçesiyle korundu (tek biri bile bozulmadı)
- TL-03'te **126.634 tehlikeli stitch adayı** otomatik uygulamadan reddedilip onay kuyruğuna düştü
- PS-16'dan **gerçek mühendislik reçetesi** çıktı: `S19/İAP-E/301` panosu **%141,7 faz dengesizlik** → LPT ile **%2,5**'e indirilebilir (saha reçetesi olarak rapora girdi)
- Uygulanan köprülerin 3/3 örneklemi 4 koşul + geometri ile doğrulandı

**Benim hatam:** `LogicalCircuit.phases` diye bir alan yok (yanlış varsayım) → `lc.phase`
string'inden türetildi. Ayrıca PS paftalarının gerçek konumu `01_Kuvvetli_Akim/` altındaydı.

---

### 2.4 Faz D — Onay İstasyonu (ben yazdım: `tools/review_station.py`)
FastAPI + tarayıcı arayüzü. **Konsept:** mühendis istediği maddeyi görür, onaylar/reddeder;
sistem paftaya cerrahi olarak uygular ve imzalı deftere yazar.

- 126 MB'lık plan dosyasını **hafif-indeks** ile sunma (UI anında açılır, apply'de diskten taze yükleme)
- **Kural bazlı toplu triyaj**: "açı ≤ 3°", "boşluk ≤ 100 mm", "açı > 30° → reddet" gibi mühendis kuralları
- İki-aşamalı buton (önizleme → onay) — gömülü tarayıcıda `confirm()` çalışmadığı için
- Statü koruması: onaylanmayanların statüsü ezilmiyor (`NOT_SELECTED`)
- Redline PNG görüntüleyici, teslim klasörü listesi, Composer tetikleyici

**Canlı test sonuçları:** 166 madde kuralla reddedildi (açı>30°), kuyruk 126.916 → **1**,
100 layer maddesi bilinçli olarak sana bırakıldı (UNCERTAIN semboller, %50 güven).

**Test sırasında bulup düzelttiğim 5 hata:** `SUFFIX.items()` açılımı (0 plan yükleniyordu) ·
boş onay setinin `None`'a dönüşüp otomatik maddeleri yeniden uygulaması (20 kopya defter kaydı —
temizlendi) · apply sonrası statü ezilmesi · AutoCAD script'inde **boşluklu yol** hatası
("autocad projesi" → Enter sayılıp yol kesiliyordu; boşluksuz geçici yol + taşıma) ·
`angle_min` filtresi eksikti.

---

### 2.5 Faz E — Composer / Teslim Bestecisi (ben yazdım: `tools/compose_delivery.py`)
Temiz DXF → DWG 2018 + teslim paketi (DWG + DXF + redline + planlar + pafta defteri + README)
+ **canlı üretilen RAPOR.md** (`regen_rapor`) + MANIFEST.json.

---

### 2.6 Faz F — AutoCAD Çökmesi: Kök Neden ve Kalıcı Çözüm
3 paftada (PRT TL-11, PS-08, PS-11) DWG dönüşümü **AutoCAD 2027'de native çökme**
(Access Violation) üretiyordu. Araştırma (AutoCAD'i test cihazı olarak kullanarak):

1. msp boşaltıldı → hâlâ çöküyor ⇒ zehir msp'de değil
2. 355 blok tanımının tümü silindi → çökme bitti ⇒ zehir blok tanımında
3. İkili arama ⇒ zehirli blok: **`M09-PRT-S19-ZZ-M3-ARC-01_detached_rvt-1_...`**
   → **Revit→CAD aktarım artığı** (296 SPLINE, 87 ELLIPSE, 213 HATCH)
4. Yalnız o bloğun SPLINE'ları silinince (izole) çökme bitti; ama tam dosyada yetmedi ⇒
   **katmanlı ve non-deterministik** native çökme (aynı girdi farklı sonuç)
5. MTEXT opsiyonel öznitelik farkı (`line_spacing_factor`, `flow_direction`) → **yanıltıcı**, sorumlu değil

**Kalıcı çözüm — ezdxf'i yazım yolundan tamamen çıkar:**
`cloudecadprogramı/common/com_dwgs.py` → **AutoCAD COM otomasyonu ile orijinal DWG
üzerinde çalışma**: `HandleToObject` ile katman taşıma, `AddLine` ile köprü, uç nokta
taşıma, silme, `SaveAs(ac2018_dwg=64)`.
**Kanıt:** 3 sorunlu pafta **11 saniyede** DWG'ye dönüştü (58+0+1 işlem, skip=0).
**Sonuç: 7/7 paftanın DWG'si var.** ezdxf bundan sonra yalnız **analiz** için kullanılıyor.

---

### 2.7 Faz G — Arayüz Sadeleştirme + Yarış Koşulu Düzeltmesi
Senin "arayüz çok karışık" şikâyetin üzerine arayüz **baştan sadeleştirildi** (benim
yaptığım sade sürüm), ardından **arayüzü sen kendin yeniden tasarladın** (18,5 KB'lık
kart + rozet + durum hapı + satır içi butonlu sürüm) — dosyadaki son hâl **senin
tasarımın**dır, ona dokunulmadı.

- 4 büyük kart (uygulanan / bekleyen / saha reçetesi / pafta), tek cümlelik açıklama
- Sekmeler: Hepsi · Katman düzeltmeleri · Kablo onarımları · Saha reçeteleri
- Satır başına **✓ ONAYLA / ✗ REDDET** butonları; insan dilinde eylem cümleleri
- Jargon (`LDP-0020`, `STITCH_COLLINEAR_GAP`, `bucket`) gizlendi; teknik detay imleç ipucuna taşındı
- Gelişmiş araçlar katlanabilir bölgede

**Yarış koşulu:** eski ekranda bir kayıt işlemi sırasında dosya yazılırken paralel okuma
yarım dosyayı okudu (`missing ENDSEC` hatası — veri bozulmadı, okuma hatasıydı).
Çözüm: **APPLY_LOCK** (uygulama kilidi) + **atomik yazma** (geçici dosya → `os.replace`).

**Doğrulama:** Butonlar çalışıyor — kullanım sırasında bekleyen kararlar 100→78,
uygulanan 691→726, mesuliyet defteri 729 kayda çıktı.

---

## 3. Şu Anki Sistem Durumu (Doğrulanmış)

| Bileşen | Durum | Kanıt |
|---|---|---|
| Altın test paketi | ✅ **13/13 yeşil** | pytest, 0,9 sn |
| Bağımsız duman testlerim | ✅ 33/33 ve 27/27 | temp scriptlerle |
| Saha koşumu | ✅ 7/7 pafta | 42 sn, 701 değişiklik |
| Onay ekranı | ✅ çalışıyor | HTTP 200, 0 konsol hatası |
| DWG teslimatı | ✅ **7/7 pafta** | AX-02 520KB · TL-02 382KB · TL-03 2.930KB · TL-11 1.799KB (COM) · PS-08 1.579KB (COM) · PS-11 3.699KB (COM) · PS-16 765KB |
| Mesuliyet defteri | ✅ 6.192+ imzalı kayıt | `RESPONSIBILITE_DEFTERI.json` (SHA-256) |
| SSOT rehber | ✅ DOCX+MD senkron | v3.0, 0 kontrol karakteri |

### Dosya envanteri
```
tools/field_run_healer.py      → saha koşumu (okuma→onarım→defter→redline)
tools/review_station.py        → onay ekranı (FastAPI + kural triyajı)
tools/compose_delivery.py      → DXF→DWG + teslim paketi + canlı RAPOR
tools/generate_system_guide.py  → SSOT rehber derleyici (docx+md)
cloudecadprogramı/common/com_dwgs.py  → COM tabanlı DWG düzeltici (çökme workaround'ı)
cloudecadprogramı/core/healer/*        → 4 onarım modülü + ortak güvenlik kalkanı
onay_istasyonu.bat / saha_indirimi.bat → tek tık başlatıcılar
jobs/JOB-2026-S19-SAHA-01/            → iş klasörü (aşağıda)
```

### İş klasörü yapısı
```
jobs/JOB-2026-S19-SAHA-01/
├── intake.yaml                iş künyesi (mühendis placeholder'ı burada)
├── output/                    7 adet *_temiz.dxf (onaylı hâli)
├── plans/                     21 plan JSON (değişiklik + wire + optimizer)
├── applied/                   pafta bazlı imzalı değişiklik defterleri
├── redline/                   7 PNG (değişiklik haritası)
├── delivery/                  7 pafta teslim paketi (DWG+DXF+README+planlar)
├── RESPONSIBILITE_DEFTERI.json   iş seviyesi imzalı defter
├── RAPOR.md                   canlı üretilen özet rapor
└── MANIFEST.json              teslim manifesti
```

---

## 4. Açık Kalan İşler (Öncelik Sırasıyla)

| # | İş | Durum / Not |
|---|---|---|
| 1 | **Arayüzde bir ONAYLA butonuna bas** | ✅ **YAPILDI** — kullanım sırasında bekleyen 100→78, uygulanan 691→726, defter 729 kayıt. Butonlar çalışıyor |
| 2 | **78 bekleyen kararı kapat** | Hepsi "E-EKIPMAN" taşıması (%50 güven = "çizimden ne olduğu anlaşılamadı"). Tamamı senin mühendislik seçimin |
| 3 | **2 saha reçetesini sahaya ilet** | Faz dengeleme reçeteleri (raporda) — teslim paketine "saha talimatı" olarak eklenmeli |
| 4 | **COM yolunu Composer'a bağla** | Şu an COM ayrı bir betik olarak çalıştı; station'daki "Tüm paftalar" butonu hâlâ accoreconsole kullanıyor ⇒ 3 paftada tekrar çöker. Composer'a 2. kademe (console → COM) eklenmeli |
| 5 | **Git deposu kur** | Proje şu an sürüm kontrolünde değil — bugün 200+ satır kod yazıldı, geri dönüş yok |
| 6 | `intake.yaml`'daki mühendis künyesini doldur | Teslim dokümanlarına işlenir |
| 7 | İlk gerçek müşteri işi için iş kabul akışı | Fiyatlama, teklif, NDA, teslim şablonları |

---

## 5. Dürüst Riskler / Teknik Borçlar

1. **Composer→COM bağlantısı eksik** (yukarıdaki 4. madde) — 3 paftada "Tüm Paftalar"
   butonu hâlâ çökmeye düşebilir. Elle Composer çalıştırılırsa sorun yok.
2. **ezdxf'in yazım hataları AutoCAD'i çökertiyor** — kalıcı çözüm COM; ancak şu an
   station'ın karar uygulaması hâlâ **ezdxf ile** temiz DXF'e yazıyor. Yani: onaylanan
   değişiklikler DXF'e ezdxf ile yazılıyor, DWG ise COM ile üretiliyor → ikisi arasında
   küçük bir tutarsızlık riski var (aynı işlem farklı dosyaya yazılıyor). **Birleştirilmeli.**
3. **Proje sürüm kontrolünde değil** (git yok) — kritik.
4. **126 MB plan dosyası** her station açılışında ~10–20 sn yükleniyor (SQLite indeks ile
   çözülebilir).
5. **İlk gerçek müşteri işi yapılmadı** — üretim hattı iç testle kanıtlandı, ticari
   iş akışı (fiyat/teklif/sözleşme) kurgulanmadı.
6. **AutoCAD COM otomasyonu AutoCAD GUI'sini başlatıyor** — kullanıcı oturumunda
   çalışırken dikkat gerektirir (kendi makinende olduğu için şu an sorun değil).
7. **Çalışan station örneği sistem Python'u ile açılmış** (PID 7968,
   `Python311\python.exe`, venv değil). Çalışıyor ama tutarlılık için
   `onay_istasyonu.bat` (venv) ile başlatılmalı; ayrıca `review_station.py`
   değişikliği **yeniden başlatmadan** ekrana yansımaz.

---

## 7. Dış Denetim Maddelerinin Kapanışı (2 Kasım 2026)

| # | Denetim maddesi | Sonuç | Kanıt |
|---|---|---|---|
| 1 | Word ve Markdown **aynı kaynaktan** üretilsin | ✅ Çözüldü | `tools/generate_system_guide.py` tek üreticidir; DOCX ve MD bölümleri aynı olguları taşır. Doğrulama: DOCX/MD başlıkları ikisi de "CloudeCAD v3.0", 6B bölümü ve olgunluk tablosu ikisinde de var |
| 2 | **v2/v3 ve 8/13 test** çelişkisi | ✅ Çözüldü | 3 başlık + 5 metin referansı düzeltildi. Doğrulama: DOCX/MD'de "CloudeCAD v2.0" kalıntısı **0**, "8 test" kalıntısı **0**, "13 test" **2** yerde |
| 3 | Türkçe karakter bozulması | ✅ **Bulgu yok** (yanlış alarm) | Kaynak, DOCX (gövde + üst/alt bilgi) ve MD'de U+FFFD sayısı **0**; MD'de kontrol karakteri **0**. Ekrandaki `�` işaretleri terminal kodlama artefaktı |
| 4 | Aktif / legacy / deneysel / tamamlanmamış ayrımı | ✅ Çözüldü | DOCX + MD'ye "6B.1 Modül Olgunluk Tablosu" eklendi (11 satır: AKTİF-ÜRETİM / AKTİF-PROTOTİP / LEGACY-ARŞİV / YARIM / YOK) |
| 5 | Composer/COM tek akış | ✅ Çözüldü | `compose_delivery.py` 3 kademeli: accoreconsole → SPLINE temizliği → **COM onarımı**. `com_dwgs.py`'ye robust AutoCAD başlatma eklendi (AutoCAD kapalıyken de çalışır). Doğrulama: 7/7 pafta tek komutla DWG üretildi (4 console + 3 COM) |
| 6 | CAT6 ve metro pafta kapsamı gerçek veride | ✅ Ölçüldü + 1 boşluk kapatıldı | 2.505 DWG'de **21 farklı pafta kodu**; GN-01/GN-07 kapsam dışıydı → `is_grounding_sheet_filename` genelleştirildi (tüm `GN-xx`), 13/13 test yeşil. CAT6 gerçeği: CAT6/UTP **yalnızca antet blok notlarında** (KMM_Antet_*) geçiyor, devre bazlı etiket yok → 90 m ölçümü çoğu paftada yapılamaz, `UNC-CAT6-SPAN` belirsizliği beklenir (rehberde belgelendi) |

### Ek kod düzeltmeleri (bu turda)
- `core/healer/table_generator.py`: belirsiz faz artık **açıkça etiketleniyor** (`*` işareti + "TAHMİNİ eşit dağıtım" dipnotu + `unknown_phase_count` + `assumptions[ESTIMATED_DEFAULT]`) — Sıfır Varsayım ilkesinin belgelenmiş istisnası hâline geldi.
- `core/engine.py`: `is_grounding_sheet_filename` tüm `GN-xx` kodlarını kapsıyor (GN-01/GN-07 gerçek veride vardı).
- `common/com_dwgs.py`: AutoCAD kapalıyken `Dispatch` çökmesi yerine `acad.exe` başlatma + COM bekleme eklendi.

### Güncel sayılar
- 13/13 test yeşil · 7/7 DWG teslim · 62 dosyalık teslim klasörü · MANIFEST + canlı RAPOR.md + 2 saha reçetesi belgesi
- Mesuliyet defteri: 729 imzalı kayıt · Bekleyen karar: kullanıcı işlemiyle azalıyor

**Sıra 1-2-4-5 → sonra ilk gerçek iş:**
1. Arayüzde tek bir ONAYLA'ya bas (senin doğrulaman)
2. 100 bekleyen kararı 5-10 dakikada kapat (toplu kural + manuel)
3. Composer'a COM kademesini bağla (2. riski sıfırla)
4. Git deposu kur (her şeyden önce!)
5. **İlk gerçek müşteri işi al** — sistem kanıtlandı, artık para kazanma aşaması

> Para tarafı: Bu oturumda üretilen şey, bir mühendislik hizmetinin "işi elle yapmak yerine
> fabrika gibi üretme" altyapısı. Kalan iş **mühendislik değil, satış ve süreç**.
