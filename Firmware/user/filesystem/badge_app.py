"""Badge application shell.

This class owns app state, routing, and shared helpers. Individual screens live
in smaller modules so main.py can stay focused on boot/setup.
"""

import gc
import time

import lvgl as lv

from backlight import set_backlight_percent
from badge_config import (
    DEFAULT_DISPLAY_ORIENTATION,
    DEFAULT_LED_BOOT_ENABLED,
    DEFAULT_LED_BRIGHTNESS,
    DEFAULT_LED_COLOR,
    DEFAULT_LED_PATTERN,
    DEFAULT_LOW_POWER_MODE,
    HEIGHT,
    IDLE_TIMEOUT_MS,
    LOW_POWER_BACKLIGHT,
    LOW_POWER_BACKLIGHT_MIN,
    LOW_POWER_IMAGE_SRC,
    LOW_POWER_MODE_DISABLED,
    LOW_POWER_MODE_LOGO,
    LOW_POWER_MODE_SCREEN_OFF,
    LOW_POWER_MODES,
    LOW_POWER_SCREEN_OFF_BACKLIGHT,
    LOW_POWER_TIMEOUT_MAX_MS,
    LOW_POWER_TIMEOUT_MIN_MS,
    NORMAL_BACKLIGHT,
    STICKER_CARD_IDS,
    WIDTH,
)
from hardware import apply_display_orientation, normalize_display_orientation
from card_carousel import (
    CARDS,
    CardCollectionView,
    color,
    find_card_index,
    unlock_card_data,
)
from credits_ui import build_credits_screen
from led_settings_ui import (
    GOLDEN_SHIMMER_RATES,
    LED_COLORS,
    available_led_patterns,
    build_led_settings,
)
from menu_ui import build_main_menu
from persistent_store import load_state, save_state
from settings_ui import (
    build_display_brightness,
    build_low_power_config,
    build_orientation,
    build_settings_menu,
)
from touch_activity import get_touch_snapshot, note_touch_activity
from trade_ui import build_trade_screen
from ui_utils import create_lv_button, delete_obj
from ui_background import add_tactical_background, pause_tactical_background


COLLECTION_REWARD_VERSION = 1


