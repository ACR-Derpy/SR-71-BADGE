try:
    import ujson as json
except ImportError:
    import json

import os


STATE_FILE = "/badge_state.json"
TMP_FILE = "/badge_state.tmp"


DEFAULT_STATE = {
    "version": 1,
    "collection_complete": False,
    "collection_animation_played": False,
    "collection_reward_version": 0,
    "cards": {
        "unlocked_ids": [],
        "selected_index": 0,
    },

    "settings": {
        "led_enabled": True,
        "led_pattern": "Afterburner",
        "led_color": "PURPLE",
        "led_brightness": 20,
        "golden_shimmer": "NORMAL",

        "screen_brightness": 100,
        "display_orientation": "flipped",
        "low_power_backlight": 15,
        "low_power_screen_off": False,
        "idle_timeout_ms": 30000,
    },
}


def _copy_default():
    return json.loads(json.dumps(DEFAULT_STATE))


def _merge_defaults(defaults, loaded):
    for key, value in defaults.items():
        if key not in loaded:
            loaded[key] = value
        elif isinstance(value, dict) and isinstance(loaded[key], dict):
            _merge_defaults(value, loaded[key])

    return loaded


def load_state():
    """
    Returns:
        state, first_run

    first_run is True when no valid save file exists.
    That should normally happen after flashing, filesystem wipe, or manual reset.
    """
    try:
        with open(STATE_FILE, "r") as f:
            loaded = json.loads(f.read())

        state = _merge_defaults(_copy_default(), loaded)
        # Gift sending is unlimited; discard the obsolete persisted counter.
        state.pop("gifts", None)
        return state, False

    except Exception:
        return _copy_default(), True


def save_state(state):
    """
    Safer flash save:
    1. write temp file
    2. remove old save
    3. rename temp save
    """
    try:
        with open(TMP_FILE, "w") as f:
            f.write(json.dumps(state))

        try:
            os.remove(STATE_FILE)
        except OSError:
            pass

        os.rename(TMP_FILE, STATE_FILE)

        try:
            os.sync()
        except Exception:
            pass

        return True

    except Exception as exc:
        print("State save failed:", exc)
        return False


def reset_state():
    try:
        os.remove(STATE_FILE)
    except OSError:
        pass

    try:
        os.remove(TMP_FILE)
    except OSError:
        pass
