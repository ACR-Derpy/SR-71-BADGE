"""Symmetric one-card peer-to-peer trade over a confirmed IDExchange.

Both badges run ``run_peer_trade``. Each badge offers one card. A random timer
causes one badge to become initiator while the other remains target.

IDExchange completes a confirmed six-frame handshake:

    ID_REQ -> ID_RES -> ID_ACK -> ID_DONE -> ID_CONFIRM -> ID_FINAL

Neither role returns success after only receiving or transmitting one side of
the trade. The trade layer therefore unlocks the peer card only after the
low-level exchange confirms that both payloads were transferred.

The default compact protocol completes the card exchange and ownership decision
inside that same six-frame handshake. The 12-byte payload slot is:

    bytes 0..7   deterministic card token
    bytes 8..11  deterministic badge fingerprint

The badge fingerprint makes two payloads different even when both users offer
the same card, preventing a badge from accepting its own residual RF echo as a
peer response.

ID_RES embeds the target's ownership decision in a marked badge-token bit.
ID_ACK carries the initiator's decision and an order-independent digest binding
both offers. The original two-handshake implementation remains available as
``run_peer_trade_legacy`` for immediate rollback.
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
    log,
)
from id_exchange import IDExchange


DEFAULT_OVERALL_TIMEOUT_MS = 10_000
BACKOFF_MIN_MS = 35
BACKOFF_MAX_MS = 160
CARD_TOKEN_LEN = 8
BADGE_TOKEN_LEN = 4
PAYLOAD_LEN = CARD_TOKEN_LEN + BADGE_TOKEN_LEN
_CARD_TOKEN_SALT = (
    b"\xb7\x7f\xc0\x2a\x89\x36\x9b\xe0"
    b"\x5d\x14\x25\xc3\x2b\x30\x61\x7a"
    b"\xa3\x50\x5f\xd4\x32\xd3\x85\xa5"
    b"\xd5\xb9\xd5\xb2\x62\x43\xbf\x56"
)
_BADGE_PREFIX = b"ACR67:BADGE:"
_DECISION_PREFIX = b"ACR67:TRADE-CHECK:"
_DECISION_MAGIC = 0xD4
_DECISION_DIGEST_LEN = 6


def normalize_card_id(card_id):
    return str(card_id).strip().upper()


def card_token(card_id):
    """Return the stable 8-byte token for a card ID."""
    value = normalize_card_id(card_id)
    return hashlib.sha256(_CARD_TOKEN_SALT + value.encode()).digest()[:CARD_TOKEN_LEN]


def badge_token(device_id):
    """Return a stable 4-byte fingerprint for one physical badge."""
    return hashlib.sha256(_BADGE_PREFIX + bytes(device_id)).digest()[:BADGE_TOKEN_LEN]


def build_trade_payload(card_id, device_id):
    return card_token(card_id) + badge_token(device_id)


def build_card_token_map(known_card_ids):
    result = {}
    for card_id in known_card_ids:
        normalized = normalize_card_id(card_id)
        if normalized:
            result[card_token(normalized)] = normalized
    return result


def parse_trade_payload(payload, token_map):
    """Return ``(card_id, peer_badge_token)`` or ``(None, None)``."""
    if payload is None:
        return None, None

    raw = bytes(payload)
    if len(raw) != PAYLOAD_LEN:
        return None, None

    card_id = token_map.get(raw[:CARD_TOKEN_LEN])
    if card_id is None:
        return None, None

    return card_id, raw[CARD_TOKEN_LEN:PAYLOAD_LEN]


def trade_decision_digest(local_card_id, local_badge, peer_card_id, peer_badge):
    """Return an order-independent digest identifying one proposed trade."""
    local_side = card_token(local_card_id) + bytes(local_badge)
    peer_side = card_token(peer_card_id) + bytes(peer_badge)
    if peer_side < local_side:
        local_side, peer_side = peer_side, local_side
    return hashlib.sha256(
        _DECISION_PREFIX + local_side + peer_side
    ).digest()[:_DECISION_DIGEST_LEN]


def build_trade_decision_payload(accepted, badge_id, digest):
    badge_id = bytes(badge_id)
    digest = bytes(digest)
    if len(badge_id) != BADGE_TOKEN_LEN:
        raise ValueError("trade decision needs a 4-byte badge token")
    if len(digest) != _DECISION_DIGEST_LEN:
        raise ValueError("trade decision needs a 6-byte digest")
    return bytes((_DECISION_MAGIC, 1 if accepted else 0)) + badge_id + digest


def parse_trade_decision_payload(payload, expected_badge, expected_digest):
    raw = bytes(payload or b"")
    if len(raw) != PAYLOAD_LEN or raw[0] != _DECISION_MAGIC:
        return None
    if raw[2:6] != bytes(expected_badge):
        return None
    if raw[6:12] != bytes(expected_digest):
        return None
    return bool(raw[1])


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
    """Re-arm a clean target/listen state before each random-timer attempt."""
    _modify_reg(idx.spi, idx.cs, REG_OP_CONTROL, OP_CONTROL_TX_EN, 0x00)
    configure_nfcip1_target(idx.spi, idx.cs)

    # ListenWorker can retain IDLE after returning a frame. Force the next
    # attempt back to POWER_OFF so it waits for a fresh EON edge.
    try:
        idx.lw._enter_power_off()
    except Exception:
        try:
            idx.lw.state = 0
        except Exception:
            pass


def _run_once(idx, t_min_ms, t_max_ms, should_cancel=None):
    timer_ms = random.randint(t_min_ms, t_max_ms - 1)
    out = {
        "ok": False,
        "role": "none",
        "timer_ms": timer_ms,
        "peer_payload": None,
    }

    _prepare_target(idx)
    log("[trade] target listen window={}ms".format(timer_ms), "info")

    # Keep one continuous target-listen window. If a request arrives,
    # IDExchange.respond() now stays in control until RES/ACK/DONE is confirmed
    # or the confirmation attempt fails. It does not report a one-sided trade.
    peer_payload = idx.respond(timeout_ms=timer_ms)
    if peer_payload is not None:
        out["ok"] = True
        out["role"] = "target"
        out["peer_payload"] = peer_payload
        return out
    if _cancelled(should_cancel):
        return out

    # Our timer won. Become initiator. IDExchange.initiate() returns only after
    # receiving the matching terminal confirmation.
    out["role"] = "initiator"
    log("[trade] listen expired; becoming initiator", "info")
    peer_payload = idx.initiate(timeout_ms=700)
    if peer_payload is not None:
        out["ok"] = True
        out["peer_payload"] = peer_payload
    return out


def run_peer_trade_legacy(
    idx,
    offered_card_id,
    known_card_ids,
    owned_card_ids=None,
    received_card_ids=None,
    t_min_ms=200,
    t_max_ms=800,
    overall_timeout_ms=DEFAULT_OVERALL_TIMEOUT_MS,
    should_cancel=None,
    progress_cb=None,
):
    """Exchange exactly one card with another badge.

    Both users call this same function. No sender/receiver selection is needed.

    After exchanging offers, both badges perform a second confirmed exchange
    carrying ownership approval. Neither side succeeds unless both received
    cards are new to their respective recipients.
    """
    if not isinstance(idx, IDExchange):
        raise TypeError("run_peer_trade requires IDExchange")
    if t_min_ms < 0 or t_max_ms <= t_min_ms:
        raise ValueError("need 0 <= t_min_ms < t_max_ms")
    if overall_timeout_ms <= 0:
        raise ValueError("overall_timeout_ms must be positive")

    offered_id = normalize_card_id(offered_card_id)
    offered_token_map = build_card_token_map(known_card_ids)
    received_token_map = build_card_token_map(
        received_card_ids
        if received_card_ids is not None
        else known_card_ids
    )
    owned_ids = set(
        normalize_card_id(card_id) for card_id in (owned_card_ids or ())
    )
    if not offered_id or card_token(offered_id) not in offered_token_map:
        raise ValueError("offered card is not in the badge card table")

    original_id = bytes(idx.my_id)

    # Force the two badges onto different arbitration/backoff sequences even
    # when they boot and enter P2P at nearly the same instant.
    seed_value = time.ticks_us()
    for value in original_id:
        seed_value = ((seed_value * 33) ^ int(value)) & 0x3FFFFFFF
    try:
        random.seed(seed_value)
    except Exception:
        pass

    local_badge_token = badge_token(original_id)
    idx.my_id = build_trade_payload(offered_id, original_id)
    result = {
        "ok": False,
        "canceled": False,
        "error": None,
        "role": "none",
        "offered_id": offered_id,
        "received_id": None,
        "peer_badge_token": None,
        "attempts": 0,
        "elapsed_ms": 0,
    }

    started = time.ticks_ms()
    deadline = time.ticks_add(started, int(overall_timeout_ms))
    last_invalid_error = None

    log(
        "[trade] P2P offer={} payload={} timeout={}ms".format(
            offered_id, idx.my_id.hex(), overall_timeout_ms
        )
    )
    _progress(progress_cb, "Hold both badges together...")

    try:
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if _cancelled(should_cancel):
                result["canceled"] = True
                result["error"] = "Peer trade canceled."
                return result

            result["attempts"] += 1
            _progress(
                progress_cb,
                "Searching for peer... attempt {}".format(result["attempts"]),
            )

            attempt = _run_once(
                idx,
                t_min_ms,
                t_max_ms,
                should_cancel=should_cancel,
            )

            if attempt.get("ok"):
                peer_id, peer_badge = parse_trade_payload(
                    attempt.get("peer_payload"), received_token_map
                )

                if peer_id is None:
                    last_invalid_error = "Peer sent an unknown card token."
                    log("[trade] rejected unknown peer payload", "warn")
                elif peer_badge == local_badge_token:
                    last_invalid_error = "Ignored local RF echo."
                    log("[trade] ignored self-echo payload", "warn")
                else:
                    result["role"] = attempt.get("role", "none")
                    result["received_id"] = peer_id
                    result["peer_badge_token"] = peer_badge

                    local_accepts = peer_id not in owned_ids
                    decision_digest = trade_decision_digest(
                        offered_id,
                        local_badge_token,
                        peer_id,
                        peer_badge,
                    )
                    idx.my_id = build_trade_decision_payload(
                        local_accepts,
                        local_badge_token,
                        decision_digest,
                    )
                    _progress(progress_cb, "Checking card ownership...")

                    # Ownership is a second complete six-frame exchange. Give
                    # it its own bounded phase budget instead of inheriting the
                    # few milliseconds that may remain after peer discovery.
                    ownership_deadline = time.ticks_add(
                        time.ticks_ms(), int(overall_timeout_ms)
                    )
                    while (
                        time.ticks_diff(ownership_deadline, time.ticks_ms()) > 0
                    ):
                        if _cancelled(should_cancel):
                            result["canceled"] = True
                            result["error"] = "Peer trade canceled."
                            return result

                        result["attempts"] += 1
                        decision_attempt = _run_once(
                            idx,
                            t_min_ms,
                            t_max_ms,
                            should_cancel=should_cancel,
                        )
                        if not decision_attempt.get("ok"):
                            continue

                        peer_accepts = parse_trade_decision_payload(
                            decision_attempt.get("peer_payload"),
                            peer_badge,
                            decision_digest,
                        )
                        if peer_accepts is None:
                            log("[trade] ignored stale ownership response", "warn")
                            continue

                        if not local_accepts:
                            result["error"] = (
                                "You already own {}. Use Gift Mode instead."
                            ).format(peer_id)
                            return result
                        if not peer_accepts:
                            result["error"] = (
                                "Peer already owns {}. Use Gift Mode instead."
                            ).format(offered_id)
                            return result

                        result["ok"] = True
                        _progress(progress_cb, "Trade complete.")
                        return result

                    result["error"] = "Ownership check timed out."
                    return result

            if _cancelled(should_cancel):
                result["canceled"] = True
                result["error"] = "Peer trade canceled."
                return result

            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                break

            time.sleep_ms(random.randint(BACKOFF_MIN_MS, BACKOFF_MAX_MS))

        result["error"] = last_invalid_error or "No peer badge found before timeout."
        return result

    finally:
        idx.my_id = original_id
        result["elapsed_ms"] = time.ticks_diff(time.ticks_ms(), started)
        try:
            _modify_reg(idx.spi, idx.cs, REG_OP_CONTROL, OP_CONTROL_TX_EN, 0x00)
        except Exception:
            pass


def _compact_badge_token(device_id):
    value = bytearray(badge_token(device_id))
    value[0] &= 0x3F
    return bytes(value)


def _build_compact_offer(card_id, device_id, accepted=None):
    badge = bytearray(_compact_badge_token(device_id))
    badge[0] |= 0x40
    if accepted:
        badge[0] |= 0x80
    return card_token(card_id) + bytes(badge)


def _parse_compact_offer(payload, token_map):
    card_id, marked_badge = parse_trade_payload(payload, token_map)
    if card_id is None:
        return None, None, None
    badge = bytearray(marked_badge)
    if not (badge[0] & 0x40):
        return None, None, None
    accepted = bool(badge[0] & 0x80)
    badge[0] &= 0x3F
    return card_id, bytes(badge), accepted


def _run_compact_once(
    idx,
    offered_id,
    original_id,
    received_token_map,
    owned_ids,
    t_min_ms,
    t_max_ms,
    should_cancel=None,
):
    timer_ms = random.randint(t_min_ms, t_max_ms - 1)
    local_badge = _compact_badge_token(original_id)
    state = {
        "peer_id": None,
        "peer_badge": None,
        "local_accepts": None,
        "peer_accepts": None,
        "digest": None,
    }

    def response_builder(requester_payload):
        peer_id, peer_badge, _unused = _parse_compact_offer(
            requester_payload, received_token_map
        )
        if peer_id is None or peer_badge == local_badge:
            raise ValueError("invalid compact trade request")
        state["peer_id"] = peer_id
        state["peer_badge"] = peer_badge
        state["local_accepts"] = peer_id not in owned_ids
        state["digest"] = trade_decision_digest(
            offered_id, local_badge, peer_id, peer_badge
        )
        return _build_compact_offer(
            offered_id, original_id, state["local_accepts"]
        )

    def ack_validator(ack_payload):
        if state["digest"] is None:
            return False
        decision = parse_trade_decision_payload(
            ack_payload, state["peer_badge"], state["digest"]
        )
        if decision is None:
            return False
        state["peer_accepts"] = decision
        return True

    _prepare_target(idx)
    response = idx.respond(
        timeout_ms=timer_ms,
        response_builder=response_builder,
        ack_validator=ack_validator,
        return_ack_payload=True,
    )
    if response is not None and state["peer_accepts"] is not None:
        state["ok"] = True
        state["role"] = "target"
        return state
    if _cancelled(should_cancel):
        return {"ok": False, "role": "none"}

    state["peer_id"] = None
    state["peer_badge"] = None
    state["local_accepts"] = None
    state["peer_accepts"] = None
    state["digest"] = None

    def ack_builder(response_payload):
        peer_id, peer_badge, peer_accepts = _parse_compact_offer(
            response_payload, received_token_map
        )
        if peer_id is None or peer_badge == local_badge:
            raise ValueError("invalid compact trade response")
        state["peer_id"] = peer_id
        state["peer_badge"] = peer_badge
        state["peer_accepts"] = peer_accepts
        state["local_accepts"] = peer_id not in owned_ids
        state["digest"] = trade_decision_digest(
            offered_id, local_badge, peer_id, peer_badge
        )
        return build_trade_decision_payload(
            state["local_accepts"], local_badge, state["digest"]
        )

    # A full confirmed exchange needs several RF turnarounds. Give the peer a
    # little more time to leave target mode and return ID_RES, especially when
    # both badges entered this screen at nearly the same instant.
    peer_payload = idx.initiate(timeout_ms=1000, ack_builder=ack_builder)
    if peer_payload is not None and state["peer_accepts"] is not None:
        state["ok"] = True
        state["role"] = "initiator"
        return state
    return {"ok": False, "role": "initiator"}


def run_peer_trade_compact(
    idx,
    offered_card_id,
    known_card_ids,
    owned_card_ids=None,
    received_card_ids=None,
    t_min_ms=200,
    t_max_ms=1200,
    overall_timeout_ms=DEFAULT_OVERALL_TIMEOUT_MS,
    should_cancel=None,
    progress_cb=None,
):
    """Exchange offers and both ownership decisions in one six-frame exchange."""
    if not isinstance(idx, IDExchange):
        raise TypeError("run_peer_trade requires IDExchange")
    if t_min_ms < 0 or t_max_ms <= t_min_ms:
        raise ValueError("need 0 <= t_min_ms < t_max_ms")
    if overall_timeout_ms <= 0:
        raise ValueError("overall_timeout_ms must be positive")

    offered_id = normalize_card_id(offered_card_id)
    offered_token_map = build_card_token_map(known_card_ids)
    received_token_map = build_card_token_map(
        received_card_ids if received_card_ids is not None else known_card_ids
    )
    owned_ids = set(normalize_card_id(value) for value in (owned_card_ids or ()))
    if not offered_id or card_token(offered_id) not in offered_token_map:
        raise ValueError("offered card is not in the badge card table")

    original_id = bytes(idx.my_id)
    local_badge = _compact_badge_token(original_id)
    idx.my_id = _build_compact_offer(offered_id, original_id)
    seed_value = time.ticks_us()
    for value in original_id:
        seed_value = ((seed_value * 33) ^ int(value)) & 0x3FFFFFFF
    try:
        random.seed(seed_value)
    except Exception:
        pass
    result = {
        "ok": False,
        "canceled": False,
        "error": None,
        "role": "none",
        "offered_id": offered_id,
        "received_id": None,
        "peer_badge_token": None,
        "attempts": 0,
        "elapsed_ms": 0,
    }
    started = time.ticks_ms()
    deadline = time.ticks_add(started, int(overall_timeout_ms))
    _progress(progress_cb, "Exchanging cards and checking ownership...")

    try:
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if _cancelled(should_cancel):
                result["canceled"] = True
                result["error"] = "Peer trade canceled."
                return result
            result["attempts"] += 1
            attempt = _run_compact_once(
                idx,
                offered_id,
                original_id,
                received_token_map,
                owned_ids,
                t_min_ms,
                t_max_ms,
                should_cancel=should_cancel,
            )
            if attempt.get("ok"):
                peer_id = attempt.get("peer_id")
                peer_badge = attempt.get("peer_badge")
                if peer_id is None or peer_badge == local_badge:
                    continue
                result["role"] = attempt.get("role", "none")
                result["received_id"] = peer_id
                result["peer_badge_token"] = peer_badge
                if not attempt.get("local_accepts"):
                    result["error"] = (
                        "You already own {}. Use Gift Mode instead."
                    ).format(peer_id)
                    return result
                if not attempt.get("peer_accepts"):
                    result["error"] = (
                        "Peer already owns {}. Use Gift Mode instead."
                    ).format(offered_id)
                    return result
                result["ok"] = True
                _progress(progress_cb, "Trade complete.")
                return result
            time.sleep_ms(random.randint(BACKOFF_MIN_MS, BACKOFF_MAX_MS))

        result["error"] = "No peer badge found before timeout."
        return result
    finally:
        idx.my_id = original_id
        result["elapsed_ms"] = time.ticks_diff(time.ticks_ms(), started)
        try:
            _modify_reg(idx.spi, idx.cs, REG_OP_CONTROL, OP_CONTROL_TX_EN, 0x00)
        except Exception:
            pass


# One-line rollback: change this alias to run_peer_trade_legacy.
run_peer_trade = run_peer_trade_compact
del run_peer_trade_compact
del run_peer_trade_legacy


def card_id_from_tag_text(text, known_card_ids):
    """Resolve a passive NDEF Text record to a known card ID.

    Only ``ACR67:CARD:<16 hex chars>`` is accepted. ``known_card_ids`` is
    supplied by the caller's ACR-card allowlist, so tokens cannot unlock
    ordinary cards. Plain IDs and legacy wrappers are deliberately rejected.
    """
    if text is None:
        return None

    value = str(text).strip().upper()
    token_prefix = "ACR67:CARD:"
    if not value.startswith(token_prefix):
        return None

    supplied_token = value[len(token_prefix):].strip()
    if len(supplied_token) != CARD_TOKEN_LEN * 2:
        return None

    for card_id in known_card_ids:
        normalized = normalize_card_id(card_id)
        if card_token(normalized).hex().upper() == supplied_token:
            return normalized
    return None
