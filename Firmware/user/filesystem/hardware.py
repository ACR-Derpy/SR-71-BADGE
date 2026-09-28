"""Hardware initialization and resilient touch driver."""

import gc
import time

import cst816s
import i2c
import lcd_bus
import lvgl as lv
import machine
import st7789

from backlight import init_backlight_pwm, set_backlight_percent
from badge_config import HEIGHT, NORMAL_BACKLIGHT, TOUCH_I2C_FREQ, WIDTH
from boot_ui import (
    register_lvgl_filesystem,
    show_boot_splash,
    update_boot_splash,
    wait_for_boot_animation,
)
from touch_activity import note_touch_activity


def normalize_display_orientation(value):
    from badge_config import DEFAULT_DISPLAY_ORIENTATION, DISPLAY_ORIENTATIONS

    if value in DISPLAY_ORIENTATIONS:
        return value
    return DEFAULT_DISPLAY_ORIENTATION


def apply_display_orientation(display, touch, value):
    """Rotate the LVGL display; LVGL rotates its attached pointer input."""
    from badge_config import DISPLAY_ORIENTATION_FLIPPED

    value = normalize_display_orientation(value)
    rotation = (
        lv.DISPLAY_ROTATION._180
        if value == DISPLAY_ORIENTATION_FLIPPED
        else lv.DISPLAY_ROTATION._0
    )
    display.set_rotation(rotation)

    if touch is not None:
        try:
            touch._last_x = -1
            touch._last_y = -1
        except Exception:
            pass

    return value


def _extract_touch_xy(coords):
    """Best-effort extraction of x/y from the CST816S driver return value."""
    if coords is None:
        return None, None

    # Mapping-like forms: {"x": ..., "y": ...}.
    try:
        if isinstance(coords, dict):
            return coords.get("x"), coords.get("y")
    except Exception:
        pass

    # Direct point-like object.
    try:
        x = getattr(coords, "x")
        y = getattr(coords, "y")
        return x, y
    except Exception:
        pass

    # PointerDriver's native form is (state, x, y). Handle that before the
    # generic two-item form so the press state is not mistaken for x.
    try:
        if len(coords) >= 3:
            x = coords[1]
            y = coords[2]
            if isinstance(x, int) and isinstance(y, int):
                return x, y

        # Direct tuple/list: (x, y), [x, y], or nested variants.
        if len(coords) >= 2:
            a = coords[0]
            b = coords[1]

            if isinstance(a, int) and isinstance(b, int):
                return a, b

            x, y = _extract_touch_xy(a)
            if x is not None and y is not None:
                return x, y

            x, y = _extract_touch_xy(b)
            if x is not None and y is not None:
                return x, y
    except Exception:
        pass

    return None, None


class ResilientCST816S(cst816s.CST816S):
    _RECOVERY_IDLE = 0
    _RECOVERY_RESET_LOW = 1
    _RECOVERY_BOOT_WAIT = 2

    def __init__(self, *args, **kwargs):
        self._recovery_state = self._RECOVERY_IDLE
        self._recovery_due = 0
        self.i2c_timeouts = 0
        super().__init__(*args, **kwargs)

    def _start_recovery(self, now):
        self.i2c_timeouts += 1
        if self._reset_pin is None:
            self._recovery_state = self._RECOVERY_BOOT_WAIT
            self._recovery_due = time.ticks_add(now, 250)
            return

        self._reset_pin(0)
        self._recovery_state = self._RECOVERY_RESET_LOW
        self._recovery_due = time.ticks_add(now, 2)

    def _get_coords(self):
        now = time.ticks_ms()

        if self._recovery_state == self._RECOVERY_RESET_LOW:
            if time.ticks_diff(now, self._recovery_due) >= 0:
                self._reset_pin(1)
                self._recovery_state = self._RECOVERY_BOOT_WAIT
                # Give the controller a full post-reset startup window before
                # touching its registers again.
                self._recovery_due = time.ticks_add(now, 120)
            return None

        if self._recovery_state == self._RECOVERY_BOOT_WAIT:
            if time.ticks_diff(now, self._recovery_due) < 0:
                return None

            try:
                self.auto_sleep_timeout = 255
                self.auto_sleep = False
                self._recovery_state = self._RECOVERY_IDLE
            except OSError:
                self._start_recovery(now)
            return None

        try:
            coords = super()._get_coords()

            if coords is not None:
                x, y = _extract_touch_xy(coords)
                if x is not None and y is not None:
                    try:
                        # LVGL rotates its own pointer coordinates for the
                        # active display. This separate observer receives raw
                        # controller coordinates, so mirror only its sample.
                        if self.get_rotation() == lv.DISPLAY_ROTATION._180:
                            x = self._orig_width - x - 1
                            y = self._orig_height - y - 1
                    except Exception:
                        pass
                note_touch_activity(x, y)
            return coords

        except OSError:
            self._start_recovery(now)
            return None


