"""
CloudeCAD — Tier 2: Proje Tipolojisi Algılayıcı (Typology Detector)
===================================================================
Çizimdeki panoları, katman adlarını ve metin anahtarlarını analiz ederek
projenin tipolojisini (Konut, Metro/Altyapı, Endüstriyel, Ticari)
otomatik tespit eder.
"""

from typing import Dict, List, Tuple
from core.models import ExtractedProjectData
from standards.typology_standards import ProjectTypology


class TypologyDetector:
    """Projenin mimari ve elektriksel karakteristiğini sınıflandıran motor."""

    @classmethod
    def detect(cls, proj_data: ExtractedProjectData) -> Tuple[ProjectTypology, float, str]:
        """
        Dönüş: (typology, confidence, rationale)
        """
        all_text_tokens = []
        all_text_tokens.append(proj_data.project_name.lower())
        all_text_tokens.extend([pname.lower() for pname in proj_data.sub_panels.keys()])

        # Tüm linyelerin açıklamalarını ekle
        for sp in proj_data.sub_panels.values():
            for c in sp.circuits:
                all_text_tokens.append(c.description.lower())
                all_text_tokens.append(c.circuit_no.lower())

        # Ham CAD metinlerini de (ilk 250 metin) dahil et
        if getattr(proj_data, "raw_cad_texts", None):
            all_text_tokens.extend([str(t).lower() for t in proj_data.raw_cad_texts[:250]])

        combined_text = " ".join(all_text_tokens)

        if getattr(proj_data, "is_metro_plan_sheet", False):
            st = getattr(proj_data, "metro_station_code", "METRO")
            disc = getattr(proj_data, "metro_sheet_discipline", "KUVVET / AYDINLATMA / PRİZ")
            return (
                ProjectTypology.INFRASTRUCTURE_METRO,
                0.98,
                f"Raylı Sistem / Metro İstasyonu ({st} — {disc}) uygulama ve kablo metraj paftası tespit edildi. NFPA 130, EN 50122 ve TS HD 60364 metro normları devrede."
            )

        # 1. Metro / Raylı Sistem / Tünel Kontrolü
        metro_score = 0
        metro_keywords = [
            'metro', 'istasyon', 'station', 'tvf', 'tünel', 'tunel', 'catenary',
            'traksiyon', 'traction', 'peron', 'concourse', 'bilet hol', 'ag-prt',
            'm09', 'm07', 'm11', 'm12', 'raylı', 'rayli', 'katener', 'vld', 'aygm'
        ]
        for kw in metro_keywords:
            if kw in combined_text:
                metro_score += 3
        if any(p.startswith('MCC-TVF') or 'TVF' in p for p in proj_data.sub_panels):
            metro_score += 10

        if metro_score >= 5:
            return (
                ProjectTypology.INFRASTRUCTURE_METRO,
                min(1.0, 0.65 + metro_score * 0.05),
                f"Metro / Raylı Sistem / Tünel altyapısı ve yükleri tespit edildi (Puan: {metro_score}). NFPA 130 ve EN 50122 metro normu devrede."
            )

        # 2. Endüstriyel / Fabrika / Trafo Merkezi Kontrolü
        ind_score = 0
        ind_keywords = [
            'fabrika', 'endüstriyel', 'endustriyel', 'üretim', 'kompresör', 'vinç',
            'atölye', 'kaynak', 'pres', 'trafo merkezi', 'mcc', 'osb', 'şalt', 'salt',
            '154kv', '34.5kv', 'gis', 'ais', 'proses', 'kazan dairesi'
        ]
        for kw in ind_keywords:
            if kw in combined_text:
                ind_score += 2

        if ind_score >= 4:
            return (
                ProjectTypology.INDUSTRIAL,
                min(1.0, 0.55 + ind_score * 0.08),
                f"Endüstriyel tesis / ağır motor ve trafo merkezi dağıtım yapısı tespit edildi (Puan: {ind_score}). IEC 60364 / IEC 60909 normu devrede."
            )

        # 3. Ticari / AVM / Ofis Kontrolü
        comm_score = 0
        comm_keywords = ['avm', 'mall', 'ofis', 'office', 'mağaza', 'chiller', 'otel', 'plaza', 'kule']
        for kw in comm_keywords:
            if kw in combined_text:
                comm_score += 2

        if comm_score >= 4:
            return (
                ProjectTypology.COMMERCIAL,
                min(1.0, 0.5 + comm_score * 0.08),
                f"Merkezi iklimlendirme ve ticari alan yükleri tespit edildi (Puan: {comm_score})."
            )

        # 4. Konut / Apartman Kontrolü (Varsayılan Türk Konut Projeleri)
        res_score = 0
        res_keywords = ['daire', 'apart', 'konut', 'site', 'blok', 'ev', 'mutfak', 'çamaşır', 'bulaşık', 'fırın']
        for kw in res_keywords:
            if kw in combined_text:
                res_score += 2
        # DT-1..n varlığı güçlü bir konut işaretidir
        dt_panels = [p for p in proj_data.sub_panels if p.startswith('DT-') or p == 'D-T']
        if dt_panels:
            res_score += 10

        if res_score >= 4:
            return (
                ProjectTypology.RESIDENTIAL,
                0.95,
                f"{len(dt_panels)} adet konut/daire tablosu ve tipik ev aletleri linyeleri tespit edildi. BEDAŞ/TEDAŞ konut normu devrede."
            )

        return (
            ProjectTypology.GENERAL,
            0.50,
            "Genel elektrik tesisatı yükleri tespit edildi. Standart IEC 60364 kural seti devrede."
        )
