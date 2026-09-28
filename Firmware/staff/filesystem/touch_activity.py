"""Global touch activity tracking.

The touch driver, buttons, and low-power timer all need one small shared signal:
"has the user touched anything recently?"

Universal navigation is handled by LVGL event callbacks in universal_nav.py.
Do not try to infer swipe gestures here from CST816S return values; that return
shape varies by driver build and made the gesture unreliable.
"""

import time

_last_touch_ms = 0
_touch_event_seq = 0


def note_touch_activity(x=None, y=None):
    global _last_touch_ms, _touch_event_seq

    _last_touch_ms = time.ticks_ms()
    _touch_event_seq += 1


def get_touch_snapshot():
    return _touch_event_seq, _last_touch_ms
