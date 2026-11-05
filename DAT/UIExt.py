import json
import os
import re
from urllib.parse import urlparse, parse_qs


class UIExt:
    """Operator UI for /project1/UI, shown in UI_window.

    Look:     UI/index.html rendered by a Web Render TOP (the UI container's background)
    Video:    native Container COMPs on top (program + cams), no JPEG, no lag
    Control:  the page talks to TD over http://localhost (Web Server DAT, tiny JSON only)
    Mouse:    the UI container's mouse is forwarded to the Web Render TOP every frame
    Auto:     scene_table / cam_table changes rebuild the camera previews; the page
              reads scene_table every poll, so new scenes appear on their own
    """

    TRUE = ("1", "true", "True", "on")

    # Layout shared with index.html (pixels from the top-left of a 1600x900 page)
    W, H = 1600, 900
    PROGRAM = (328, 112, 800, 450)           # x, top, w, h  (same as build_ui.py)
    CAMS = (328, 634, 800, 144)
    GAP = 16

    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self.lastMouse = None
        self.mouseWarned = False

    # ------------------------------------------------------------ lookups

    @property
    def selector(self):
        return self.ownerComp.par.Selector.eval()

    @property
    def recorder(self):
        return self.ownerComp.par.Recorder.eval()

    def OutTop(self, comp):
        """The TOP a COMP outputs: out1 if it exists, else the first Out TOP inside."""
        if comp is None:
            return None
        if comp.isTOP:
            return comp
        outs = comp.findChildren(type=outTOP, depth=1)
        outs.sort(key=lambda o: o.digits or 0)
        return outs[0] if outs else None

    def tableRows(self, table) -> list:
        """[{'name', 'path'}] from an OP Find table (header row: name ... path)."""
        if table is None or table.numRows < 2:
            return []
        header = [c.val for c in table.row(0)]
        rows = []
        for r in range(1, table.numRows):
            path = table[r, "path"].val if "path" in header else table[r, 0].val
            target = op(path)
            if target is None:
                continue
            name = table[r, "name"].val if "name" in header else target.name
            rows.append({"name": name, "path": target.path})
        return rows

    def Scenes(self) -> list:
        """Rows of scene_table, names unchanged; 'num' = leading digits ('03_SIDE_CAM' -> '03')."""
        scenes = []
        for row in self.tableRows(self.ownerComp.par.Scenetable.eval()):
            m = re.match(r"^(\d+)_", row["name"])
            row["num"] = m.group(1) if m else ""  # name stays exactly as in scene_table
            scenes.append(row)
        return scenes

    def Cameras(self) -> list:
        return self.tableRows(self.ownerComp.par.Camtable.eval())

    def settings(self):
        try:
            return op.SETTINGS
        except Exception:
            return None

    def outputInfo(self) -> dict:
        s = self.settings()
        info = {}
        if s is not None:
            for key, attr in (("resX", "OutResX"), ("resY", "OutResY"), ("fps", "OutFps"), ("display", "Display")):
                info[key] = getattr(s, attr, None)
        top = self.OutTop(self.selector)
        if top is not None:
            info["actualW"], info["actualH"] = top.width, top.height
        return info

    def cameraInfo(self) -> list:
        """cam_table rows + SETTINGS.Cameras (CAM1 -> Cameras[0]) + the real TOP size."""
        s = self.settings()
        configs = list(getattr(s, "Cameras", []) or []) if s is not None else []
        cams = []
        for i, cam in enumerate(self.Cameras()):
            comp = op(cam["path"])
            index = (comp.digits - 1) if comp is not None and comp.digits else i
            cfg = configs[index] if 0 <= index < len(configs) else {}
            info = dict(cam)
            info.update({k: cfg.get(k) for k in ("device", "resX", "resY", "fps", "active")})
            top = self.OutTop(comp)
            if top is not None:
                info["actualW"], info["actualH"] = top.width, top.height
            cams.append(info)
        return cams

    def CurrentScene(self):
        sel = self.selector
        if sel is None or not hasattr(sel.par, "Scene"):
            return None
        return op(sel.par.Scene.eval())

    def IsRecorderScene(self) -> bool:
        rec, cur = self.recorder, self.CurrentScene()
        return rec is not None and cur is not None and rec.path == cur.path

    def RecorderStatus(self) -> str:
        rec = self.recorder
        if rec is None:
            return ""
        return rec.par.Status.eval() if hasattr(rec.par, "Status") else ""

    def Recording(self) -> bool:
        return self.RecorderStatus().startswith("REC")

    # ------------------------------------------------------------ pars

    def parKind(self, p):
        if p.style == "Header" or p.isOP or getattr(p, "isPython", False):
            return None
        if p.isPulse:
            return "pulse"
        if p.isMomentary:
            return "momentary"
        if p.isToggle:
            return "toggle"
        if p.isMenu:
            return "menu"
        if p.isFloat or p.isInt:
            return "number"
        if p.isString:
            return "string"
        return None

    def describePars(self, target) -> list:
        if target is None:
            return []
        out = []
        for p in target.customPars:
            kind = self.parKind(p)
            if kind is None:
                continue
            label = p.label
            if len(p.tuplet) > 1:
                label = f"{p.label} {p.name[len(p.tupletName):]}"
            item = {
                "name": p.name,
                "label": label,
                "page": p.page.name,
                "kind": kind,
                "readOnly": bool(p.readOnly)
                or p.mode in (ParMode.EXPRESSION, ParMode.EXPORT),
            }
            if kind == "number":
                item.update(val=p.eval(), min=p.normMin, max=p.normMax, isInt=p.isInt)
            elif kind == "toggle":
                item["val"] = bool(p.eval())
            elif kind == "menu":
                item.update(val=str(p.eval()), names=list(p.menuNames), labels=list(p.menuLabels))
            elif kind == "string":
                item["val"] = str(p.eval())
            out.append(item)
        return out

    def setPar(self, target, name: str, value: str) -> None:
        p = getattr(target.par, name, None)
        if p is None or not p.isCustom:
            raise ValueError(f"{target.name} has no custom par {name}")
        if p.isPulse:
            p.pulse()
        elif p.isMomentary or p.isToggle:
            p.val = value in self.TRUE
        elif p.isMenu or p.isString:
            p.val = value
        elif p.isFloat or p.isInt:
            v = float(value)
            p.val = int(round(v)) if p.isInt else v
        else:
            raise ValueError(f"{name}: unsupported par type")

    def allowedTargets(self) -> set:
        paths = {s["path"] for s in self.Scenes()}
        paths.add(self.ownerComp.path)
        if self.recorder is not None:
            paths.add(self.recorder.path)
        return paths

    # ------------------------------------------------------------ state + commands

    def clips(self, rec) -> list:
        table = rec.op("table_clips")
        if table is None or table.numRows < 2:
            return []
        header = [c.val for c in table.row(0)]
        return [
            {k: table[r, k].val for k in ("index", "name", "modified", "size_MB") if k in header}
            for r in range(1, table.numRows)
        ]

    def State(self) -> dict:
        cur = self.CurrentScene()
        rec = self.recorder
        recorder = None
        if rec is not None:
            status = self.RecorderStatus()
            recorder = {
                "path": rec.path,
                "status": status,
                "recording": status.startswith("REC"),
                "clips": self.clips(rec),
                "pars": self.describePars(rec),
            }
        return {
            "scenes": self.Scenes(),
            "current": cur.path if cur is not None else "",
            "pars": self.describePars(cur),
            "recorder": recorder,
            "output": self.outputInfo(),
            "cameras": self.cameraInfo(),
        }

    def Command(self, q: dict) -> None:
        action = q.get("action", "")
        value = q.get("value", "")
        rec = self.recorder

        if action == "scene":
            sel = self.selector
            if sel is None:
                raise ValueError("Scene Selector not found")
            if value not in sel.par.Scene.menuNames:
                raise ValueError(f"{value} is not in the scene menu")
            sel.par.Scene = value
        elif action == "par":
            path = q.get("op", "")
            if path not in self.allowedTargets():
                raise ValueError(f"{path} is not controllable from the UI")
            self.setPar(op(path), q.get("name", ""), value)
        elif action in ("record", "play", "stop"):
            if rec is None:
                raise ValueError("Recorder not found")
            ext = getattr(rec.ext, "RecorderExt", None)
            if action == "record" and ext is not None and ext.recordingFile:
                ext.StopRecord()  # REC while recording = stop recording
            else:
                getattr(rec.par, action.capitalize()).pulse()
        else:
            raise ValueError(f"unknown action {action}")

    # ------------------------------------------------------------ http (localhost only use)

    def HandleHTTP(self, request: dict, response: dict) -> dict:
        parsed = urlparse(request.get("uri", "/"))
        path = parsed.path
        q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        q.update({k: str(v) for k, v in (request.get("pars") or {}).items()})
        response["Cache-Control"] = "no-store"
        try:
            if path in ("/", "/index.html"):
                return self.reply(response, self.html(), "text/html; charset=utf-8")
            if path == "/api/state":
                return self.reply(response, json.dumps(self.State()), "application/json")
            if path == "/api/cmd":
                self.Command(q)
                return self.reply(response, json.dumps({"ok": True}), "application/json")
            return self.reply(response, "not found", "text/plain", 404, "Not Found")
        except Exception as e:
            print(f"[UI] {path} {q}: {e}")
            if path == "/api/cmd":
                return self.reply(response, json.dumps({"ok": False, "error": str(e)}), "application/json")
            return self.reply(response, str(e), "text/plain", 500, "Server Error")

    def reply(self, response, data, contentType, code=200, reason="OK") -> dict:
        response["statusCode"] = code
        response["statusReason"] = reason
        response["Content-Type"] = contentType
        response["data"] = data
        return response

    def html(self) -> str:
        """Read from disk every time: edit index.html, then pulse UI > Reload Page."""
        path = self.ownerComp.par.Htmlfile.eval()
        if not os.path.isabs(path):
            path = os.path.join(project.folder, path)
        if not os.path.isfile(path):
            return f"<h1>UI</h1><p>HTML file not found: {path}</p>"
        with open(path, encoding="utf-8") as f:
            return f.read()

    def ReloadPage(self) -> None:
        web = self.ownerComp.op("webrender")
        web.par.url = ""
        run(f"op({web.path!r}).par.url = {self.Url()!r}", delayFrames=2)

    def Url(self) -> str:
        return f"http://localhost:{int(self.ownerComp.par.Port.eval())}/"

    # ------------------------------------------------------------ mouse -> Web Render TOP

    def ForwardMouse(self) -> None:
        """Called every frame: pass the UI container's mouse to the page.

        Clicks and drags go through interactMouse. Hover goes through JavaScript
        (window.tdHover), because the page doesn't reliably get mouse-move events.
        """
        panel = self.ownerComp.panel
        inside = bool(panel.inside.val)
        down = bool(panel.lselect.val)
        # u/v only update while the button is held; rollu/rollv follow the mouse on hover
        if down:
            u, v = panel.u.val, panel.v.val
        else:
            u, v = panel.rollu.val, panel.rollv.val
        wheel = panel.wheel.val
        state = (round(u, 4), round(v, 4), inside, down, wheel)
        if state == self.lastMouse:
            return
        self.lastMouse = state
        web = self.ownerComp.op("webrender")

        # Hover: page pixels, y from the top
        x, y = u * self.W, (1 - v) * self.H
        try:
            web.executeJavaScript(f"window.tdHover && window.tdHover({x:.1f}, {y:.1f}, {int(inside)})")
        except Exception as e:
            if not self.mouseWarned:
                print(f"[UI] executeJavaScript failed: {e}")
                self.mouseWarned = True

        if self.ownerComp.par.Flipv.eval():
            v = 1 - v
        try:
            web.interactMouse(u, v, left=down, wheel=wheel)
        except Exception as e:
            if not self.mouseWarned:
                print(f"[UI] interactMouse failed: {e}")
                self.mouseWarned = True

    # ------------------------------------------------------------ native overlays

    @staticmethod
    def setPars(o, **pars) -> None:
        """Set pars by name; a string starting with '=' becomes an expression."""
        for name, value in pars.items():
            p = getattr(o.par, name, None)
            if p is None:
                print(f"[UI] {o.name}: no par '{name}', skipped")
                continue
            if isinstance(value, str) and value.startswith("="):
                p.expr = value[1:]
            else:
                p.val = value

    @staticmethod
    def place(o, x, top, w, h) -> None:
        """Position from the top-left (TD panels measure y from the bottom)."""
        parentH = o.parent().par.h.eval()
        o.par.x, o.par.y = x, parentH - top - h
        o.par.w, o.par.h = w, h

    def Rebuild(self) -> None:
        self.RebuildCams()
        self.EnsureKeyboard()

    # ------------------------------------------------------------ keyboard -> page

    KEY_CALLBACKS = (
        "# Keys -> UIExt.OnKey -> page (typing numbers into parameter fields)\n\n"
        "def onKey(dat, key, character, *args, **kwargs):\n"
        "\tstate = kwargs.get('state', args[9] if len(args) > 9 else True)\n"
        "\tparent.UI.OnKey(key, character, state)\n"
        "\treturn\n"
    )

    def EnsureKeyboard(self) -> None:
        """Keyboard In DAT whose key presses are sent to the page."""
        ui = self.ownerComp
        cb = ui.op("keyboard_callbacks") or ui.create(textDAT, "keyboard_callbacks")
        cb.nodeX, cb.nodeY = 600, 400
        cb.text = self.KEY_CALLBACKS
        kb = ui.op("keyboard") or ui.create(keyboardinDAT, "keyboard")
        kb.nodeX, kb.nodeY = 600, 250
        self.setPars(kb, callbacks=cb)

    def OnKey(self, key, character, state) -> None:
        """Only key-downs; the page ignores them unless a number field is being edited."""
        if not state:
            return
        web = self.ownerComp.op("webrender")
        try:
            web.executeJavaScript(
                f"window.tdKey && window.tdKey({json.dumps(str(key))}, {json.dumps(str(character))})"
            )
        except Exception as e:
            print(f"[UI] key forward failed: {e}")

    def RebuildCams(self) -> None:
        row = self.ownerComp.op("cams")
        for child in row.findChildren(name="cam_*", depth=1):
            child.destroy()
        h = row.par.h.eval()
        w = round(h * 16 / 9)
        cams = self.Cameras()
        for i, cam in enumerate(cams):
            box = row.create(containerCOMP, f"cam_{i + 1}")
            box.nodeX, box.nodeY = 200 * i, 0
            self.place(box, i * (w + self.GAP), 0, w, h)
            self.setPars(box, top=f"=parent.UI.OutTop(op({cam['path']!r}))",
                         bgcolorr=0, bgcolorg=0, bgcolorb=0, bgalpha=1)
        print(f"[UI] {len(cams)} camera previews")
