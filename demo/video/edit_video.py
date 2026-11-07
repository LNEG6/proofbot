"""Cut the Proofbot demo video from the scene recordings and the Telegram screenshots.

    python edit_video.py telegram_frames.txt OUT.mp4

telegram_frames.txt lists screenshots, one per line: "<seconds> <path>".
"""
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
W, H, FPS = 1920, 1080, 20  # recordings are 10 fps, so each recorded frame is shown twice
BG, PANEL, ACCENT, TEXT, MUTED = "#0b1220", "#111c2e", "#4dd5cf", "#ffffff", "#a9bacb"
GOOD, BAD = "#7ee787", "#ff7b72"
FONTS = "C:/Windows/Fonts/"


def font(size, bold=False, mono=False):
    name = ("consolab.ttf" if bold else "consola.ttf") if mono else ("segoeuib.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(FONTS + name, size)


def wrap(draw, text, face, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=face) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + [line]


def paragraph(draw, xy, text, face, width, fill, gap=8):
    x, y = xy
    for line in wrap(draw, text, face, width):
        draw.text((x, y), line, font=face, fill=fill)
        y += face.size + gap
    return y


def canvas():
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, W, 6), fill=ACCENT)
    return image, draw


def to_frame(image):
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


class Video:
    def __init__(self, path):
        # MPEG-4: Windows' H.264 encoder here ignores quality settings and writes about 5 MB per second.
        self.writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
        self.frames, self.last = 0, None

    def hold(self, frame, seconds):
        if self.last is not None:  # a short cross-fade between shots
            for step in range(1, 7):
                self.writer.write(cv2.addWeighted(self.last, 1 - step / 7, frame, step / 7, 0))
                self.frames += 1
        for _ in range(max(1, int(seconds * FPS))):
            self.writer.write(frame)
            self.frames += 1
        self.last = frame

    def stream(self, frames):
        for frame in frames:
            self.writer.write(frame)
            self.frames += 1
            self.last = frame

    def close(self):
        self.writer.release()
        return self.frames / FPS


def title_card():
    image, draw = canvas()
    draw.text((140, 250), "Proofbot", font=font(120, True), fill=TEXT)
    draw.text((146, 400), "Lean for agent work", font=font(54, True), fill=ACCENT)
    paragraph(draw, (146, 520), "Text an AI agent a task. A harness the agent can't touch proves the work is done, "
              "and done the way you meant, before you ever read the code.", font(38), 1500, MUTED, 12)
    draw.text((146, 960), "Flip the Switch hackathon  ·  built on Switch, Codex and Telegram", font=font(26), fill=MUTED)
    return to_frame(image)


def lean_card():
    image, draw = canvas()
    draw.text((120, 90), "Why people trust AI-written proofs in Lean", font=font(52, True), fill=TEXT)
    draw.text((120, 175), "An AI writes the proof. A small kernel checks every step. You only read the statement.",
              font=font(32), fill=MUTED)
    rows = [("In Lean", "In Proofbot"),
            ("The theorem statement, written first", "Checks, sealed before the agent works"),
            ("A misformalized statement", "A second AI compares the checks with what you asked"),
            ("decide: check every case", "Proof by exhaustion: every input, every output"),
            ("The kernel", "The harness reruns everything itself"),
            ("Mathlib: proven once, stays proven", "The proven library: break it and you're NOT DONE"),
            ("#print axioms", "THIS PROOF RELIES ON, in every report")]
    y = 280
    for index, (left, right) in enumerate(rows):
        head = index == 0
        if not head:
            draw.rounded_rectangle((110, y - 14, 1810, y + 66), 14, fill=PANEL)
        face = font(34, True) if head else font(34)
        draw.text((140, y), left, font=face, fill=ACCENT if head else MUTED)
        draw.text((980, y), right, font=face, fill=ACCENT if head else TEXT)
        y += 100
    return to_frame(image)


def end_card():
    image, draw = canvas()
    draw.text((140, 230), "Proofbot", font=font(110, True), fill=TEXT)
    y = 400
    for line in ("What changed, measured by the harness",
                 "Whether the checks match what you asked",
                 "Every input tried, every output mapped",
                 "Nothing proven earlier was broken",
                 "What the proof relies on, and a receipt anyone can verify"):
        draw.line([(150, y + 30), (166, y + 46), (192, y + 14)], fill=GOOD, width=6, joint="curve")  # a tick
        draw.text((206, y), line, font=font(40), fill=TEXT)
        y += 72
    draw.text((146, 960), "Switch connects the agent to your chat. Proofbot makes its \"done\" mean something.",
              font=font(28), fill=MUTED)
    return to_frame(image)


