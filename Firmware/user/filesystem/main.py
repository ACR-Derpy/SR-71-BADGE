"""Badge boot entrypoint.

main.py intentionally stays small:
- prevent accidental double init
- initialize display/touch and prepare the NFC service
- register LVGL filesystem
- load/apply saved state
- create the app
- start LVGL task handler and LEDs
"""
def stabilize_cold_boot():
    """Give badge power rails and peripherals time to settle after power-on."""
    try:
        import machine
        import time

        reset_cause = machine.reset_cause()
        power_on_reset = getattr(machine, "PWRON_RESET", reset_cause)

        if reset_cause == power_on_reset:
            print("Cold power-on: waiting for hardware to stabilize")
            time.sleep_ms(1000)
    except Exception as exc:
        # If reset-cause detection is unavailable, a short unconditional delay
        # is safer than racing the display and NeoPixel power-up sequence.
        try:
            print("Reset-cause check unavailable:", exc)
            import time
            time.sleep_ms(1000)
        except Exception:
            pass


def reset_boot_hardware():
    """Return externally powered peripherals to a known state before boot."""
    try:
        import time
        from machine import Pin

        print("Preflight: resetting badge hardware")

        # Reclaim BL_CTRL from any PWM channel left active by an interrupted
        # interpreter and keep the panel dark until a complete frame exists.
        try:
            backlight = Pin(8, Pin.OUT)
            backlight.value(0)
        except Exception as exc:
            print("Preflight backlight reset skipped:", exc)

        # Hold both external controllers in reset while the buses are returned
        # to idle. This is the part a battery reseat was previously doing.
        display_reset = None
        touch_reset = None

        try:
            display_cs = Pin(13, Pin.OUT)
            display_cs.value(1)
            display_dc = Pin(9, Pin.OUT)
            display_dc.value(0)
            display_clock = Pin(14, Pin.OUT)
            display_clock.value(0)
            display_data = Pin(15, Pin.OUT)
            display_data.value(0)

            display_reset = Pin(10, Pin.OUT)
            display_reset.value(0)
        except Exception as exc:
            print("Preflight display reset skipped:", exc)

        try:
            # Release the I2C lines before resetting the CST816S. The native
            # I2C driver will take ownership of them again in init_hardware().
            touch_sda = Pin(20, Pin.IN, Pin.PULL_UP)
            touch_scl = Pin(21, Pin.IN, Pin.PULL_UP)
            del touch_sda, touch_scl

            touch_reset = Pin(17, Pin.OUT)
            touch_reset.value(0)
        except Exception as exc:
            print("Preflight touch reset skipped:", exc)

        # Return the ST25R3911B SPI bus to an idle electrical state. The chip
        # itself is reset later with CMD_SET_DEFAULT during NFCRuntime.initialize().
        try:
            nfc_cs = Pin(5, Pin.OUT)
            nfc_cs.value(1)
            nfc_clock = Pin(6, Pin.OUT)
            nfc_clock.value(0)
            nfc_mosi = Pin(7, Pin.OUT)
            nfc_mosi.value(0)
            nfc_miso = Pin(4, Pin.IN)
            del nfc_cs, nfc_clock, nfc_mosi, nfc_miso
        except Exception as exc:
            print("Preflight NFC bus reset skipped:", exc)

        # Clear any color latched in the NeoPixel chain before showing a new
        # boot sequence. The LEDs retain their last frame across MCU resets.
        try:
            import neopixel

            pixels = neopixel.NeoPixel(Pin(0), 10)
            for i in range(10):
                pixels[i] = (0, 0, 0)
            pixels.write()
        except Exception as exc:
            print("Preflight LED reset skipped:", exc)

        time.sleep_ms(25)

        if display_reset is not None:
            display_reset.value(1)
        if touch_reset is not None:
            touch_reset.value(1)

        # ST7789 and CST816S both need time after reset release before their
        # drivers issue commands. This delay applies on every reset, not only
        # a cold power-on.
        time.sleep_ms(150)
        print("Preflight: hardware reset complete")

    except Exception as exc:
        # Cleanup is fail-open: diagnostics are useful, but it must never be a
        # new reason the badge cannot attempt normal initialization.
        try:
            print("Preflight hardware cleanup skipped:", exc)
        except Exception:
            pass


def boot_led_flash():
    try:
        import time
        import neopixel
        from machine import Pin

        LED_PIN = 0
        NUM_LEDS = 10
        BRIGHTNESS = 0.18
        # The badge is shaped like an SR-71. LEDs 1/2 and 9/10 are reserved for
        # the Afterburner runtime; the middle six are the aircraft body.
        ENGINE_LEDS = (0, 1, 8, 9)
        BODY_LEDS = (2, 3, 4, 5, 6, 7)
        BODY_POWER_PAIRS = ((4, 5), (3, 6), (2, 7))

        np = neopixel.NeoPixel(Pin(LED_PIN), NUM_LEDS)

        def scale(rgb):
            return (
                int(rgb[0] * BRIGHTNESS),
                int(rgb[1] * BRIGHTNESS),
                int(rgb[2] * BRIGHTNESS),
            )

        def clear():
            for i in range(NUM_LEDS):
                np[i] = (0, 0, 0)
            np.write()

        purple = scale((180, 0, 255))
        body_idle = scale((70, 0, 140))

        clear()

        # Charge the aircraft body from its center outward toward both engines.
        # Each pair stays lit, so this reads as power routing instead of a
        # single glitching pixel moving around the outline.
        for pair in BODY_POWER_PAIRS:
            for i in pair:
                np[i] = purple
            np.write()
            time.sleep_ms(75)

        # Hold at "airframe powered, engines cold." After the UI is ready, the
        # Afterburner pattern owns the ignition flash and engine power-up.
        for i in BODY_LEDS:
            np[i] = body_idle
        for i in ENGINE_LEDS:
            np[i] = (0, 0, 0)
        np.write()

    except Exception as exc:
        # Never let LEDs prevent boot.
        try:
            print("Boot LED animation skipped:", exc)
        except Exception:
            pass


