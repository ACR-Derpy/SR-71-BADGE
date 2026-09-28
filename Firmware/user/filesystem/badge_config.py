"""Shared badge constants.

Keep hardware/layout constants here so main.py and feature modules do not need
hardcoded duplicate values.
"""

WIDTH = 240
HEIGHT = 280
TOUCH_I2C_FREQ = 400_000

DISPLAY_ORIENTATION_ORIGINAL = "original"
DISPLAY_ORIENTATION_FLIPPED = "flipped"
DISPLAY_ORIENTATIONS = (
    DISPLAY_ORIENTATION_ORIGINAL,
    DISPLAY_ORIENTATION_FLIPPED,
)
DEFAULT_DISPLAY_ORIENTATION = DISPLAY_ORIENTATION_FLIPPED

# Animated startup screen. The compact GIF is 160x186, 87 frames at 15 FPS,
# and plays once in about 5.8 seconds without runtime scaling.
BOOT_GIF_SRC = "A:/acr_badge_boot.gif"
BOOT_GIF_DURATION_MS = 5_800
BOOT_GIF_TIMEOUT_MS = 6_500

DEFAULT_LED_BOOT_ENABLED = True
DEFAULT_LED_PATTERN = "Afterburner"
DEFAULT_LED_COLOR = "PURPLE"
DEFAULT_LED_BRIGHTNESS = 80

# First-run starter cards. These are only chosen when badge_state.json does
# not exist yet, usually after flashing or a filesystem wipe.
STARTER_RANDOM_UNLOCK_COUNT = 3
ALWAYS_UNLOCKED_CARD_IDS = ()

# Passive NFC stickers may unlock only these dedicated cards. The sticker cards
# have not been added yet, so this remains empty until their final IDs exist.
# Card definitions may also set ``sticker_only=True``.
STICKER_CARD_IDS = ()

# Display backlight is controlled manually with PWM on BL_CTRL / GPIO 8.
# Do not use display.set_backlight() for brightness changes after init.
BACKLIGHT_PIN = 8
BACKLIGHT_PWM_FREQ = 1000

# Idle / low-power display mode.
IDLE_TIMEOUT_MS = 30_000
NORMAL_BACKLIGHT = 100
LOW_POWER_BACKLIGHT = 15
LOW_POWER_BACKLIGHT_MIN = 10
LOW_POWER_SCREEN_OFF_BACKLIGHT = 0

# Low-power behavior modes.
LOW_POWER_MODE_DISABLED = "disabled"
LOW_POWER_MODE_LOGO = "logo"
LOW_POWER_MODE_SCREEN_OFF = "screen_off"
LOW_POWER_MODES = (
    LOW_POWER_MODE_DISABLED,
    LOW_POWER_MODE_LOGO,
    LOW_POWER_MODE_SCREEN_OFF,
)
DEFAULT_LOW_POWER_MODE = LOW_POWER_MODE_LOGO

# Timeout tuning shown on the low-power settings page.
LOW_POWER_TIMEOUT_MIN_MS = 5_000
LOW_POWER_TIMEOUT_MAX_MS = 60_000
LOW_POWER_TIMEOUT_STEP_MS = 15_000

# Put a LVGL-compatible image at this path.
# If missing or invalid, the code falls back to text.
LOW_POWER_IMAGE_SRC = "A:/sleep.bin"

# Universal navigation gesture. The pill is only a visual cue: the input-device
# observer watches the full width of the lower 80 px without adding a blocking
# hitbox. The generous band also catches swipes first sensed above a curved edge.
UNIVERSAL_MENU_SWIPE_START_ZONE_H = 80
UNIVERSAL_MENU_SWIPE_MIN_TRAVEL = 30
UNIVERSAL_MENU_SWIPE_HANDLE_W = 132
UNIVERSAL_MENU_SWIPE_HANDLE_H = 6