def side_panel(step, title, bullets, lean):
    image, draw = canvas()
    draw.rectangle((0, 6, 600, H), fill=PANEL)
    draw.text((50, 50), step, font=font(26, True), fill=ACCENT)
    y = paragraph(draw, (50, 95), title, font(46, True), 510, TEXT, 6) + 24
    for bullet in bullets:
        draw.ellipse((52, y + 14, 64, y + 26), fill=ACCENT)
        y = paragraph(draw, (80, y), bullet, font(28), 480, MUTED, 6) + 18
    if lean:
        draw.rounded_rectangle((50, 960, 550, 1030), 12, outline=ACCENT, width=2)
        draw.text((70, 978), lean, font=font(26, True), fill=ACCENT)
    return image


def place(panel, shot, box=(640, 40, 1880, 1040)):
    """Put a screenshot (BGR array) into the box on the right, scaled to fit, on top of the panel."""
    frame = to_frame(panel)
    x0, y0, x1, y1 = box
    h, w = shot.shape[:2]
    scale = min((x1 - x0) / w, (y1 - y0) / h)
    shot = cv2.resize(shot, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    h, w = shot.shape[:2]
    x, y = x0 + (x1 - x0 - w) // 2, y0 + (y1 - y0 - h) // 2
    frame[y:y + h, x:x + w] = shot
    cv2.rectangle(frame, (x - 2, y - 2), (x + w + 1, y + h + 1), (90, 80, 60), 2)
    return frame


def recording(path, panel, top=52, max_idle=2.6, tail=3.0):
    """Frames of a terminal recording on its panel, with long idle stretches trimmed. 10 fps in, FPS out."""
    capture = cv2.VideoCapture(str(path))
    previous, idle, out, last = None, 0, [], None
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        frame = frame[top:]
        if previous is not None and cv2.absdiff(frame, previous).mean() < 0.15:
            idle += 1
            if idle > max_idle * 10:
                continue
        else:
            idle = 0
        previous = frame
        last = place(panel, frame)
        out += [last] * (FPS // 10)
    out += [last] * int(tail * FPS)
    return out


SCENES = [
    ("misunderstand", "1 / 4  ·  THE STATEMENT", "It misunderstood you", [
        "You ask for percent(1, 4) to return 25.",
        "The agent reads \"percentage\" as a fraction. Its own check expects 0.25, so the check agrees with its mistake.",
        "A second AI that sees only your request and the sealed check says WRONG.",
        "Its check passes and your tests are green. Proofbot says UNPROVEN."], "Lean: a misformalized statement"),
    ("everyday", "2 / 4  ·  EVERY CASE", "An everyday rule, every case tried", [
        "Only admins and a post's author may delete it. Editors may edit. Everyone may read.",
        "The check lists every role × action × author: 18 cases. The harness tries every one.",
        "First try: NOT DONE. An editor can't delete their own post.",
        "After the fix: DONE AND PROVEN, with the whole table in the report."], "Lean: decide, every case"),
    ("regress", "3 / 4  ·  STAYS PROVEN", "Proven once, stays proven", [
        "Job 1 proves add on all 1,005,004 inputs, each one mapped to its output.",
        "Its check joins the proven library.",
        "Job 2 adds text support with int(). Its own check passes, your tests pass.",
        "NOT DONE: a=-500, b=0.5 now gives -500, not -499.5."], "Lean: Mathlib"),
]


def main():
    telegram_list, out = sys.argv[1], sys.argv[2]
    video = Video(out)
    video.hold(title_card(), 5)
    video.hold(lean_card(), 11)
    for scene, step, title, bullets, lean in SCENES:
        path = HERE / f"scene_{scene}.mp4"
        if path.exists():
            panel = side_panel(step, title, bullets, lean)
            frames = recording(path, panel)
            video.hold(frames[0], 0.2)
            video.stream(frames)
    panel = side_panel("4 / 4  ·  FOR REAL", "The real thing, over Telegram", [
        "You text the task to doer, a Codex agent running on Switch.",
        "doer writes exhaustive checks. The harness seals them, a second AI reviews them, then doer works.",
        "The harness writes the report. doer posts it word for word.",
        "About two minutes of work, sped up."], "Same harness, real agent")
    for line in Path(telegram_list).read_text(encoding="utf-8").splitlines():
        if line.strip():
            seconds, path = line.split(" ", 1)
            shot = cv2.imread(path.strip())
            video.hold(place(panel, shot), float(seconds))
    verify = HERE / "scene_verify.mp4"
    if verify.exists():
        panel = side_panel("4 / 4  ·  FOR REAL", "Anyone can check it", [
            "verify rebuilds the receipt from the evidence and the ledger.",
            "It reruns the sealed checks and confirms every input still maps to the same output.",
            "A forged or edited report fails."], "Lean: re-check the proof")
        frames = recording(verify, panel, tail=4)
        video.hold(frames[0], 0.2)
        video.stream(frames)
    video.hold(end_card(), 7)
    print(f"{video.close():.0f} s written to {out}")


if __name__ == "__main__":
    main()