class BadgeApp:
    def __init__(self, screen, display=None, state=None, touch=None, nfc_runtime=None):
        self.screen = screen
        self.display = display
        self.touch = touch
        self.nfc = nfc_runtime

        if state is None:
            state, _first_run = load_state()

        self.state = state
        self.persisted_unlocked_ids = set(
            self.state.get("cards", {}).get("unlocked_ids", [])
        )

        self.active_root = None
        self.active_app = None
        self.switching = False
        self.carousel_view = None
        self.credits_view = None
        self._pending_unlock_animation_ids = []
        self._selected_card_save_timer = None
        self._selected_card_save_cb = self._on_selected_card_save_timer
        self._selected_card_dirty = False
        self._collection_boot_timer = None
        self._collection_boot_timer_cb = self._on_collection_boot_timer
        self.trade_running = False
        self.led_mode = "DIM"
        self.trade_view = None
        self._nfc_start_timer = None
        self._nfc_start_cb = None
        self._nfc_poll_timer = None
        self._nfc_poll_cb = self._poll_nfc_status
        self._nfc_last_message = None

        settings = self.state.get("settings", {})

        self.led_hw = None
        self.led_enabled = settings.get("led_enabled", DEFAULT_LED_BOOT_ENABLED)
        self.led_pattern = settings.get("led_pattern", DEFAULT_LED_PATTERN)
        self.led_color = settings.get("led_color", DEFAULT_LED_COLOR)
        if self.led_color == "OLD_LACE":
            self.led_color = "WARM WHITE"
        self.led_brightness = settings.get("led_brightness", DEFAULT_LED_BRIGHTNESS)
        self.golden_shimmer = settings.get("golden_shimmer", "NORMAL")

        if self.led_pattern not in available_led_patterns(self):
            self.led_pattern = DEFAULT_LED_PATTERN

        if self.led_color not in LED_COLORS:
            self.led_color = DEFAULT_LED_COLOR
        if self.golden_shimmer not in GOLDEN_SHIMMER_RATES:
            self.golden_shimmer = "NORMAL"

        # Hold Python callback references so LVGL does not lose them.
        self.callbacks = []

        self._credits_taps = 0
        self._credits_tap_t = 0

        # Idle / low-power state.
        self.low_power = False
        self.low_power_overlay = None
        self._low_power_wake_cb = None
        self.low_power_timer = None
        self._ambient_orientation_override = False
        self.last_activity_ms = time.ticks_ms()
        self.last_seen_touch_seq = get_touch_snapshot()[0]

        # Display settings.
        self.display_orientation = normalize_display_orientation(
            settings.get("display_orientation", DEFAULT_DISPLAY_ORIENTATION)
        )
        self.screen_brightness = settings.get("screen_brightness", NORMAL_BACKLIGHT)
        self.low_power_backlight = settings.get("low_power_backlight", LOW_POWER_BACKLIGHT)
        self.low_power_mode = self._normalize_low_power_mode(
            settings.get("low_power_mode", None),
            settings.get("low_power_screen_off", False),
        )
        # Legacy mirror used by older UI/helper code. The mode is now the
        # source of truth, but this keeps old checks from breaking.
        self.low_power_screen_off = self.low_power_mode == LOW_POWER_MODE_SCREEN_OFF
        self.idle_timeout_ms = self._clamp_timeout_ms(
            settings.get("idle_timeout_ms", IDLE_TIMEOUT_MS)
        )

        self.screen_brightness = self._clamp_percent(self.screen_brightness, 1, 100)
        self.low_power_backlight = self._clamp_percent(
            self.low_power_backlight,
            LOW_POWER_BACKLIGHT_MIN,
            100,
        )

        self.screen.set_style_bg_color(color("black"), 0)
        self.screen.set_style_bg_opa(lv.OPA.COVER, 0)
        self.screen.set_style_pad_all(0, 0)

        try:
            self.screen.remove_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass

        try:
            self.screen.clean()
        except Exception:
            pass

        self.show_menu()
        self.start_idle_timer()

    # ------------------------------------------------------------
    # Shared state helpers
    # ------------------------------------------------------------

    def _clamp_percent(self, value, minimum=0, maximum=100):
        try:
            value = int(value)
        except Exception:
            value = maximum

        if value < minimum:
            value = minimum
        elif value > maximum:
            value = maximum

        return value

    def _clamp_timeout_ms(self, value):
        try:
            value = int(value)
        except Exception:
            value = IDLE_TIMEOUT_MS

        if value < LOW_POWER_TIMEOUT_MIN_MS:
            value = LOW_POWER_TIMEOUT_MIN_MS
        elif value > LOW_POWER_TIMEOUT_MAX_MS:
            value = LOW_POWER_TIMEOUT_MAX_MS

        return value

    def _normalize_low_power_mode(self, mode, legacy_screen_off=False):
        if mode in LOW_POWER_MODES:
            return mode

        # Backward compatibility: old saves only had low_power_screen_off.
        if legacy_screen_off:
            return LOW_POWER_MODE_SCREEN_OFF

        return DEFAULT_LOW_POWER_MODE

    def save_settings(self):
        settings = self.state.get("settings", {})
        settings["led_enabled"] = self.led_enabled
        settings["led_pattern"] = self.led_pattern
        settings["led_color"] = self.led_color
        settings["led_brightness"] = self.led_brightness
        settings["golden_shimmer"] = self.golden_shimmer
        settings["screen_brightness"] = self.screen_brightness
        settings["display_orientation"] = self.display_orientation
        self.low_power_backlight = self._clamp_percent(
            self.low_power_backlight,
            LOW_POWER_BACKLIGHT_MIN,
            100,
        )
        settings["low_power_backlight"] = self.low_power_backlight
        self.low_power_mode = self._normalize_low_power_mode(
            getattr(self, "low_power_mode", DEFAULT_LOW_POWER_MODE),
            getattr(self, "low_power_screen_off", False),
        )
        self.low_power_screen_off = self.low_power_mode == LOW_POWER_MODE_SCREEN_OFF
        self.idle_timeout_ms = self._clamp_timeout_ms(self.idle_timeout_ms)
        settings["low_power_mode"] = self.low_power_mode
        # Legacy mirror for older save files / older helper code.
        settings["low_power_screen_off"] = self.low_power_screen_off
        settings["idle_timeout_ms"] = self.idle_timeout_ms

        self.state["settings"] = settings
        return save_state(self.state)

    def set_backlight(self, percent):
        return set_backlight_percent(percent)

    def save_unlocked_card_id(self, card_id):
        if not card_id:
            return

        cards_state = self.state.get("cards", {})
        unlocked_ids = cards_state.get("unlocked_ids", [])

        if card_id not in unlocked_ids:
            unlocked_ids.append(card_id)
        else:
            return

        cards_state["unlocked_ids"] = unlocked_ids
        self.state["cards"] = cards_state
        self.persisted_unlocked_ids = set(unlocked_ids)

        saved = save_state(self.state)
        if saved:
            self._check_collection_completion()
        return saved

    def save_selected_card_index(self, index):
        cards_state = self.state.get("cards", {})

        try:
            index = int(index)
        except Exception:
            index = 0

        if cards_state.get("selected_index") == index and not self._selected_card_dirty:
            return

        cards_state["selected_index"] = index
        self.state["cards"] = cards_state
        self._selected_card_dirty = True
        self._schedule_selected_card_save()

    def _cancel_selected_card_save(self):
        timer = self._selected_card_save_timer
        self._selected_card_save_timer = None
        if timer is None:
            return
        for name in ("delete", "_del", "del_"):
            try:
                getattr(timer, name)()
                return
            except Exception:
                pass
        try:
            lv.timer_delete(timer)
        except Exception:
            pass

    def _schedule_selected_card_save(self):
        """Save after one idle second instead of flash-syncing in a snap callback."""
        self._cancel_selected_card_save()
        try:
            timer = lv.timer_create(self._selected_card_save_cb, 1000, None)
            self._selected_card_save_timer = timer
            try:
                timer.set_repeat_count(1)
            except Exception:
                pass
        except Exception as exc:
            print("Card index save debounce unavailable:", exc)

    def _on_selected_card_save_timer(self, timer):
        if timer is self._selected_card_save_timer:
            self._selected_card_save_timer = None
        deleted = False
        for name in ("delete", "_del", "del_"):
            try:
                getattr(timer, name)()
                deleted = True
                break
            except Exception:
                pass
        if not deleted:
            try:
                lv.timer_delete(timer)
            except Exception:
                pass

        view = self.carousel_view
        if view is not None and (view.dragging or view.animating):
            self._schedule_selected_card_save()
            return
        self._flush_selected_card_index()

    def _flush_selected_card_index(self):
        self._cancel_selected_card_save()
        if self._selected_card_dirty and save_state(self.state):
            self._selected_card_dirty = False

    # ------------------------------------------------------------
    # Idle / low-power display mode
    # ------------------------------------------------------------

    def start_idle_timer(self):
        try:
            self.low_power_timer = lv.timer_create(self._idle_timer_cb, 500, None)
            print("Idle low-power timer started")
        except Exception as exc:
            print("Idle low-power timer failed:", exc)
            self.low_power_timer = None

    def _idle_timer_cb(self, timer):
        now = time.ticks_ms()
        touch_seq, last_touch_ms = get_touch_snapshot()

        led = self.led_hw
        if led is not None and hasattr(led, "health_check"):
            try:
                led.health_check(now)
            except Exception as exc:
                print("LED watchdog failed:", exc)

        # Any touch anywhere wakes or resets the idle timer.
        if touch_seq != self.last_seen_touch_seq:
            self.last_seen_touch_seq = touch_seq
            self.last_activity_ms = last_touch_ms

            if self.low_power:
                self.exit_low_power_mode()

            return

        if self.low_power:
            return

        if self.trade_running:
            return

        if self.low_power_mode == LOW_POWER_MODE_DISABLED:
            return

        if time.ticks_diff(now, self.last_activity_ms) >= self.idle_timeout_ms:
            self.enter_low_power_mode()

    def enter_low_power_mode(self):
        if self.low_power:
            return

        self.low_power_mode = self._normalize_low_power_mode(
            getattr(self, "low_power_mode", DEFAULT_LOW_POWER_MODE),
            getattr(self, "low_power_screen_off", False),
        )

        if self.low_power_mode == LOW_POWER_MODE_DISABLED:
            return

        screen_off_mode = self.low_power_mode == LOW_POWER_MODE_SCREEN_OFF
        self.low_power_screen_off = screen_off_mode

        self.low_power = True
        print("Entering low-power display mode:", self.low_power_mode)

        if self.carousel_view is not None:
            try:
                self.carousel_view.suspend_for_low_power()
            except Exception as exc:
                print("Carousel low-power suspend failed:", exc)

        # Do not touch LEDs here. They stay exactly as they are.

        overlay = lv.obj(self.screen)
        overlay.set_size(WIDTH, HEIGHT)
        overlay.set_pos(0, 0)
        overlay.set_style_bg_color(lv.color_hex(0x000000), 0)
        overlay.set_style_bg_opa(lv.OPA.COVER, 0)
        overlay.set_style_border_width(0, 0)
        overlay.set_style_radius(0, 0)
        overlay.set_style_pad_all(0, 0)

        try:
            overlay.remove_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass

        try:
            overlay.add_flag(lv.obj.FLAG.CLICKABLE)
        except Exception:
            pass

        def wake_cb(event):
            del event
            note_touch_activity()
            self.exit_low_power_mode()

        self._low_power_wake_cb = wake_cb
        self.callbacks.append(wake_cb)
        overlay.add_event_cb(wake_cb, lv.EVENT.PRESSED, None)
        overlay.add_event_cb(wake_cb, lv.EVENT.CLICKED, None)

        if not screen_off_mode:
            image_loaded = False

            try:
                if hasattr(lv, "image"):
                    img = lv.image(overlay)
                else:
                    img = lv.img(overlay)

                img.set_src(LOW_POWER_IMAGE_SRC)
                img.center()
                image_loaded = True

            except Exception as exc:
                print("Low-power image failed:", exc)
                image_loaded = False

            if not image_loaded:
                title = lv.label(overlay)
                title.set_text("// BADGE OS")
                title.set_style_text_color(lv.color_hex(0x22C55E), 0)
                title.set_pos(42, 96)

                msg = lv.label(overlay)
                msg.set_text("LOW POWER MODE")
                msg.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
                msg.set_pos(42, 126)

                hint = lv.label(overlay)
                hint.set_text("TOUCH TO WAKE")
                hint.set_style_text_color(lv.color_hex(0x6B7280), 0)
                hint.set_pos(42, 160)

        self.low_power_overlay = overlay

        try:
            overlay.move_foreground()
        except Exception:
            pass

        # The ambient logo always keeps the original physical orientation,
        # independent of the user's UI preference.
        if not screen_off_mode:
            try:
                set_backlight_percent(0)
                apply_display_orientation(
                    self.display,
                    self.touch,
                    "original",
                )
                self._ambient_orientation_override = True
            except Exception as exc:
                print("Ambient orientation failed:", exc)

        try:
            if screen_off_mode:
                set_backlight_percent(LOW_POWER_SCREEN_OFF_BACKLIGHT)
            else:
                self.low_power_backlight = self._clamp_percent(
                    self.low_power_backlight,
                    LOW_POWER_BACKLIGHT_MIN,
                    100,
                )
                set_backlight_percent(self.low_power_backlight)
        except Exception as exc:
            print("Backlight dim failed:", exc)

    def exit_low_power_mode(self):
        if not self.low_power:
            return

        print("Exiting low-power display mode")

        self.low_power = False
        self.last_activity_ms = time.ticks_ms()

        if self._ambient_orientation_override:
            try:
                set_backlight_percent(0)
                apply_display_orientation(
                    self.display,
                    self.touch,
                    self.display_orientation,
                )
            except Exception as exc:
                print("UI orientation restore failed:", exc)
            self._ambient_orientation_override = False

        if self.low_power_overlay is not None:
            delete_obj(self.low_power_overlay)
            self.low_power_overlay = None

        wake_cb = self._low_power_wake_cb
        self._low_power_wake_cb = None
        if wake_cb is not None:
            try:
                self.callbacks.remove(wake_cb)
            except ValueError:
                pass

        try:
            set_backlight_percent(self.screen_brightness)
        except Exception as exc:
            print("Backlight restore failed:", exc)

        # The overlay is an entire temporary LVGL object tree. Reclaim its
        # Python wrappers before restoring bitmap-heavy carousel activity.
        gc.collect()

        if self.carousel_view is not None:
            try:
                self.carousel_view.resume_from_low_power()
            except Exception as exc:
                print("Carousel wake restore failed:", exc)

    # ------------------------------------------------------------
    # App view helpers
    # ------------------------------------------------------------

    def make_root(self, with_background=True):
        root = lv.obj(self.screen)

        # Hidden during construction so LVGL does not render half-built views.
        root.add_flag(lv.obj.FLAG.HIDDEN)

        root.set_size(WIDTH, HEIGHT)
        root.set_pos(0, 0)
        root.set_style_bg_color(color("black"), 0)
        root.set_style_bg_opa(lv.OPA.COVER, 0)
        root.set_style_border_width(0, 0)
        root.set_style_radius(0, 0)
        root.set_style_pad_all(0, 0)

        try:
            root.remove_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass

        # Draw the shared tactical background before each screen adds its
        # controls. The returned objects are children of root and are deleted
        # automatically when the view is replaced.
        if with_background:
            add_tactical_background(root, WIDTH, HEIGHT)

        self.active_root = root
        return root

    def clear_active_view(self):
        # There is no observer to re-enable during the very first menu build.
        # Keeping this conditional also keeps universal_nav completely out of
        # the boot path; it is loaded only after a sub-screen is visible.
        if self.active_app is not None:
            self.enable_universal_nav()
        self.stop_trade_if_running()

        if self.carousel_view is not None:
            self._flush_selected_card_index()
            try:
                self.carousel_view.stop()
            except Exception:
                pass

        if self.trade_view is not None:
            try:
                self.trade_view.stop_active_trade()
            except Exception:
                pass
            self.trade_view = None

        self.carousel_view = None
        self.credits_view = None
        delete_obj(self.active_root)
        self.active_root = None
        # The deleted root owned every native event descriptor for this view.
        # Drop the corresponding Python closures as well so repeated navigation
        # does not retain callbacks from screens that no longer exist.
        self.callbacks = []
        gc.collect()

    def switch_to(self, app_name, build_func):
        if self.switching:
            return

        # A touch while asleep should only wake the badge, not also switch apps.
        if self.low_power:
            self.exit_low_power_mode()
            return

        self.switching = True
        self.clear_active_view()
        self.active_app = app_name
        build_func()

        # Install the universal input observer and a non-clickable home
        # indicator on every sub-screen. No overlay participates in hit testing.
        # Import this locally so a universal_nav/badge_config mismatch cannot
        # prevent the badge from booting.
        if app_name not in ("menu", "credits"):
            try:
                from universal_nav import install_universal_menu_swipe
                install_universal_menu_swipe(self)
            except Exception as exc:
                print("Universal nav install failed:", exc)
                self._universal_menu_swipe_rail = None
                self._universal_menu_swipe_handle = None
        else:
            self._universal_menu_swipe_rail = None
            self._universal_menu_swipe_handle = None

        gc.collect()

        if self.active_root is not None:
            self.active_root.remove_flag(lv.obj.FLAG.HIDDEN)

        self.switching = False

    def make_label(self, parent, text, x, y, w=None, h=None, text_color="white"):
        label = lv.label(parent)
        label.set_text(text)
        label.set_style_text_color(color(text_color), 0)
        label.set_pos(x, y)

        if w is not None and h is not None:
            label.set_size(w, h)

        return label

    def make_button(self, parent, text, x, y, w, h, callback):
        btn = create_lv_button(parent)
        btn.set_size(w, h)
        btn.set_pos(x, y)
        btn.set_style_bg_color(color("panel_2"), 0)
        btn.set_style_bg_opa(lv.OPA.COVER, 0)
        btn.set_style_border_width(2, 0)
        btn.set_style_border_color(color("green_dim"), 0)
        btn.set_style_radius(2, 0)
        btn.set_style_shadow_width(0, 0)

        try:
            btn.remove_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass

        # Settings controls are intentionally sparse. Expand their invisible
        # touch targets into the surrounding empty space without changing the
        # visual layout. Keep a small gap between adjacent LED-setting rows so
        # LVGL never has to choose between overlapping controls.
        if self.active_app in (
            "settings",
            "leds",
            "screen_brightness",
            "orientation",
            "low_power_config",
        ):
            hitbox = 7 if self.active_app == "settings" else 9
            try:
                btn.set_ext_click_area(hitbox)
            except Exception:
                pass

        label = lv.label(btn)
        label.set_text(text)
        label.set_style_text_color(color("white"), 0)
        label.center()

        def clicked(event):
            note_touch_activity()

            if self.low_power:
                self.exit_low_power_mode()
                return

            callback()

        self.callbacks.append(clicked)
        btn.add_event_cb(clicked, lv.EVENT.CLICKED, None)

        return btn

    def make_back_button(self, parent, callback=None, text="BACK"):
        """Uniform top-left back button for nested screens.

        Keep this independent of make_button() so it has a large, reliable
        hitbox and does not get registered as a bottom/swipe-overlap control.
        """
        if callback is None:
            callback = self.show_menu

        btn = create_lv_button(parent)
        btn.set_size(66, 30)
        btn.set_pos(4, 4)
        btn.set_style_bg_color(color("panel_2"), 0)
        btn.set_style_bg_opa(lv.OPA.COVER, 0)
        btn.set_style_border_width(1, 0)
        btn.set_style_border_color(color("green_dim"), 0)
        btn.set_style_radius(2, 0)
        btn.set_style_shadow_width(0, 0)
        btn.set_style_pad_all(0, 0)

        try:
            btn.remove_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass

        # Make the top-left target easier to hit without making the visual
        # button huge. This is especially helpful near the display bezel.
        try:
            btn.set_ext_click_area(16)
        except Exception:
            pass

        label = lv.label(btn)
        label.set_text(text)
        label.set_style_text_color(color("white"), 0)
        label.center()

        def clicked(event):
            note_touch_activity()

            if self.low_power:
                self.exit_low_power_mode()
                return

            callback()

        self.callbacks.append(clicked)
        btn.add_event_cb(clicked, lv.EVENT.CLICKED, None)

        try:
            btn.move_foreground()
        except Exception:
            pass

        return btn

    # ------------------------------------------------------------
    # Universal navigation suppression
    # ------------------------------------------------------------

    def disable_universal_nav(self):
        try:
            from universal_nav import set_indicator_visible, set_universal_menu_swipe_enabled
            set_universal_menu_swipe_enabled(False)
            set_indicator_visible(self, False)
        except Exception as exc:
            print("Universal nav disable failed:", exc)

    def enable_universal_nav(self):
        try:
            from universal_nav import set_indicator_visible, set_universal_menu_swipe_enabled
            set_universal_menu_swipe_enabled(True)
            if self.active_app != "menu":
                set_indicator_visible(self, True)
        except Exception as exc:
            print("Universal nav enable failed:", exc)

    # ------------------------------------------------------------
    # App routing
    # ------------------------------------------------------------

    def show_menu(self):
        self.switch_to("menu", lambda: build_main_menu(self))

    def show_cards(self):
        self.switch_to("cards", self.build_cards)

    def show_trade(self):
        self.switch_to("trade", lambda: build_trade_screen(self))

    def show_leds(self):
        self.switch_to("leds", lambda: build_led_settings(self))

    def show_settings(self):
        self.switch_to("settings", lambda: build_settings_menu(self))

    def show_screen_brightness(self):
        self.switch_to("screen_brightness", lambda: build_display_brightness(self))

    def show_orientation(self):
        self.switch_to("orientation", lambda: build_orientation(self))

    def show_low_power_config(self):
        self.switch_to("low_power_config", lambda: build_low_power_config(self))

    def show_credits(self):
        self.switch_to("credits", lambda: build_credits_screen(self))

    def build_cards(self):
        root = self.make_root()
        pause_tactical_background(root)
        cards_state = self.state.get("cards", {})
        pending_id = (
            self._pending_unlock_animation_ids[0]
            if self._pending_unlock_animation_ids
            else None
        )
        initial_index = cards_state.get("selected_index", 0)
        if pending_id is not None:
            pending_index = find_card_index(pending_id)
            if pending_index >= 0:
                initial_index = pending_index

        self.carousel_view = CardCollectionView(
            root,
            on_back=self.show_menu,
            initial_index=initial_index,
            on_index_changed=self.save_selected_card_index,
            on_card_unlocked=self.save_unlocked_card_id,
            on_details_open=self.disable_universal_nav,
            on_details_close=self.enable_universal_nav,
            on_unlock_animation_complete=self._play_next_pending_unlock,
        )
        if pending_id is not None:
            if not self.carousel_view.play_unlock_animation(pending_id):
                self._play_next_pending_unlock(pending_id)

    def _play_next_pending_unlock(self, completed_card_id=None):
        if completed_card_id is not None:
            try:
                self._pending_unlock_animation_ids.remove(completed_card_id)
            except ValueError:
                pass

        view = self.carousel_view
        while view is not None and self._pending_unlock_animation_ids:
            card_id = self._pending_unlock_animation_ids[0]
            index = find_card_index(card_id)
            if index < 0:
                self._pending_unlock_animation_ids.pop(0)
                continue
            view.focus_card(index)
            if view.play_unlock_animation(card_id):
                return
            self._pending_unlock_animation_ids.pop(0)

    # ------------------------------------------------------------
    # NFC peer-trade and tag-reader hooks
    # ------------------------------------------------------------

    def _known_card_ids(self):
        """Cards an attendee badge may offer in a peer trade."""
        result = []
        for card in CARDS:
            try:
                card_id = str(card.get("id", "")).strip().upper()
            except Exception:
                card_id = ""
            if (
                card_id.startswith("ACR-")
                or card.get("acr_designation", False)
                or card.get("non_tradeable", False)
                or self._is_sticker_only_card(card)
            ):
                continue
            if card_id and card_id not in result:
                result.append(card_id)
        return result

    def _peer_receive_card_ids(self):
        """Cards an attendee may decode when offered by another firmware."""
        result = []
        for card in CARDS:
            card_id = str(card.get("id", "")).strip().upper()
            if card_id and card_id not in result:
                result.append(card_id)
        return result

    def _is_sticker_only_card(self, card):
        try:
            card_id = str(card.get("id", "")).strip().upper()
            return bool(card.get("sticker_only", False)) or (
                card_id in STICKER_CARD_IDS
            )
        except Exception:
            return False

    def _is_sticker_card(self, card):
        """Return whether a card may be unlocked from a passive NFC sticker."""
        try:
            card_id = str(card.get("id", "")).strip().upper()
            return card_id.startswith("ACR-")
        except Exception:
            return False

    def _gift_send_card_ids(self):
        result = []
        try:
            from trade_ops import is_acr_card
            for card in CARDS:
                if (
                    is_acr_card(card)
                    or card.get("non_tradeable", False)
                    or self._is_sticker_only_card(card)
                ):
                    continue
                card_id = str(card.get("id", "")).strip().upper()
                if card_id and card_id not in result:
                    result.append(card_id)
        except Exception:
            return []
        return result

    def _gift_receive_card_ids(self):
        result = []
        for card in CARDS:
            card_id = str(card.get("id", "")).strip().upper()
            if card_id and card_id not in result:
                result.append(card_id)
        return result

    def _sticker_card_ids(self):
        result = []
        for card in CARDS:
            if not self._is_sticker_card(card):
                continue
            card_id = str(card.get("id", "")).strip().upper()
            if card_id and card_id not in result:
                result.append(card_id)
        return result

    def _delete_nfc_start_timer(self):
        timer = self._nfc_start_timer
        self._nfc_start_timer = None
        self._nfc_start_cb = None
        if timer is None:
            return

        for name in ("delete", "_del", "del_"):
            try:
                getattr(timer, name)()
                return
            except Exception:
                pass

        try:
            lv.timer_delete(timer)
        except Exception:
            try:
                lv.timer_del(timer)
            except Exception:
                pass

    def _delete_nfc_poll_timer(self):
        timer = self._nfc_poll_timer
        self._nfc_poll_timer = None
        if timer is None:
            return

        for name in ("delete", "_del", "del_"):
            try:
                getattr(timer, name)()
                return
            except Exception:
                pass

        try:
            lv.timer_delete(timer)
        except Exception:
            try:
                lv.timer_del(timer)
            except Exception:
                pass

    def _start_nfc_polling(self):
        self._delete_nfc_poll_timer()
        self._nfc_last_message = None
        try:
            self._nfc_poll_timer = lv.timer_create(self._nfc_poll_cb, 100, None)
            return True
        except Exception as exc:
            print("NFC UI poll timer failed:", exc)
            self._nfc_poll_timer = None
            return False

    def _nfc_error_now(self, message):
        self.trade_running = False
        view = self.trade_view
        if view is not None:
            try:
                view.complete_trade_error(message)
                return
            except Exception as exc:
                print("NFC error screen failed:", exc)
        print("NFC error:", message)

    def _start_nfc_job(self, starter, unavailable_message):
        """Paint the active screen, then run the blocking NFC call on core 0."""
        if self.trade_running:
            return False

        if self.nfc is None or not getattr(self.nfc, "available", False):
            message = unavailable_message
            if self.nfc is not None:
                message = getattr(self.nfc, "init_error", None) or message
            self._nfc_error_now(message)
            return False

        self.trade_running = True
        self.last_activity_ms = time.ticks_ms()
        self._delete_nfc_start_timer()

        def run_synchronous_nfc(timer):
            del timer
            self._delete_nfc_start_timer()

            # The user may have left the trade page during the short paint delay.
            if not self.trade_running or self.active_app != "trade":
                return

            try:
                started = bool(starter())
            except Exception as exc:
                self._nfc_error_now("Could not run NFC: {}".format(exc))
                return

            if not started:
                try:
                    snapshot = self.nfc.snapshot()
                    message = snapshot.get("message") or "NFC operation failed."
                except Exception:
                    message = "NFC operation failed."
                self._nfc_error_now(message)
                return

            # The synchronous call has returned with a complete state. Use the
            # existing result handler on the next LVGL tick.
            if not self._start_nfc_polling():
                self._nfc_error_now("Could not display NFC result.")

        self._nfc_start_cb = run_synchronous_nfc

        try:
            # Three normal 25 ms LVGL service periods are enough to flush the
            # active NFC screen before the main core enters the blocking RF call.
            timer = lv.timer_create(run_synchronous_nfc, 75, None)
            self._nfc_start_timer = timer
            try:
                timer.set_repeat_count(1)
            except Exception:
                pass
            return True
        except Exception as exc:
            self.trade_running = False
            self._nfc_start_cb = None
            self._nfc_error_now("Could not schedule NFC operation: {}".format(exc))
            return False

    def begin_peer_trade(self, offered_card_id):
        offered_id = str(offered_card_id).strip().upper()
        print("Peer trade requested")
        known_ids = self._known_card_ids()
        received_ids = self._peer_receive_card_ids()
        owned_ids = list(self.persisted_unlocked_ids)
        if self.trade_view is not None:
            self.trade_view.set_active_status(
                "Hold both badge antennas together.\nWaiting for peer...",
                "cyan",
            )
        self._start_nfc_job(
            lambda: self.nfc.start_peer_trade(
                offered_id,
                known_ids,
                owned_ids,
                received_ids,
            ),
            "NFC peer-to-peer service is unavailable.",
        )

    def begin_gift_send(self, card_id):
        gift_id = str(card_id or "").strip().upper()

        giftable = False
        try:
            from trade_ops import is_tradeable
            for card in CARDS:
                if str(card.get("id", "")).strip().upper() == gift_id:
                    giftable = bool(is_tradeable(card))
                    break
        except Exception:
            giftable = False

        if not giftable:
            if self.trade_view is not None:
                self.trade_view.complete_trade_error(
                    "That card cannot be gifted."
                )
            return

        known_ids = self._gift_send_card_ids()
        if self.trade_view is not None:
            self.trade_view.set_active_status(
                "Looking for gift receiver...", "cyan"
            )
        self._start_nfc_job(
            lambda: self.nfc.start_gift_send(gift_id, known_ids),
            "NFC gift sender is unavailable.",
        )

    def begin_gift_receive(self):
        known_ids = self._gift_receive_card_ids()
        if self.trade_view is not None:
            self.trade_view.set_active_status(
                "Waiting for gift sender...", "cyan"
            )
        self._start_nfc_job(
            lambda: self.nfc.start_gift_receive(known_ids),
            "NFC gift receiver is unavailable.",
        )

    def begin_nfc_tag_scan(self):
        print("Passive NFC tag scan requested")
        known_ids = self._sticker_card_ids()
        if self.trade_view is not None:
            self.trade_view.set_active_status(
                "Hold the sticker near the NFC antenna...",
                "cyan",
            )
        self._start_nfc_job(
            lambda: self.nfc.start_tag_scan(known_ids),
            "NFC tag reader is unavailable.",
        )

    def _poll_nfc_status(self, timer):
        del timer
        if self.nfc is None:
            self._delete_nfc_poll_timer()
            self._nfc_error_now("NFC runtime disappeared.")
            return

        try:
            snapshot = self.nfc.snapshot()
        except Exception as exc:
            self._delete_nfc_poll_timer()
            self._nfc_error_now("NFC status failed: {}".format(exc))
            return

        message = snapshot.get("message")
        if message and message != self._nfc_last_message:
            self._nfc_last_message = message
            if self.trade_view is not None:
                try:
                    self.trade_view.set_active_status(message, "cyan")
                except Exception:
                    pass

        if not snapshot.get("done"):
            return

        self._delete_nfc_poll_timer()
        self.trade_running = False
        result = snapshot.get("result") or {}
        mode = snapshot.get("mode")

        # Commit every confirmed operation before consulting UI state. Screen
        # navigation must never decide whether protocol-confirmed data persists.
        acquisition = None
        if result.get("ok") and mode in ("peer", "gift_receive", "scan"):
            incoming_id = (
                result.get("received_id")
                if mode == "peer"
                else result.get("card_id")
            )
            if incoming_id:
                acquisition = self.handle_card_acquisition(incoming_id, mode)

        # The user may have navigated away while the worker was winding down.
        if self.active_app != "trade" or self.trade_view is None:
            return

        if not result.get("ok"):
            message = result.get("error") or snapshot.get("error") or "NFC operation failed."
            self.trade_view.complete_trade_error(message)
            return

        if mode == "peer":
            offered_id = result.get("offered_id")
            received_id = result.get("received_id")
            if not offered_id or not received_id:
                self.trade_view.complete_trade_error("Peer trade returned incomplete card data.")
                return

            if acquisition is None or not acquisition.get("ok"):
                self.trade_view.complete_trade_error(
                    "Received card is not in the badge card table."
                )
                return
            self.trade_view.complete_peer_trade(
                offered_id,
                received_id,
                newly_unlocked=acquisition.get("newly_unlocked", False),
            )
            return

        if mode == "gift_send":
            card_id = result.get("card_id")
            if not card_id:
                self.trade_view.complete_trade_error(
                    "Gift sender returned incomplete data."
                )
                return
            self.trade_view.complete_gift_send(card_id)
            return

        if mode == "gift_receive":
            card_id = result.get("card_id")
            if not card_id:
                self.trade_view.complete_trade_error(
                    "Gift receiver returned incomplete data."
                )
                return
            if acquisition is None or not acquisition.get("ok"):
                self.trade_view.complete_trade_error(
                    "Gift card is not in the badge card table."
                )
                return
            self.trade_view.complete_gift_receive(
                card_id,
                newly_unlocked=acquisition.get("newly_unlocked", False),
            )
            return

        if mode == "scan":
            card_id = result.get("card_id")
            if not card_id:
                self.trade_view.complete_trade_error("Tag did not contain a card ID.")
                return

            if acquisition is None or not acquisition.get("ok"):
                self.trade_view.complete_trade_error(
                    "Sticker card is not in the badge card table."
                )
                return
            self.trade_view.complete_tag_scan(
                card_id,
                newly_unlocked=acquisition.get("newly_unlocked", False),
            )
            return

        self.trade_view.complete_trade_error("Unknown NFC completion mode.")

    def stop_trade_if_running(self):
        if self.trade_running:
            self.trade_running = False
            print("NFC operation stopped")

        self._delete_nfc_start_timer()
        self._delete_nfc_poll_timer()
        if self.nfc is not None:
            try:
                self.nfc.cancel()
            except Exception as exc:
                print("NFC cancel failed:", exc)

    # ------------------------------------------------------------
    # LED runtime hooks
    # ------------------------------------------------------------

    def start_default_leds(self):
        # Use saved LED settings. Do not overwrite them with defaults on boot.
        if not self.led_enabled or self.led_pattern == "NONE":
            print("Saved LED state is off")

            led = self.ensure_led_hw()
            if led is not None:
                try:
                    led.off()
                except Exception as exc:
                    print("LED off failed:", exc)

            self._schedule_collection_completion_check()
            return

        print("Starting saved LEDs:", self.led_pattern, self.led_color)

        # Use the same path that works from the LED menu.
        self.apply_led_mode()
        self._schedule_collection_completion_check()

    def _schedule_collection_completion_check(self):
        """Run the boot reward only after the main menu is visibly settled."""
        if self._collection_boot_timer is not None:
            return
        try:
            timer = lv.timer_create(self._collection_boot_timer_cb, 900, None)
            timer.set_repeat_count(1)
            self._collection_boot_timer = timer
        except Exception as exc:
            print("Collection reward timer failed:", exc)
            self._collection_boot_timer = None
            self._check_collection_completion()

    def _on_collection_boot_timer(self, _timer):
        self._collection_boot_timer = None
        self._check_collection_completion()

    def ensure_led_hw(self):
        if self.led_hw is not None:
            return self.led_hw

        try:
            from LEDS import LEDRuntime

            led = LEDRuntime()

            if not led.start():
                print("LED runtime failed to start")
                return None

            if not hasattr(led, "set"):
                print("LEDRuntime missing set()")
                return None

            if not hasattr(led, "off"):
                print("LEDRuntime missing off()")
                return None

            self.led_hw = led
            return led

        except Exception as exc:
            import sys

            print("LED init failed:")
            sys.print_exception(exc)
            self.led_hw = None
            return None

    def apply_led_mode(self):
        led = self.ensure_led_hw()

        if led is None:
            print("LED hardware unavailable")
            return

        self.led_enabled = self.led_pattern != "NONE"

        print(
            "Apply LED:",
            self.led_enabled,
            self.led_pattern,
            self.led_color,
            "bright:",
            self.led_brightness,
        )

        led.set(
            pattern=self.led_pattern,
            color=self.led_color,
            enabled=self.led_enabled,
            brightness=self.led_brightness,
            golden_shimmer=self.golden_shimmer,
        )

    # ------------------------------------------------------------
    # Card unlock hook
    # ------------------------------------------------------------

    def _collection_is_complete(self):
        found_card = False
        for card in CARDS:
            found_card = True
            if not bool(card.get("unlocked", False)):
                return False
        return found_card

    def _check_collection_completion(self):
        if not self._collection_is_complete():
            return False

        state_changed = False
        if not self.state.get("collection_complete", False):
            self.state["collection_complete"] = True
            state_changed = True

        reward_version = int(self.state.get("collection_reward_version", 0) or 0)
        if (
            self.state.get("collection_animation_played", False)
            and reward_version >= COLLECTION_REWARD_VERSION
        ):
            if state_changed:
                save_state(self.state)
            return True

        led = self.ensure_led_hw()
        queued = False
        if led is not None and hasattr(led, "play_collection_reward"):
            try:
                queued = bool(led.play_collection_reward())
            except Exception as exc:
                print("Collection reward failed:", exc)

        if queued:
            self.state["collection_animation_played"] = True
            self.state["collection_reward_version"] = COLLECTION_REWARD_VERSION
            state_changed = True

        if state_changed:
            save_state(self.state)

        return True

    def handle_card_acquisition(self, card_id, source="unknown"):
        """Apply every card acquisition through one persistence/UI pipeline."""
        normalized = str(card_id or "").strip().upper()
        index = find_card_index(normalized)
        if index < 0:
            print("Rejected unknown card acquisition:", normalized, source)
            return {
                "ok": False,
                "card_id": normalized,
                "newly_unlocked": False,
                "source": source,
            }

        newly_unlocked = normalized not in self.persisted_unlocked_ids
        if unlock_card_data(normalized) < 0:
            return {
                "ok": False,
                "card_id": normalized,
                "newly_unlocked": False,
                "source": source,
            }

        self.save_unlocked_card_id(normalized)

        if newly_unlocked and normalized not in self._pending_unlock_animation_ids:
            self._pending_unlock_animation_ids.append(normalized)

        # Acquisitions normally complete on an NFC result screen. Keep this
        # safe for REPL/staff-firmware callers that unlock while cards are open.
        view = self.carousel_view if self.active_app == "cards" else None
        if view is not None:
            try:
                view.unlock_card(normalized)
                if newly_unlocked:
                    self._play_next_pending_unlock()
            except Exception as exc:
                print("Card carousel acquisition refresh failed:", exc)

        return {
            "ok": True,
            "card_id": normalized,
            "newly_unlocked": newly_unlocked,
            "source": source,
        }

    def unlock_card(self, card_id):
        """Compatibility wrapper for REPL and older staff-firmware callers."""
        return bool(self.handle_card_acquisition(card_id).get("ok"))
