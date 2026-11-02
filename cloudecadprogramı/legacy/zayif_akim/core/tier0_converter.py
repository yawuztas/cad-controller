"""
CloudeCAD — Tier 0: DWG to DXF Dönüştürücü ve Önbellek Yöneticisi (Zayıf Akım)
=============================================================================
Öncelikle sistemdeki AutoCAD Core Console (accoreconsole.exe) kullanarak
DWG dosyalarını DXF'e dönüştürür. Bulunamazsa ODA File Converter'a geçer.
Eğer güncel bir DXF zaten mevcutsa doğrudan önbellekten kullanır.
"""

import os
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import Optional


ODA_CONVERTER_PATHS = [
    r"C:\Program Files\ODA\ODAFileConverter 26.1.0\ODAFileConverter.exe",
    r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe",
    r"C:\Program Files (x86)\ODA\ODAFileConverter\ODAFileConverter.exe",
]


def find_accoreconsole() -> Optional[Path]:
    """Sistemdeki AutoCAD Core Console çalıştırılabilir dosyasını dinamik olarak arar."""
    for year in range(2030, 2019, -1):
        p = Path(rf"C:\Program Files\Autodesk\AutoCAD {year}\accoreconsole.exe")
        if p.exists():
            return p

    autodesk_dir = Path(r"C:\Program Files\Autodesk")
    if autodesk_dir.exists():
        try:
            for sub in sorted(autodesk_dir.iterdir(), reverse=True):
                cand = sub / "accoreconsole.exe"
                if cand.exists():
                    return cand
        except Exception:
            pass

    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Autodesk\AutoCAD") as root_key:
            subkeys = []
            i = 0
            while True:
                try:
                    subkeys.append(winreg.EnumKey(root_key, i))
                    i += 1
                except OSError:
                    break
            for r_ver in sorted(subkeys, reverse=True):
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Autodesk\AutoCAD\{r_ver}") as r_key:
                        j = 0
                        while True:
                            try:
                                prod_key_name = winreg.EnumKey(r_key, j)
                                j += 1
                                try:
                                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Autodesk\AutoCAD\{r_ver}\{prod_key_name}") as prod_key:
                                        loc, _ = winreg.QueryValueEx(prod_key, "AcadLocation")
                                        cand = Path(loc) / "accoreconsole.exe"
                                        if cand.exists():
                                            return cand
                                except OSError:
                                    pass
                            except OSError:
                                break
                except OSError:
                    pass
    except Exception:
        pass

    which_path = shutil.which("accoreconsole.exe")
    if which_path:
        return Path(which_path)
    return None


def find_oda_converter() -> Optional[Path]:
    """Sistemde kurulu ODA File Converter yolunu döner."""
    for p in ODA_CONVERTER_PATHS:
        pth = Path(p)
        if pth.exists():
            return pth
    return None


