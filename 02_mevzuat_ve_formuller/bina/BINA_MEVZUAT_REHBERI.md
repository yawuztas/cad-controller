# BİNA ELEKTRİK PROJELERİ DENETİM VE MEVZUAT REHBERİ

Bina projeleri, CloudeCAD tarafından **3 ana disiplin** altında incelenir ve onarılır:

---

## 1. Topraklama ve Eşpotansiyel Sistemleri (`01_topraklama.yaml`)
* **Mevzuat:** Elektrik Tesislerinde Topraklamalar Yönetmeliği & TS HD 60364-5-54
* **Temel Topraklaması:** $30\times3.5\text{ mm}$ galvaniz şerit ile en fazla $20\times20\text{ m}$ göz aralığı oluşturulmalıdır.
* **Toprak Direnci Sınırları:** Genel şebekede $\le 5\,\Omega$, trafolu binalarda $\le 2\,\Omega$, paratonerde $\le 10\,\Omega$.
* **Temas Gerilimi:** İnsan hayatı için azami izin verilen temas gerilimi $U_t \le 50\text{ V}$ (AC).
* **Koruma İletkeni (PE):**
  * $S_{\text{faz}} \le 16\text{ mm}^2 \implies S_{PE} = S_{\text{faz}}$
  * $16 < S_{\text{faz}} \le 35\text{ mm}^2 \implies S_{PE} = 16\text{ mm}^2$
  * $S_{\text{faz}} > 35\text{ mm}^2 \implies S_{PE} = S_{\text{faz}} / 2$
* **Eşpotansiyel Bara:** Su, kalorifer, doğalgaz ve asansör rayları ana potansiyel dengeleme barasına (EBD) bağlanmalıdır.

---

## 2. Kuvvetli Akım Dağıtım ve Pano Sistemleri (`02_kuvvetli_akim.yaml`)
* **Mevzuat:** Elektrik İç Tesisleri Yönetmeliği (EİTY) & BYKHY
* **Gerilim Düşümü:**
  * Aydınlatma linyesi: $\%1.5$
  * Priz linyesi: $\%3.0$
  * Ana besleme / kolon: $\%1.5$
  * Toplam sınır: $\%3.0$ (kendi trafosu olan binalarda $\%5.0$)
* **Sorti Sınırları:** Bir aydınlatma linyesine en fazla 9 lamba, bir priz linyesine en fazla 7 priz bağlanabilir.
* **Akım Koordinasyonu:** $I_b \le I_n \le I_z$ kuralı her linyede kontrol edilir.
* **Faz Dengeleme:** Panolardaki 3 faz dengesizliği $\%15$ üzerinde uyarı, $\%25$ üzerinde hata verir; LPT algoritması ile $<\%5$'e indirilir.
* **Yangın Pompası:** Kesinlikle en az 180 dk aleve dayanıklı (`FE180`) kablo ile beslenmeli ve $30\text{ mA}$ KAK rölesi **bağlanmamalıdır**.

---

## 3. Zayıf Akım Sistemleri (`03_zayif_akim.yaml`)
* **Yangın Algılama (BYKHY & TS EN 54-14):**
  * Duman dedektörü yarıçapı: Maksimum $7.5\text{ m}$ (yaklaşık $80\text{ m}^2$).
  * Sıcaklık dedektörü yarıçapı: Maksimum $5.3\text{ m}$ (yaklaşık $40\text{ m}^2$).
  * Yangın ihbar butonu: En uzak noktadan yürüme mesafesi $\le 30\text{ m}$.
  * Siren / Flaşör: Ortam sesinden en az 5 dBA yüksek, asgari $65\text{ dBA}$ (yatak başlarında $75\text{ dBA}$).
  * Kablo tipi: `JH(St)H ... lg FE180 / PH120` yangına dayanıklı kablo zorunludur.
* **Data / Yapısal Kablolama (ISO/IEC 11801):**
  * Kat panosu ile priz arası kalıcı hat mesafesi **en fazla $90\text{ m}$** olabilir ($90\text{ m}$ üstü hata üretir).
  * Kuvvetli akım tavası ile zayıf akım tavası arasında min $50\text{ mm}$ (bölmeli) veya $200\text{ mm}$ (ayrı tava) mesafe olmalıdır.
* **CCTV & Geçiş Kontrol:**
  * Yangın anında kartlı geçiş kapılarındaki manyetik kilitler enerjisi kesilerek kapıları kaçışa serbest bırakmalıdır.
