"""Boot splash and LVGL filesystem setup."""

import time
import lvgl as lv

from badge_config import (
    BOOT_GIF_DURATION_MS,
    BOOT_GIF_SRC,
    BOOT_GIF_TIMEOUT_MS,
    HEIGHT,
    WIDTH,
)

_lv_fs_drv = None
_boot_splash = None
_boot_splash_status = None
_boot_gif = None
_boot_gif_ready = False
_boot_gif_started_at = None


def register_lvgl_filesystem():
    global _lv_fs_drv

    if _lv_fs_drv is not None:
        return True

    try:
        import fs_driver

        _lv_fs_drv = lv.fs_drv_t()
        fs_driver.fs_register(_lv_fs_drv, "A")

        buf = bytearray(32)
        lv.fs_get_letters(buf)
        print("LVGL FS letters after:", buf)

        return True

    except Exception as e:
        print("LVGL filesystem register failed:", e)
        return False


def pump_lvgl(cycles=3, delay_ms=15):
    for _ in range(cycles):
        time.sleep_ms(delay_ms)

        # The normal TaskHandler is not started until after the menu is built.
        # Advance LVGL's clock manually during boot so GIF/animation timers run.
        try:
            lv.tick_inc(delay_ms)
        except Exception:
            pass

        try:
            lv.task_handler()
        except Exception:
            pass


def show_boot_splash(status_text="BOOTING"):
    global _boot_splash, _boot_splash_status
    global _boot_gif, _boot_gif_ready, _boot_gif_started_at

    splash = lv.obj()
    lv.screen_load(splash)

    splash.set_size(WIDTH, HEIGHT)
    splash.set_style_bg_color(lv.color_hex(0x000000), 0)
    splash.set_style_bg_opa(lv.OPA.COVER, 0)
    splash.set_style_border_width(0, 0)
    splash.set_style_radius(0, 0)
    splash.set_style_pad_all(0, 0)

    try:
        splash.remove_flag(lv.obj.FLAG.SCROLLABLE)
    except Exception:
        pass

    _boot_splash = splash
    _boot_splash_status = None
    _boot_gif = None
    _boot_gif_ready = False
    _boot_gif_started_at = time.ticks_ms()

    try:
        gif_class = getattr(lv, "gif")
        animation = gif_class(splash)
        animation.set_src(BOOT_GIF_SRC)

        # Keep the compact source at native size; decoding a full-screen GIF
        # exhausts the badge heap and runtime scaling makes playback stutter.
        try:
            animation.set_style_transform_scale_x(256, 0)
            animation.set_style_transform_scale_y(256, 0)
        except Exception:
            try:
                animation.set_scale(256)
            except Exception:
                try:
                    animation.set_zoom(256)
                except Exception:
                    pass

        animation.center()

        def animation_ready(_event):
            global _boot_gif_ready
            _boot_gif_ready = True
            try:
                animation.pause()
            except Exception:
                pass

        animation.add_event_cb(animation_ready, lv.EVENT.READY, None)
        _boot_gif = animation
    except Exception as gif_exc:
        print("Animated boot screen unavailable:", gif_exc)

        status = lv.label(splash)
        status.set_text(status_text)
        status.set_style_text_color(lv.color_hex(0xBF5FFF), 0)
        status.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        status.set_width(WIDTH)
        status.center()
        _boot_splash_status = status

    pump_lvgl(5, 15)

    return splash, _boot_splash_status


def update_boot_splash(text):
    global _boot_splash_status

    if _boot_splash_status is None:
        return

    try:
        _boot_splash_status.set_text(text)
        pump_lvgl(2, 10)
    except Exception:
        pass


def wait_for_boot_animation(release=True):
    """Run the GIF once; optionally retain its final frame until the menu."""
    global _boot_gif, _boot_gif_ready

    if _boot_gif is None or _boot_gif_started_at is None:
        return

    while not _boot_gif_ready:
        elapsed = time.ticks_diff(time.ticks_ms(), _boot_gif_started_at)
        if elapsed >= BOOT_GIF_TIMEOUT_MS:
            break

        pump_lvgl(1, 15)

    # Wait for at least the known animation duration so an early READY event
    # cannot cut off the last frame.
    while time.ticks_diff(time.ticks_ms(), _boot_gif_started_at) < BOOT_GIF_DURATION_MS:
        pump_lvgl(1, 15)

    if not release:
        return

    try:
        _boot_gif.delete()
    except Exception:
        try:
            lv.obj.delete(_boot_gif)
        except Exception:
            pass

    _boot_gif = None
    _boot_gif_ready = True
    pump_lvgl(1, 1)


def forget_boot_animation():
    """Drop references after the menu has replaced the retained splash tree."""
    global _boot_gif, _boot_gif_ready

    _boot_gif = None
    _boot_gif_ready = True


def show_boot_error(stage, exc=None):
    """Replace any half-built UI with a persistent, readable error screen."""
    try:
        _splash, status = show_boot_splash("BOOT FAILED")

        if status is None:
            global _boot_gif

            if _boot_gif is not None:
                try:
                    _boot_gif.delete()
                except Exception:
                    try:
                        lv.obj.delete(_boot_gif)
                    except Exception:
                        pass
                _boot_gif = None

            status = lv.label(_splash)
            status.set_style_text_color(lv.color_hex(0xFF3B45), 0)
            status.set_pos(24, 96)

        message = "FAILED: " + str(stage)
        if exc is not None:
            try:
                message += "\n" + type(exc).__name__
            except Exception:
                pass

        status.set_text(message)
        status.set_style_text_color(lv.color_hex(0xFF3B45), 0)
        status.set_size(WIDTH - 48, 48)
        try:
            status.set_long_mode(lv.label.LONG_MODE.WRAP)
        except Exception:
            pass

        pump_lvgl(8, 20)
        return True
    except Exception as error_exc:
        try:
            print("Unable to show boot error:", error_exc)
        except Exception:
            pass
        return False


def get_screen():
    screen = lv.screen_active()
    if screen is None:
        screen = lv.obj()
        lv.screen_load(screen)

    screen.set_style_bg_color(lv.color_hex(0x000000), 0)
    screen.set_style_bg_opa(lv.OPA.COVER, 0)

    return screen
