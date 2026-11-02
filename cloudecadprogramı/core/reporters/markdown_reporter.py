# -*- coding: utf-8 -*-
"""
Kanıt ve Güven Puanı Destekli Raporlayıcı (MarkdownReporter)
============================================================
Deterministik mühendislik sonuçlarını, kanıt zincirlerini ve
'İncelenmesi Gereken Belirsizlikler' listesini içeren kapsamlı rapor üretir.
"""

from __future__ import annotations
from typing import List
from ..model.audit import StationAuditReport, AuditFinding, UncertaintyItem


def generate_markdown_report(report: StationAuditReport) -> str:
    crit = [f for f in report.findings if f.severity == "CRITICAL"]
    warn = [f for f in report.findings if f.severity == "WARNING"]
    passed = [f for f in report.findings if f.severity == "PASS"]
    uncert = report.uncertainties

    lines = []
    lines.append(f"# {report.station_code} {report.station_name} — Müşavir Kontrol Mühendisliği Birleşik Denetim ve Hesap Raporu\n")
    lines.append("> [!IMPORTANT]")
    lines.append(f"> **Denetim Kapsamı:** Bu rapor, CloudeCAD v2.0 Deterministik Mühendislik Motoru ve Kural Paketleri")
    lines.append(f"> (`{report.rule_pack_used}`) tarafından **{report.total_sheets_analyzed} pafta**, ")
    lines.append(f"> **{len(report.panel_summaries)} birleşik pano**, **{len(report.circuit_calculations)} linye hesabı** ")
    lines.append(f"> ve **{len(report.reconciliation_items)} çapraz mutabakat maddesi** üzerinde otomatik olarak üretilmiştir.\n")
    lines.append(f"- **Taranan Pafta Sayısı:** {report.total_sheets_analyzed}")
    lines.append(f"- **Kullanılan Kural Paketi:** `{report.rule_pack_used}`")
    lines.append(f"- **Mühendislik Bulguları:** 🔴 **{len(crit)} Kritik Hata** | 🟡 **{len(warn)} Uyarı** | 🟢 **{len(passed)} Standartlara Uygun**")
    lines.append(f"- **İncelenmesi Gereken Belirsizlikler:** ℹ️ **{len(uncert)} Adet Belirsizlik / İnceleme Maddesi**\n")
    lines.append("---\n")

    # 1. YÖNETİCİ ÖZETİ
    lines.append("## 1. Yönetici Özeti: Öncelikli Mühendislik Bulguları ve Güven Dereceleri\n")
    if crit or warn:
        lines.append("| Seviye | Kod | Güven Puanı | Bulgu Başlığı | Tespit Edilen Değer / Kanıt | Standart Sınırı |")
        lines.append("| :---: | :--- | :---: | :--- | :--- | :--- |")
        for f in crit:
            c_badge = f"**`%{f.confidence_score * 100:.0f}`** ({f.confidence_level})"
            lines.append(f"| 🔴 **KRİTİK** | `{f.code}` | {c_badge} | **{f.title}** | {f.measured_value} | {f.standard_limit} |")
        for f in warn:
            c_badge = f"**`%{f.confidence_score * 100:.0f}`** ({f.confidence_level})"
            lines.append(f"| 🟡 **UYARI** | `{f.code}` | {c_badge} | **{f.title}** | {f.measured_value} | {f.standard_limit} |")
    else:
        lines.append("🟢 *Kritik veya uyarı gerektiren herhangi bir uygunsuzluk tespit edilmemiştir; tüm sistemler standartlara uygundur.*\n")
    lines.append("\n---\n")

    # 2. İNCELENMESİ GEREKEN BELİRSİZLİKLER LİSTESİ (Manifestodaki Kilit İlke)
    lines.append("## 2. Mühendis İncelemesi Gerektiren Belirsizlikler (Uncertainty Review List)\n")
    lines.append("> [!NOTE]")
    lines.append("> Çizimdeki eksiklik, açıkta kalan etiket veya belirsizliklerden dolayı doğrudan 'Kritik Hata' ilan edilmeyip,")
    lines.append("> mühendisin yerinde veya projede doğrulamasını gerektiren maddeler bu bölümde listelenir.\n")
    if uncert:
        lines.append("| Kod | Kapsam | Şüpheli Eleman | Güven Skoru | Çizimdeki Kanıt / Belirti | Tavsiye Edilen Doğrulama |")
        lines.append("| :--- | :--- | :--- | :---: | :--- | :--- |")
        for u in uncert:
            lines.append(f"| `{u.code}` | {u.floor_or_scope} | `{u.suspected_element}` | %{u.confidence_score*100:.0f} | {u.evidence} | {u.recommended_verification} |")
    else:
        lines.append("🟢 *Çizimde sınıflandırılamayan veya şüpheli kalan herhangi bir kritik belirsizlik bulunmamaktadır.*\n")

    ts = report.symbol_triage_summary or {}
    if ts:
        lines.append("\n**Sembol Triyajı Sayısal Özeti (hiçbir blok sessizce silinmez):**\n")
        lines.append("| Kategori | Adet | Anlamı |")
        lines.append("| :--- | :---: | :--- |")
        lines.append(f"| `IGNORED_ARCHITECTURAL` | {ts.get('IGNORED_ARCHITECTURAL', 0)} | Mimari/XREF olduğu kanıtlandı ve elektrik izi yok; belirsizlik listesi dışında tutuldu |")
        lines.append(f"| `UNCERTAIN_ELECTRICAL` | {ts.get('UNCERTAIN_ELECTRICAL', 0)} | Elektrik katmanında / elektrik sembolü veya etiketi yakınında; belirsizlikte tutuldu |")
        lines.append(f"| `UNCLASSIFIED` | {ts.get('UNCLASSIFIED', 0)} | Kanıt yok; belirsizlikte tutuldu |")
        lines.append("")
    lines.append("\n---\n")

    # 3. BİRLEŞİK PANO CETVELİ
    lines.append("## 3. Dağıtım Panoları Yük ve Faz Dengesi Cetveli\n")
    if report.panel_summaries:
        lines.append("| Pano Kodu | Kat / Mahal | Linye | Armatür/Priz | L1 Fazı (W) | L2 Fazı (W) | L3 Fazı (W) | Toplam Güç (kW) | Güç Kaynağı | Faz Dengesi (%Δ) | Sonuç |")
        lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        for p in report.panel_summaries:
            s_icon = "🟢 **UYGUN**" if p.imbalance_pct <= 15.0 else ("🟡 **UYARI**" if p.imbalance_pct <= 25.0 else "🔴 **KRİTİK**")
            pwr_src_badge = "KESİN (Çizim/Lejant)" if p.power_source == "EXPLICIT" else ("⚠️ TAHMİNİ YÜK" if p.power_source == "ESTIMATED_DEFAULT" else p.power_source)
            lines.append(
                f"| **`{p.panel_tag}`** | {p.floor_name} | {p.circuit_count} | {p.total_fixtures} | "
                f"{p.l1_power_w:,.0f} W | {p.l2_power_w:,.0f} W | {p.l3_power_w:,.0f} W | **{p.total_power_w / 1000.0:.2f} kW** | "
                f"`{pwr_src_badge}` | **`%{p.imbalance_pct:.1f}`** | {s_icon} |"
            )
    else:
        lines.append("*Pano yük özeti bulunamadı.*\n")
    lines.append("\n---\n")

    # 3.B LİNYE / DEVRE HESAPLARI VE VERİ KAYNAĞI İZLENEBİLİRLİK TABLOSU
    if report.circuit_calculations:
        lines.append("## 3.B. Linye / Devre Mühendislik Hesapları ve Veri Kaynağı İzlenebilirliği\n")
        lines.append("| Linye Kodu | Pano | Kablo Kesiti | Güç (W) | Akım Ib (A) | Akım Taşıma Iz (A) | Gerilim Düşümü (%e) | Kablo Kaynağı | Güç Kaynağı | Mesafe Kaynağı | Güven | Sonuç |")
        lines.append("| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        for cc in report.circuit_calculations[:60]:
            iz_str = f"{cc.ampacity_iz_a:.1f} A" if cc.ampacity_iz_a is not None else "Belirsiz"
            vd_str = f"%{cc.voltage_drop_pct:.2f}" if cc.voltage_drop_pct is not None else "Hesaplanamadı"
            if cc.status == "UYGUN":
                st_badge = "🟢 UYGUN"
            elif cc.status == "UYGUN (TAHMİNİ YÜK/MESAFE)":
                st_badge = "🟡 TAHMİNİ UYGUN"
            elif cc.status == "VERİ_YETERSİZ":
                st_badge = "⚪ VERİ YETERSİZ"
            else:
                st_badge = f"🔴 {cc.status}"
            c_spec_str = f"{cc.cable_cross_section} {cc.cable_type}".strip()
            lines.append(
                f"| `{cc.circuit_no}` | `{cc.panel_tag}` | `{c_spec_str}` | {cc.power_w:,.0f} | "
                f"{cc.current_ib_a:.2f} A | {iz_str} | {vd_str} | `{cc.cable_source}` | `{cc.power_source}` | `{cc.length_source}` | "
                f"%{cc.confidence_score*100:.0f} | {st_badge} |"
            )
        if len(report.circuit_calculations) > 60:
            lines.append(f"\n*... ve {len(report.circuit_calculations) - 60} linye hesabı daha JSON raporunda yer almaktadır.*\n")
        lines.append("\n---\n")

    # 4. ÇAPRAZ MUTABAKAT (RECONCILIATION)
    lines.append("## 4. Paftalar Arası Çapraz Mutabakat (Reconciliation) Denetimi\n")
    if report.reconciliation_items:
        lines.append("| Kategori | Pafta | Eleman / Linye | Çizim / Plan Değeri | Referans / Tablo Değeri | Durum | Detay |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :---: | :--- |")
        for r in report.reconciliation_items:
            s_icon = "🟢 UYGUN" if r.status == "UYGUN" else ("🟡 UYARI" if r.status == "EKSİK" else "🔴 UYUŞMAZLIK")
            lines.append(f"| {r.category} | {r.sheet_name} | `{r.item_id}` | {r.source_a_label} | {r.source_b_label} | {s_icon} | {r.detail} |")
    else:
        lines.append("*Çapraz mutabakat öğesi bulunamadı.*\n")
    lines.append("\n---\n")

    # 5. ZAYIF AKIM ALT SİSTEMLERİ
    if report.weak_current_audits:
        lines.append("## 5. Zayıf Akım Sistemleri Mühendislik Analizi\n")
        lines.append("| Kod | Alt Sistem Adı | Kolon Şeması | Kat Planı | Plan Cihazı | FE180 Durumu | CAT6 / Mesafe | Sonuç |")
        lines.append("| :---: | :--- | :---: | :---: | :---: | :--- | :--- | :---: |")
        for za in report.weak_current_audits:
            res_icon = "🟢 UYGUN" if za.engineering_status == "UYGUN" else "🟡 UYARI"
            riser_txt = "Var" if za.riser_sheets else "-"
            plan_txt = f"{len(za.plan_sheets)} Pafta" if za.plan_sheets else "-"
            if za.has_fiber_backbone:
                cat6_txt = "SM F/O Omurga"
            elif za.has_cat6_cables:
                if za.max_station_span_m is not None:
                    cat6_txt = f"CAT6 ({za.max_station_span_m:.1f}m)"
                else:
                    cat6_txt = "CAT6 (Mesafe Ölçülemedi)"
            else:
                cat6_txt = "-"
            lines.append(
                f"| `{za.sys_code}` | **{za.sys_name}** | {riser_txt} | {plan_txt} | {za.plan_symbol_count} Sembol | "
                f"{za.fe180_status} | {cat6_txt} | {res_icon} |"
            )
        lines.append("\n---\n")

    # 6. TOPRAKLAMA VE KABLO TAVASI
    if report.grounding_tray_summaries:
        lines.append("## 6. Topraklama ve Kablo Tavası Mühendislik Analizi\n")
        lines.append("| Mahal / Kat | Eşpotansiyel Baralar (ECB) | Pano Topraklama Bağlantıları | İletken Kesitleri | Tava Noktaları | Doluluk |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for gt in report.grounding_tray_summaries:
            ecb_str = ", ".join(gt.ecb_bars[:3]) if gt.ecb_bars else "-"
            ts_str = f"{len(gt.ts28_panel_bonds)} Adet Bağlantı" if gt.ts28_panel_bonds else "-"
            cond_str = ", ".join(gt.conductor_specs[:3]) if gt.conductor_specs else "-"
            tray_str = f"LV: {gt.lv_tray_count}, WC: {gt.wc_tray_count}"
            lv_fill_str = f"LV: %{gt.estimated_lv_fill_pct:.1f}" if gt.estimated_lv_fill_pct is not None else "LV: Hesaplanamadı"
            wc_fill_str = f"WC: %{gt.estimated_wc_fill_pct:.1f}" if gt.estimated_wc_fill_pct is not None else "WC: Hesaplanamadı"
            fill_str = f"{lv_fill_str}, {wc_fill_str}"
            lines.append(f"| **{gt.floor_name}** | {ecb_str} | {ts_str} | {cond_str} | {tray_str} | {fill_str} |")
        lines.append("\n---\n")

    # 7. DETAYLI BULGULAR VE KANIT ZİNCİRİ
    lines.append("## 7. Detaylı Mühendislik Bulguları ve Kanıt Zincirleri\n")
    for i, f in enumerate(report.findings, 1):
        sev_label = "🔴 KRİTİK UYGUNSUZLUK" if f.severity == "CRITICAL" else ("🟡 MÜHENDİSLİK UYARISI" if f.severity == "WARNING" else "🟢 UYGUNLUK ONAYI")
        lines.append(f"### 7.{i}. [{f.code}] {f.title} ({sev_label})\n")
        lines.append(f"- **Kapsam / Mahal:** {f.floor_or_scope}")
        lines.append(f"- **İlgili Paftalar:** {', '.join(f.sheet_names[:4])}")
        lines.append(f"- **Güven Seviyesi:** **{f.confidence_level}** (Skor: `%{f.confidence_score * 100:.0f}`)")
        lines.append(f"- **Ölçülen / Tespit Edilen Değer:** `{f.measured_value}`")
        std_detail = f.standard_ref
        if f.standard_version:
            std_detail += f" | Sürüm: `{f.standard_version}`"
        if f.clause_or_table:
            std_detail += f" | Madde/Tablo: `{f.clause_or_table}`"
        lines.append(f"- **Standart / Şartname Sınırı:** `{f.standard_limit}` ({std_detail})")
        if f.data_sources:
            ds_str = ", ".join(f"`{k}={v}`" for k, v in f.data_sources.items())
            lines.append(f"- **Veri Kaynağı İzlenebilirliği:** {ds_str}")
        if f.assumptions_used:
            lines.append(f"- **Kullanılan Varsayımlar:** {'; '.join(f.assumptions_used)}")
        lines.append(f"- **Mühendislik Değerlendirmesi:** {f.engineering_explanation}")
        if f.evidence_chain:
            lines.append("- **Tespit Kanıt Zinciri (Evidence Chain):**")
            for ev in f.evidence_chain:
                lines.append(f"  - 🔎 {ev}")
        lines.append(f"- **Çözüm / Uygulama Önerisi:** {f.recommendation}\n")

    return "\n".join(lines)
