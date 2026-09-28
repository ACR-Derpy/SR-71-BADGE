"""Non-blocking, universal swipe-up navigation.

The gesture is observed on LVGL's input device instead of by a transparent
object layered over the UI.  Buttons, cards, and every other control therefore
remain the real touch targets.  The only object added to a screen is a small,
non-clickable home indicator.
"""

import lvgl as lv

try:
    from badge_config import (
        HEIGHT,
        UNIVERSAL_MENU_SWIPE_HANDLE_H,
        UNIVERSAL_MENU_SWIPE_HANDLE_W,
        UNIVERSAL_MENU_SWIPE_MIN_TRAVEL,
        UNIVERSAL_MENU_SWIPE_START_ZONE_H,
        WIDTH,
    )
except Exception:
    WIDTH = 240
    HEIGHT = 280
    UNIVERSAL_MENU_SWIPE_START_ZONE_H = 80
    UNIVERSAL_MENU_SWIPE_MIN_TRAVEL = 30
    UNIVERSAL_MENU_SWIPE_HANDLE_W = 132
    UNIVERSAL_MENU_SWIPE_HANDLE_H = 6


_INDICATOR_COLOR = 0xD8F3E2
_INDICATOR_OPA = 220

_AXIS_NONE = 0
_AXIS_UP = 1
_AXIS_REJECTED = 2
_AXIS_LOCK_PX = 6
_HORIZONTAL_LOCK_PX = 22

_universal_menu_swipe_enabled = True


def set_universal_menu_swipe_enabled(enabled):
    global _universal_menu_swipe_enabled
    _universal_menu_swipe_enabled = bool(enabled)


def is_universal_menu_swipe_enabled():
    return _universal_menu_swipe_enabled


def _remove_flag(obj, flag):
    try:
        obj.remove_flag(flag)
    except Exception:
        try:
            obj.clear_flag(flag)
        except Exception:
            pass


def _reset_gesture(app):
    app._universal_nav_pressed = False
    app._universal_nav_armed = False
    app._universal_nav_start_x = None
    app._universal_nav_start_y = None
    app._universal_nav_last_x = None
    app._universal_nav_last_y = None
    app._universal_nav_axis = _AXIS_NONE
    app._universal_nav_recognized = False


def _gesture_is_available(app):
    if not _universal_menu_swipe_enabled:
        return False
    if getattr(app, "low_power", False):
        return False
    return getattr(app, "active_app", None) not in (None, "menu", "credits")


def _resolve_indev(app, input_device=None):
    """Return the LVGL indev object owned by the touch driver."""
    source = input_device
    if source is None:
        source = getattr(app, "touch", None)

    if source is not None:
        candidate = getattr(source, "_indev_drv", source)
        if hasattr(candidate, "add_event_cb") and hasattr(candidate, "get_point"):
            return candidate

    # This also keeps BadgeApp usable in a simulator that does not pass the
    # hardware touch-driver instance into its constructor.
    try:
        candidate = lv.indev_get_next(None)
        if candidate is not None:
            return candidate
    except Exception:
        pass

    return None


def _get_touch_xy(app, indev):
    try:
        point = getattr(app, "_universal_nav_point", None)
        if point is None:
            point = lv.point_t()
            app._universal_nav_point = point

        indev.get_point(point)
        return point.x, point.y
    except Exception:
        return None, None


def _movement(app, x, y):
    start_x = getattr(app, "_universal_nav_start_x", None)
    start_y = getattr(app, "_universal_nav_start_y", None)

    dx = 0 if x is None or start_x is None else x - start_x
    dy = 0 if y is None or start_y is None else y - start_y
    return dx, dy


def _track_bottom_entry(app, x, y):
    """Arm anywhere on-screen and anchor at the lowest sensed touch point."""
    if x is None or y is None:
        return False

    armed = getattr(app, "_universal_nav_armed", False)
    anchor_y = getattr(app, "_universal_nav_start_y", None)

    if not armed:
        # A deliberate upward swipe may begin anywhere on the display. Axis
        # locking below still rejects horizontal carousel movement.
        app._universal_nav_armed = True
        app._universal_nav_start_x = x
        app._universal_nav_start_y = y
        app._universal_nav_axis = _AXIS_NONE
        app._universal_nav_recognized = False
        return True

    if anchor_y is None or y > anchor_y:
        # Curved-edge contact patches often settle several pixels toward the
        # bezel after PRESSED. Count vertical travel from that lower point, but
        # retain the armed x origin so incremental horizontal drift cannot hide
        # a carousel swipe. A decisive horizontal lock stays permanent.
        app._universal_nav_start_y = y
        app._universal_nav_recognized = False
        if getattr(app, "_universal_nav_axis", _AXIS_NONE) != _AXIS_REJECTED:
            app._universal_nav_axis = _AXIS_NONE

    return True


