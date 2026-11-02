"""
TS EN 50083 SMATV & Uydu / TV Dağıtım Standartları
=================================================
Multiswitch çıkış kapasitesi, kat dağıtıcı (TAP) zayıflama seviyeleri
ve priz ucu standart sinyal seviyesi (60 - 80 dBµV) denetimi.
"""

from typing import Dict, Any


def evaluate_smatv_system(dwelling_count: int, floor_count: int, sockets_per_dwelling: int = 2) -> Dict[str, Any]:
    """
    Bina SMATV / Uydu dağıtım sistemi kapasite ve zayıflama gereksinimlerini hesaplar.
    """
    total_sockets = dwelling_count * sockets_per_dwelling

    # Multiswitch port seçimi (Örn: 9/16, 9/24, 9/32, 17/32, kaskat çoklu multiswitch)
    multiswitch_standard_ports = [8, 12, 16, 24, 32, 40, 48, 64]
    recommended_ports = multiswitch_standard_ports[-1]
    for p in multiswitch_standard_ports:
        if p >= dwelling_count:
            recommended_ports = p
            break

    cascade_required = dwelling_count > 32

    return {
        "dwelling_count": dwelling_count,
        "floor_count": floor_count,
        "total_tv_sockets": total_sockets,
        "multiswitch_min_ports": dwelling_count,
        "recommended_multiswitch": f"{recommended_ports} Abone Çıkışlı Multiswitch (Kaskat)" if cascade_required else f"{recommended_ports} Abone Çıkışlı Multiswitch (Sonlu)",
        "min_socket_signal_dbuv": 60.0,
        "max_socket_signal_dbuv": 80.0,
        "recommended_cable": "RG-6 U4 veya RG-11 (Dikey Şaft Omurga)"
    }