def boot_led_error():
    """Leave an unmistakable hardware signal if Python boot aborts."""
    try:
        import neopixel
        from machine import Pin

        np = neopixel.NeoPixel(Pin(0), 10)
        for i in range(10):
            np[i] = (46, 0, 0)
        np.write()
    except Exception:
        pass


# Prevent accidental double init when running from an IDE without resetting.
try:
    _BADGE_MAIN_ACTIVE
except Exception:
    _BADGE_MAIN_ACTIVE = False

if _BADGE_MAIN_ACTIVE:
    # MicroPico can execute main.py again in the existing interpreter. The old
    # behavior ran the boot LEDs and then raised here, leaving a dark/stopped
    # UI. Force one clean hardware reset instead so normal boot can resume.
    print("Badge app already active; restarting cleanly")
    import machine
    machine.reset()
    raise RuntimeError("machine.reset() returned unexpectedly")

_BADGE_MAIN_ACTIVE = True
stabilize_cold_boot()
reset_boot_hardware()
boot_led_flash()

import gc
import lvgl as lv
import task_handler

from backlight import set_backlight_percent
from badge_config import NORMAL_BACKLIGHT
from boot_ui import (
    forget_boot_animation,
    get_screen,
    register_lvgl_filesystem,
    show_boot_error,
    update_boot_splash,
    wait_for_boot_animation,
)
from hardware import apply_display_orientation, init_hardware
from touch_activity import note_touch_activity


_boot_stage = "INITIALIZING HARDWARE"

try:
    print("Boot stage:", _boot_stage)

    # Keep all hardware references global so they are not garbage-collected.
    spi_bus, display_bus, display, touch_bus, touch_device, touch = init_hardware()

    # Start idle tracking from the moment the app comes up.
    note_touch_activity()

    _boot_stage = "REGISTERING FILESYSTEM"
    print("Boot stage:", _boot_stage)
    update_boot_splash(_boot_stage)
    register_lvgl_filesystem()

    _boot_stage = "LOADING NFC SERVICE"
    print("Boot stage:", _boot_stage)
    update_boot_splash(_boot_stage)
    nfc_runtime = None
    try:
        from nfc_runtime import NFCRuntime

        # The service imports the large P2P stack and initializes the chip only
        # when the user starts a trade/tag scan. This protects boot-time RAM.
        nfc_runtime = NFCRuntime()
        if not nfc_runtime.available:
            print("NFC service unavailable; badge UI will continue without it")
    except Exception as nfc_exc:
        print("NFC service failed to load:", nfc_exc)
        try:
            import sys
            sys.print_exception(nfc_exc)
        except Exception:
            pass
        nfc_runtime = None

    gc.collect()

    # Load the large UI tree only after the display is online. If an uploaded
    # module is missing, truncated, or incompatible, the badge can now show
    # the failing stage instead of remaining completely black.
    _boot_stage = "LOADING APP MODULES"
    print("Boot stage:", _boot_stage)
    update_boot_splash(_boot_stage)
    gc.collect()
    from badge_app import BadgeApp
    from persistent_store import load_state
    from state_bootstrap import (
        apply_persisted_card_unlocks,
        initialize_state_if_first_run,
    )

    _boot_stage = "LOADING SAVE STATE"
    print("Boot stage:", _boot_stage)
    update_boot_splash(_boot_stage)
    state, first_run = load_state()
    state = initialize_state_if_first_run(state, first_run)
    apply_persisted_card_unlocks(state["cards"].get("unlocked_ids", []))

    _boot_stage = "BUILDING UI"
    print("Boot stage:", _boot_stage)
    update_boot_splash(_boot_stage)
    wait_for_boot_animation(release=False)
    ui_orientation = state.get("settings", {}).get("display_orientation")
    apply_display_orientation(display, touch, ui_orientation)
    screen = get_screen()
    app = BadgeApp(
        screen,
        display=display,
        touch=touch,
        state=state,
        nfc_runtime=nfc_runtime,
    )
    # BadgeApp has replaced the splash tree with the completed menu. Drop the
    # retained GIF wrapper only now, avoiding a black frame between screens.
    forget_boot_animation()

    _boot_stage = "STARTING SERVICES"
    print("Boot stage:", _boot_stage)
    app.start_default_leds()
    lv.task_handler()
    # Blank two-card transit is light enough to service at ~40 Hz.
    handler = task_handler.TaskHandler(25)
    lv.task_handler()
    set_backlight_percent(app.screen_brightness)

except Exception as exc:
    print("Badge boot failed during", _boot_stage, ":", exc)
    try:
        import sys
        sys.print_exception(exc)
    except Exception:
        pass

    boot_led_error()
    try:
        show_boot_error(_boot_stage, exc)
        set_backlight_percent(NORMAL_BACKLIGHT)
    except Exception:
        pass
    raise

print("Badge app initialized")
