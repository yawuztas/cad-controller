# -*- coding: utf-8 -*-
"""
Yapılandırılabilir Kural ve Standartlar Motoru (RuleEngine)
===========================================================
Kural ve standart sınırlarını koddan ayırır; YAML/JSON kural paketlerinden okur.
"""

from __future__ import annotations
import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger("CloudeCAD.RuleEngine")

_MEVZUAT_DIR = Path(__file__).resolve().parents[3] / "02_mevzuat_ve_formuller"
_PACKS_DIR = Path(__file__).parent / "packs"
_RULES_DIR = _MEVZUAT_DIR if _MEVZUAT_DIR.exists() else _PACKS_DIR


class RuleEngine:
    _instance: Optional["RuleEngine"] = None
    _cached_packs: Dict[str, Dict[str, Any]] = {}

    def __init__(self, default_pack: str = "turkey_bina"):
        self.active_pack_name = default_pack
        self.active_pack: Dict[str, Any] = self.load_pack(default_pack)

    @classmethod
    def get_instance(cls, default_pack: str = "turkey_bina") -> "RuleEngine":
        if cls._instance is None:
            cls._instance = cls(default_pack=default_pack)
        return cls._instance

    @classmethod
    def load_pack(cls, pack_name_or_path: str) -> Dict[str, Any]:
        """YAML veya JSON kural paketini yükler ve önbelleğe alır.
        Klasör verilirse (örn: 'bina' veya 'metro') içindeki tüm alt disiplinleri
        (topraklama, kuvvetli_akim, zayif_akim) birleşik paket olarak yükler."""
        p = Path(pack_name_or_path)

        def _merge_dir(d: Path) -> Dict[str, Any]:
            merged: Dict[str, Any] = {}
            for yf in sorted(d.glob("*.yaml")) + sorted(d.glob("*.yml")):
                if yaml is not None:
                    with open(yf, "r", encoding="utf-8") as f:
                        part = yaml.safe_load(f) or {}
                        merged.update(part)
            return merged

        # 1. Önce tam dosya adı kontrolü (örn: turkey_bina.yaml veya ibb_metro.yaml)
        cand_yaml = _RULES_DIR / f"{pack_name_or_path}.yaml"
        cand_json = _RULES_DIR / f"{pack_name_or_path}.json"
        if cand_yaml.is_file():
            p = cand_yaml
        elif cand_json.is_file():
            p = cand_json
        elif p.is_file():
            pass
        else:
            # 2. Klasör kontrolü (örn: 'bina' veya 'metro') -> altındaki yaml'ları birleştir
            target_dir = None
            if p.is_dir():
                target_dir = p
            elif (_RULES_DIR / pack_name_or_path).is_dir():
                target_dir = _RULES_DIR / pack_name_or_path

            if target_dir is not None:
                cache_key = str(target_dir.resolve())
                if cache_key in cls._cached_packs:
                    return cls._cached_packs[cache_key]
                data = _merge_dir(target_dir)
                cls._cached_packs[cache_key] = data
                return data

            # 3. Alt klasörlerde ara (örn: bina/01_topraklama veya topraklama)
            found = list(_RULES_DIR.rglob(f"*{pack_name_or_path}*.yaml"))
            if found:
                p = found[0]
            elif (_RULES_DIR / "turkey_bina.yaml").exists():
                p = _RULES_DIR / "turkey_bina.yaml"
            elif (_RULES_DIR / "bina" / "02_kuvvetli_akim.yaml").exists():
                p = _RULES_DIR / "bina" / "02_kuvvetli_akim.yaml"

        cache_key = str(p.resolve())
        if cache_key in cls._cached_packs:
            return cls._cached_packs[cache_key]

        data: Dict[str, Any] = {}
        if p.is_file() and p.suffix in (".yaml", ".yml"):
            if yaml is not None:
                with open(p, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            else:
                logger.warning(f"PyYAML modülü bulunamadı, varsayılan kural değerleri kullanılıyor.")
        elif p.is_file() and p.suffix == ".json":
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)

        cls._cached_packs[cache_key] = data
        return data

    def select_pack_for_project(self, project_metadata: Dict[str, Any]) -> str:
        """Proje niteliğine göre en uygun kural paketini seçer."""
        st_code = str(project_metadata.get("station_code", "")).upper()
        sheet_title = str(project_metadata.get("sheet_title", "")).upper()
        discipline = str(project_metadata.get("system_discipline", "")).upper()

        # Metro / Raylı Sistem Tespiti
        if (
            st_code.startswith("S") and len(st_code) == 3
            or "İSTASYONU" in sheet_title
            or "METRO" in sheet_title
            or "M09" in sheet_title
            or "M3-" in sheet_title
        ):
            self.active_pack_name = "ibb_metro"
            self.active_pack = self.load_pack("ibb_metro")
            return "ibb_metro"

        # Klasik Türk Bina / Tesis Tespiti
        self.active_pack_name = "turkey_bina"
        self.active_pack = self.load_pack("turkey_bina")
        return "turkey_bina"

    # --------------------------------------------------------------------------
    # MÜHENDİSLİK SINIR DEĞERLERİ VE KONTROL FONKSİYONLARI
    # --------------------------------------------------------------------------
    @property
    def pack_name(self) -> str:
        return self.active_pack.get("name", "VARSAYILAN ELEKTRİK STANDARDI")

    def get_vd_limit(self, circuit_type: str = "AYDINLATMA") -> float:
        vd_limits = self.active_pack.get("voltage_drop_limits", {})
        if "AYD" in circuit_type.upper():
            return float(vd_limits.get("lighting_max_pct", 1.5))
        return float(vd_limits.get("socket_power_max_pct", 3.0))

    def get_copper_conductivity(self) -> float:
        return float(self.active_pack.get("cable_physics", {}).get("copper_conductivity", 56.0))

    def get_derating_factor(self) -> float:
        return float(self.active_pack.get("cable_physics", {}).get("derating_factor", 0.85))

    def get_ampacity_detailed(
        self,
        cond_mm2: float,
        cable_type: str = "",
        is_3phase: bool = False,
        install_method: str = "",
        apply_derating: bool = True,
    ) -> Tuple[Optional[float], str, List[str]]:
        """
        TS HD 60364-5-52:2014 tablolarına göre yalıtım tipi (PVC 70°C vs XLPE 90°C),
        yüklü iletken sayısı (1 Faz: 2 yüklü, 3 Faz: 3 yüklü) ve referans döşeme yöntemini (B1/C/E)
        dikkate alarak düzeltilmiş akım taşıma kapasitesini (Iz), ilgili standart maddesini ve
        kullanılan varsayımları döner.
        """
        if cond_mm2 <= 0.0:
            return None, "Tanımsız Kesit (<=0)", []

        assumptions: List[str] = []
        ct_up = cable_type.strip().upper()
        tables = self.active_pack.get("ampacity_tables_tshd60364", {})
        derating = self.get_derating_factor() if apply_derating else 1.0
        default_method = str(self.active_pack.get("cable_physics", {}).get("default_installation_method", "C"))
        method = install_method.strip().upper() or default_method

        if not install_method:
            assumptions.append(
                f"Döşeme yöntemi çizimde belirtilmediği için Referans Yöntem {method} ve gruplama/sıcaklık katsayısı (k={derating:.2f}) uygulandı"
            )

        if any(k in ct_up for k in ["N2X", "NHXMH", "NA2X", "XLPE", "EPR", "FE180", "FE-180"]):
            insul_key = "XLPE_90C"
        elif any(k in ct_up for k in ["NYY", "NYM", "H07V", "PVC", "LIHCH"]):
            insul_key = "PVC_70C"
        else:
            insul_key = "XLPE_90C" if self.active_pack.get("code") == "IBB_METRO_CODE" else "PVC_70C"
            if not ct_up:
                assumptions.append(f"Kablo yalıtım tipi çizimde yazılı olmadığından {insul_key} tablosu baz alındı")

        loaded_str = "3_LOADED" if is_3phase else "2_LOADED"
        table_key = f"{method}_{loaded_str}"

        insul_block = tables.get(insul_key, {})
        clause_str = str(insul_block.get("clause", self.get_standard_reference("ampacity")))
        sub_table = insul_block.get(table_key) or insul_block.get(f"C_{loaded_str}") or {}
        num_map = {float(k): float(v) for k, v in sub_table.items()}

        if cond_mm2 not in num_map:
            base_map = self.active_pack.get("ampacity_base_a", {})
            num_map = {float(k): float(v) for k, v in base_map.items()}
            if cond_mm2 not in num_map:
                return None, f"{clause_str} [Tanımsız Kesit: {cond_mm2} mm²]", assumptions

        base_iz = num_map[cond_mm2]
        return round(base_iz * derating, 1), f"{clause_str} [{insul_key}, Yöntem {method}, {loaded_str}, k={derating:.2f}]", assumptions

    def get_ampacity_a(self, cond_mm2: float, cable_type: str = "", is_3phase: bool = False) -> Optional[float]:
        """Kablo anma kesitine göre sıcaklık/grup derating uygulanmış akım taşıma kapasitesi (Iz)."""
        iz, _, _ = self.get_ampacity_detailed(cond_mm2, cable_type=cable_type, is_3phase=is_3phase)
        return iz

    def evaluate_phase_imbalance(self, imbalance_pct: float) -> Tuple[str, str]:
        """Faz yük dengesizliğini değerlendirir."""
        limits = self.active_pack.get("phase_imbalance_limits", {})
        warn_pct = float(limits.get("warning_pct", 15.0))
        crit_pct = float(limits.get("critical_pct", 25.0))

        if imbalance_pct > crit_pct:
            return "KRİTİK_DENGESİZLİK", f"Faz dengesizliği (%{imbalance_pct:.1f}) izin verilen kritik sınırın (%{crit_pct:.0f}) üzerindedir!"
        elif imbalance_pct > warn_pct:
            return "UYARI", f"Faz dengesizliği (%{imbalance_pct:.1f}) tavsiye edilen sınırın (%{warn_pct:.0f}) üzerindedir."
        return "UYGUN", f"Faz yük dağılımı dengelidir (<= %{warn_pct:.0f})."

    def get_phase_limits_text(self) -> str:
        """Aktif kural paketindeki faz dengesizliği sınırlarını rapor metni olarak döner.
        Raporlarda standart_limit alanı asla sabit yazılmaz; bu metottan türetilir."""
        limits = self.active_pack.get("phase_imbalance_limits", {})
        warn_pct = float(limits.get("warning_pct", 15.0))
        crit_pct = float(limits.get("critical_pct", 25.0))
        return f"Maks. %{warn_pct:.0f} (Uyarı) / %{crit_pct:.0f} (Kritik)"

    def check_protection_coordination(
        self, ib_current_a: float, in_mcb_a: float, iz_cable_a: float, in_rcd_a: Optional[float] = None
    ) -> List[str]:
        """
        TS HD 60364-4-43 ve IEC 60364 uyarınca:
        1) Ib <= In <= Iz (İşletme Akımı <= Sigorta Anma Akımı <= Kablo Akım Taşıma Kapasitesi)
        2) In_RCD >= In_MCB (Kaçak Akım Rölesi anma akımı kendisini koruyan sigortadan küçük olamaz)
        """
        issues: List[str] = []
        if ib_current_a > in_mcb_a:
            issues.append(f"İşletme Akımı ({ib_current_a:.1f}A) > Sigorta Anma Akımı ({in_mcb_a:.1f}A) [Nominal aşırı yük!]")
        if in_mcb_a > iz_cable_a:
            issues.append(f"Sigorta Anma Akımı ({in_mcb_a:.1f}A) > Kablo Akım Taşıma Kapasitesi Iz ({iz_cable_a:.1f}A) [Kablo korunamaz!]")
        if in_rcd_a is not None and in_rcd_a < in_mcb_a:
            issues.append(f"Kaçak Akım Rölesi Anma Akımı ({in_rcd_a:.1f}A) < Ön Sigorta Anma Akımı ({in_mcb_a:.1f}A) [KAK termik hasar riski!]")
        return issues

    def is_fe180_required(self, panel_tag: str, circuit_no: str = "", system_code: str = "") -> bool:
        """Yangına dayanıklı (FE180 / E90) kablo zorunluluğu kontrolü."""
        p_up = panel_tag.upper()
        s_up = system_code.upper()
        c_up = circuit_no.upper()

        # Yangın pompası, duman tahliye veya acil durum devreleri
        if any(k in p_up for k in ["İAP-E", "IAPE", "CDB", "MCC_E", "YANGIN", "FPP", "FACP"]):
            return True
        if any(k in c_up for k in ["YANGIN", "POMPA", "DUMAN", "BASINÇLANDIRMA"]):
            return True
        if s_up in ("AX-02", "TL-05"):
            return True
        return False

    def get_standard_reference(self, topic: str) -> str:
        refs = self.active_pack.get("standard_references", {})
        return str(refs.get(topic, "TS HD 60364 & Elektrik İç Tesisleri Yönetmeliği"))
