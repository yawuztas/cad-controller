# -*- coding: utf-8 -*-
"""
CloudeCAD — 03_hesap_motoru
============================
Mühendislik çekirdeği: CAD Okuma, Triyaj, Güvenlik Kalkanı, Healer (Onarıcı)
ve Elektriksel Optimizasyon motorları.
"""
from pathlib import Path
import sys

_MOTOR_DIR = Path(__file__).resolve().parent
if str(_MOTOR_DIR) not in sys.path:
    sys.path.insert(0, str(_MOTOR_DIR))