def _is_upward(dx, dy, minimum):
    upward = -dy
    if upward < minimum:
        return False

    # Allow moderate diagonal drift. Strong horizontal movement is rejected by
    # the axis lock before it can become a home gesture.
    return upward * 3 >= abs(dx) * 2


def _lock_axis(app, dx, dy):
    """Lock only after motion is clear; edge-entry samples are often noisy."""
    axis = getattr(app, "_universal_nav_axis", _AXIS_NONE)
    if axis != _AXIS_NONE:
        return axis

    upward = -dy
    abs_dx = abs(dx)

    if (
        upward >= _AXIS_LOCK_PX
        and upward * 3 >= abs_dx * 2
    ):
        axis = _AXIS_UP
    elif (
        abs_dx >= _HORIZONTAL_LOCK_PX
        and abs_dx * 2 >= abs(dy) * 3
    ):
        axis = _AXIS_REJECTED

    app._universal_nav_axis = axis
    return axis


def _queue_menu(app):
    """Navigate after LVGL finishes the current input dispatch."""
    if getattr(app, "_universal_nav_menu_pending", False):
        return

    app._universal_nav_menu_pending = True

    def navigate(_arg=None):
        app._universal_nav_menu_pending = False
        app._universal_nav_async_timer = None

        if not _gesture_is_available(app):
            return

        print("Universal swipe -> menu")
        app.show_menu()

    # Retain the callback on MicroPython even when lv.async_call is used.
    app._universal_nav_deferred_cb = navigate

    try:
        lv.async_call(navigate, None)
        return
    except Exception:
        pass

    # All supported badge builds expose LVGL timers.  This fallback is kept for
    # bindings that do not export lv.async_call.
    try:
        timer = lv.timer_create(navigate, 1, None)
        timer.set_repeat_count(1)
        app._universal_nav_async_timer = timer
    except Exception as exc:
        app._universal_nav_menu_pending = False
        print("Universal nav defer failed:", exc)


def _make_cb_pressed(app, indev):
    def cb(event):
        del event
        _reset_gesture(app)

        if not _gesture_is_available(app):
            return

        x, y = _get_touch_xy(app, indev)
        # PRESSED can precede the first usable coordinate on this controller.
        # Keep the contact active so a later in-band sample can still arm it.
        app._universal_nav_pressed = True
        if x is None or y is None:
            return

        # Track every contact. The recognizer may begin anywhere on-screen and
        # never creates an LVGL hitbox over the active view.
        app._universal_nav_start_x = x
        app._universal_nav_start_y = y
        app._universal_nav_last_x = x
        app._universal_nav_last_y = y
        _track_bottom_entry(app, x, y)

    return cb


def _make_cb_pressing(app, indev):
    def cb(event):
        del event
        if not getattr(app, "_universal_nav_pressed", False):
            # A contact entering from below the glass can have its initial
            # PRESSED coordinate outside the controller's usable range. Some
            # builds then deliver the first usable point as PRESSING.
            if not _gesture_is_available(app):
                return
            x, y = _get_touch_xy(app, indev)
            if x is None or y is None:
                return
            _reset_gesture(app)
            app._universal_nav_pressed = True
            app._universal_nav_last_x = x
            app._universal_nav_last_y = y
            app._universal_nav_start_x = x
            app._universal_nav_start_y = (
                HEIGHT - 1
                if y >= HEIGHT - UNIVERSAL_MENU_SWIPE_START_ZONE_H
                else y
            )
            app._universal_nav_armed = True
            return
        if not _gesture_is_available(app):
            _reset_gesture(app)
            return

        x, y = _get_touch_xy(app, indev)
        if x is None or y is None:
            return

        app._universal_nav_last_x = x
        app._universal_nav_last_y = y
        if not _track_bottom_entry(app, x, y):
            return
        dx, dy = _movement(app, x, y)
        axis = _lock_axis(app, dx, dy)

        if axis == _AXIS_UP and _is_upward(
            dx, dy, UNIVERSAL_MENU_SWIPE_MIN_TRAVEL
        ):
            app._universal_nav_recognized = True

    return cb


