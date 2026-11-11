"""Conservative on-screen detector for the bright yellow Fortnite Play Again button.

No OCR, process memory or injection. Only a distinctive *screen layout* is
accepted: a wide lemon-yellow rectangle in the right-middle UI panel.
A user-saved replay_*.png template remains the accurate fallback for other
resolutions, Fortnite UI revisions and game languages.
"""
from __future__ import annotations

import cv2
import numpy as np


def yellow_replay_button(frame: np.ndarray) -> tuple[float, tuple[int, int]] | None:
    """Return (confidence, screen pixel centre) or None.

    Never uses placement text such as '#5' (which changes every match), and
    never selects the top spirit button / left battle-pass action.
    """
    if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
        return None
    H, W = frame.shape[:2]
    if W < 560 or H < 350:
        return None

    # Layout-normalised search region; smaller left-hand yellow action is ignored.
    x0, x1 = round(W * .60), round(W * .98)
    y0, y1 = round(H * .39), round(H * .72)
    roi = frame[y0:y1, x0:x1]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (19, 120, 190), (40, 255, 255))
    close_w = max(13, round(W * .020) | 1)
    close_h = max(5, round(H * .014) | 1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (close_w, close_h)))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    best = None
    for i in range(1, count):
        x, y, w, h, _ = (int(v) for v in stats[i])
        cx, cy = x0 + x + w // 2, y0 + y + h // 2
        if not (.64 <= cx / W <= .96 and .45 <= cy / H <= .66):
            continue
        if not (.18 <= w / W <= .43 and .045 <= h / H <= .14 and w / max(1, h) >= 3.4):
            continue
        patch = roi[y:y+h, x:x+w]
        yellow = cv2.inRange(cv2.cvtColor(patch, cv2.COLOR_BGR2HSV),
                             (19, 120, 190), (40, 255, 255))
        fill = cv2.countNonZero(yellow) / (w * h)
        if fill < .50:
            continue
        # A flat yellow effect is not necessarily a button: real UI has dark lettering.
        middle = patch[h//4:3*h//4, w//5:4*w//5]
        if middle.size == 0:
            continue
        dark = np.all(middle < 150, axis=2)
        if np.count_nonzero(dark) / dark.size < .012:
            continue
        # On this specific results screen, a pale "Back to lobby" panel
        # sits immediately above the yellow Replay button. We READ this
        # as context; we never click it or the "Stay with team" panel.
        abs_top = y0 + y
        upper = frame[max(0, abs_top-round(H*.065)):max(0, abs_top-round(H*.017)),
                      x0 + x + w//9:x0 + x + 8*w//9]
        if upper.size == 0:
            continue
        upper_hsv = cv2.cvtColor(upper, cv2.COLOR_BGR2HSV)
        pale = cv2.inRange(upper_hsv, (0, 0, 165), (179, 110, 255))
        if cv2.countNonZero(pale) / pale.size < .45:
            continue
        confidence = min(.98, .65 + .30 * fill)
        if best is None or confidence > best[0]:
            best = (float(confidence), (cx, cy))
    return best
