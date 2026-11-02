"""
CloudeCAD — Zayıf Akım Sistemleri Denetim Motoru (SystemsAuditor)
================================================================
BYKHY, TS EN 54, BTK ve TS EN 50083 standartlarına göre yangın ihbar,
telefon/data, SMATV ve interkom sistemlerini denetler, bulguları üretir.
"""

from typing import List
from core.models import WeakCurrentAuditReport, WeakCurrentAuditFinding
from standards.bykhy_fire import evaluate_fire_alarm_mandate, check_detector_spacing
from standards.telecom_data import calculate_telecom_capacities
from standards.smatv_tv import evaluate_smatv_system
from standards.intercom import evaluate_intercom_system


class WeakCurrentAuditor:
    """Zayıf akım sistemleri deterministik denetim motoru."""

    def __init__(self, report: WeakCurrentAuditReport):
        self.report = report
        self.findings: List[WeakCurrentAuditFinding] = []

    def audit_all(self) -> WeakCurrentAuditReport:
        """Tüm zayıf akım alt sistemlerini proje tipolojisine (Bina / Metro / Endüstriyel) göre denetler."""
        if self.report.typology == "METRO_RAIL":
            self._audit_metro_weak_current()
        elif self.report.typology == "INDUSTRIAL":
            self._audit_industrial_weak_current()
        else:
            self._audit_fire_alarm()
            self._audit_telecom_data()
            self._audit_smatv_tv()
            self._audit_intercom()
            self._audit_cad_and_risers()

        self._evaluate_verdict_and_score()
        self.report.findings = self.findings
        return self.report

    def _audit_fire_alarm(self):
        """Yangın algılama ve ihbar sistemini BYKHY ve TS EN 54'e göre denetler."""
        fire = self.report.fire_alarm
        d_cnt = self.report.dwelling_count
        h_bld = self.report.building_height_m

        # 1. Yasal Zorunluluk Kontrolü (BYKHY)
        mand_check = evaluate_fire_alarm_mandate(
            building_height_m=h_bld,
            dwelling_count=d_cnt,
            total_area_m2=d_cnt * 120.0
        )

        if mand_check.is_mandatory and not fire.is_drawn:
            self.findings.append(WeakCurrentAuditFinding(
                id=len(self.findings) + 1,
                system="YANGIN",
                element="Yangın Algılama Sistemi",
                issue=f"BYKHY uyarınca yangın algılama sistemi zorunlu olmasına rağmen projede çizilmemiştir!",
                impact=f"Yapı yüksekliği {h_bld:.1f} m veya {d_cnt} bağımsız bölüm nedeniyle belediye ve itfaiye onayından geçemez.",
                correction="Kat planlarına dedektör, buton ve sirenleri yerleştirip Yangın Kolon Şeması ekleyiniz.",
                severity="KRİTİK"
            ))
            fire.status = "ZORUNLU_ANCAK_ÇİZİLMEMİŞ"
            return

        if fire.is_drawn:
            # Dedektör Dağılımı ve Sayı Kontrolü
            min_expected_detectors = max(d_cnt, self.report.floor_count * 2)
            if fire.smoke_detectors < min_expected_detectors and fire.smoke_detectors > 0:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="YANGIN",
                    element="Duman Dedektörleri (DS)",
                    issue=f"Çizimdeki duman dedektörü sayısı ({fire.smoke_detectors} adet) bina ölçeğine ({d_cnt} daire, {self.report.floor_count} kat) göre yetersiz kalabilir.",
                    impact="Kat hollerinde veya ortak alanlarda kör nokta kalma riski (TS EN 54-14).",
                    correction=f"Her kat holüne ve ortak kaçış koridoruna en az 1-2 adet optik duman dedektörü yerleştiriniz.",
                    severity="UYARI"
                ))

            # Buton Mesafesi ve Kaçış Yolu
            if fire.manual_call_points < self.report.floor_count:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="YANGIN",
                    element="Yangın İhbar Butonları (YB)",
                    issue=f"Yangın butonu sayısı ({fire.manual_call_points} adet), kat sayısından ({self.report.floor_count}) azdır!",
                    impact="Kaçış merdiveni çıkışlarında buton bulunmaması acil tahliye bildirimini geciktirir (BYKHY Md 75).",
                    correction="Her katın yangın kaçış merdiveni sahanlığına ve bina ana çıkışına en az 1 adet yangın butonu (YB) ekleyiniz.",
                    severity="KRİTİK"
                ))

            # Yangın Santrali (YIS / FACP)
            if fire.control_panels == 0:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="YANGIN",
                    element="Yangın İhbar Santrali (YIS)",
                    issue="Kat planlarında veya ana tabloda yangın santrali (YIS) sembolü/yeri gösterilmemiştir.",
                    impact="Santralin yeri belirsiz olduğunda güvenlik/giriş noktasından izleme yapılamaz.",
                    correction="Bina giriş holüne veya güvenlik mahaline yangın kontrol santrali (YIS) yerleştiriniz.",
                    severity="UYARI"
                ))

            # Uzamsal STRtree Dedektör Kapsama Yarıçapı (r=6.2m / TS EN 54-14) ve Kör Nokta Kontrolü
            if getattr(fire, "over_spaced_detectors", 0) > 0:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="YANGIN",
                    element="Dedektör Kapsama Yarıçapı (STRtree Uzamsal Denetim)",
                    issue=f"{fire.over_spaced_detectors} adet dedektör arasında TS EN 54-14 azami kapsama mesafesi (Duman r=6.2m / ~9.0m aralık) aşılmıştır.",
                    impact="Dedektörler arası ölü bölge (kör nokta) oluşur; dumanın dedektöre ulaşma süresi gecikir.",
                    correction="TS EN 54-14 Madde A.6.2 uyarınca koridor ve salonlarda duman dedektörleri arası yatay mesafeyi <= 9.0 m (duvardan <= 4.5 m) olacak şekilde sıklaştırınız.",
                    severity="UYARI"
                ))

            if getattr(fire, "unmonitored_rooms", None):
                rooms_str = ", ".join(fire.unmonitored_rooms[:5])
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="YANGIN",
                    element="Kör Nokta / Dedektörsüz Mahal Denetimi (STRtree)",
                    issue=f"Şu mahallerin 7.5 m yarıçapında yangın dedektörü tespit edilemedi: {rooms_str}",
                    impact="Kapalı hacimlerde veya teknik odalarda başlayan yangın algılanamaz (BYKHY Md 75).",
                    correction=f"Belirtilen mahallere ({rooms_str}) uygun tipte (optik duman veya mutfak/kazan dairesi için sıcaklık) dedektör ekleyiniz.",
                    severity="UYARI"
                ))

    def _audit_telecom_data(self):
        """Telefon ve data tesisatını BTK standartlarına göre denetler."""
        tel = self.report.telecom
        d_cnt = self.report.dwelling_count

        tel_req = calculate_telecom_capacities(d_cnt, self.report.floor_count)

        if not tel.is_drawn:
            self.findings.append(WeakCurrentAuditFinding(
                id=len(self.findings) + 1,
                system="TELEFON_DATA",
                element="Telefon & Data Altyapısı",
                issue="Projede telefon / data (yapısal kablolama) tesisatı tespit edilemedi.",
                impact="BTK Bina İçi Elektronik Haberleşme Şartnamesi ihlali; telekom abonelik onayı alınamaz.",
                correction="Kat planlarına telefon prizleri (T), kat kutuları (1TK) ve bina ana kutusu (BTK) ekleyiniz.",
                severity="KRİTİK"
            ))
            tel.status = "ÇİZİMDE_YOK"
            return

        # Priz Sayısı vs Daire Sayısı
        expected_min_sockets = d_cnt * 2 # Daire başı salon + yatak odası en az 2 priz
        if tel.sockets < expected_min_sockets and tel.sockets > 0:
            self.findings.append(WeakCurrentAuditFinding(
                id=len(self.findings) + 1,
                system="TELEFON_DATA",
                element="Telefon Prizleri (T)",
                issue=f"Toplam priz sayısı ({tel.sockets} adet), daire başına asgari 2 priz kuralına göre ({expected_min_sockets} adet) azdır.",
                impact="Odalarda internet/telefon altyapısı eksik kalır.",
                correction="Her bağımsız bölümün salon ve ebeveyn yatak odasına en az 1'er adet RJ-45/Cat6 prizi yerleştiriniz.",
                severity="BİLGİ"
            ))

        # Bina Telefon Kutusu (BTK) Kontrolü
        if tel.main_boxes == 0:
            self.findings.append(WeakCurrentAuditFinding(
                id=len(self.findings) + 1,
                system="TELEFON_DATA",
                element="Bina Telefon Kutusu (BTK)",
                issue="Bina ana telefon dağıtım kutusu (BTK) kat planında veya şemada blok olarak gösterilmemiştir.",
                impact="Türk Telekom şebeke irtibatının nereye sonlandırılacağı belirsiz kalır.",
                correction=f"Bina girişine veya zemin kata {tel_req['btk_recommended_spec']} yerleştiriniz.",
                severity="UYARI"
            ))

    def _audit_smatv_tv(self):
        """TV ve uydu dağıtım tesisatını TS EN 50083'e göre denetler."""
        tv = self.report.smatv
        d_cnt = self.report.dwelling_count

        smatv_req = evaluate_smatv_system(d_cnt, self.report.floor_count)

        if not tv.is_drawn:
            self.findings.append(WeakCurrentAuditFinding(
                id=len(self.findings) + 1,
                system="TV_UYDU",
                element="SMATV / TV Dağıtım Sistemi",
                issue="Çizimde TV / Uydu anten dağıtım sistemi tespit edilemedi.",
                impact="Bina sakinlerinin merkezi uydu yayını altyapısı eksik kalır.",
                correction="Kat planlarına TV prizleri ve çatı/şafta Multiswitch dağıtım sistemi ekleyiniz.",
                severity="UYARI"
            ))
            tv.status = "ÇİZİMDE_YOK"
            return

        # Daire başı TV prizi
        if tv.tv_sockets < d_cnt and tv.tv_sockets > 0:
            self.findings.append(WeakCurrentAuditFinding(
                id=len(self.findings) + 1,
                system="TV_UYDU",
                element="TV Prizleri (TV)",
                issue=f"TV prizi sayısı ({tv.tv_sockets} adet), bağımsız bölüm sayısından ({d_cnt}) düşüktür.",
                impact="Bazı dairelerde TV yayını prizi unutulmuş olabilir.",
                correction="Her daireye en az 1 (tercihen salon + mutfak + oda olarak 2-3) adet TV prizi yerleştiriniz.",
                severity="UYARI"
            ))

        # Dağıtıcı (TAP) ve Multiswitch (TVS) Kontrolü
        if tv.tap_offs == 0 and tv.multiswitches == 0:
            self.findings.append(WeakCurrentAuditFinding(
                id=len(self.findings) + 1,
                system="TV_UYDU",
                element="TV Kat Dağıtıcıları (TAP) / Santral (TVS)",
                issue="Prizler çizilmiş ancak kat dağıtıcı (TAP) veya TV Multiswitch santrali şemada gösterilmemiştir.",
                impact="Kablo dağıtım güzergahı ve sinyal zayıflama kademeleri belirsizdir.",
                correction=f"Kat şaftlarına TAP dağıtıcılar ve {smatv_req['recommended_multiswitch']} ekleyiniz.",
                severity="BİLGİ"
            ))

    def _audit_intercom(self):
        """Görüntülü diafon ve kapı kontrol sistemini denetler."""
        dia = self.report.intercom
        d_cnt = self.report.dwelling_count

        if not dia.is_drawn:
            self.findings.append(WeakCurrentAuditFinding(
                id=len(self.findings) + 1,
                system="INTERCOM",
                element="İnterkom / Diafon Sistemi",
                issue="Projede interkom / görüntülü diafon tesisatı bulunamadı.",
                impact="Daireler ile bina ana girişi arasında sesli/görüntülü irtibat ve kapı açma sağlanamaz.",
                correction="Kat planlarına daire diafon şubeleri (ID), zil butonu (Z) ve kapı otomatiği (KO) ekleyiniz.",
                severity="UYARI"
            ))
            dia.status = "ÇİZİMDE_YOK"
            return

        # Daire Monitörü (ID) ile Daire Sayısı Eşleşmesi
        if dia.monitors > 0 and dia.monitors < d_cnt:
            diff = d_cnt - dia.monitors
            self.findings.append(WeakCurrentAuditFinding(
                id=len(self.findings) + 1,
                system="INTERCOM",
                element="Diafon Monitörü (ID)",
                issue=f"Diafon monitör sayısı ({dia.monitors} adet), toplam daire sayısından ({d_cnt}) {diff} adet eksiktir!",
                impact="Bazı dairelerde interkom şubesi atlanmış veya layer/blok hatası yapılmış.",
                correction="Tüm dairelerin giriş hollerine 1'er adet görüntülü diafon monitörü (ID) yerleştiriniz.",
                severity="UYARI"
            ))

        # Kapı Otomatiği (KO)
        if dia.door_releases == 0:
            self.findings.append(WeakCurrentAuditFinding(
                id=len(self.findings) + 1,
                system="INTERCOM",
                element="Kapı Otomatiği (KO)",
                issue="Bina ana giriş kapısında kapı otomatiği (KO) kilidi/rölesi çizilmemiştir.",
                impact="Dairelerden ana kapı kilidinin açılması fonksiyonu devre dışı kalır.",
                correction="Ana bina giriş kapısına kapı otomatiği (KO) ekleyip zil trafosuna bağlayınız.",
                severity="UYARI"
            ))

    def _audit_cad_and_risers(self):
        """Çizim katmanları ve kolon şemalarını denetler."""
        layers = self.report.cad_layers_found

        # Katman Standart Hijyeni
        expected_prefixes = ["00-YANGIN", "00-TEL", "00-TV", "00-INTERCOM"]
        missing_std_layers = []
        for pref in expected_prefixes:
            if not any(pref in l.upper() for l in layers):
                missing_std_layers.append(pref)

        if missing_std_layers:
            self.findings.append(WeakCurrentAuditFinding(
                id=len(self.findings) + 1,
                system="GENEL_CAD",
                element="Zayıf Akım Katman Standartları",
                issue=f"Bazı standart zayıf akım katmanları çizimde bulunamadı: {', '.join(missing_std_layers)}",
                impact="Katman ayrımı yapılmadığında tesisat elemanları mimari veya kuvvetli akım katmanlarına karışır.",
                correction=f"Eksik katmanları ({', '.join(missing_std_layers)}) standart renk ve çizgi tipleriyle oluşturunuz.",
                severity="BİLGİ"
            ))

    def _audit_metro_weak_current(self):
        """
        Metro / Raylı Sistem / Tünel Zayıf Akım & Yangın Denetimi
        (NFPA 130, TS EN 54-14/16/22/24, EN 50121-4 EMC, İBB Raylı Sistemler Şartnamesi)
        11 Alt Rolün her biri için özel mühendislik denetimi uygular.
        """
        role = self.report.sheet_role
        d_code = self.report.discipline_code
        devs = self.report.metro_device_counts
        self.report.smatv.status = "KAPSAM_DIŞI (METRO)"
        self.report.intercom.status = "KAPSAM_DIŞI (METRO)"

        # 0. Genel Çizim Hijyeni: Kopyala-Yapıştır ve Yabancı Blok Kontrolleri
        for cp in self.report.metro_copypaste_errors:
            self.findings.append(WeakCurrentAuditFinding(
                id=len(self.findings) + 1,
                system="GENEL_CAD",
                element="İstasyon / Hat Kopyala-Yapıştır Çağrı Etiketi",
                issue=f"Çizim üzerinde başka istasyondan kopyalanıp unutulan etiket: {cp}",
                impact="Saha montajında veya işletme devreye almada yanlış kabin/cihaz tanımlamasına yol açar.",
                correction="Kablo çağrı ve cihaz etiketini mevcut istasyon kodu ile güncelleyiniz.",
                severity="UYARI"
            ))

        for fb in self.report.metro_foreign_block_warnings:
            self.findings.append(WeakCurrentAuditFinding(
                id=len(self.findings) + 1,
                system="GENEL_CAD",
                element="Farklı Hat / İstasyon Blok Referansı",
                issue=f"Çizim içinde farklı hat/istasyon blok referansı ({fb}) unutulmuştur.",
                impact="Blok kütüphanesinde yabancı hat kalıntıları paftanın As-Built onayını engeller.",
                correction="Yabancı istasyon referanslı blokları mevcut istasyon kütüphanesinden güncelleyiniz.",
                severity="UYARI"
            ))

        # 1. AX-02: Yangın Algılama ve İhbar Tesisatı (NFPA 130 & EN 54)
        if role == "METRO_YANGIN_ALGILAMA" or d_code == "AX-02":
            smoke = devs.get("SMOKE_DETECTOR", 0)
            heat = devs.get("HEAT_DETECTOR", 0)
            comb = devs.get("COMBINED_DETECTOR", 0)
            call_pts = devs.get("FIRE_CALL_POINT", 0)
            sirens = devs.get("FIRE_SIREN", 0)
            modules = devs.get("FIRE_MODULE", 0)
            pwr_24v = devs.get("POWER_SUPPLY", 0)
            tot_det = smoke + heat + comb

            if tot_det == 0:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="YANGIN",
                    element="Noktasal Yangın Dedektörleri (EN 54-7 & EN 54-5)",
                    issue="Yangın algılama paftasında noktasal optik duman veya sıcaklık dedektörü tespit edilemedi.",
                    impact="NFPA 130 uyarınca peron, bilet holü ve teknik odalarda yangın erken algılanamaz.",
                    correction="Tüm teknik odalara (OG, Trafo, SER, CER, UPS) ve yolcu alanlarına uygun dedektörleri yerleştiriniz.",
                    severity="KRİTİK"
                ))

            if call_pts == 0:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="YANGIN",
                    element="Yangın İhbar Butonları (EN 54-11)",
                    issue="Paftada manuel yangın ihbar butonu (YB) sembolü bulunamadı.",
                    impact="Yolcular ve istasyon personeli yangını manuel olarak Yangın SCADA'ya bildiremez.",
                    correction="Kaçış merdiveni çıkışlarına, acil çıkış kapılarına ve peron başı/sonuna EN 54-11 butonları ekleyiniz.",
                    severity="KRİTİK"
                ))

            if modules == 0:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="YANGIN",
                    element="Giriş-Çıkış Yangın Arayüz Modülleri (EN 54-18)",
                    issue="Yangın senaryo kontrolü için Giriş-Çıkış Arayüz Modülü (I/O) tespit edilemedi.",
                    impact="Yangın anında duman tahliye damperleri (FS), fanlar, turnikeler ve yangın asansörleri otomatik tetiklenemez.",
                    correction="Her yangın damperine, yangın kapısına ve TVS MCC panosuna adresli izleme/kontrol modülü ekleyiniz.",
                    severity="KRİTİK"
                ))

            if self.report.metro_fe180_cable_m <= 0:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="YANGIN",
                    element="Yangına Dayanıklı Kablo (FE180 / PH120)",
                    issue="Yangın loop ve siren devrelerinde FE180 (120-180 dk dayanımlı) yangın kablosu katmanı/metrajı tespit edilemedi.",
                    impact="NFPA 130 gereği yangın tahliyesi süresince çevrim kablolarının yangın altında işlevini sürdürmesi zorunludur.",
                    correction="Tüm yangın loop ve besleme kablolarını LIH(St)CH FE180 / PH120 olarak seçip metrajını paftaya işleyiniz.",
                    severity="KRİTİK"
                ))

        # 2. TL-02: Veri İletişim, LAN & Fiber Optik Altyapı
        elif role == "METRO_VERI_ILETISIM_LAN" or d_code == "TL-02":
            sw_cnt = devs.get("LAN_SWITCH", 0)
            mpls_cnt = devs.get("MPLS_ROUTER", 0)
            odf_cnt = devs.get("FIBER_PATCH_PANEL", 0)
            data_cnt = devs.get("DATA_OUTLET", 0)

            if sw_cnt == 0:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="TELEKOM_DATA",
                    element="Endüstriyel Yönetilebilir Switch (LAN Backbone)",
                    issue="Veri iletişim paftasında endüstriyel switch veya dağıtım anahtarı sembolü tespit edilemedi.",
                    impact="İstasyon IP kameraları, PIS ekranları, kartlı geçiş ve anons sistemi omurga ağına bağlanamaz.",
                    correction="CER ve SER sistem odalarına A+B yedekli Ring topolojili endüstriyel switchler yerleştiriniz.",
                    severity="KRİTİK"
                ))
            if odf_cnt == 0:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="TELEKOM_DATA",
                    element="Fiber Optik Bağlantı Paneli (ODF)",
                    issue="İstasyon omurga fiber optik terminasyon paneli (ODF) tespit edilemedi.",
                    impact="İstasyonlar arası hat boyu haberleşme ve ana kontrol merkezi (OCC) bağlantısı sağlanamaz.",
                    correction="Kabin içi 24/48 portlu Tek Modlu (SM) Fiber Optik terminasyon paneli (ODF) ekleyiniz.",
                    severity="UYARI"
                ))

        # 3. TL-03: Telefon, Acil SOS & Dahili Haberleşme
        elif role == "METRO_TELEFON_INTERKOM" or d_code == "TL-03":
            emg_cnt = devs.get("EMERGENCY_PHONE", 0)
            srv_cnt = devs.get("SERVICE_PHONE", 0)
            mdf_cnt = devs.get("TELECOM_MDF", 0)

            if emg_cnt == 0 and "BT0" in self.report.floor_code:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="TELEFON_DATA",
                    element="Tünel & Peron Acil Durum Telefonu (SOS)",
                    issue="Peron katında veya tünel girişinde acil durum (SOS) yardım telefonu tespit edilemedi.",
                    impact="Acil durumlarda yolcuların veya hattaki personelin İstasyon Kontrol Merkezi (SCR/OCC) ile doğrudan irtibatı kesilir.",
                    correction="Peron başı ve sonuna ışıklı/korumalı Acil Durum Telefonu (SOS) ünitesi yerleştiriniz.",
                    severity="KRİTİK"
                ))

        # 4. TL-04: Telsiz / TETRA Haberleşme & Anten
        elif role == "METRO_TETRA_TELSIZ" or d_code == "TL-04":
            ant_cnt = devs.get("TETRA_ANTENNA", 0)
            cpl_cnt = devs.get("TETRA_COUPLER", 0)
            spl_cnt = devs.get("TETRA_SPLITTER", 0)

            if ant_cnt == 0:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="TETRA_RADIO",
                    element="TETRA İstasyon Telsiz Anteni",
                    issue="Telsiz paftasında omni/yönlendirilebilir telsiz anteni tespit edilemedi.",
                    impact="İstasyon içi güvenlik, itfaiye ve işletme telsiz haberleşmesi (TETRA) kör noktada kalır.",
                    correction="Bilet holü ve peron tavanlarına kapsama simülasyonuna uygun TETRA antenleri yerleştiriniz.",
                    severity="KRİTİK"
                ))

        # 5. TL-05: Acil Anons ve Sesli Tahliye (PA/VA)
        elif role == "METRO_ACIL_ANONS_PAVA" or d_code == "TL-05":
            spk_cnt = devs.get("PAVA_SPEAKER", 0)
            ans_cnt = devs.get("AMBIENT_NOISE_MIC", 0)

            if spk_cnt == 0:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="PA_VA_ACIL_ANONS",
                    element="Acil Anons Hoparlörleri (EN 54-24)",
                    issue="Acil anons paftasında EN 54-24 sertifikalı hoparlör sembolü tespit edilemedi.",
                    impact="NFPA 130 ve BYKHY uyarınca yangın anında sesli tahliye bildirimi yapılamaz.",
                    correction="Peron ve bilet holü tavanlarına A+B yedekli EN 54-24 yangına dayanıklı hoparlörler yerleştiriniz.",
                    severity="KRİTİK"
                ))
            if ans_cnt == 0 and "BT0" in self.report.floor_code:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="PA_VA_ACIL_ANONS",
                    element="Ortam Gürültü Sensörü (ANS Mikrofonu)",
                    issue="Peron katında tren yanaşma gürültüsünü dengeleyecek Ortam Gürültü Mikrofonu (ANS) tespit edilemedi.",
                    impact="Gürültülü anlarda anons seviyesi arka planın +10 dBA üzerinde kalamaz; konuşma anlaşılabilirliği (STI) düşer.",
                    correction="Peron bölgesine en az 1-2 adet EN 54-16 uyumlu Ortam Gürültü Sensörü (ANS) ekleyiniz.",
                    severity="UYARI"
                ))

        # 6. TL-06: Kapalı Devre Televizyon / CCTV Kamera Sistemi
        elif role == "METRO_CCTV_KAMERA" or d_code == "TL-06":
            dome_cnt = devs.get("CCTV_DOME_CAMERA", 0)
            ptz_cnt = devs.get("CCTV_PTZ_CAMERA", 0)
            mon_cnt = devs.get("CCTV_MONITOR", 0)
            tot_cam = dome_cnt + ptz_cnt

            if tot_cam == 0:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="CCTV",
                    element="Sabit ve Hareketli IP Kameralar",
                    issue="CCTV paftasında güvenlik kamerası sembolü tespit edilemedi.",
                    impact="İstasyon yolcu güvenliği, turnike geçişleri ve peron hattı izlenemez.",
                    correction="Peron kenarları, bilet holü, yürüyen merdivenler ve asansör önlerine IP kameralar yerleştiriniz.",
                    severity="KRİTİK"
                ))
            if mon_cnt == 0 and "BT0" in self.report.floor_code:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="CCTV",
                    element="Tren Önü / Peron Başı Monitörü (TÖM)",
                    issue="Peron katında makinistin kapı kapanma hattını izleyeceği Peron Başı Monitörü (TÖM) tespit edilemedi.",
                    impact="Makinist yolcu sıkışmalarını göremez; peron sürüş güvenliği tehlikeye girer.",
                    correction="Her iki peronun tren durma noktasına 2x2 veya 1x2 TÖM monitör grubu ekleyiniz.",
                    severity="UYARI"
                ))

        # 7. TL-07: Saat Sistemi (Master Clock & Tali Saatler)
        elif role == "METRO_SAAT_SISTEMI" or d_code == "TL-07":
            ana_cnt = devs.get("ANALOG_CLOCK", 0)
            dig_cnt = devs.get("DIGITAL_CLOCK", 0)

            if (ana_cnt + dig_cnt) == 0:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="CLOCK_SYSTEM",
                    element="İstasyon Analog ve Dijital Tali Saatleri",
                    issue="Saat sistemi paftasında tali saat sembolü tespit edilemedi.",
                    impact="Yolcular ve istasyon personeli merkezi senkronize zaman bilgisini göremez.",
                    correction="Peron tavanlarına çift taraflı analog saat, bilet holü ve SCR odasına dijital saat yerleştiriniz.",
                    severity="UYARI"
                ))

        # 8. TL-08: Kartlı Geçiş ve Kapı Güvenlik (ACS)
        elif role == "METRO_KARTLI_GECIS_ACS" or d_code == "TL-08":
            rdr_cnt = devs.get("ACS_CARD_READER", 0)
            cnt_cnt = devs.get("ACS_MAGNETIC_CONTACT", 0)
            btn_cnt = devs.get("ACS_EXIT_BUTTON", 0)

            if cnt_cnt == 0:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="ACCESS_CONTROL",
                    element="Teknik Kapı Manyetik Kontakları",
                    issue="Güvenlik paftasında teknik oda kapıları için manyetik kontak tespit edilemedi.",
                    impact="Yetkisiz kişilerin trafo, cer gücü ve telekom odalarına izinsiz girişleri algılanamaz.",
                    correction="Tüm teknik mahallerin (OG, UPS, SER, CER, Depo) kapılarına manyetik kontak ekleyiniz.",
                    severity="UYARI"
                ))

        # 9. TL-10: Yolcu Bilgilendirme Sistemi (PIS)
        elif role == "METRO_YOLCU_BILGILENDIRME_PIS" or d_code == "TL-10":
            pis_dbl = devs.get("PIS_DISPLAY_DOUBLE", 0)
            pis_sgl = devs.get("PIS_DISPLAY_SINGLE", 0)

            if (pis_dbl + pis_sgl) == 0:
                self.findings.append(WeakCurrentAuditFinding(
                    id=len(self.findings) + 1,
                    system="PIS_DISPLAY",
                    element="LED / LCD Yolcu Bilgilendirme Ekranları (PIS)",
                    issue="PIS paftasında yolcu bilgilendirme ekran sembolü tespit edilemedi.",
                    impact="Tren varış süreleri ve acil durum yönlendirme mesajları yolculara gösterilemez.",
                    correction="Peron tavanlarına çift yüzlü PIS ekranları, bilet holü girişlerine tek yüzlü ekranlar ekleyiniz.",
                    severity="UYARI"
                ))

    def _audit_industrial_weak_current(self):
        """
        Endüstriyel Tesis / Fabrika / Trafo Merkezi Zayıf Akım & Yangın Denetimi
        (BYKHY, TS EN 54-12 Beam Dedektör, TS EN 54-23 Görsel Flaşör VAD, EN 60079 ATEX)
        """
        fire = self.report.fire_alarm
        self.report.smatv.status = "KAPSAM_DIŞI (ENDÜSTRİYEL)"
        self.report.intercom.status = "KAPSAM_DIŞI (ENDÜSTRİYEL)"

        # 1. Yüksek Tavan (H > 8 m) Işın Tipi (Beam) Optik Duman Dedektörü (TS EN 54-12)
        if fire.beam_flame_detectors <= 0:
            self.findings.append(WeakCurrentAuditFinding(
                id=len(self.findings) + 1,
                system="YANGIN",
                element="Yüksek Tavan Işın Tipi (Beam) / Alev Dedektörü (TS EN 54-12)",
                issue="Endüstriyel yüksek tavanlı (H > 8 m) üretim/depo hollerinde Beam (Işın) tipi duman dedektörü veya Hava Örneklemeli (ASD) sistem tespit edilmedi.",
                impact="TS EN 54-14 uyarınca klasik noktasal duman dedektörleri 10.5 m üzerinde duman tabakalaşması (stratification) nedeniyle yangını algılayamaz!",
                correction="Üretim ve depo hollerinde çatı makas kotuna karşılıklı TS EN 54-12 onaylı Motorize Lazer Hizalamalı Beam Dedektörler yerleştiriniz.",
                severity="UYARI"
            ))

        # 2. Patlayıcı / Yanıcı Ortam (ATEX / Ex-Proof) ve Gaz Algılama (EN 60079)
        if fire.ex_proof_devices <= 0:
            self.findings.append(WeakCurrentAuditFinding(
                id=len(self.findings) + 1,
                system="YANGIN",
                element="ATEX / Ex-Proof Dedektör & Gaz Algılama (Kazan, Akü, Boyahane)",
                issue="Kazan dairesi, akü şarj odası, boyahane veya yanıcı sıvı depoları için Ex-Proof (ATEX Zone 1/2) gaz/alev dedektörü ve Zener bariyer belirtilmemiştir.",
                impact="Doğalgaz (CH4), Hidrojen (H2 - akü odası) veya solvent buharı birikiminde standart dedektörler patlama kaynağı oluşturabilir.",
                correction="Kazan dairesine doğalgaz+CO, akü odasına Ex-proof H2 dedektörü ekleyip selenoid gaz kesme vanası ve ex-proof egzoz fanı ile kilitleyiniz.",
                severity="UYARI"
            ))

        # 3. Yüksek Gürültülü Üretim Sahasında Flaşörlü Görsel Uyarıcı (VAD - TS EN 54-23)
        self.findings.append(WeakCurrentAuditFinding(
            id=len(self.findings) + 1,
            system="YANGIN",
            element="Endüstriyel Yüksek Desibelli Siren (>=100 dBA) & VAD Flaşör (TS EN 54-23)",
            issue="Makine gürültüsünün >85 dBA olduğu üretim hollerinde standart 85 dBA duvar sireni işitilemez.",
            impact="Kulaklık takan operatörlerin yangın tahliye alarmını fark edememesi can güvenliği riski doğurur.",
            correction="Üretim sahasında >=100-110 dBA motorlu korna sirenler ile TS EN 54-23 sertifikalı yüksek çakarlı kırmızı LED/Xenon Flaşör (VAD) birlikte kullanılmalıdır.",
            severity="BİLGİ"
        ))

        # 4. Trafo / AG-OG Pano Odası Gazlı Söndürme & Acil Durdurma (ESD) İnterlokları
        self.findings.append(WeakCurrentAuditFinding(
            id=len(self.findings) + 1,
            system="YANGIN",
            element="OG/Trafo/MCC Odaları Otomatik Gazlı Söndürme & HVAC/ESD İnterlok",
            issue="Trafo, OG Hücre, AG Ana Dağıtım (ADP/MCC) ve Server odalarında çapraz zonlu (Cross-Zone) söndürme ve enerji kesme otomasyonu teyidi.",
            impact="Yangın anında taze hava fanları ve proses konveyörleri durdurulmazsa yangın hızla yayılır.",
            correction="Yangın santralinden HVAC yangın damperlerine, MCC acil durdurma (shunt trip) bobinlerine ve gazlı söndürme panellerine izleme/kontrol modülü bağlayınız.",
            severity="BİLGİ"
        ))

    def _evaluate_verdict_and_score(self):
        """Projenin nihai zayıf akım karnesini ve puanını hesaplar."""
        criticals = [f for f in self.findings if f.severity == "KRİTİK"]
        warnings = [f for f in self.findings if f.severity == "UYARI"]

        penalty = (len(criticals) * 25.0) + (len(warnings) * 8.0)
        self.report.score_pct = max(0.0, min(100.0, 100.0 - penalty))

        if criticals:
            self.report.overall_verdict = "UYGUN DEĞİLDİR (YASAL / YÖNETMELİK EKSİKLİĞİ)"
        elif warnings:
            self.report.overall_verdict = "ŞARTLI UYGUN (DÜZELTİLMESİ GEREKEN UYARILAR VAR)"
        else:
            self.report.overall_verdict = "UYGUNDUR (TÜM ZAYIF AKIM STANDARTLARINA TAM UYUMLU)"
