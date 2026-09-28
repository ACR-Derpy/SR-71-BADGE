"""LED settings screen.

This file owns the LVGL widgets and callbacks for LED configuration. The app
object still owns the selected LED state and applies it through LEDRuntime.
"""

import lvgl as lv

from card_carousel import color

LED_PATTERNS = (
    "NONE",
    "Solid",
    "Rainbow",
    "Theater",
    "Scanner",
    "Breathe",
    "Twinkle",
    "Rainbow Breathe",
    "Flame",
    "Afterburner",
)

LED_COLORS = (
    "PURPLE",
    "BLUE",
    "CYAN",
    "AMBER",
    "GOLD",
    "JADE",
    "MAGENTA",
    "ORANGE",
    "PINK",
    "RED",
    "GREEN",
    "YELLOW",
    "WARM WHITE",
)

LED_COLORLESS_PATTERNS = (
    "NONE",
    "LightShow",
    "Dead",
    "Connecting",
    "Rainbow",
    "Rainbow Breathe",
    "GOLDEN",
)

GOLDEN_SHIMMER_RATES = ("RARE", "NORMAL", "OFTEN")


def collection_progress(app):
    total = 0
    unlocked = 0
    try:
        from card_carousel import CARDS
        for card in CARDS:
            total += 1
            if bool(card.get("unlocked", False)):
                unlocked += 1
    except Exception:
        pass
    return unlocked, total


def available_led_patterns(app):
    patterns = LED_PATTERNS
    unlocked, total = collection_progress(app)
    if total and unlocked * 2 >= total:
        patterns = patterns + ("BLACKBIRD",)
    if total and unlocked >= total:
        patterns = patterns + ("GOLDEN",)
    return patterns


def normalize_led_state(app):
    if app.led_pattern not in available_led_patterns(app):
        app.led_pattern = "Afterburner"

    if app.led_color not in LED_COLORS:
        app.led_color = "PURPLE"


def led_pattern_uses_color(pattern):
    return pattern not in LED_COLORLESS_PATTERNS


