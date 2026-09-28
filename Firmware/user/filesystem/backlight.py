"""Manual PWM display backlight control."""

import machine

from badge_config import BACKLIGHT_PIN, BACKLIGHT_PWM_FREQ, NORMAL_BACKLIGHT

_backlight_pwm = None


def init_backlight_pwm():
    global _backlight_pwm

    try:
        _backlight_pwm = machine.PWM(machine.Pin(BACKLIGHT_PIN))
        _backlight_pwm.freq(BACKLIGHT_PWM_FREQ)
        set_backlight_percent(0)
        print("Manual PWM backlight initialized")
        return True

    except Exception as exc:
        print("Manual PWM backlight failed:", exc)
        _backlight_pwm = None
        return False


def set_backlight_percent(percent):
    try:
        percent = int(percent)
    except Exception:
        percent = NORMAL_BACKLIGHT

    if percent < 0:
        percent = 0
    elif percent > 100:
        percent = 100

    duty = int((percent * 65535) // 100)

    if _backlight_pwm is not None:
        try:
            _backlight_pwm.duty_u16(duty)
            return True
        except Exception as exc:
            print("PWM backlight set failed:", exc)

    print("Backlight PWM unavailable")
    return False