def init_hardware():
    lv.init()

    # Image cache: keep decoded .bin art in RAM so LVGL does not re-read from
    # flash on every render stripe. Without this every frame reloads the image.
    try:
        lv.image_cache_set_max_size(96 * 1024)   # LVGL 9.x
    except AttributeError:
        try:
            lv.img.cache_set_size(4)             # LVGL 8.x
        except Exception:
            pass

    spi_bus = machine.SPI(
        1,
        baudrate=40_000_000,
        polarity=0,
        phase=0,
        sck=14,
        mosi=15,
        miso=12,
    )

    display_bus = lcd_bus.SPIBus(
        spi_bus=spi_bus,
        freq=40_000_000,
        dc=9,
        cs=13,
    )

    # Use one bounded partial DMA buffer. Two full-screen internal DMA buffers
    # consume 268,800 bytes and, on a cold boot, the first FULL-mode flush can
    # stall in the native SPI driver. A 70-row buffer keeps memory predictable
    # and uses the framework's conservative 1/10-screen stripe size.
    gc.collect()
    buffer_rows = 28
    buf_size = WIDTH * buffer_rows * 2
    fb2 = None

    try:
        fb1 = display_bus.allocate_framebuffer(
            buf_size,
            lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA,
        )
        print("Partial-frame DMA x1:", buf_size, "B (", buffer_rows, "rows )")
    except Exception as exc:
        print("Partial DMA allocation unavailable:", exc)
        gc.collect()
        fb1 = bytearray(buf_size)
        print("Partial-frame bytearray x1:", buf_size, "B")

    # RGB565_SWAPPED avoids a per-pixel byte swap where supported.
    try:
        color_space = lv.COLOR_FORMAT.RGB565_SWAPPED
        byte_swap = False
    except AttributeError:
        color_space = lv.COLOR_FORMAT.RGB565
        byte_swap = True

    display = st7789.ST7789(
        data_bus=display_bus,
        display_width=WIDTH,
        display_height=HEIGHT,
        frame_buffer1=fb1,
        frame_buffer2=fb2,
        reset_pin=10,
        reset_state=st7789.STATE_LOW,
        backlight_pin=8,
        backlight_on_state=st7789.STATE_HIGH,
        offset_x=0,
        offset_y=20,
        color_space=color_space,
        color_byte_order=st7789.BYTE_ORDER_RGB,
        rgb565_byte_swap=byte_swap,
    )

    display.init()
    # The boot animation always uses the badge's flipped physical orientation.
    display.set_rotation(lv.DISPLAY_ROTATION._180)

    # Take over BL_CTRL / GPIO 8 with manual PWM immediately after display init.
    # From this point forward, brightness is controlled only by set_backlight_percent().
    init_backlight_pwm()
    set_backlight_percent(0)

    # The ST7789 framework selects PARTIAL while constructing the display
    # because fb1 is smaller than a complete frame. Do not change render mode
    # afterward; the driver configures its address-window strategy at init.
    print("LVGL render mode: PARTIAL (buffer-sized)")

    # Boot screen appears before touch init delay.
    print("Rendering boot splash")
    register_lvgl_filesystem()
    show_boot_splash("DISPLAY ONLINE")
    print("Boot splash rendered")
    set_backlight_percent(NORMAL_BACKLIGHT)

    # Give the display exclusive time for one smooth pass. Keep the final frame
    # alive while the remaining boot work runs; main releases it before menu.
    wait_for_boot_animation(release=False)

    update_boot_splash("INITIALIZING TOUCH")

    # The animation interval also satisfies the board's touch stabilization
    # delay, so no additional fixed wait is needed here.

    touch_bus = i2c.I2C.Bus(
        host=0,
        scl=21,
        sda=20,
        freq=TOUCH_I2C_FREQ,
        use_locks=False,
    )

    touch_device = i2c.I2C.Device(
        bus=touch_bus,
        dev_id=cst816s.I2C_ADDR,
        reg_bits=cst816s.BITS,
    )

    touch = ResilientCST816S(
        touch_device,
        reset_pin=17,
    )

    try:
        touch.auto_sleep_timeout = 255
        touch.auto_sleep = False
        time.sleep_ms(10)
        print("Touch auto-sleep enabled:", touch.auto_sleep)
    except (AttributeError, OSError) as exc:
        print("Touch auto-sleep control unavailable:", exc)

    update_boot_splash("TOUCH ONLINE")

    return spi_bus, display_bus, display, touch_bus, touch_device, touch
