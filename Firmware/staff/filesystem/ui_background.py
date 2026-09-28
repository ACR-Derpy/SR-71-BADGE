"""Lightweight animated SR-71 / tactical-terminal background chrome.

The grid remains static. A single LVGL timer moves a few tiny telemetry objects,
keeping invalidation regions small and avoiding full-screen animation redraws.
"""

import lvgl as lv


WIDTH = 240
HEIGHT = 280

BG_BASE = 0x02070B
BG_GRID = 0x0B2029
BG_GRID_FAINT = 0x07151C
BG_ACCENT = 0x173B47
BG_POINT = 0x245466
BG_CONTACT = 0x2E7082
BG_SCAN = 0x5C2499

# Retain timer and callback references for MicroPython/LVGL. States remove
# themselves when their parent screen is deleted.
_ACTIVE_BACKGROUNDS = []


def _remove_flag(obj, flag):
    try:
        obj.remove_flag(flag)
    except Exception:
        try:
            obj.clear_flag(flag)
        except Exception:
            pass


def _plain(parent, x, y, w, h, color_value):
    obj = lv.obj(parent)
    obj.set_pos(x, y)
    obj.set_size(w, h)
    obj.set_style_bg_color(lv.color_hex(color_value), 0)
    obj.set_style_bg_opa(lv.OPA.COVER, 0)
    obj.set_style_border_width(0, 0)
    obj.set_style_radius(0, 0)
    obj.set_style_pad_all(0, 0)
    _remove_flag(obj, lv.obj.FLAG.SCROLLABLE)
    _remove_flag(obj, lv.obj.FLAG.CLICKABLE)
    return obj


def _delete_timer(timer):
    if timer is None:
        return

    for name in ("delete", "_del", "del_"):
        try:
            getattr(timer, name)()
            return
        except Exception:
            pass

    try:
        lv.timer_del(timer)
    except Exception:
        pass


def _set_x_safe(obj, value):
    try:
        obj.set_x(int(value))
        return True
    except Exception:
        try:
            obj.set_pos(int(value), obj.get_y())
            return True
        except Exception:
            return False


def _set_y_safe(obj, value):
    try:
        obj.set_y(int(value))
        return True
    except Exception:
        try:
            obj.set_pos(obj.get_x(), int(value))
            return True
        except Exception:
            return False


def _advance_bounce(item):
    value = item["value"] + item["direction"] * item["step"]

    if value >= item["maximum"]:
        value = item["maximum"]
        item["direction"] = -1
    elif value <= item["minimum"]:
        value = item["minimum"]
        item["direction"] = 1

    item["value"] = value

    if item["axis"] == "y":
        return _set_y_safe(item["obj"], value)

    return _set_x_safe(item["obj"], value)


def _start_background_timer(parent, moving_items, period_ms=100):
    """Drive tiny moving contacts using the broadly supported timer API."""
    state = {
        "parent": parent,
        "items": moving_items,
        "timer": None,
        "tick": 0,
        "timer_cb": None,
        "delete_cb": None,
    }

    def timer_cb(_timer):
        state["tick"] += 1

        for item in state["items"]:
            divider = item.get("divider", 1)
            if divider < 1:
                divider = 1

            if state["tick"] % divider == 0:
                if not _advance_bounce(item):
                    _delete_timer(state.get("timer"))
                    state["timer"] = None
                    return

    def delete_cb(_event):
        _delete_timer(state.get("timer"))
        state["timer"] = None

        try:
            _ACTIVE_BACKGROUNDS.remove(state)
        except Exception:
            pass

    state["timer_cb"] = timer_cb
    state["delete_cb"] = delete_cb
    _ACTIVE_BACKGROUNDS.append(state)

    try:
        state["timer"] = lv.timer_create(timer_cb, period_ms, None)
    except Exception as exc:
        print("Background timer unavailable:", exc)
        try:
            _ACTIVE_BACKGROUNDS.remove(state)
        except Exception:
            pass
        return None

    try:
        parent.add_event_cb(delete_cb, lv.EVENT.DELETE, None)
    except Exception:
        # The timer still works. If this binding lacks DELETE events, the next
        # failed object update stops the timer automatically.
        pass

    return state["timer"]


