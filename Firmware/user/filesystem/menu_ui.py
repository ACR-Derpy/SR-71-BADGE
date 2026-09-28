"""Main menu screen."""

import time

import lvgl as lv

from card_carousel import CARDS
from touch_activity import note_touch_activity


def build_main_menu(app):
    root = app.make_root()

    title = app.make_label(root, "// BADGE OS", 15, 8, 180, 28, "green")
    title.add_flag(lv.obj.FLAG.CLICKABLE)

    # Keep Credits as an easter egg, but use one large native touch target and
    # count presses immediately so release jitter cannot lose a tap.
    try:
        title.set_ext_click_area(20)
    except Exception:
        pass

    def title_tap(event):
        del event
        note_touch_activity()

        if app.low_power:
            app.exit_low_power_mode()
            return

        now = time.ticks_ms()
        if time.ticks_diff(now, app._credits_tap_t) > 1800:
            app._credits_taps = 0

        app._credits_taps += 1
        app._credits_tap_t = now

        if app._credits_taps >= 3:
            app._credits_taps = 0
            app.show_credits()

    app.callbacks.append(title_tap)
    title.add_event_cb(title_tap, lv.EVENT.PRESSED, None)

    app.make_label(root, "MAIN MENU", 8, 35, 180, 22, "white")

    unlocked_count = 0
    for card in CARDS:
        try:
            if card.get("unlocked", False):
                unlocked_count += 1
        except Exception:
            pass

    card_total = len(CARDS)
    collection_text = "CARDS UNLOCKED  %02d/%02d" % (
        unlocked_count,
        card_total,
    )
    collection_label = app.make_label(
        root,
        collection_text,
        20,
        63,
        200,
        16,
        "cyan",
    )
    collection_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

    app.make_button(root, "CARD DISPLAY", 20, 91, 200, 46, app.show_cards)
    app.make_button(root, "NFC OPERATIONS", 20, 148, 200, 46, app.show_trade)
    app.make_button(root, "SETTINGS", 20, 205, 200, 46, app.show_settings)
