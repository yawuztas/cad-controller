# -*- coding: utf-8 -*-
"""
CloudeCAD v3.0 — COM Tabanlı DWG Düzeltici (com_dwgs.py)
=========================================================
ezdxf roundtrip'i AutoCAD 2027'nin bazı çizimlerdeki ayrıştırıcısını çökerttiği için
DWG üretiminin alternatif/yedek yolu: orijinal DWG'yi AutoCAD COM otomasyonuyla açar,
planlardaki işlemleri (katman taşıma, köprü, snap, silme, metin güncelleme) doğrudan
AutoCAD API'si ile uygular ve DWG 2018 olarak kaydeder.
Yalnızca ONAYLI (auto + station approve) işlemler uygulanır; bekleyenlere dokunulmaz.
"""
import sys, json, time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import pythoncom
import win32com.client
import pywintypes

AC2018_DWG = 64  # AutoCAD SaveAs FileType enum: ac2018_dwg


class ComDwgApplier:
    def __init__(self, visible: bool = False, auto_start: bool = True, start_timeout: int = 240):
        pythoncom.CoInitialize()
        self._launched = False
        try:
            self.app = win32com.client.GetActiveObject("AutoCAD.Application")
        except Exception:
            if not auto_start:
                raise
            self._launch_acad(start_timeout)
        self.app.Visible = visible
        time.sleep(1.0)

    def _launch_acad(self, timeout_s: int):
        """AutoCAD GUI'yi açıkça başlatır ve COM bağlantısını bekler
        (Dispatch tek başına CO_E_SERVER_EXEC_FAILURE veriyor)."""
        import subprocess as _sp
        exe = None
        for year in range(2030, 2018, -1):
            cand = Path(rf"C:\Program Files\Autodesk\AutoCAD {year}\acad.exe")
            if cand.exists():
                exe = cand
                break
        if exe is None:
            raise RuntimeError("acad.exe bulunamadi; AutoCAD COM baslatilamaz.")
        _sp.Popen([str(exe)])
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            time.sleep(4)
            try:
                self.app = win32com.client.GetActiveObject("AutoCAD.Application")
                time.sleep(4)
                self._launched = True
                return
            except Exception:
                continue
        raise RuntimeError("AutoCAD COM zaman asiminda baslatilamadi.")

    def open(self, path: Path):
        return self.app.Documents.Open(str(path.resolve()))

    def apply_plan_json(self, doc, change_plan_path: Path, wire_plan_path: Path,
                        approve_layer: set, approve_wire: set) -> dict:
        """Kayıtlı plan JSON'larındaki ONAYLI işlemleri COM ile uygular."""
        from core.healer.layer_doctor import STANDARD_LAYER_SPECS

        report = {"layer_applied": 0, "wire_applied": 0, "skipped": 0}
        handle = lambda h: doc.HandleToObject(h)

        cp = json.loads(change_plan_path.read_text(encoding="utf-8")) if change_plan_path.exists() else {}
        wp = json.loads(wire_plan_path.read_text(encoding="utf-8")) if wire_plan_path.exists() else {}

        # Önce hedef katmanları oluştur ve işlem süresince kilitlerini aç
        needed_layers = set()
        for p in cp.get("proposals", []):
            if p.get("proposal_id", "") in approve_layer and p.get("new_layer"):
                needed_layers.add(p["new_layer"])
        for p in wp.get("proposals", []):
            if p.get("proposal_id", "") in approve_wire and p.get("layer"):
                needed_layers.add(p["layer"])
        self.ensure_layers(doc, sorted(needed_layers), unlock_for_edit=True)

        # --- LayerDoctor: katman taşıma ---
        for p in cp.get("proposals", []):
            pid = p.get("proposal_id", "")
            if pid not in approve_layer:
                continue
            try:
                obj = handle(p["dxf_handle"])
                obj.Layer = p["new_layer"]
                obj.color = 256          # BYLAYER
                obj.Lineweight = -1      # BYLAYER
                obj.Linetype = "BYLAYER"
                report["layer_applied"] += 1
            except Exception:
                report["skipped"] += 1

        # --- WireHealer: duplicate sil / köprü ekle / snap ---
        msp = doc.ModelSpace
        for p in wp.get("proposals", []):
            pid = p.get("proposal_id", "")
            if pid not in approve_wire:
                continue
            action = p.get("action", "")
            try:
                if action == "DELETE_DUPLICATE":
                    handle(p["secondary_handle"]).Delete()
                    report["wire_applied"] += 1
                elif action == "STITCH_COLLINEAR_GAP":
                    s = p["start_pt"]; e = p["end_pt"]
                    ln = msp.AddLine(
                        win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [s[0], s[1], 0.0]),
                        win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [e[0], e[1], 0.0]))
                    ln.Layer = p["layer"]
                    ln.color = 256
                    report["wire_applied"] += 1
                elif action.startswith("SNAP_TO_SYMBOL_"):
                    obj = handle(p["primary_handle"])
                    pt = p["end_pt"]
                    newpt = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [pt[0], pt[1], 0.0])
                    if action.endswith("_START"):
                        obj.StartPoint = newpt
                    else:
                        obj.EndPoint = newpt
                    report["wire_applied"] += 1
            except Exception:
                report["skipped"] += 1

        # Kilitli olması gereken standart katmanları (örn: A-MIMARI-ALTYAPI) kilitle
        for name in needed_layers:
            spec = STANDARD_LAYER_SPECS.get(name)
            if spec and spec.locked:
                try:
                    doc.Layers.Item(name).Lock = True
                except Exception:
                    pass

        return report

    def ensure_layers(self, doc, layer_names: list, unlock_for_edit: bool = False):
        from core.healer.layer_doctor import STANDARD_LAYER_SPECS
        for name in layer_names:
            try:
                if not self._layer_exists(doc, name):
                    lyr = doc.Layers.Add(name)
                else:
                    lyr = doc.Layers.Item(name)
                spec = STANDARD_LAYER_SPECS.get(name)
                if spec:
                    try:
                        lyr.color = spec.color
                        lyr.Lineweight = spec.lineweight
                    except Exception:
                        pass
                if unlock_for_edit:
                    try:
                        lyr.Lock = False
                    except Exception:
                        pass
            except Exception:
                pass

    @staticmethod
    def _layer_exists(doc, name: str) -> bool:
        try:
            doc.Layers.Item(name)
            return True
        except Exception:
            return False

    def saveas_dwg(self, doc, dwg_path: Path):
        doc.SaveAs(str(dwg_path.resolve()), AC2018_DWG)

    def close(self, doc):
        try:
            doc.Close(False)
        except Exception:
            pass

    def quit(self):
        try:
            self.app.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()