def build_led_settings(app):
    normalize_led_state(app)
    patterns = available_led_patterns(app)

    root = app.make_root()
    app.make_back_button(root, app.show_settings)
    app.make_label(root, "// LED SETTINGS", 86, 14, 150, 16, "green")

    # Row layout constants.
    lx = 8
    btn_w = 44
    btn_h = 40
    vx = lx + btn_w + 4
    vw = 240 - vx - 4 - btn_w - 8
    rx = vx + vw + 4
    value_y_offset = (btn_h - 16) // 2

    # Status box.
    status_box = lv.obj(root)
    status_box.set_pos(10, 62)
    status_box.set_size(220, 36)
    status_box.set_style_bg_color(color("panel_2"), 0)
    status_box.set_style_bg_opa(lv.OPA.COVER, 0)
    status_box.set_style_border_color(color("green_dim"), 0)
    status_box.set_style_border_width(1, 0)
    status_box.set_style_radius(3, 0)
    status_box.set_style_pad_all(4, 0)

    try:
        status_box.remove_flag(lv.obj.FLAG.SCROLLABLE)
        status_box.remove_flag(lv.obj.FLAG.CLICKABLE)
    except Exception:
        pass

    status_label = lv.label(status_box)
    status_label.set_size(212, 28)
    status_label.set_style_text_color(color("white"), 0)
    status_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

    try:
        status_label.align(lv.ALIGN.CENTER, 0, 0)
    except Exception:
        status_label.set_pos(0, 0)

    try:
        status_label.set_long_mode(lv.label.LONG_MODE.WRAP)
    except Exception:
        pass

    # Pattern row.
    app.make_label(root, "PATTERN", lx, 103, 80, 16, "muted")
    pattern_value = app.make_label(root, "", vx, 117 + value_y_offset, vw, 16, "white")
    pattern_value.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

    # Color row.
    color_row_label = app.make_label(root, "COLOR", lx, 162, 80, 16, "muted")
    color_value = app.make_label(root, "", vx, 176 + value_y_offset, vw, 16, "white")
    color_value.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

    # Brightness row.
    app.make_label(root, "BRIGHTNESS", lx, 221, 120, 16, "muted")
    brightness_value = app.make_label(root, "", vx, 235 + value_y_offset, vw, 16, "cyan")
    brightness_value.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

    refs = {
        "status_label": status_label,
        "pattern_value": pattern_value,
        "color_row_label": color_row_label,
        "color_value": color_value,
        "brightness_value": brightness_value,
        "color_buttons": [],
    }

    def update_led_ui():
        on = app.led_pattern != "NONE"
        uses_color = led_pattern_uses_color(app.led_pattern)
        uses_shimmer = app.led_pattern == "GOLDEN"

        try:
            pattern_value.set_text(app.led_pattern)
            pattern_value.set_style_text_color(color("white" if on else "muted"), 0)
        except Exception:
            pass

        try:
            if uses_shimmer:
                color_row_label.set_text("SHIMMER")
            else:
                color_row_label.set_text(
                    "BODY COLOR" if app.led_pattern == "Flame" else "COLOR"
                )
            for widget in refs["color_buttons"] + [color_row_label, color_value]:
                if uses_color or uses_shimmer:
                    widget.remove_flag(lv.obj.FLAG.HIDDEN)
                else:
                    widget.add_flag(lv.obj.FLAG.HIDDEN)

            if uses_shimmer:
                color_value.set_text(app.golden_shimmer)
            elif uses_color:
                color_value.set_text(app.led_color)

        except Exception:
            pass

        try:
            brightness_value.set_text("%d%%" % app.led_brightness)
            brightness_value.set_style_text_color(color("cyan" if on else "muted"), 0)
        except Exception:
            pass

        try:
            if not on:
                status_label.set_text("OFF")
                status_label.set_style_text_color(color("muted"), 0)

            elif uses_shimmer:
                status_label.set_text(
                    "%s  /  %s  /  %d%%"
                    % (app.led_pattern, app.golden_shimmer, app.led_brightness)
                )
                status_label.set_style_text_color(color("green"), 0)

            elif uses_color:
                status_label.set_text(
                    "%s  /  %s  /  %d%%"
                    % (app.led_pattern, app.led_color, app.led_brightness)
                )
                status_label.set_style_text_color(color("green"), 0)

            else:
                status_label.set_text("%s  /  %d%%" % (app.led_pattern, app.led_brightness))
                status_label.set_style_text_color(color("green"), 0)

        except Exception:
            pass

    def commit_led_change():
        update_led_ui()
        app.save_settings()
        app.apply_led_mode()

    def prev_led_pattern():
        idx = patterns.index(app.led_pattern)
        app.led_pattern = patterns[(idx - 1) % len(patterns)]
        app.led_enabled = app.led_pattern != "NONE"
        commit_led_change()

    def next_led_pattern():
        idx = patterns.index(app.led_pattern)
        app.led_pattern = patterns[(idx + 1) % len(patterns)]
        app.led_enabled = app.led_pattern != "NONE"
        commit_led_change()

    def prev_led_color():
        if app.led_pattern == "GOLDEN":
            idx = GOLDEN_SHIMMER_RATES.index(app.golden_shimmer)
            app.golden_shimmer = GOLDEN_SHIMMER_RATES[
                (idx - 1) % len(GOLDEN_SHIMMER_RATES)
            ]
            commit_led_change()
            return
        if not led_pattern_uses_color(app.led_pattern):
            return

        idx = LED_COLORS.index(app.led_color)
        app.led_color = LED_COLORS[(idx - 1) % len(LED_COLORS)]
        commit_led_change()

    def next_led_color():
        if app.led_pattern == "GOLDEN":
            idx = GOLDEN_SHIMMER_RATES.index(app.golden_shimmer)
            app.golden_shimmer = GOLDEN_SHIMMER_RATES[
                (idx + 1) % len(GOLDEN_SHIMMER_RATES)
            ]
            commit_led_change()
            return
        if not led_pattern_uses_color(app.led_pattern):
            return

        idx = LED_COLORS.index(app.led_color)
        app.led_color = LED_COLORS[(idx + 1) % len(LED_COLORS)]
        commit_led_change()

    def dec_brightness():
        app.led_brightness = max(10, app.led_brightness - 10)
        commit_led_change()

    def inc_brightness():
        app.led_brightness = min(100, app.led_brightness + 10)
        commit_led_change()

    app.make_button(root, "<", lx, 117, btn_w, btn_h, prev_led_pattern)
    app.make_button(root, ">", rx, 117, btn_w, btn_h, next_led_pattern)

    color_prev_button = app.make_button(root, "<", lx, 176, btn_w, btn_h, prev_led_color)
    color_next_button = app.make_button(root, ">", rx, 176, btn_w, btn_h, next_led_color)
    refs["color_buttons"] = [color_prev_button, color_next_button]

    app.make_button(root, "-", lx, 235, btn_w, btn_h, dec_brightness)
    app.make_button(root, "+", rx, 235, btn_w, btn_h, inc_brightness)

    update_led_ui()
