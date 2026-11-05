from TDStoreTools import StorageManager
import TDFunctions as TDF
import os


class SettingsExt:
    def __init__(self, ownerComp):
        # The component to which this extension is attached
        self.ownerComp = ownerComp
        self.settingsTable = op("table_settings")
        self.camerasTable = op("table_cameras")
        self.NumCameras: int = 3

        # properties
        TDF.createProperty(self, "AssetPath", value="", dependable=True, readOnly=False)
        TDF.createProperty(self, "RecordingPath", value="", dependable=True, readOnly=False)

        # Projection output (Display = monitor index of the projector, for Window COMP)
        TDF.createProperty(self, "Display", value=0, dependable=True, readOnly=False)
        TDF.createProperty(self, "OutResX", value=1920, dependable=True, readOnly=False)
        TDF.createProperty(self, "OutResY", value=1080, dependable=True, readOnly=False)
        TDF.createProperty(self, "OutFps", value=60, dependable=True, readOnly=False)

        # Cameras: list of dicts, index 0 = cam 1
        # e.g. op.SETTINGS.Cameras[0]['device']
        TDF.createProperty(self, "Cameras", value=[], dependable=True, readOnly=False)

    def Startup(self) -> None:
        node = var("NODE")
        if node == "":
            node = "WF"

        # Paths (relative paths resolve against the .toe folder)
        self.AssetPath = self.resolvePath(self.settingsTable[node, "asset_path"].val)
        self.RecordingPath = self.resolvePath(self.settingsTable[node, "recording_path"].val)

        # Projection output
        self.Display = int(self.settingsTable[node, "display"].val)
        self.OutResX = int(self.settingsTable[node, "out_resX"].val)
        self.OutResY = int(self.settingsTable[node, "out_resY"].val)
        self.OutFps = int(self.settingsTable[node, "out_fps"].val)

        # Cameras
        self.Cameras = self.loadCameras(node)

        self.printSummary(node)

    def printSummary(self, node: str) -> None:
        lines = [f"[SETTINGS] node {node}"]

        # Paths as key/value, same names as table_settings
        paths = [("asset_path", self.AssetPath), ("recording_path", self.RecordingPath)]
        width = max(len(k) for k, _ in paths)
        lines += [f"  {k.ljust(width)} : {v}" for k, v in paths]

        # Output and cameras as tables, same column order as their tables
        lines += ["", "[OUTPUT]"]
        lines += self.formatTable(
            ["display", "out_resX", "out_resY", "out_fps"],
            [[self.Display, self.OutResX, self.OutResY, self.OutFps]],
        )
        keys = ["cam", "device", "resX", "resY", "fps", "flipX", "active"]
        lines += ["", "[CAMERAS]"]
        lines += self.formatTable(keys, [[cam[k] for k in keys] for cam in self.Cameras])
        print("\n".join(lines))

    def formatTable(self, keys: list, rows: list) -> list:
        rows = [[str(v) if v != "" else "(auto)" for v in row] for row in rows]
        widths = [max(len(k), *(len(r[i]) for r in rows)) for i, k in enumerate(keys)]
        lines = ["  " + " | ".join(k.ljust(w) for k, w in zip(keys, widths))]
        lines += ["  " + " | ".join(v.ljust(w) for v, w in zip(row, widths)) for row in rows]
        return lines

    def resolvePath(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.join(project.folder, path)

    def loadCameras(self, node: str) -> list:
        # Defaults so Cameras[0..NumCameras-1] always exists
        cameras = [
            {"cam": i + 1, "device": "", "resX": 1280, "resY": 720,
             "fps": 30, "flipX": 0, "active": 0}
            for i in range(self.NumCameras)
        ]
        table = self.camerasTable
        for r in range(1, table.numRows):
            if table[r, "node"].val != node:
                continue
            index = int(table[r, "cam"].val) - 1
            if not 0 <= index < self.NumCameras:
                print(f"Settings: skipping cam {index + 1}, out of range")
                continue
            cameras[index] = {
                "cam": index + 1,
                "device": table[r, "device"].val,
                "resX": int(table[r, "resX"].val),
                "resY": int(table[r, "resY"].val),
                "fps": int(table[r, "fps"].val),
                "flipX": int(table[r, "flipX"].val),
                "active": int(table[r, "active"].val),
            }
        return cameras
