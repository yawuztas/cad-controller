# 🏢 BİNA ELEKTRİK PROJELERİ — TAM SÜRÜM MEVZUAT VE MÜHENDİSLİK FORMÜLLERİ REHBERİ

Bu klasör (`02_mevzuat_ve_formuller/bina/`), Türkiye'deki konut, ofis, ticari yapı, hastane, otel ve kamu binalarının elektrik projelerini **3 ana disiplin başlığında** denetleyen **tam sürüm (full-formulation)** mühendislik kurallarını ve analitik denklemlerini içerir:

1. [`01_topraklama.yaml`](file:///d:/autocad%20projesi/02_mevzuat_ve_formuller/bina/01_topraklama.yaml) — **Topraklama ve Yıldırımdan Korunma (LPS)**
2. [`02_kuvvetli_akim.yaml`](file:///d:/autocad%20projesi/02_mevzuat_ve_formuller/bina/02_kuvvetli_akim.yaml) — **Kuvvetli Akım, Yükleme Cetveli, Kısa Devre, Kompanzasyon ve Aydınlatma**
3. [`03_zayif_akim.yaml`](file:///d:/autocad%20projesi/02_mevzuat_ve_formuller/bina/03_zayif_akim.yaml) — **Zayıf Akım (Yangın Algılama, Data/Fiber, CCTV/PoE, Acil Anons PA/VA, SMATV)**

Tüm formüller [`03_hesap_motoru/core/calculators/electrical_calc.py`](file:///d:/autocad%20projesi/03_hesap_motoru/core/calculators/electrical_calc.py) içinde deterministik Python fonksiyonları olarak kodlanmıştır.

---

## 1️⃣ BÖLÜM 1: TOPRAKLAMA VE YILDIRIMDAN KORUNMA (`01_topraklama.yaml`)

* **Dayanak Mevzuat:** Elektrik Tesislerinde Topraklamalar Yönetmeliği (ETTMY Ek-N & Ek-P), TS HD 60364-5-54:2013, TS HD 60364-4-41:2017, DIN 18014:2014, IEEE Std 80-2013, TS EN 62305-1..4.

### 1.1 Yayılma Direnci Analitik Formülleri
* **Dikey Topraklama Çubuğu (Dwight & ETTMY Ek-P):**
  $$R_{c1} = \frac{\rho_E}{2\pi L} \ln\left(\frac{4L}{d}\right) \quad \text{(Tam Dwight: } \frac{\rho_E}{2\pi L}\left[\ln\left(\frac{8L}{d}\right) - 1\right]\text{)}$$
  $$R_{cn} = \frac{R_{c1}}{n \cdot \eta}$$
  *(Burada $\eta$, paralel kazıkların karşılıklı etkileşim verim katsayısıdır: $n=2 \Rightarrow 0.90$, $n=4 \Rightarrow 0.80$, $n=10 \Rightarrow 0.70$).*
* **Yatay Gömülü Şerit / Çevre İletkeni ($h$ derinliğinde):**
  $$R_{\text{şerit}} = \frac{\rho_E}{2\pi L} \left[\ln\left(\frac{2L^2}{d \cdot h}\right) - 1\right]$$
* **Temel Topraklayıcı — Laurent-Niemann Metodu (ETTMY Ek-N & EMO):**
  $$D = 2\sqrt{\frac{A}{\pi}} = \sqrt{\frac{4A}{\pi}}, \qquad R_{\text{temel}} = \frac{\rho_E}{2D} + \frac{\rho_E}{L_{\text{toplam}}}$$
* **Uluslararası Altın Standart — IEEE Std 80-2013 Sverak Formülü:**
  $$L_T = L_{\text{şerit}} + n \cdot L_{\text{çubuk}}, \qquad R_g = \rho_E \left[ \frac{1}{L_T} + \frac{1}{\sqrt{20A}} \left(1 + \frac{1}{1 + h\sqrt{20/A}}\right) \right]$$
* **Temel Izgarası + Kazık Grubu Schwarz Karşılıklı Kuplaj Bileşkesi:**
  $$R_m = 0.33 \cdot R_{\text{temel}}, \qquad R_e = \frac{R_{\text{temel}} \cdot R_{\text{çubuk}} - R_m^2}{R_{\text{temel}} + R_{\text{çubuk}} - 2 R_m}$$

### 1.2 Koruma İletkeni (PE) Kesit Hesabı (TS HD 60364-5-54)
* **Yöntem 1 — Geometrik Çizelge 54.2:**
  * $S_{\text{faz}} \le 16\text{ mm}^2 \implies S_{PE} = S_{\text{faz}}$
  * $16 < S_{\text{faz}} \le 35\text{ mm}^2 \implies S_{PE} = 16\text{ mm}^2$
  * $S_{\text{faz}} > 35\text{ mm}^2 \implies S_{PE} \ge \frac{S_{\text{faz}}}{2}$
* **Yöntem 2 — Madde 543.1.1 Tam Adyabatik Termik Dayanım Formülü ($t \le 5\text{ s}$):**
  $$S_{PE,\min} = \frac{\sqrt{I_k^2 \cdot t}}{k} = \frac{I_k \sqrt{t}}{k}$$
  *($k$ katsayıları: Kablo içi PVC Bakır $k=115$, XLPE/HFFR Bakır $k=143$, Çıplak Bakır $k=159$, Galvaniz Çelik Şerit $k=52$).*

### 1.3 Dolaylı Temasa Karşı Koruma (TS HD 60364-4-41) ve LPS (TS EN 62305)
* **TN Sistemi Çevrim Empedansı:** $Z_s \cdot I_a \le U_0$ ($230\text{ V}$). Maksimum açma süresi $\le 63\text{ A}$ son devrelerde $0.4\text{ s}$, dağıtım hatlarında $5.0\text{ s}$.
* **TT Sistemi Dokunma Gerilimi:** $R_A \cdot I_{\Delta n} \le 50\text{ V}$ (ETTMY genel bina hedefi $R_A \le 5\,\Omega$, özel trafo $R_B \le 2\,\Omega$, paratoner $\le 10\,\Omega$).
* **LPS Ayırma Mesafesi (TS EN 62305-3):**
  $$s = \frac{k_i \cdot k_c}{k_m} \cdot l$$

---

## 2️⃣ BÖLÜM 2: KUVVETLİ AKIM (`02_kuvvetli_akim.yaml`)

* **Dayanak Mevzuat:** EİTY (Md. 57), BYKHY (Md. 67–84), TS HD 60364-5-52:2014, TS HD 60364-4-43:2012, TS EN 60909-0, EPDK Reaktif Güç Yönetmeliği, TS EN 12464-1:2021.

### 2.1 İşletme Akımı ve Gerilim Düşümü (Omik vs Tam Empedanslı)
* **İşletme Akımı ($I_b$):**
  $$I_{b,\text{1f}} = \frac{P}{U_0 \cdot \cos\varphi}, \qquad I_{b,\text{3f}} = \frac{P}{\sqrt{3} \cdot U_n \cdot \cos\varphi}$$
* **Yöntem A — Klasik Omik Gerilim Düşümü (EİTY Md. 57, $\kappa_{\text{Cu}} = 56$):**
  $$\%e_{\text{1f}} = \frac{200 \cdot L \cdot P}{\kappa \cdot S \cdot U_0^2}, \qquad \%e_{\text{3f}} = \frac{100 \cdot L \cdot P}{\kappa \cdot S \cdot U_n^2}$$
* **Yöntem B — TS HD 60364-5-52 Ek-G Tam Empedanslı (Reaktans Dahil) Gerilim Düşümü:**
  $$\Delta U = b \cdot I_b \cdot \frac{L}{1000} \cdot \frac{R_{\text{km}}\cos\varphi + X_{\text{km}}\sin\varphi}{n_{\text{paralel}}}, \qquad \%e = \frac{\Delta U}{U_n} \times 100$$
  *(Burada 1 faz için $b=2, U_n=230\text{ V}$; 3 faz için $b=\sqrt{3}, U_n=400\text{ V}$. Sınırlar: Aydınlatma $\le \%1.5$, Priz/Kuvvet $\le \%3.0$, Özel Trafolu Toplam $\le \%5.0$).*

### 2.2 Düzeltilmiş Akım Taşıma Kapasitesi ve Aşırı Akım Koordinasyonu
* **TS HD 60364-5-52 Düzeltilmiş Kablo Kapasitesi ($I_z$):**
  $$I_z = I_{z0} \cdot k_1(\text{sıcaklık}) \cdot k_2(\text{gruplama})$$
* **TS HD 60364-4-43 Koruma Koordinasyonu:**
  $$I_b \le I_n \le I_z \quad \text{ve} \quad I_2 \le 1.45 \cdot I_z$$
* **Kısa Devre Hesabı (TS EN 60909-0):**
  $$I_{k3,\max} = \frac{1.05 \cdot U_n}{\sqrt{3} \cdot \sqrt{R_{\text{top}}^2 + X_{\text{top}}^2}}, \qquad I_{k1,\min} = \frac{0.95 \cdot U_0}{\sqrt{(2 R_{\text{top,sıcak}})^2 + (2 X_{\text{top}})^2}}, \qquad I_{cn} \ge I_{k3,\max}$$

### 2.3 Talep Gücü, Faz Dengesi, Kompanzasyon ve Aydınlatma
* **Konut Daire Talep Gücü (EİTY Md. 57 — 8 kW Kuralı):**
  $$P_{\text{talep}} = \begin{cases} 0.60 \cdot P_{\text{kurulu}}, & P_{\text{kurulu}} \le 8000\text{ W} \\ 4800 + 0.40 \cdot (P_{\text{kurulu}} - 8000), & P_{\text{kurulu}} > 8000\text{ W} \end{cases}$$
* **Üç Faz Dengesizliği ve Vektörel Nötr Akımı ($120^\circ$):**
  $$\%\Delta = \frac{P_{\max} - P_{\min}}{P_{\text{ort}}} \times 100, \qquad I_N = \sqrt{I_R^2 + I_S^2 + I_T^2 - (I_R I_S + I_S I_T + I_T I_R)}$$
* **EPDK Reaktif Güç Kompanzasyonu ($\ge 50\text{ kVA}$ için endüktif $\le \%20$, kapasitif $\le \%15$):**
  $$Q_c = P_{\text{aktif}} \cdot (\tan\varphi_1 - \tan\varphi_2)$$
* **TS EN 12464-1 Aydınlatma Lümen Yöntemi:**
  $$K = \frac{a \cdot b}{h_m(a+b)}, \qquad \Phi_{\text{toplam}} = \frac{E_{\text{ort}} \cdot A}{\eta_u \cdot MF}, \qquad N = \left\lceil \frac{\Phi_{\text{toplam}}}{\Phi_{\text{armatür}}} \right\rceil$$

---

## 3️⃣ BÖLÜM 3: ZAYIF AKIM (`03_zayif_akim.yaml`)

* **Dayanak Mevzuat:** BYKHY (Md. 74–84), TS EN 54-14:2018, TS EN 54-4, TS EN 54-16/24, ISO/IEC 11801-1, TS EN 62676, TS EN 60728-1.

### 3.1 Yangın Algılama, Akü Yedekleme ve Çevrim Gerilim Düşümü
* **Dedektör Kapsama ve Buton Mesafesi (TS EN 54-14):**
  * Duman dedektörü: $A \le 80\text{ m}^2$, $r \le 7.5\text{ m}$ (açık alan aralık $\le 9.0\text{–}10.6\text{ m}$, dar koridor $\le 15\text{ m}$), tavan yüksekliği $\le 12\text{ m}$.
  * Sıcaklık dedektörü: $A \le 30\text{ m}^2$, $r \le 5.3\text{ m}$ (açık alan aralık $\le 7.5\text{ m}$, dar koridor $\le 10\text{ m}$), tavan yüksekliği $\le 7.5\text{ m}$ (Sınıf A1).
  * Yangın ihbar butonu: yürüme mesafesi $\le 30\text{ m}$, montaj yüksekliği $1.40\text{ m}$.
* **TS EN 54-4 Yangın Santrali Akü Kapasite Hesabı:**
  $$C_{\text{Ah}} = 1.25 \times \left( I_{\text{sükunet}} \cdot T_{\text{bekleme (24h/72h)}} + I_{\text{alarm}} \cdot T_{\text{alarm (0.5h)}} \right)$$
* **Çevrim (Loop) ve Siren Hattı Gerilim Düşümü ($24\text{ V DC}$):**
  $$\Delta U_{\text{loop}} = 2 \cdot \frac{L}{1000} \cdot R_{\text{km}} \cdot I_{\text{alarm}} \le 6.0\text{ V}$$

### 3.2 Yapısal Kablolama & Fiber Optik Zayıflama Bütçesi (ISO/IEC 11801)
* **Bakır Cat6/Cat6A Sınırı:** Permanent Link $\le 90\text{ m}$, Channel $\le 100\text{ m}$.
* **Fiber Optik Link Loss Budget:**
  $$\text{Loss}_{\text{dB}} = (\alpha_{\text{fiber}} \cdot L_{\text{km}}) + (N_{\text{konnektör}} \cdot 0.50\text{ dB}) + (N_{\text{ek}} \cdot 0.10\text{ dB}) + \text{Margin}_{\text{dB}}$$

### 3.3 CCTV Depolama / PoE Bütçesi (TS EN 62676) & Acil Anons (TS EN 54-16)
* **NVR Disk Kapasitesi ve PoE Switch Gücü:**
  $$\text{Disk}_{\text{TB}} = \frac{\text{Bitrate (Mbps)} \times 86400 \times \text{Gün} \times N_{\text{kamera}}}{8 \times 10^6}, \qquad P_{\text{PoE,Switch}} \ge 1.25 \sum P_{\text{kamera}}$$
* **100V PA/VA Anons Amfi Gücü, Hat Empedansı ve Akustik SPL:**
  $$P_{\text{amfi}} \ge 1.25 \sum P_{\text{hoparlör}}, \qquad Z_{\text{hat}} = \frac{100^2}{P_{\text{toplam}}}, \qquad \text{SPL}(r) = \text{SPL}_{1\text{W}/1\text{m}} + 10\log_{10}(P) - 20\log_{10}(r)$$
