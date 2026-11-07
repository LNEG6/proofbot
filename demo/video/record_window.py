"""Record one demo scene: open it in its own terminal window and capture only that window until it closes.

    python record_window.py SCENE OUT.mp4 [COMMAND...]

Nothing outside the window's rectangle is captured, so other apps on the screen never end up in the video.
"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import ImageGrab

ctypes.windll.shcore.SetProcessDpiAwareness(2)  # real pixels, so the capture is sharp
user32 = ctypes.windll.user32
DEMO = Path(__file__).resolve().parents[1]
FPS = 10


def find(title, timeout=20):
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def visit(hwnd, _):
        buffer = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buffer, 256)
        if buffer.value == title and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    deadline = time.time() + timeout
    while time.time() < deadline:
        found.clear()
        user32.EnumWindows(visit, 0)
        if found:
            return found[0]
        time.sleep(0.2)
    raise SystemExit(f"no window titled {title!r} appeared")


def rect(hwnd):
    r = wt.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r))  # frame without shadow
    return r.left, r.top, r.right, r.bottom


def main():
    scene, out, *command = sys.argv[1:]
    title = f"Proofbot demo - {scene} {int(time.time())}"
    # A batch file avoids Windows Terminal's own parsing of quotes and ";". It holds the last screen for 5 seconds,
    # then exits 0 so the window closes and the recording stops.
    batch = Path(__file__).with_name(f"run_{scene}.cmd")
    body = " ".join(command) if command else f"python lazy_agent.py {scene}"
    batch.write_text(f"@echo off\r\ncd /d \"{DEMO}\"\r\nset DEMO_PAUSE=2.2\r\n{body}\r\n"
                     "python -c \"__import__('time').sleep(5)\"\r\nexit /b 0\r\n", encoding="utf-8")
    subprocess.Popen(["wt.exe", "--size", "118,36", "--pos", "40,20", "-w", "new", "new-tab", "--title", title,
                      "--suppressApplicationTitle", "cmd", "/c", str(batch)])
    hwnd = find(title)
    HWND_TOPMOST, SWP_NOMOVE_NOSIZE_SHOW = -1, 0x0001 | 0x0002 | 0x0040
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE_NOSIZE_SHOW)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.8)
    box = rect(hwnd)
    size = (box[2] - box[0]) // 2 * 2, (box[3] - box[1]) // 2 * 2
    writer = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), FPS, size)
    frames, start = 0, time.time()
    while user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd) and time.time() - start < 600:
        shot = ImageGrab.grab(bbox=(box[0], box[1], box[0] + size[0], box[1] + size[1]), all_screens=True)
        frame = cv2.cvtColor(np.asarray(shot), cv2.COLOR_RGB2BGR)
        due = int((time.time() - start) * FPS) + 1
        while frames < due:  # keep real time even if a grab was slow
            writer.write(frame)
            frames += 1
        time.sleep(max(0, (frames / FPS) - (time.time() - start)))
    writer.release()
    print(f"recorded {frames / FPS:.0f} s, {size[0]}x{size[1]}, to {out}")


if __name__ == "__main__":
    main()