def _make_cb_released(app, indev):
    def cb(event):
        del event
        if not getattr(app, "_universal_nav_pressed", False):
            _reset_gesture(app)
            return

        x, y = _get_touch_xy(app, indev)
        if x is None:
            x = getattr(app, "_universal_nav_last_x", None)
        if y is None:
            y = getattr(app, "_universal_nav_last_y", None)

        if not _track_bottom_entry(app, x, y):
            _reset_gesture(app)
            return

        dx, dy = _movement(app, x, y)
        axis = getattr(app, "_universal_nav_axis", _AXIS_NONE)
        recognized = getattr(app, "_universal_nav_recognized", False)

        # Release-time classification covers fast flicks with few PRESSING
        # samples, while the axis lock keeps horizontal card swipes untouched.
        should_navigate = recognized or (
            axis != _AXIS_REJECTED
            and _is_upward(dx, dy, UNIVERSAL_MENU_SWIPE_MIN_TRAVEL)
        )

        _reset_gesture(app)
        if should_navigate and _gesture_is_available(app):
            # Input-device callbacks run before the event reaches the widget.
            # Consume only the recognized home gesture so its RELEASED cannot
            # also click the control underneath it. Ordinary taps and swipes
            # are never stopped and continue through LVGL normally.
            try:
                indev.stop_processing()
            except Exception:
                pass
            _queue_menu(app)

    return cb


def _make_cb_gesture(app, indev):
    def cb(event):
        del event
        if not getattr(app, "_universal_nav_pressed", False):
            # Recover the same edge-entry case on LVGL builds that emit a
            # GESTURE event but no input-device PRESSING callbacks.
            if not _gesture_is_available(app):
                return
            x, y = _get_touch_xy(app, indev)
            if x is None or y is None:
                return
            _reset_gesture(app)
            app._universal_nav_pressed = True
            app._universal_nav_last_x = x
            app._universal_nav_last_y = y
            app._universal_nav_start_x = x
            app._universal_nav_start_y = (
                HEIGHT - 1
                if y >= HEIGHT - UNIVERSAL_MENU_SWIPE_START_ZONE_H
                else y
            )
            app._universal_nav_armed = True
            return
        if not _gesture_is_available(app):
            _reset_gesture(app)
            return

        x, y = _get_touch_xy(app, indev)
        if x is None or y is None:
            return

        app._universal_nav_last_x = x
        app._universal_nav_last_y = y
        if not _track_bottom_entry(app, x, y):
            return
        dx, dy = _movement(app, x, y)
        # Indev GESTURE is available even on LVGL builds that do not send
        # PRESSING to input-device callbacks. Ambiguous edge noise stays
        # unlocked until later samples or RELEASED clarify the direction.
        axis = _lock_axis(app, dx, dy)

        if axis == _AXIS_UP and _is_upward(
            dx, dy, UNIVERSAL_MENU_SWIPE_MIN_TRAVEL
        ):
            app._universal_nav_recognized = True

    return cb


def _make_cb_click_blocker(app, indev):
    def cb(event):
        del event
        # LVGL sends RELEASED, SHORT_CLICKED, and CLICKED as separate indev
        # events. stop_processing() applies to only the event currently being
        # dispatched, so consume each click event that follows a recognized
        # home gesture. The pending flag is set only for that one gesture.
        if getattr(app, "_universal_nav_menu_pending", False):
            try:
                indev.stop_processing()
            except Exception:
                pass

    return cb


