"""Settings and display/low-power configuration screens for the badge.

This module owns only settings UI construction and simple settings callbacks.
main.py still owns hardware, state, app switching, and backlight application.
"""

import lvgl as lv

from badge_config import (
    DISPLAY_ORIENTATION_FLIPPED,
    DISPLAY_ORIENTATION_ORIGINAL,
    LOW_POWER_MODE_DISABLED,
    LOW_POWER_MODE_LOGO,
    LOW_POWER_MODE_SCREEN_OFF,
    LOW_POWER_BACKLIGHT_MIN,
    LOW_POWER_TIMEOUT_MAX_MS,
    LOW_POWER_TIMEOUT_MIN_MS,
    LOW_POWER_TIMEOUT_STEP_MS,
)


LOW_POWER_MODE_CHOICES = (
    (LOW_POWER_MODE_DISABLED, "DISABLED"),
    (LOW_POWER_MODE_LOGO, "STATIC LOGO"),
    (LOW_POWER_MODE_SCREEN_OFF, "SCREEN OFF"),
)


def _clamp_percent(app, value, minimum=1, maximum=100):
    try:
        return app._clamp_percent(value, minimum, maximum)
    except Exception:
        try:
            value = int(value)
        except Exception:
            value = maximum

        if value < minimum:
            value = minimum
        elif value > maximum:
            value = maximum

        return value


def _clamp_timeout_ms(value):
    try:
        value = int(value)
    except Exception:
        value = 30_000

    if value < LOW_POWER_TIMEOUT_MIN_MS:
        value = LOW_POWER_TIMEOUT_MIN_MS
    elif value > LOW_POWER_TIMEOUT_MAX_MS:
        value = LOW_POWER_TIMEOUT_MAX_MS

    return value


def _mode_label(mode):
    for value, label in LOW_POWER_MODE_CHOICES:
        if value == mode:
            return label
    return "STATIC LOGO"


def _mode_index(mode):
    for i, item in enumerate(LOW_POWER_MODE_CHOICES):
        if item[0] == mode:
            return i
    return 1


