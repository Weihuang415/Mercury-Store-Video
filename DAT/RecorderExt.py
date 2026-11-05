import os
import random
import re
from datetime import datetime


class RecorderExt:
    """Record clips of the live input, then play one back over the live input."""

    VIDEO_EXT = (".mov", ".mp4", ".m4v")

    def __init__(self, ownerComp):
        # The component to which this extension is attached
        self.ownerComp = ownerComp
        self.checkOps()
        self.addMissingPars()
        self.movieOut = ownerComp.op("moviefileout_rec")
        self.movieIn = ownerComp.op("moviefilein_play")
        self.cross = ownerComp.op("cross_mix")
        self.clipsTable = ownerComp.op("table_clips") or self.createClipsTable()

        self.recordingFile = ""
        self.state = "live"  # live | opening | fadein | playing | fadeout
        self.mix = 0.0
        self.lastIndex = -1.0
        self.playStart = 0.0
        self.lastClip = ""
        self.recordToken = 0  # bumps on every Record, so an old auto-stop can't cut a newer clip
        self.folderSignature = None

        # Switch TOP with blend on: index 0 = live, 1 = clip, in between = crossfade
        self.cross.par.blend = True
        self.cross.par.index = 0
        self.setStatus("live")
        self.UpdateClipsTable()

    def addMissingPars(self) -> None:
        """Pars added after RECORDER was first built."""
        if not self.ownerComp.pars("Loop"):
            page = next(p for p in self.ownerComp.customPages if p.name == "Recorder")
            page.appendToggle("Loop")

    def checkOps(self) -> None:
        required = {
            "moviefileout_rec": "moviefileoutTOP",
            "moviefilein_play": "moviefileinTOP",
            "cross_mix": "switchTOP",
        }
        problems = []
        for name, opType in required.items():
            found = self.ownerComp.op(name)
            if found is None:
                problems.append(f"{name}: missing (needs a {opType})")
            elif found.OPType != opType:
                problems.append(f"{name}: is a {found.OPType}, needs a {opType}")
        if problems:
            raise Exception("[RECORDER] " + "; ".join(problems))

    # ------------------------------------------------------------ record

    def Record(self) -> None:
        if self.recordingFile:
            print("[RECORDER] already recording")
            return
        folder = op.SETTINGS.RecordingPath
        os.makedirs(folder, exist_ok=True)
        self.recordingFile = self.newClipPath(folder)
        name = os.path.basename(self.recordingFile)

        seconds = self.ownerComp.par.Recordseconds.eval()
        self.movieOut.par.file = self.recordingFile
        self.movieOut.par.record = True
        self.recordToken += 1
        run(self.autoStopRecord, self.recordToken, delayMilliSeconds=int(seconds * 1000))
        print(f"[RECORDER] record  {seconds}s  {name}")
        self.setStatus(f"recording {seconds}s")

    def newClipPath(self, folder: str) -> str:
        """clip_1103_103512.mov = recorded Nov 3, 10:35:12. Never reuses a name, even after deleting clips."""
        stamp = datetime.now().strftime("%m%d_%H%M%S")
        path = os.path.join(folder, f"clip_{stamp}.mov")
        n = 2
        while os.path.exists(path):  # two recordings in the same second
            path = os.path.join(folder, f"clip_{stamp}_{n}.mov")
            n += 1
        return path

    def autoStopRecord(self, token: int) -> None:
        """Record Seconds timer; ignored if that recording was already stopped by hand."""
        if token == self.recordToken:
            self.StopRecord()

    def StopRecord(self) -> None:
        if not self.recordingFile:
            return
        self.movieOut.par.record = False
        print(f"[RECORDER] saved   {os.path.basename(self.recordingFile)}")
        self.recordingFile = ""
        self.setStatus(self.state)
        self.UpdateClipsTable()

    # ------------------------------------------------------------ clips

    def Clips(self) -> list:
        """Finished clips in the recording folder, oldest first."""
        folder = op.SETTINGS.RecordingPath
        if not os.path.isdir(folder):
            return []
        clips = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith(self.VIDEO_EXT) and not f.startswith(".")
        ]
        clips = [c for c in clips if c != self.recordingFile]
        return sorted(clips, key=os.path.getmtime)

    def createClipsTable(self):
        table = self.ownerComp.create(tableDAT, "table_clips")
        table.nodeX, table.nodeY = 600, 400
        return table

    def UpdateClipsTable(self) -> None:
        """Row number = Clip Index (row 1 = oldest clip)."""
        clips = self.Clips()
        self.folderSignature = self.clipsSignature()
        table = self.clipsTable
        table.clear()
        table.appendRow(["index", "name", "modified", "size_MB", "path"])
        for i, clip in enumerate(clips, start=1):
            modified = datetime.fromtimestamp(os.path.getmtime(clip))
            table.appendRow([
                i,
                os.path.basename(clip),
                modified.strftime("%m-%d %H:%M:%S"),
                f"{os.path.getsize(clip) / 1e6:.1f}",
                clip,
            ])

        # Limit Clip Index to the rows in the table
        par = self.ownerComp.par.Clipindex
        last = max(len(clips), 1)
        par.min, par.max, par.normMin, par.normMax = 1, last, 1, last
        par.clampMin, par.clampMax = True, True

    def watchFolder(self) -> None:
        """Once a second, refresh table_clips if files were added, removed or changed."""
        if int(absTime.frame) % max(int(project.cookRate), 1):
            return
        if self.clipsSignature() != self.folderSignature:
            self.UpdateClipsTable()

    def clipsSignature(self) -> tuple:
        return tuple((c, os.path.getmtime(c)) for c in self.Clips())

    def PrintClips(self) -> None:
        self.UpdateClipsTable()
        clips = self.Clips()
        print(f"[RECORDER] {len(clips)} clips in {op.SETTINGS.RecordingPath}")
        for i, clip in enumerate(clips, start=1):
            print(f"  {i:>3} | {os.path.basename(clip)}")

    def pickClip(self):
        clips = self.Clips()
        if not clips:
            return None
        mode = self.ownerComp.par.Mode.eval()
        if mode == "random":
            choices = [c for c in clips if c != self.lastClip] or clips
            return random.choice(choices)
        if mode == "index":
            index = self.ownerComp.par.Clipindex.eval()
            index = max(1, min(index, len(clips)))
            return clips[index - 1]
        return clips[-1]

    # ------------------------------------------------------------ playback

    def Play(self) -> None:
        clip = self.pickClip()
        if clip is None:
            print("[RECORDER] no clips to play")
            return
        self.lastClip = clip
        self.movieIn.par.file = clip
        self.movieIn.par.speed = self.ownerComp.par.Speed.eval()
        self.movieIn.par.cuepoint = 0
        self.movieIn.par.play = True
        self.state = "opening"
        self.playStart = absTime.seconds
        print(f"[RECORDER] play    {os.path.basename(clip)}")
        self.setStatus("opening")

    def Stop(self) -> None:
        """Stop everything: an ongoing recording and the playback."""
        if self.recordingFile:
            self.StopRecord()
        if self.state != "live":
            self.state = "fadeout"
            self.movieIn.par.play = False

    def Update(self) -> None:
        """Called every frame by exec_frame."""
        self.watchFolder()
        if self.state == "live":
            return
        par = self.ownerComp.par
        now = absTime.seconds
        target = par.Opacity.eval()
        fade = max(par.Fadeseconds.eval(), 0.0)
        step = target if fade == 0 else target / (fade * project.cookRate)
        movie = self.movieIn

        if self.state == "opening":
            if movie.isOpen:
                movie.par.cuepulse.pulse()
                self.lastIndex = -1.0
                self.playStart = now
                self.state = "fadein"
            elif now - self.playStart > 5:
                print("[RECORDER] clip did not open, back to live")
                self.state = "fadeout"

        elif self.state in ("fadein", "playing"):
            if self.state == "fadein":
                self.mix = min(self.mix + step, target)
                if self.mix >= target:
                    self.state = "playing"
            else:
                self.mix = target

            # Loop on: keep playing until Stop
            # Loop off: end when the movie hits its last frame, loops back, or overruns
            index = movie.index
            looped = index < self.lastIndex
            if looped and par.Loop.eval():
                self.playStart = now
            elapsed = now - self.playStart
            length = movie.numSeconds / max(par.Speed.eval(), 0.01)
            if not par.Loop.eval() and elapsed > 0.1 and (
                movie.isLastFrame or looped or elapsed > length + 1
            ):
                movie.par.play = False  # hold last frame during fade out
                self.state = "fadeout"
            self.lastIndex = index

        elif self.state == "fadeout":
            self.mix = max(self.mix - step, 0.0)
            if self.mix <= 0:
                self.state = "live"
                movie.par.play = False

        self.cross.par.index = self.mix
        self.setStatus(self.state)

    def setStatus(self, text: str) -> None:
        if self.recordingFile:
            text = f"REC | {text}"
        self.ownerComp.par.Status = text
