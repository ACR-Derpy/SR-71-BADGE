"""Confirmed one-way NFC card gifting.

Gift payloads are typed so they cannot be accepted as normal trade payloads.
The sender always initiates and the receiver always listens. Both roles return
success only after IDExchange completes its six-frame confirmation handshake.
"""

try:
    import hashlib
except ImportError:
    import uhashlib as hashlib

import random
import time

from P2P_config import (
    OP_CONTROL_TX_EN,
    REG_OP_CONTROL,
    _modify_reg,
    configure_nfcip1_target,
)
from id_exchange import IDExchange
from trade import badge_token, normalize_card_id


DEFAULT_GIFT_TIMEOUT_MS = 10_000
GIFT_CARD_TYPE = 0x47
GIFT_RECEIVER_TYPE = 0x52
GIFT_TOKEN_LEN = 7
PAYLOAD_LEN = 12
_GIFT_CARD_PREFIX = b"ACR67:GIFT:CARD:"
_GIFT_RECEIVER_PREFIX = b"ACR67:GIFT:RECEIVER:"


def _gift_card_token(card_id):
    value = normalize_card_id(card_id)
    return hashlib.sha256(_GIFT_CARD_PREFIX + value.encode()).digest()[:GIFT_TOKEN_LEN]


def _gift_card_map(known_card_ids):
    result = {}
    for card_id in known_card_ids:
        normalized = normalize_card_id(card_id)
        if normalized:
            result[_gift_card_token(normalized)] = normalized
    return result


def build_gift_card_payload(card_id, device_id):
    return (
        bytes([GIFT_CARD_TYPE])
        + _gift_card_token(card_id)
        + badge_token(device_id)
    )


def build_gift_receiver_payload(device_id):
    nonce_material = (
        _GIFT_RECEIVER_PREFIX
        + bytes(device_id)
        + str(time.ticks_us()).encode()
    )
    nonce = hashlib.sha256(nonce_material).digest()[:GIFT_TOKEN_LEN]
    return bytes([GIFT_RECEIVER_TYPE]) + nonce + badge_token(device_id)


def parse_gift_card_payload(payload, token_map):
    if payload is None:
        return None, None
    raw = bytes(payload)
    if len(raw) != PAYLOAD_LEN or raw[0] != GIFT_CARD_TYPE:
        return None, None
    return token_map.get(raw[1:8]), raw[8:12]


def parse_gift_receiver_payload(payload):
    if payload is None:
        return None
    raw = bytes(payload)
    if len(raw) != PAYLOAD_LEN or raw[0] != GIFT_RECEIVER_TYPE:
        return None
    return raw[8:12]


def _cancelled(should_cancel):
    if should_cancel is None:
        return False
    try:
        return bool(should_cancel())
    except Exception:
        return False


def _progress(progress_cb, text):
    if progress_cb is None:
        return
    try:
        progress_cb(str(text))
    except Exception:
        pass


def _prepare_target(idx):
    _modify_reg(idx.spi, idx.cs, REG_OP_CONTROL, OP_CONTROL_TX_EN, 0x00)
    configure_nfcip1_target(idx.spi, idx.cs)
    try:
        idx.lw._enter_power_off()
    except Exception:
        try:
            idx.lw.state = 0
        except Exception:
            pass


def _base_result(role):
    return {
        "ok": False,
        "canceled": False,
        "error": None,
        "role": role,
        "card_id": None,
        "peer_badge_token": None,
        "attempts": 0,
        "elapsed_ms": 0,
    }


def run_gift_send(
    idx,
    card_id,
    known_card_ids,
    overall_timeout_ms=DEFAULT_GIFT_TIMEOUT_MS,
    should_cancel=None,
    progress_cb=None,
):
    """Send one typed card payload to a badge in gift-receive mode."""
    if not isinstance(idx, IDExchange):
        raise TypeError("run_gift_send requires IDExchange")

    normalized = normalize_card_id(card_id)
    token_map = _gift_card_map(known_card_ids)
    if not normalized or _gift_card_token(normalized) not in token_map:
        raise ValueError("gift card is not in the badge card table")

    original_id = bytes(idx.my_id)
    local_badge_token = badge_token(original_id)
    idx.my_id = build_gift_card_payload(normalized, original_id)
    result = _base_result("sender")
    result["card_id"] = normalized
    started = time.ticks_ms()
    deadline = time.ticks_add(started, int(overall_timeout_ms))

    _progress(progress_cb, "Hold antennas together...")
    try:
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if _cancelled(should_cancel):
                result["canceled"] = True
                result["error"] = "Gift canceled."
                return result

            result["attempts"] += 1
            _progress(progress_cb, "Looking for gift receiver...")
            peer_payload = idx.initiate(timeout_ms=700)
            if peer_payload is not None:
                peer_badge = parse_gift_receiver_payload(peer_payload)
                if peer_badge is not None and peer_badge != local_badge_token:
                    result["ok"] = True
                    result["peer_badge_token"] = peer_badge
                    _progress(progress_cb, "Gift sent.")
                    return result

            if time.ticks_diff(deadline, time.ticks_ms()) > 0:
                time.sleep_ms(random.randint(80, 180))

        result["error"] = "No gift receiver found before timeout."
        return result
    finally:
        idx.my_id = original_id
        result["elapsed_ms"] = time.ticks_diff(time.ticks_ms(), started)
        try:
            _modify_reg(idx.spi, idx.cs, REG_OP_CONTROL, OP_CONTROL_TX_EN, 0x00)
        except Exception:
            pass


def run_gift_receive(
    idx,
    known_card_ids,
    overall_timeout_ms=DEFAULT_GIFT_TIMEOUT_MS,
    should_cancel=None,
    progress_cb=None,
):
    """Listen for and receive one typed gift-card payload."""
    if not isinstance(idx, IDExchange):
        raise TypeError("run_gift_receive requires IDExchange")

    original_id = bytes(idx.my_id)
    local_badge_token = badge_token(original_id)
    token_map = _gift_card_map(known_card_ids)
    idx.my_id = build_gift_receiver_payload(original_id)
    result = _base_result("receiver")
    started = time.ticks_ms()
    deadline = time.ticks_add(started, int(overall_timeout_ms))

    _progress(progress_cb, "Waiting for gift sender...")
    try:
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if _cancelled(should_cancel):
                result["canceled"] = True
                result["error"] = "Gift receive canceled."
                return result

            result["attempts"] += 1
            _prepare_target(idx)
            remaining = time.ticks_diff(deadline, time.ticks_ms())
            peer_payload = idx.respond(timeout_ms=min(800, max(1, remaining)))
            if peer_payload is not None:
                received_id, peer_badge = parse_gift_card_payload(
                    peer_payload, token_map
                )
                if (
                    received_id is not None
                    and peer_badge is not None
                    and peer_badge != local_badge_token
                ):
                    result["ok"] = True
                    result["card_id"] = received_id
                    result["peer_badge_token"] = peer_badge
                    _progress(progress_cb, "Gift received.")
                    return result

        result["error"] = "No gift sender found before timeout."
        return result
    finally:
        idx.my_id = original_id
        result["elapsed_ms"] = time.ticks_diff(time.ticks_ms(), started)
        try:
            _modify_reg(idx.spi, idx.cs, REG_OP_CONTROL, OP_CONTROL_TX_EN, 0x00)
        except Exception:
            pass