def pause_tactical_background(parent):
    """Pause the animated background belonging to one active screen."""
    for state in _ACTIVE_BACKGROUNDS:
        if state.get("parent") is not parent:
            continue

        timer = state.get("timer")
        if timer is None:
            return True

        try:
            timer.pause()
            return True
        except Exception:
            # This screen will be deleted when the user leaves the carousel,
            # so deleting the unsupported timer is equivalent to pausing it.
            _delete_timer(timer)
            state["timer"] = None
            return True

    return False


def add_tactical_background(parent, width=WIDTH, height=HEIGHT):
    """Add a low-cost animated Halo/SR-71 tactical background to *parent*.

    Call this before creating labels, buttons, or screen-specific panels so all
    interactive controls naturally remain above the background.
    """
    try:
        parent.set_style_bg_color(lv.color_hex(BG_BASE), 0)
        parent.set_style_bg_opa(lv.OPA.COVER, 0)
    except Exception:
        pass

    objects = []

    # Sparse horizontal scanlines. These remain completely static.
    for y in (34, 66, 98, 130, 162, 194, 226, 258):
        objects.append(_plain(parent, 0, y, width, 1, BG_GRID_FAINT))

    # Wide tactical grid divisions.
    for x in (40, 120, 200):
        objects.append(_plain(parent, x, 0, 1, height, BG_GRID))

    # Segmented center datum line.
    horizon_y = 139
    objects.append(_plain(parent, 8, horizon_y, 76, 1, BG_ACCENT))
    objects.append(_plain(parent, 96, horizon_y, 48, 1, BG_ACCENT))
    objects.append(_plain(parent, 156, horizon_y, 76, 1, BG_ACCENT))

    # Technical corner brackets.
    bracket = 12
    inset = 5
    objects.append(_plain(parent, inset, inset, bracket, 1, BG_ACCENT))
    objects.append(_plain(parent, inset, inset, 1, bracket, BG_ACCENT))
    objects.append(_plain(parent, width - inset - bracket, inset, bracket, 1, BG_ACCENT))
    objects.append(_plain(parent, width - inset - 1, inset, 1, bracket, BG_ACCENT))
    objects.append(_plain(parent, inset, height - inset - 1, bracket, 1, BG_ACCENT))
    objects.append(_plain(parent, inset, height - inset - bracket, 1, bracket, BG_ACCENT))
    objects.append(_plain(parent, width - inset - bracket, height - inset - 1, bracket, 1, BG_ACCENT))
    objects.append(_plain(parent, width - inset - 1, height - inset - bracket, 1, bracket, BG_ACCENT))

    # Fixed low-contrast sensor points provide depth behind moving returns.
    for x, y in (
        (18, 52),
        (218, 48),
        (29, 177),
        (210, 212),
        (101, 19),
        (151, 246),
    ):
        objects.append(_plain(parent, x, y, 2, 2, BG_POINT))

    contact_a = _plain(parent, 18, 57, 3, 2, BG_CONTACT)
    contact_b = _plain(parent, 188, 181, 2, 2, BG_CONTACT)
    contact_c = _plain(parent, 74, 239, 3, 1, BG_CONTACT)
    edge_scan = _plain(parent, width - 15, 24, 10, 1, BG_SCAN)
    objects.extend((contact_a, contact_b, contact_c, edge_scan))

    # Different update divisors keep the contacts from moving in lockstep.
    moving_items = (
        {
            "obj": contact_a,
            "axis": "x",
            "value": 18,
            "minimum": 18,
            "maximum": 82,
            "direction": 1,
            "step": 1,
            "divider": 2,
        },
        {
            "obj": contact_b,
            "axis": "x",
            "value": 188,
            "minimum": 126,
            "maximum": 188,
            "direction": -1,
            "step": 1,
            "divider": 3,
        },
        {
            "obj": contact_c,
            "axis": "x",
            "value": 74,
            "minimum": 74,
            "maximum": 158,
            "direction": 1,
            "step": 1,
            "divider": 4,
        },
        {
            "obj": edge_scan,
            "axis": "y",
            "value": 24,
            "minimum": 24,
            "maximum": height - 25,
            "direction": 1,
            "step": 1,
            "divider": 2,
        },
    )

    _start_background_timer(parent, moving_items, 100)

    return objects