def _format_timeout(ms):
    seconds = int(ms // 1000)
    if seconds < 60:
        return "%d SEC" % seconds

    minutes = seconds // 60
    rem = seconds % 60
    if rem == 0:
        return "%d MIN" % minutes

    return "%dM %02dS" % (minutes, rem)


def _sync_low_power_legacy_flag(app):
    app.low_power_screen_off = app.low_power_mode == LOW_POWER_MODE_SCREEN_OFF


def build_settings_menu(app):
    root = app.make_root()

    app.make_back_button(root)
    app.make_label(root, "// SETTINGS", 96, 14, 140, 16, "green")

    app.make_button(root, "LED CONFIG", 20, 58, 200, 38, app.show_leds)
    app.make_button(root, "DISPLAY BRIGHTNESS", 20, 104, 200, 38, app.show_screen_brightness)
    app.make_button(root, "ORIENTATION", 20, 150, 200, 38, app.show_orientation)
    app.make_button(root, "LOW POWER CONFIG", 20, 196, 200, 38, app.show_low_power_config)


def build_orientation(app):
    root = app.make_root()

    app.make_back_button(root, app.show_settings)
    app.make_label(root, "// ORIENTATION", 82, 14, 145, 16, "green")

    app.make_label(root, "BADGE ORIENTATION", 20, 64, 200, 16, "muted")
    current = app.make_label(root, "", 20, 88, 200, 22, "cyan")
    current.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

    def refresh():
        if app.display_orientation == DISPLAY_ORIENTATION_FLIPPED:
            current.set_text("ORIGINAL (DEFAULT)")
        else:
            current.set_text("FLIPPED 180")

    def choose(value):
        if app.display_orientation == value:
            return

        app.display_orientation = value
        if not app.save_settings():
            refresh()
            return

        # Applying orientation from a clean boot avoids rebuilding every
        # active LVGL object and guarantees touch starts in the same rotation.
        import machine
        machine.reset()

    app.make_button(
        root,
        "ORIGINAL",
        20,
        124,
        200,
        42,
        lambda: choose(DISPLAY_ORIENTATION_FLIPPED),
    )
    app.make_button(
        root,
        "FLIPPED 180",
        20,
        180,
        200,
        42,
        lambda: choose(DISPLAY_ORIENTATION_ORIGINAL),
    )
    app.make_label(root, "Changing this setting restarts the badge.", 20, 238, 200, 28, "muted")
    refresh()


def build_low_power_config(app):
    root = app.make_root()

    app.make_back_button(root, app.show_settings)
    app.make_label(root, "// LOW POWER", 92, 14, 130, 16, "green")

    app.make_label(root, "MODE", 20, 64, 80, 16, "muted")
    mode_value = app.make_label(root, "", 68, 92, 104, 18, "white")
    mode_value.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

    app.make_label(root, "TIMEOUT", 20, 138, 100, 16, "muted")
    timeout_value = app.make_label(root, "", 68, 166, 104, 18, "cyan")
    timeout_value.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

    hint = app.make_label(root, "", 12, 208, 216, 44, "muted")
    hint.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
    try:
        hint.set_long_mode(lv.label.LONG_MODE.WRAP)
    except Exception:
        pass

    def refresh_labels():
        try:
            mode = getattr(app, "low_power_mode", LOW_POWER_MODE_LOGO)
            mode_value.set_text(_mode_label(mode))
            mode_value.set_style_text_color(
                app_color("muted") if mode == LOW_POWER_MODE_DISABLED else app_color("white"),
                0,
            )
        except Exception:
            pass

        try:
            if getattr(app, "low_power_mode", LOW_POWER_MODE_LOGO) == LOW_POWER_MODE_DISABLED:
                timeout_value.set_text("OFF")
                timeout_value.set_style_text_color(app_color("muted"), 0)
                hint.set_text("Idle sleep is disabled.")
            else:
                timeout_value.set_text(_format_timeout(app.idle_timeout_ms))
                timeout_value.set_style_text_color(app_color("cyan"), 0)
                hint.set_text("Touch wakes the badge. LEDs stay unchanged.")
        except Exception:
            pass

    # settings_ui intentionally does not import card_carousel.color to avoid a
    # circular import edge. Reuse app.make_label colors via this tiny local map.
    def app_color(name):
        try:
            from card_carousel import color
            return color(name)
        except Exception:
            fallback = {
                "white": 0xD8F3E2,
                "muted": 0x6C9384,
                "cyan": 0x38E8FF,
            }
            return lv.color_hex(fallback.get(name, 0xFFFFFF))

    def set_mode(mode):
        app.low_power_mode = mode
        _sync_low_power_legacy_flag(app)
        app.save_settings()
        refresh_labels()

    def prev_mode():
        idx = _mode_index(getattr(app, "low_power_mode", LOW_POWER_MODE_LOGO))
        set_mode(LOW_POWER_MODE_CHOICES[(idx - 1) % len(LOW_POWER_MODE_CHOICES)][0])

    def next_mode():
        idx = _mode_index(getattr(app, "low_power_mode", LOW_POWER_MODE_LOGO))
        set_mode(LOW_POWER_MODE_CHOICES[(idx + 1) % len(LOW_POWER_MODE_CHOICES)][0])

    def set_timeout(value):
        app.idle_timeout_ms = _clamp_timeout_ms(value)
        app.save_settings()
        refresh_labels()

    def dec_timeout():
        set_timeout(app.idle_timeout_ms - LOW_POWER_TIMEOUT_STEP_MS)

    def inc_timeout():
        set_timeout(app.idle_timeout_ms + LOW_POWER_TIMEOUT_STEP_MS)

    app.make_button(root, "<", 20, 84, 42, 38, prev_mode)
    app.make_button(root, ">", 178, 84, 42, 38, next_mode)

    app.make_button(root, "-", 20, 158, 42, 38, dec_timeout)
    app.make_button(root, "+", 178, 158, 42, 38, inc_timeout)

    refresh_labels()


def build_display_brightness(app):
    root = app.make_root()

    app.make_back_button(root, app.show_settings)
    app.make_label(root, "// DISPLAY", 92, 14, 130, 16, "green")

    # Normal UI brightness.
    app.make_label(root, "UI BRIGHTNESS", 20, 62, 200, 16, "muted")
    screen_brightness_label = app.make_label(
        root,
        "",
        20,
        82,
        200,
        24,
        "white",
    )
    screen_brightness_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

    # Low-power logo / ambient display brightness.
    app.make_label(root, "AMBIENT LOGO", 20, 154, 200, 16, "muted")
    low_power_brightness_label = app.make_label(
        root,
        "",
        20,
        174,
        200,
        24,
        "cyan",
    )
    low_power_brightness_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

    def refresh_labels():
        try:
            screen_brightness_label.set_text("UI: %d%%" % app.screen_brightness)
        except Exception:
            pass

        try:
            low_power_brightness_label.set_text(
                "LOW POWER LOGO: %d%%" % app.low_power_backlight
            )
        except Exception:
            pass

    def set_screen_brightness(value):
        app.screen_brightness = _clamp_percent(app, value, 1, 100)

        if not app.low_power:
            app.set_backlight(app.screen_brightness)

        refresh_labels()
        app.save_settings()

    def set_low_power_backlight(value):
        app.low_power_backlight = _clamp_percent(
            app,
            value,
            LOW_POWER_BACKLIGHT_MIN,
            100,
        )

        # Preview immediately only if the badge is already in low-power logo mode.
        if app.low_power and getattr(app, "low_power_mode", LOW_POWER_MODE_LOGO) == LOW_POWER_MODE_LOGO:
            app.set_backlight(app.low_power_backlight)

        refresh_labels()
        app.save_settings()

    def dec_screen_brightness():
        set_screen_brightness(app.screen_brightness - 10)

    def inc_screen_brightness():
        set_screen_brightness(app.screen_brightness + 10)

    def dec_low_power_backlight():
        set_low_power_backlight(app.low_power_backlight - 5)

    def inc_low_power_backlight():
        set_low_power_backlight(app.low_power_backlight + 5)

    app.make_button(root, "-", 20, 108, 80, 38, dec_screen_brightness)
    app.make_button(root, "+", 140, 108, 80, 38, inc_screen_brightness)

    app.make_button(root, "-", 20, 200, 80, 38, dec_low_power_backlight)
    app.make_button(root, "+", 140, 200, 80, 38, inc_low_power_backlight)

    refresh_labels()