def convert_dwg_via_accoreconsole(dwg_path: Path, dxf_path: Path) -> Path:
    """AutoCAD Core Console kullanarak DWG -> DXF çevrimi yapar."""
    accore = find_accoreconsole()
    if not accore:
        raise RuntimeError("accoreconsole.exe bulunamadı.")

    temp_dir = Path(tempfile.mkdtemp(prefix="cad_conv_za_"))
    temp_dwg = temp_dir / "input.dwg"
    temp_dxf = temp_dir / "output.dxf"
    scr_path = temp_dir / "script.scr"

    try:
        shutil.copy2(dwg_path, temp_dwg)
        clean_temp_dxf = str(temp_dxf).replace("\\", "/")
        script_cmds = [
            "FILEDIA 0",
            f'_DXFOUT "{clean_temp_dxf}" 16',
            "_QUIT",
            "_Y",
            "",
        ]
        scr_path.write_text("\n".join(script_cmds), encoding="utf-8")

        cmd = [
            str(accore),
            "/i", str(temp_dwg),
            "/s", str(scr_path),
            "/l", "en-US",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=120)

        if temp_dxf.exists() and temp_dxf.stat().st_size > 1000:
            shutil.copy2(temp_dxf, dxf_path)
            return dxf_path
        else:
            raise RuntimeError(f"AutoCAD Core Console DXF üretemedi: {result.stderr or result.stdout}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _get_central_cache_dxf_path(dwg_path: Path) -> Path:
    """Merkezi .dxf_cache klasöründe dosya boyutu ve mtime imzalı önbellek yolu döner."""
    cache_dir = Path(__file__).resolve().parents[3] / ".dxf_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    st = dwg_path.stat()
    safe_stem = "".join(c if c.isalnum() or c in "-_." else "_" for c in dwg_path.stem)
    cache_name = f"{safe_stem}_{st.st_size}_{int(st.st_mtime)}.dxf"
    return cache_dir / cache_name


def ensure_dxf(input_path: str) -> str:
    """
    DWG ise DXF'e çevirir ve yolunu döner. DXF ise doğrudan döner.
    Önce merkezi .dxf_cache ve yan yana DXF önbelleğini kontrol eder.
    """
    try:
        from common.dxf_converter import ensure_dxf as common_ensure_dxf
        return str(common_ensure_dxf(input_path, use_cache=True))
    except Exception:
        pass

    p = Path(input_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Proje dosyası bulunamadı: {p}")

    if p.suffix.lower() == ".dxf":
        return str(p)

    if p.suffix.lower() != ".dwg":
        raise ValueError(f"Desteklenmeyen dosya formatı: {p.suffix}")

    # 0. Öncelik: Merkezi .dxf_cache kontrolü
    cached_dxf = _get_central_cache_dxf_path(p)
    if cached_dxf.exists() and cached_dxf.stat().st_size > 1000:
        return str(cached_dxf)

    # Aynı isimli .dxf yan yana var mı kontrol et
    dxf_sibling = p.with_suffix(".dxf")
    if dxf_sibling.exists() and dxf_sibling.stat().st_mtime >= p.stat().st_mtime:
        try:
            shutil.copy2(dxf_sibling, cached_dxf)
        except Exception:
            pass
        return str(dxf_sibling)

    # 1. Öncelik: Topraklama Motorunun Çoklu Dönüştürücüsü (ODA / CoreConsole / COM)
    try:
        import importlib.util
        tm_conv_path = Path(__file__).resolve().parents[2] / "topraklama_motoru" / "core" / "tier0_converter.py"
        if tm_conv_path.exists():
            spec = importlib.util.spec_from_file_location("tm_tier0_conv", str(tm_conv_path))
            tm_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(tm_mod)
            res_dxf, _ = tm_mod.ensure_dxf(str(p))
            return str(res_dxf)
    except Exception:
        pass

    # 2. Öncelik: AutoCAD Core Console
    if find_accoreconsole() is not None:
        try:
            out_p = convert_dwg_via_accoreconsole(p, cached_dxf)
            return str(out_p)
        except Exception:
            pass

    # 3. Öncelik: ODA File Converter
    oda = find_oda_converter()
    if oda:
        out_dir = p.parent
        cmd = [
            str(oda),
            str(p.parent),
            str(out_dir),
            "ACAD2018",
            "DXF",
            "0",
            "1",
            p.name
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            if dxf_sibling.exists():
                try:
                    shutil.copy2(dxf_sibling, cached_dxf)
                except Exception:
                    pass
                return str(dxf_sibling)
        except Exception:
            pass

    # 4. Öncelik: Varsa eski DXF'e fallback
    if dxf_sibling.exists():
        return str(dxf_sibling)

    raise RuntimeError(
        "Ne AutoCAD Core Console ne de ODA File Converter bulunamadı.\n"
        "Lütfen DWG dosyasını AutoCAD ile DXF olarak kaydediniz veya ODA File Converter kurunuz."
    )
