"""
CloudeCAD — Tier 0: DWG -> DXF Dönüştürücü (Akıllı Önbellekli & Çoklu Motorlu)
==============================================================================
Merkezi .dxf_cache klasörünü kullanarak değişmemiş DWG dosyalarını 0.005 saniyede
önbellekten döner; yeni DWG dosyalarını ise AutoCAD Core Console, AutoCAD COM
veya ODA File Converter ile dönüştürür.
"""

import shutil
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _get_central_dxf_cache_dir() -> Path:
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    cache_dir = root_dir / ".dxf_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def ensure_dxf(file_path: str, use_cache: bool = True) -> str:
    """
    Verilen dosya .dxf ise doğrudan döner, .dwg ise önce merkezi .dxf_cache'i
    kontrol eder; yoksa topraklama_motoru/core/tier0_converter motoru üzerinden
    dönüştürüp önbelleğe kaydeder.
    """
    p = Path(file_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Dosya bulunamadı: {p}")

    suffix = p.suffix.lower()
    if suffix == ".dxf":
        return str(p)
    elif suffix == ".dwg":
        if use_cache:
            try:
                stat = p.stat()
                cache_dir = _get_central_dxf_cache_dir()
                cache_name = f"{p.stem}_{stat.st_size}_{int(stat.st_mtime)}.dxf"
                cached_dxf = cache_dir / cache_name
                if cached_dxf.exists() and cached_dxf.stat().st_size > 1000:
                    logger.info(f"⚡ DXF merkezi önbellekten okundu: {p.name}")
                    return str(cached_dxf)
            except Exception:
                pass

        # Aynı klasörde güncel DXF var mı kontrol et
        candidate_dxf = p.with_suffix(".dxf")
        if candidate_dxf.exists() and candidate_dxf.stat().st_mtime >= p.stat().st_mtime and candidate_dxf.stat().st_size > 1000:
            return str(candidate_dxf)

        # Ortak Tier-0 dönüştürücüyü çağır (AutoCAD Core Console + COM + ODA Converter destekli)
        import importlib.util
        repo_root = Path(__file__).resolve().parent.parent.parent
        tm_conv_path = repo_root / "topraklama_motoru" / "core" / "tier0_converter.py"
        spec = importlib.util.spec_from_file_location("tm_tier0_converter", str(tm_conv_path))
        tm_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tm_mod)
        dxf_out = tm_mod.ensure_dxf(p, use_cache=use_cache)
        return str(dxf_out)
    else:
        raise ValueError(f"Desteklenmeyen dosya formatı: {p.suffix}")
