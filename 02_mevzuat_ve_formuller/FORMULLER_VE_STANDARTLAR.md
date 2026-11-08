# Elektrik Mühendisliği Hesap Formülleri ve Mevzuat Standartları

Bu klasör, CloudeCAD hesap motorunun projeyi incelerken ve düzeltirken baz aldığı **tüm formülleri, sınır değerleri ve mevzuat kurallarını** içerir. Herhangi bir sınır değerini veya kuralı değiştirmek isterseniz, bu klasördeki `turkey_bina.yaml` veya `ibb_metro.yaml` dosyasını düzenleyebilirsiniz.

---

## 1. Gerilim Düşümü Formülleri ($e\%$)

Elektrik İç Tesisleri Yönetmeliği ve IEC 60364 uyarınca linye ve ana besleme hatlarındaki gerilim düşümü hesapları:

### A. Monofaze Devreler (1 Faz + Nötr, $U = 230\text{ V}$)
$$e\% = \frac{200 \cdot L \cdot P}{k \cdot S \cdot U^2}$$

* $P$: Devre aktif gücü (Watt)
* $L$: Hat uzunluğu (metre)
* $k$: İletken öz iletkenliği (Bakır için $k = 56 \text{ m}/(\Omega\cdot\text{mm}^2)$, Alüminyum için $k = 35$)
* $S$: İletken kesiti ($\text{mm}^2$)
* $U$: Faz-Nötr gerilimi ($230\text{ V}$)

### B. Trifaze Devreler (3 Faz, $U = 400\text{ V}$)
$$e\% = \frac{100 \cdot L \cdot P}{k \cdot S \cdot U^2}$$

* $U$: Faz-Faz gerilimi ($400\text{ V}$)

### Sınır Değerler (Mevzuat Limitleri)
| Yapı Tipi | Aydınlatma Linyesi | Priz Linyesi | Ana Besleme (Kolon) | Toplam Maksimum |
|---|:---:|:---:|:---:|:---:|
| **Bina / Konut (EİTY)** | $\%1.5$ | $\%3.0$ | $\%3.0$ | $\%5.0$ |
| **Metro / Endüstri (İBB)**| $\%1.5$ | $\%2.5$ | $\%2.0$ | $\%3.0$ |

---

## 2. Devre İşletme Akımı ve Sigorta Koordinasyonu

### A. İşletme Akımı Hesabı ($I_b$)
* **Monofaze:**
  $$I_b = \frac{P}{U \cdot \cos\varphi}$$
* **Trifaze:**
  $$I_b = \frac{P}{\sqrt{3} \cdot U \cdot \cos\varphi}$$

### B. Koruma Koordinasyonu Kuralı (TS HD 60364-4-43)
Tüm devrelerde şu sıralama mutlak suretle sağlanmalıdır:
$$I_b \le I_n \le I_z$$

* $I_b$: Devre işletme akımı
* $I_n$: Sigorta (MCB/MCCB) anma akımı (örn: 10A, 16A, 20A, 25A)
* $I_z$: Kablonun döşeme şekline göre akım taşıma kapasitesi (Ampacity)

---

## 3. Pano Faz Dengeleme Formülü ve Optimizasyon

Panolardaki linyelerin 3 faza ($L_1, L_2, L_3$) dengeli dağıtılması için:

### Faz Dengesizliği Yüzdesi
$$\text{Dengesizlik (\%)} = \frac{P_{\max} - P_{\min}}{P_{\text{ortalama}}} \times 100$$

* $P_{\max} = \max(P_{L1}, P_{L2}, P_{L3})$
* $P_{\min} = \min(P_{L1}, P_{L2}, P_{L3})$
* $P_{\text{ortalama}} = \frac{P_{L1} + P_{L2} + P_{L3}}{3}$

### Sınırlar ve LPT Optimizasyonu:
* **Uyarı Sınırı:** $\%15$
* **Kritik Hata Sınırı:** $\%20$
* **Çözüm:** Greedy LPT (Longest Processing Time) algoritması ile linyeler güçlerine göre büyükten küçüğe sıralanır ve en az yüklü faza sırayla atanarak dengesizlik $<\%5$ seviyesine indirilir.

---

## 4. BYKHY Yangın Güvenliği Standartları (Binaların Yangından Korunması Hakkında Yönetmelik)

Yangın anında can ve mal güvenliği için zorunlu 2 kritik kural:

1. **FE180 Yangına Dayanıklı Kablo Zorunluluğu (Madde 84):**
   * Yangın pompası, duman tahliye fanları, acil anons ve acil aydınlatma beslemeleri en az **180 dakika (FE180 / PH120)** alev altında çalışabilen halogen-free kablo (örn: `NHXMH`, `0.6/1kV FE180`) ile yapılmalıdır. Standart PVC kablo (`NYY`, `NYM`) kullanılamaz.
2. **Yangın Pompasında 30 mA KAK (Kaçak Akım Koruma) Yasağı:**
   * Yangın pompası besleme devresine $30\text{ mA}$ hayat koruma kaçak akım rölesi konulamaz (yanlış açma ile söndürme sistemini durdurmaması için). Yangın durumunda kesinti yerine alarm prensibi uygulanır.

---

## 5. CAD Katman ve Blok Güvenlik Standartları

1. **Mimari Altlık Koruması (`A-MIMARI-ALTYAPI`):**
   * Algoritma tarafından mimari olduğu tespit edilen duvar, kolon, kapı, pencere vb. elemanlar tek bir `A-MIMARI-ALTYAPI` katmanına toplanır.
   * Rengi: **Color 8 (Açık Gri)**, Çizgi Kalınlığı: **0.09 mm**, Durumu: **Kilitli (Locked)**. Böylece elektrik tesisatı öne çıkar.
2. **Blok Tanımı Dokunulmazlığı:**
   * Blok tanımı (BLOCK header) asla değiştirilmez; sadece çizim içindeki kopya referansın (INSERT) katmanı değiştirilir. Böylece diğer elemanlar bozulmaz.
3. **XREF Dokunulmazlığı:**
   * Dış referans (XREF) içerisindeki varlıklar kesinlikle salt-okunur olarak kabul edilir; taşınmaz veya silinmez.

---

## 6. Kablo Topolojisi İyileştirme Sınırları

1. **Doğrusal Birleştirme (Collinear Stitch):**
   * Aynı katmanda, aynı devreye ait, aralarında başka sembol bulunmayan ve açı farkı $\le 5^\circ$ olan kopuk uçlar birleştirilir.
   * Maksimum boşluk toleransı: $\le 200\text{ mm}$ (çizim birimine göre dinamik ölçeklenir).
2. **Yan Yana Paralel Hatları Koruma Kalkanı (Bridge Angle):**
   * Uç uca olmayan, yan yana paralel uzanan iki farklı linye kablosunun birleştirilmesi kesinlikle engellenir.
3. **Sembole Bağlama (Snap):**
   * $\le 50\text{ mm}$ mesafedeki açıkta kalan uçlar otomatik olarak en yakın armatür/priz klemens noktasına bağlanır.
   * $> 50\text{ mm}$ mesafeler Onay İstasyonu'nda mühendis onayına sunulur.