def install_universal_input_observer(app, input_device=None):
    """Attach the non-consuming gesture observer once for this BadgeApp."""
    indev = _resolve_indev(app, input_device)
    if indev is None:
        return None

    if getattr(app, "_universal_nav_indev", None) is indev:
        return indev
    if getattr(app, "_universal_nav_failed_indev", None) is indev:
        return None

    pressed_cb = _make_cb_pressed(app, indev)
    pressing_cb = _make_cb_pressing(app, indev)
    gesture_cb = _make_cb_gesture(app, indev)
    released_cb = _make_cb_released(app, indev)
    click_blocker_cb = _make_cb_click_blocker(app, indev)

    click_events = []
    for event_name in (
        "SHORT_CLICKED",
        "CLICKED",
        "SINGLE_CLICKED",
        "DOUBLE_CLICKED",
        "TRIPLE_CLICKED",
    ):
        event_code = getattr(lv.EVENT, event_name, None)
        if event_code is not None and event_code not in click_events:
            click_events.append(event_code)

    gesture_event = getattr(lv.EVENT, "GESTURE", None)

    def observer_cb(event):
        try:
            code = event.get_code()
        except Exception:
            return

        if code == lv.EVENT.PRESSED:
            pressed_cb(event)
        elif code == lv.EVENT.PRESSING:
            pressing_cb(event)
        elif code == lv.EVENT.RELEASED:
            released_cb(event)
        elif gesture_event is not None and code == gesture_event:
            gesture_cb(event)
        elif code in click_events:
            click_blocker_cb(event)

    # Root every closure before registering it with native LVGL. One ALL
    # observer replaces up to nine native event descriptors and makes the
    # install atomic: it can no longer leave a half-installed callback set.
    app._universal_nav_callbacks = [
        observer_cb,
        pressed_cb,
        pressing_cb,
        gesture_cb,
        released_cb,
        click_blocker_cb,
    ]

    try:
        indev.add_event_cb(observer_cb, lv.EVENT.ALL, None)
    except Exception as exc:
        print("Universal input observer install failed:", exc)
        # Some bindings can raise after allocating the descriptor. Remove the
        # callback if possible, then fail open and do not retry on every view.
        try:
            indev.remove_event_cb(observer_cb)
        except Exception:
            pass
        app._universal_nav_callbacks = []
        app._universal_nav_failed_indev = indev
        return None

    app._universal_nav_indev = indev
    app._universal_nav_failed_indev = None
    _reset_gesture(app)
    return indev


def _make_home_indicator(parent):
    """Create an Apple-style visual cue that can never receive a touch."""
    indicator = lv.obj(parent)
    indicator.set_size(
        UNIVERSAL_MENU_SWIPE_HANDLE_W,
        UNIVERSAL_MENU_SWIPE_HANDLE_H,
    )
    indicator.set_pos(
        (WIDTH - UNIVERSAL_MENU_SWIPE_HANDLE_W) // 2,
        HEIGHT - UNIVERSAL_MENU_SWIPE_HANDLE_H - 4,
    )
    indicator.set_style_bg_color(lv.color_hex(_INDICATOR_COLOR), 0)
    indicator.set_style_bg_opa(_INDICATOR_OPA, 0)
    indicator.set_style_border_width(0, 0)
    indicator.set_style_radius(UNIVERSAL_MENU_SWIPE_HANDLE_H, 0)
    indicator.set_style_pad_all(0, 0)
    _remove_flag(indicator, lv.obj.FLAG.SCROLLABLE)
    _remove_flag(indicator, lv.obj.FLAG.CLICKABLE)

    try:
        indicator.move_foreground()
    except Exception:
        pass

    return indicator


def set_indicator_visible(app, visible):
    indicator = getattr(app, "_universal_menu_swipe_handle", None)
    if indicator is None:
        return

    try:
        if visible:
            _remove_flag(indicator, lv.obj.FLAG.HIDDEN)
            indicator.move_foreground()
        else:
            indicator.add_flag(lv.obj.FLAG.HIDDEN)
    except Exception:
        pass

    if not visible:
        _reset_gesture(app)


def install_universal_menu_swipe(app):
    """Install the input observer and the current screen's visual indicator."""
    _reset_gesture(app)

    if getattr(app, "active_root", None) is None:
        return None
    if getattr(app, "active_app", None) == "menu":
        app._universal_menu_swipe_rail = None
        app._universal_menu_swipe_handle = None
        return None

    if install_universal_input_observer(app) is None:
        app._universal_menu_swipe_rail = None
        app._universal_menu_swipe_handle = None
        return None

    try:
        indicator = _make_home_indicator(app.active_root)
        # There is deliberately no rail/hitbox.  Keep the old attribute as
        # None so legacy code cannot accidentally make an overlay clickable.
        app._universal_menu_swipe_rail = None
        app._universal_menu_swipe_handle = indicator

        if not _universal_menu_swipe_enabled:
            set_indicator_visible(app, False)

        return indicator
    except Exception as exc:
        print("Universal home indicator install failed:", exc)
        app._universal_menu_swipe_rail = None
        app._universal_menu_swipe_handle = None
        return None
