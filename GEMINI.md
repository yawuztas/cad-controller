# CLOUDECAD — Evrensel Mühendislik ve CAD Geliştirme Anayasası (`GEMINI.md`)

Bu dosyadaki kurallar **`d:\autocad projesi`** altındaki tüm geliştirme, hata ayıklama ve test adımlarında **kesin ve tartışılamaz** çalışma talimatıdır.

---

## 1. Projenin Temel Amacı ve 4 Adımlı İş Akışı

CloudeCAD; **tek bir örnek dosyaya göre değil**, `01_girdi/` klasörüne konulacak **herhangi bir Bina veya Metro AutoCAD (`.dwg` / `.dxf`) projesinde** evrensel olarak çalışmak üzere geliştirilen bir CAD okuma, çizim/katman onarım ve mühendislik denetim motorudur.

1. **Adım 1 — Evrensel CAD Okuma, Mimari Altlığın Ayrılması ve Saf Çizim Onarımı:**
   * **1. Adım: Mimari Altlığın Kopya Çakıştırma (`cKDTree`) + Morfoloji (`Shapely`/`momepy`) ile Ayrılması, Ölü Kopyaların Elenmesi ve Evrensel Sembol/Topoloji Kütüphanelerinin Kullanımı** ilkesini uygula.
   * Çizim birimini (`mm` / `cm` / `m`) projedeki fiziksel referans nesnelerden (kapı yayları, elektrik sembol yarıçapları, yazı yükseklikleri) dinamik tespit et. Çıktı DWG'de **yalnızca çizim/katman hatalarını, kopuk kabloları ve mükerrer çizgileri** düzelt; DWG içindeki yazılı hesaplara/sayılara dokunma.
2. **Adım 2 — Görsel Gömülü Hesap ve Tablo Çapraz Kontrolü:** Projeye çizilmiş/yazılmış tüm şemaları (Kolon Dağıtım Şeması, Tek Hat, Yükleme Cetveli, Gerilim Düşümü Hesabı, Topraklama Planı, Kat Planları) birbirleriyle çapraz doğrula.
3. **Adım 3 — Kendi Mevzuat ve Formül Motorumuzla Gerçek Hesaplama:** Çizimden gerçek verileri çekip `02_mevzuat_ve_formuller/` ve `03_hesap_motoru/core/calculators/electrical_calc.py` formüllerine koyarak olması gereken gerçek değerleri ($I_b$, $I_z$, $I_n$, seçicilik, $\%e$, Laurent-Niemann $R_E$) hesapla.
4. **Adım 4 — Karşılaştırma Raporu ve Temiz DWG Teslimatı (`04_cikti/`):** Projedeki yazılı/çizili değerler ile formül motorumuzun bulduğu doğru değerleri yan yana karşılaştıran dürüst raporu (`04_cikti/raporlar/`) ve çizimi temizlenmiş DWG'yi (`04_cikti/temiz_cizimler/`) üret.

---

## 2. KIRMIZI ÇİZGİLER — KESİNLİKLE YASAKLAR

### 2.1. Sıfır Hardcode (Proje Ezberi Kesinlikle Yasaktır)
* **ASLA** eldeki test projesine (`5katlı 10 daireli.dwg`, `Pafta #13` vb.) ait sayıları kodun içine **sabit değer veya `else` / `fallback` olarak yazma** (örn. `10900.0`, `5960.0`, `7920.0`, `5527.0`, `28004.0`, `73609`, `0.36`, `0.37`, `250.90`, `83.62`, `"4x6NYY/6mm2"`, `"C3(20A)"` gibi).
* **ASLA** koda DXF nesne `handle` ID'leri (`8DF0B`, `A1BDD` vb.) gömme; raporlarda yalnızca çalışma anında dosyadan **dinamik okunan** gerçek handle'ları gösterebilirsin.
* **ASLA** belirli bir panoya veya test senaryosuna özel `if` yazma (örneğin `DT-10` için ayrı, `DT-16` için ayrı, belirli bir sabit formül sonucunu yakalayan `abs(val - 0.36) < 0.015` gibi kontroller **YASAKTIR**).

### 2.2. Koordinat Ezberleme / Overfitting Yasaktır
* Bir örnek projedeki hatayı yakalamak için DXF koordinatlarını döküp arama penceresini (`dx`, `dy` kutularını, uzunluk filtrelerini) sadece o örnek dosyaya oturacak şekilde daraltma veya eğip bükme.
* Kolon şeması, kat planı ve topraklama planı ayrıştırması **koordinat tahminine değil**:
  * Çizgilerin/polyline'ların uç uca bağlanmasından oluşan **topolojik ağaca (graph/connectivity)**,
  * Metinlerin/tabloların **geometrik satır-sütun hizalamasına**,
  * Kapalı poligon ve temas noktalarının **gerçek vektör geometrisine** dayanmak zorundadır.

### 2.3. Sahte Başarı ve Hayali Doğrulama Yasaktır (Dürüstlük İlkesi)
* Program çizimdeki bir metni, tabloyu, kabloyu, kesiciyi, uzunluğu veya güç değerini **gerçekten okuyamadıysa**:
  * **ASLA** varsayılan bir sayı uydurup hesaplamaya devam etme.
  * **ASLA** "okundu / doğrulandı" diye raporlama.
  * Eksik veya ayrıştırılamayan her veriyi açıkça **`BELİRSİZ / OKUNAMADI`** olarak işaretle ve hangi bilginin çizimde eksik/ayrıştırılamaz olduğunu dürüstçe raporla.
