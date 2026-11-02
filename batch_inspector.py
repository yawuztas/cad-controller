# -*- coding: utf-8 -*-
"""
CloudeCAD — Otomatik Proje Denetim ve Klasör İzleme Servisi (Batch Inspector v2.0)
=================================================================================
Bu modül CloudeCAD v2.0 UniversalCADReader ve StationAuditEngine altyapısına
yönlendirilmiş modern köprüdür. 

Kullanım:
    python batch_inspector.py          (Mevcut projeleri denetler)
    python batch_inspector.py --watch  (Klasörü sürekli izler, yeni proje atıldıkça inceler)
"""

import sys
from pathlib import Path

# Windows konsolunda UTF-8 karakter uyumluluğu
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

_ROOT = Path(__file__).parent.resolve()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cloudecad import main, scan_all_projects, DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Parametresiz çağrıldığında (örn: otomatik_denetim.bat Seçenek 1)
        # Mevcut projeleri tara
        scan_all_projects(DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR)
    else:
        main()
