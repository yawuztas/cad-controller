# -*- coding: utf-8 -*-
"""
Tek Merkezi CAD Metin Temizleyici ve Türkçe Normalizasyon Modülü
=================================================================
Tüm projedeki dağınık `clean_turkish_text`, `_norm_tr` ve `_tu` kopyalarının
yerini alır. MTEXT satır yapısını (`\\P` -> ayrı satırlar) korur ve hem ham
satır listesini hem tek-satır çıktısını döner.
"""

from __future__ import annotations
import re
from typing import List, Tuple

_UNICODE_AND_SYMBOL_REPLACEMENTS: Tuple[Tuple[str, str], ...] = (
    (r"\\U\+0130", "İ"),
    (r"\\U\+0131", "ı"),
    (r"\\U\+015E", "Ş"),
    (r"\\U\+015F", "ş"),
    (r"\\U\+011E", "Ğ"),
    (r"\\U\+011F", "ğ"),
    (r"\\U\+00DC", "Ü"),
    (r"\\U\+00FC", "ü"),
    (r"\\U\+00D6", "Ö"),
    (r"\\U\+00F6", "ö"),
    (r"\\U\+00C7", "Ç"),
    (r"\\U\+00E7", "ç"),
    (r"%%[Cc]", "Ø"),
    (r"%%[Dd]", "°"),
    (r"%%[Pp]", "±"),
    (r"%%[UuOoKk]", ""),
    (r"%%%", "%"),
)

_CP1254_BYTES_MAP = str.maketrans({
    "\xdd": "İ",
    "\xfd": "ı",
    "\xde": "Ş",
    "\xfe": "ş",
    "\xd0": "Ğ",
    "\xf0": "ğ",
})

_TR_TO_ASCII_MAP = str.maketrans({
    "İ": "I",
    "I": "I",
    "ı": "I",
    "i": "I",
    "Ş": "S",
    "ş": "S",
    "Ğ": "G",
    "ğ": "G",
    "Ü": "U",
    "ü": "U",
    "Ö": "O",
    "ö": "O",
    "Ç": "C",
    "ç": "C",
})


def clean_cad_text_lines(raw_text: str) -> Tuple[str, List[str]]:
    """
    DXF TEXT / MTEXT içeriğini temizler ve MTEXT satır kırılımlarını (`\\P`) korur.

    Returns:
        (single_line_text, lines_list)
    """
    if not raw_text:
        return "", []

    t = raw_text.translate(_CP1254_BYTES_MAP)
    for pat, rep in _UNICODE_AND_SYMBOL_REPLACEMENTS:
        t = re.sub(pat, rep, t)

    # MTEXT istiflenmiş kesirler: \S30^6; -> 30/6, \S5#2; -> 5/2
    t = re.sub(r"\\S([^;\^#/]+?)[\^#/]+([^;]+?);", r"\1/\2", t)

    # MTEXT paragraf / satır break'leri
    t = t.replace("\\~", " ")
    t = re.sub(r"\\p[^;]*;", "\n", t)
    t = t.replace("\\P", "\n")

    # MTEXT biçimlendirme kodları
    t = re.sub(r"\\[fF][^;]*;", "", t)
    t = re.sub(r"\\[ACHWQT][0-9.+-]*[x]?;", "", t)
    t = re.sub(r"\\[LlOoKk]", "", t)
    t = re.sub(r"[{}\\]", lambda m: "" if m.group(0) in "{}" else m.group(0), t)
    # Kalan kaçışlı olmayan tekil \X; biçim belirteçlerini sadeleştir
    t = re.sub(r"\\[A-Za-z][^;]{0,30};", "", t)

    lines: List[str] = []
    for ln in t.splitlines():
        cleaned_ln = re.sub(r"[ \t\r\f\v]+", " ", ln).strip()
        if cleaned_ln:
            lines.append(cleaned_ln)

    single_line = " ".join(lines).strip()
    return single_line, lines


def clean_turkish_text(text: str) -> str:
    """Tek satırlık temiz metin döner (geriye dönük uyumlu yardımcı)."""
    single, _ = clean_cad_text_lines(text)
    return single


def norm_tr(text: str) -> str:
    """Türkçe karakterleri büyük ASCII eşdeğerine normalize eder."""
    if not text:
        return ""
    return text.translate(_TR_TO_ASCII_MAP).upper().strip()


def parse_tr_float(token: str) -> float | None:
    """Türkçe virgül/noktalı sayıları güvenli biçimde float'a çevirir."""
    if not token:
        return None
    s = str(token).strip().replace(" ", "")
    if not s:
        return None
    # "1.250,50" -> "1250.50", "5,960" -> "5.960"
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None