* Kullanıcıyı veya testi memnun etmek adına **kolaya kaçıp projeye özel yama yapmaya yeltenme**. Bir şey genel olarak çözülemiyorsa, bunu açıkça söyle ve genel mekanizmayı tasarla.

### 2.4. Açık Kaynak Kütüphanelerden İstifade ve Maksimum Sadelik (KISS) İlkesi
* **Tekerleği Yeniden İcat Etme:** Karmaşık, iç içe `if/else` yığınları ve kırılgan özel buluşsal (heuristic) kurallar yazmak yerine; `venv` içinde ve sistemde hazır bulunan açık kaynak kütüphane ve profesyonel araçların gücünden doğrudan istifade et:
  * **CAD ve Çizim Altyapısı:** `ezdxf` (DXF okuma/geometri), AutoCAD Core Console / COM (`AUDIT`, `DXFOUT`), AutoCAD Electrical `IEC-60617` sembol ve `default_cat.mdb` katalog kütüphaneleri.
  * **Geometri, Mekânsal Ayırma ve Morfoloji:** `shapely` (vektör/poligon/STRtree), `geopandas` (`sjoin`/`overlay` fark alma), `momepy` (mimari/oda kabuğu morfolojisi), `scipy.spatial` (`cKDTree`, `Voronoi`) ve `scipy.optimize.linear_sum_assignment` (1'e 1 eşleme).
  * **Kümeleme ve Topolojik Graf:** `scikit-learn` (`HDBSCAN`/`DBSCAN` ada kümeleme), `libpysal` (mekânsal komşuluk grafları), `networkx` (kablo/kolon topoloji takibi) ve `pandapower` (yük akışı ve kısa devre analizi).
* **Sade ve Katmanlı Kurulum (KISS):** Sistemi yapabildiğimiz kadar sade, az dallanmalı ve net sorumluluklara bölünmüş halde kur:
  1. Önce proje içi bölgeleri/adaları ayır ve unutulmuş/ölü kopyaları ele.
  2. Mimari altlığı kopya çakıştırma (`cKDTree`) ve morfolojiyle tamamen temizleyip maskele.
  3. Geriye kalan saf elektrik çizimini geometrik sembol şekli ve topolojik graf üzerinden oku.

---

## 3. Evrensel Kural vs. Proje Verisi Ayrımı

| Kodda Olabilir (Evrensel Mühendislik / CAD Bilgisi) | Kodda KESİNLİKLE OLAMAZ (Proje Ezberi) |
| :--- | :--- |
| EİTY, TS HD 60364, BTY, BYKHY formül ve sınır değerleri (`02_mevzuat_ve_formuller/*.yaml`) | Tek bir projenin kW/W, A, m, $\Omega$, $\%e$ sayıları veya fallback'leri |
| Genel kablo, kesici, KAKR, birim, güç ifade kalıpları (regex) | Belirli bir dosya adı, pafta numarası, handle ID veya proje metni birebir araması |
| Fiziksel ölçek referansları (kapı genişliği $70\text{–}100\text{ cm}$, metin/sembol oranı) | Örnek çizimden ölçülmüş sabit $X/Y$ pencere ofsetleri (`dy=-1460`, `oy+550`) |
| Graf üzerindeki **herhangi** ebeveyn-çocuk kesici için $I_{n,\text{üst}}/I_{n,\text{alt}} \ge 1.6$ kuralı | Sabit pano isimleri (`DT-10`, `O-T`, `AT` dışında isim verilirse çökmesi) |
| Temel ring poligonuna fiziksel temas eden **tüm** filizlerin dinamik tespiti | "Bina 4 köşelidir" veya "filiz $1.0\text{–}4.5\text{ m}$ arasıdır" varsayımları |

---

## 4. Zorunlu Doğrulama ve Değişmezlik Protokolü

1. **Genelleştirme Testi (Anti-Overfit Şartı):** Eklenen veya güncellenen her denetim kuralı için `tests/` altında mevcut örnek proje **dışında** sentetik/farklılaştırılmış senaryolarla (farklı pano isimleri, farklı kat sayısı, farklı $L/P/S$ değerleri, farklı köşe sayısı ve farklı çizim birimleri `mm`/`cm`/`m`) test yaz ve çalıştır. Değerler değiştirildiğinde sonuçlar da gerçekten değişmiyorsa orada hardcode vardır; kabul etme.
2. **Klasör Sınırları:**
   * `01_girdi/`: Sadece okunur proje girdileri.
   * `02_mevzuat_ve_formuller/`: Tek mevzuat ve formül kaynağı (`bina/`, `metro/`).
   * `03_hesap_motoru/`: Aktif üretim kodu (yeni kod yalnızca buraya yazılır).
   * `04_cikti/`: Üretilen temiz DWG/DXF ve raporlar.
   * `_arsiv/`: Yalnızca arşivdir; aktif motora karıştırılmaz.
3. **Kod Temizliği Hedefi:** `03_hesap_motoru/core/cad/building_audit.py` ve `03_hesap_motoru/core/engine.py` içinde geçmiş adımlardan kalmış projeye özel sabit blok/fallback kalıntıları tamamen temizlenmeden "evrensel bina motoru tamamlandı" iddiasında bulunulmaz.
