"""First-run card unlock and saved card restore logic."""

from random import randint, seed

import machine
import time

from badge_config import (
    ALWAYS_UNLOCKED_CARD_IDS,
    STARTER_RANDOM_UNLOCK_COUNT,
    STICKER_CARD_IDS,
)
from card_carousel import CARDS, unlock_card_data
from persistent_store import save_state


def _get_card_id(card):
    """Return the stable unlock ID for a card definition."""
    if isinstance(card, dict):
        for key in ("id", "card_id", "uid", "unlock_id", "nfc_id", "code"):
            value = card.get(key)
            if value:
                return value

    for key in ("id", "card_id", "uid", "unlock_id", "nfc_id", "code"):
        try:
            value = getattr(card, key)
            if value:
                return value
        except Exception:
            pass

    return None


def _is_acr_card_id(card_id):
    """Return True for ACR-only cards that require an external unlock source."""
    try:
        return str(card_id).upper().startswith("ACR-")
    except Exception:
        return False


def _is_card_starter_eligible(card):
    """Return whether a card may be granted during first-run random setup."""
    card_id = _get_card_id(card)

    # ACR cards are reserved for staff distribution. Dedicated sticker cards
    # are also excluded so Tag Reader remains their only unlock path.
    if _is_acr_card_id(card_id):
        return False

    if isinstance(card, dict):
        if (
            card.get("sticker_only", False)
            or str(card_id).strip().upper() in STICKER_CARD_IDS
        ):
            return False
        return card.get("starter_eligible", True) is not False

    try:
        if (
            getattr(card, "sticker_only", False)
            or str(card_id).strip().upper() in STICKER_CARD_IDS
        ):
            return False
        return getattr(card, "starter_eligible") is not False
    except Exception:
        return True


def seed_random_once():
    value = 0

    try:
        value ^= time.ticks_us()
    except Exception:
        pass

    try:
        uid = machine.unique_id()
        shift = 0
        for b in uid:
            value ^= int(b) << shift
            shift += 8
            if shift >= 24:
                shift = 0
    except Exception:
        pass

    value &= 0x3fffffff

    if value == 0:
        value = 12345

    seed(value)


def shuffle_list(items):
    # MicroPython-safe Fisher-Yates shuffle.
    for i in range(len(items) - 1, 0, -1):
        j = randint(0, i)
        items[i], items[j] = items[j], items[i]


def pick_random_starter_card_ids(card_defs, count, always_unlocked=None):
    if always_unlocked is None:
        always_unlocked = ()

    final_ids = []

    for card_id in always_unlocked:
        # Keep the same protection on the explicit starter list.
        if (
            not card_id
            or _is_acr_card_id(card_id)
            or str(card_id).strip().upper() in STICKER_CARD_IDS
        ):
            continue

        if card_id not in final_ids:
            final_ids.append(card_id)

    locked_eligible_ids = []

    for card in card_defs:
        card_id = _get_card_id(card)

        if not card_id:
            continue

        if card_id in final_ids:
            continue

        if not _is_card_starter_eligible(card):
            continue

        locked_eligible_ids.append(card_id)

    shuffle_list(locked_eligible_ids)

    for card_id in locked_eligible_ids[:count]:
        if card_id not in final_ids:
            final_ids.append(card_id)

    return final_ids


def apply_persisted_card_unlocks(unlocked_ids):
    for card_id in unlocked_ids:
        try:
            result = unlock_card_data(card_id)

            # Existing code treats a negative index as "not found". Some
            # versions may return True/False/None, so keep this tolerant.
            try:
                if result < 0:
                    print("Saved card unlock not found:", card_id)
            except Exception:
                pass

        except Exception as exc:
            print("Saved card unlock failed:", card_id, exc)


def initialize_state_if_first_run(state, first_run):
    if first_run:
        print("First staff boot detected. Picking starter cards.")
        seed_random_once()
        state["cards"]["unlocked_ids"] = pick_random_starter_card_ids(
            CARDS,
            STARTER_RANDOM_UNLOCK_COUNT,
            always_unlocked=ALWAYS_UNLOCKED_CARD_IDS,
        )
        state["cards"]["selected_index"] = 0

    unlocked_ids = state["cards"].get("unlocked_ids", [])
    changed = bool(first_run)
    for card in CARDS:
        card_id = str(_get_card_id(card) or "").strip().upper()
        if card_id and card_id not in unlocked_ids:
            unlocked_ids.append(card_id)
            changed = True

    state["cards"]["unlocked_ids"] = unlocked_ids

    if changed:
        save_state(state)
        print("All staff cards initialized")

    return state
