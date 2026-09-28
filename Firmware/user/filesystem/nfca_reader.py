"""ISO14443A (NFC-A) reader mode for the ST25R3911B.

Adapted from the standalone `14443a_cleanup.py` prototype.  Key differences
from that file:

  * Does NOT run its own boot sequence.  We assume `main._bring_chip_up()`
    already ran reset / osc_on / configure_supply / configure_fifo_and_aux
    / configure_analog_chip_init / calibrate.  This module only handles
    the ISO14443A-specific mode config + polling loop.
  * Reuses the low-level SPI helpers and register/command constants from
    P2P_config (which re-exports P2P_regs), rather than duplicating them.
  * All output goes through log(msg, level=...) so verbosity honours the
    global LOG_LEVEL set in main.py.
  * The polling loop has an overall wall-clock timeout (default 10 s) and
    tears the RF field back down on exit so a subsequent trade lands in
    a clean idle state.

Public entry point:

    result = run_nfca_reader(spi, cs, overall_timeout_ms=10_000)

Returns a small dict:

    {
        "ok":         bool,               # True iff a card was fully read
        "uid":        bytes | None,       # 4, 7, or 10-byte NFC-A UID
        "text":       str   | None,       # NDEF text record if extracted
        "raw":        bytes,              # concatenated page reads
        "elapsed_ms": int,
        "polls":      int,                # REQA cycles attempted
    }
"""

import time

from P2P_config import (
    # low-level SPI helpers (all re-exported from P2P_regs)
    _read_reg, _write_reg, _modify_reg, _send_cmd,
    _write_fifo, _read_fifo, _read_irq,
    # register addresses
    REG_OP_CONTROL, REG_MODE, REG_BIT_RATE, REG_ISO14443A_NFC,
    REG_AUX, REG_RX_CONF1, REG_RX_CONF2, REG_RX_CONF3, REG_RX_CONF4,
    REG_MASK_RX_TIMER, REG_NO_RESPONSE_TIMER1, REG_NO_RESPONSE_TIMER2,
    REG_IRQ_MASK_MAIN, REG_IRQ_MASK_TIMER_NFC, REG_IRQ_MASK_ERROR_WUP,
    REG_IRQ_MAIN, REG_IRQ_TIMER_NFC, REG_IRQ_ERROR_WUP,
    REG_FIFO_RX_STATUS1, REG_FIFO_RX_STATUS2,
    REG_NUM_TX_BYTES1, REG_NUM_TX_BYTES2,
    REG_RFO_AM_ON_LEVEL, REG_AUX_DISPLAY,
    # direct commands
    CMD_CLEAR_FIFO, CMD_TRANSMIT_WITH_CRC, CMD_TRANSMIT_WITHOUT_CRC,
    CMD_UNMASK_RECEIVE_DATA, CMD_CLEAR_SQUELCH,
    # bit masks
    OP_CONTROL_TX_EN, OP_CONTROL_RX_EN, OP_CONTROL_WU,
    AUX_TR_AM, AUX_RX_TOL,
    IRQ_TXE, IRQ_RXE, IRQ_RXS, IRQ_FWL, IRQ_COL, IRQ_CRC, IRQ_PAR,
    AUX_DISPLAY_EFD_O,
    # logging
    log,
)


# CMD_TRANSMIT_REQA (0xC6) is not exposed via P2P_regs (the P2P stack
# doesn't use it - it uses NFC-A NFCIP-1 framing instead).  Define it
# locally so we don't have to touch P2P_regs just for reader mode.
CMD_TRANSMIT_REQA = 0xC6


# ---------------------------------------------------------------------------
# Mode setup / teardown
# ---------------------------------------------------------------------------

# Keep the original, previously working RF drive setting.  The stability fix
# here is deterministic state/IRQ cleanup and controlled field cycling, not a
# transmitter-power change.
FIELD_STARTUP_MS = 15
FIELD_RECOVERY_OFF_MS = 5


def _is_cancelled(should_cancel):
    if should_cancel is None:
        return False
    try:
        return bool(should_cancel())
    except Exception:
        return False


def _sleep_ms_cancelable(delay_ms, should_cancel=None):
    """Sleep in short slices so UI cancellation remains responsive."""
    deadline = time.ticks_add(time.ticks_ms(), int(delay_ms))
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        if _is_cancelled(should_cancel):
            return False
        remaining = time.ticks_diff(deadline, time.ticks_ms())
        time.sleep_ms(1 if remaining > 1 else remaining)
    return True


def _clear_fifo_and_irqs(spi, cs):
    """Discard stale FIFO bytes and all read-to-clear IRQ state."""
    _send_cmd(spi, cs, CMD_CLEAR_FIFO)
    _read_irq(spi, cs)


def _force_rf_idle(spi, cs):
    """Leave the RF front end quiescent while preserving oscillator power.

    OP_CONTROL bits 6..0 include RX enable/channel/manual selection, TX enable,
    and wake-up controls.  Clearing all seven prevents P2P state from leaking
    into reader mode and guarantees TX/RX are both off when NFC is finished.
    """
    _modify_reg(spi, cs, REG_OP_CONTROL, 0x7F, 0x00)
    _clear_fifo_and_irqs(spi, cs)


def _configure_nfca_106(spi, cs):
    """Apply a complete, deterministic ISO14443A reader configuration."""
    # Start from oscillator-only idle.  This removes any target/initiator P2P
    # receiver-channel selection or wake-up state left by a previous operation.
    _force_rf_idle(spi, cs)

    # MODE: initiator, ISO14443A at 106 kbps TX/RX.
    _write_reg(spi, cs, REG_MODE, 0x08)
    _write_reg(spi, cs, REG_BIT_RATE, 0x00)

    # Normal NFC-A parity/framing.  antcl is enabled immediately before REQA
    # and anticollision, then cleared before SELECT and normal READ commands.
    _modify_reg(spi, cs, REG_ISO14443A_NFC, 0xE1, 0x00)

    # Preserve the original RF drive configuration that previously detected
    # the sticker reliably.
    _modify_reg(spi, cs, REG_RFO_AM_ON_LEVEL, 0xFF, 0xF0)
    _modify_reg(spi, cs, REG_AUX, AUX_TR_AM, 0x00)

    # NFC-A 106 kbps receive path.
    _write_reg(spi, cs, REG_RX_CONF3, 0x18)
    _modify_reg(spi, cs, REG_RX_CONF4, 0xF0, 0x20)
    _modify_reg(spi, cs, REG_AUX, AUX_RX_TOL, 0x00)
    _modify_reg(spi, cs, REG_RX_CONF1, 0x7F, 0x00)

    # Deterministic receive timing before the first REQA.
    _write_reg(spi, cs, REG_MASK_RX_TIMER, 13)
    _write_reg(spi, cs, REG_NO_RESPONSE_TIMER1, 0x10)
    _write_reg(spi, cs, REG_NO_RESPONSE_TIMER2, 0x00)
    _write_reg(spi, cs, REG_NUM_TX_BYTES1, 0x00)
    _write_reg(spi, cs, REG_NUM_TX_BYTES2, 0x00)

    # Mask everything first, then unmask only the events consumed by this
    # polled reader.  ST25R3911B mask bits are active-high.
    _write_reg(spi, cs, REG_IRQ_MASK_MAIN, 0xFF)
    _write_reg(spi, cs, REG_IRQ_MASK_TIMER_NFC, 0xFF)
    _write_reg(spi, cs, REG_IRQ_MASK_ERROR_WUP, 0xFF)
    _modify_reg(
        spi, cs, REG_IRQ_MASK_MAIN,
        IRQ_TXE | IRQ_RXS | IRQ_RXE | IRQ_FWL | IRQ_COL,
        0x00,
    )
    _modify_reg(
        spi, cs, REG_IRQ_MASK_ERROR_WUP,
        IRQ_CRC | IRQ_PAR,
        0x00,
    )

    _clear_fifo_and_irqs(spi, cs)


def _field_on(spi, cs, should_cancel=None):
    """Turn on the reader field from a clean state and let the tag power up."""
    # TX/RX must be off while checking for a foreign carrier.
    _modify_reg(
        spi, cs, REG_OP_CONTROL,
        OP_CONTROL_TX_EN | OP_CONTROL_RX_EN,
        0x00,
    )
    _clear_fifo_and_irqs(spi, cs)

    if _read_reg(spi, cs, REG_AUX_DISPLAY) & AUX_DISPLAY_EFD_O:
        raise RuntimeError(
            "nfca_reader: external RF field detected - cannot power up as initiator"
        )

    _modify_reg(spi, cs, REG_OP_CONTROL, OP_CONTROL_TX_EN, OP_CONTROL_TX_EN)
    _modify_reg(spi, cs, REG_OP_CONTROL, OP_CONTROL_RX_EN, OP_CONTROL_RX_EN)

    # Give a small passive sticker enough time to harvest power and initialize.
    if not _sleep_ms_cancelable(FIELD_STARTUP_MS, should_cancel):
        return False

    _clear_fifo_and_irqs(spi, cs)
    return True


def _field_off(spi, cs):
    """Drop TX/RX and remove all pending receive/transmit state."""
    _modify_reg(
        spi, cs, REG_OP_CONTROL,
        OP_CONTROL_TX_EN | OP_CONTROL_RX_EN,
        0x00,
    )
    _clear_fifo_and_irqs(spi, cs)


def _restart_field(spi, cs, should_cancel=None):
    """Power-cycle the tag and rebuild the complete reader configuration."""
    _field_off(spi, cs)
    if not _sleep_ms_cancelable(FIELD_RECOVERY_OFF_MS, should_cancel):
        return False

    # A failed anticollision can leave antcl enabled and AGC disabled; a failed
    # page read can leave FIFO/IRQ and timing state behind.  Reapply the entire
    # reader configuration instead of only toggling TX_EN.
    _configure_nfca_106(spi, cs)
    return _field_on(spi, cs, should_cancel=should_cancel)


def _cleanup_nfca(spi, cs):
    """Fully tear down reader mode and leave the chip in safe idle."""
    # First guarantee the carrier and receiver are off.
    _force_rf_idle(spi, cs)

    # Remove reader framing/timing state so the next NFC operation always
    # starts from its own configuration rather than inheriting this one.
    _write_reg(spi, cs, REG_MODE, 0x00)
    _write_reg(spi, cs, REG_BIT_RATE, 0x00)
    _write_reg(spi, cs, REG_ISO14443A_NFC, 0x00)
    _write_reg(spi, cs, REG_MASK_RX_TIMER, 0x00)
    _write_reg(spi, cs, REG_NO_RESPONSE_TIMER1, 0x00)
    _write_reg(spi, cs, REG_NO_RESPONSE_TIMER2, 0x00)
    _write_reg(spi, cs, REG_NUM_TX_BYTES1, 0x00)
    _write_reg(spi, cs, REG_NUM_TX_BYTES2, 0x00)

    # No NFC operation is active after return, so mask every source and drain
    # any final read-to-clear status.  The oscillator/regulator stay enabled.
    _write_reg(spi, cs, REG_IRQ_MASK_MAIN, 0xFF)
    _write_reg(spi, cs, REG_IRQ_MASK_TIMER_NFC, 0xFF)
    _write_reg(spi, cs, REG_IRQ_MASK_ERROR_WUP, 0xFF)
    _clear_fifo_and_irqs(spi, cs)

    op_control = _read_reg(spi, cs, REG_OP_CONTROL)
    if op_control & (OP_CONTROL_TX_EN | OP_CONTROL_RX_EN):
        # Defensive second clear in case a direct command completed during
        # teardown.  Do not allow the function to return with RF still active.
        _modify_reg(
            spi, cs, REG_OP_CONTROL,
            OP_CONTROL_TX_EN | OP_CONTROL_RX_EN,
            0x00,
        )
        _clear_fifo_and_irqs(spi, cs)

# ---------------------------------------------------------------------------
# Frame-level helpers
# ---------------------------------------------------------------------------


def _transmit_reqa(spi, cs):
    """Send the 7-bit REQA (0x26) via the chip's built-in direct cmd."""
    _send_cmd(spi, cs, CMD_TRANSMIT_REQA)


def _transmit_with_crc(spi, cs, data):
    """FIFO-load `data`, program NUM_TX_BYTES in bits, fire TX_WITH_CRC."""
    _clear_fifo_and_irqs(spi, cs)
    _write_fifo(spi, cs, data)
    total_bits = len(data) * 8
    _write_reg(spi, cs, REG_NUM_TX_BYTES2, total_bits & 0xFF)
    _write_reg(spi, cs, REG_NUM_TX_BYTES1, (total_bits >> 8) & 0xFF)
    _send_cmd(spi, cs, CMD_TRANSMIT_WITH_CRC)


def _wait_txe(spi, cs, timeout_ms=20, should_cancel=None):
    """Wait for TXE while remaining responsive to scan cancellation."""
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    while True:
        if _is_cancelled(should_cancel):
            return False
        irq, _, _ = _read_irq(spi, cs)
        if irq & IRQ_TXE:
            return True
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            return False
        time.sleep_us(500)


def _receive(spi, cs, timeout_ms=10, should_cancel=None):
    """Wait for RXE, or return None on cancellation, error, or timeout."""
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    while True:
        if _is_cancelled(should_cancel):
            return None

        irq, _, err = _read_irq(spi, cs)

        if irq & IRQ_COL:
            log("[nfca] collision during RX", level="warn")
            return None

        if err & (IRQ_CRC | IRQ_PAR):
            log("[nfca] RX error 0x{:02X} ({}{})".format(
                err,
                "CRC " if err & IRQ_CRC else "",
                "PAR" if err & IRQ_PAR else ""),
                level="warn")
            return None

        if irq & IRQ_RXE:
            rx_len = _read_reg(spi, cs, REG_FIFO_RX_STATUS1)
            if rx_len == 0:
                return bytearray()
            return _read_fifo(spi, cs, rx_len)

        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            return None
        time.sleep_us(200)

# ---------------------------------------------------------------------------
# Anti-collision + SELECT (4-, 7-, and 10-byte UID cascades)
# ---------------------------------------------------------------------------

def _anticollision_level(spi, cs, sel, should_cancel=None):
    """Run one ISO14443A cascade level and return (uid_block, sak)."""
    # Enable parity and anti-collision mode; disable AGC for collision detect.
    _modify_reg(spi, cs, REG_ISO14443A_NFC, 0xC1, 0x01)
    _modify_reg(spi, cs, REG_RX_CONF2, 0x10, 0x00)
    _write_reg(spi, cs, REG_MASK_RX_TIMER, 13)
    _write_reg(spi, cs, REG_NO_RESPONSE_TIMER1, 0x10)
    _write_reg(spi, cs, REG_NO_RESPONSE_TIMER2, 0x00)

    _clear_fifo_and_irqs(spi, cs)
    _send_cmd(spi, cs, CMD_CLEAR_SQUELCH)
    _write_fifo(spi, cs, bytes([sel, 0x20]))
    _write_reg(spi, cs, REG_NUM_TX_BYTES2, 16)
    _write_reg(spi, cs, REG_NUM_TX_BYTES1, 0x00)

    # IRQ mask bits are active-high, so write zero to unmask the events used
    # by this polled transaction.  Do not inherit the masks from P2P mode.
    _modify_reg(
        spi,
        cs,
        REG_IRQ_MASK_MAIN,
        IRQ_TXE | IRQ_RXS | IRQ_RXE | IRQ_FWL | IRQ_COL,
        0x00,
    )
    _modify_reg(
        spi, cs, REG_IRQ_MASK_ERROR_WUP,
        IRQ_CRC | IRQ_PAR,
        0x00,
    )
    _send_cmd(spi, cs, CMD_TRANSMIT_WITHOUT_CRC)

    if not _wait_txe(spi, cs, timeout_ms=20, should_cancel=should_cancel):
        log("[nfca] anticoll TX timeout at SEL=0x{:02X}".format(sel),
            level="warn")
        return None, None

    time.sleep_us(500)
    ac = _receive(spi, cs, timeout_ms=30, should_cancel=should_cancel)
    if ac is None or len(ac) < 5:
        fifo_len = _read_reg(spi, cs, REG_FIFO_RX_STATUS1)
        if 1 <= fifo_len <= 10:
            ac = _read_fifo(spi, cs, fifo_len)

    if ac is None or len(ac) < 5:
        log("[nfca] anticoll response short at SEL=0x{:02X}".format(sel),
            level="debug")
        return None, None

    uid_block = bytes(ac[:4])
    bcc = ac[4]
    expected_bcc = uid_block[0] ^ uid_block[1] ^ uid_block[2] ^ uid_block[3]
    if bcc != expected_bcc:
        log(
            "[nfca] BCC mismatch at SEL=0x{:02X}: got=0x{:02X} exp=0x{:02X}"
            .format(sel, bcc, expected_bcc),
            level="warn",
        )
        return None, None

    # Clear anti-collision mode and restore AGC for SELECT.
    _modify_reg(spi, cs, REG_ISO14443A_NFC, 0x01, 0x00)
    _modify_reg(spi, cs, REG_RX_CONF2, 0x10, 0x10)

    select_cmd = bytes([sel, 0x70]) + uid_block + bytes([bcc])
    _transmit_with_crc(spi, cs, select_cmd)
    if not _wait_txe(spi, cs, timeout_ms=20, should_cancel=should_cancel):
        log("[nfca] SELECT TX timeout at SEL=0x{:02X}".format(sel),
            level="warn")
        return None, None

    time.sleep_us(200)
    sak = _receive(spi, cs, timeout_ms=30, should_cancel=should_cancel)
    if sak is None or len(sak) < 1:
        fifo_len = _read_reg(spi, cs, REG_FIFO_RX_STATUS1)
        if 1 <= fifo_len <= 10:
            sak = _read_fifo(spi, cs, fifo_len)

    if sak is None or len(sak) < 1:
        log("[nfca] SELECT: no SAK at SEL=0x{:02X}".format(sel),
            level="debug")
        return None, None

    return uid_block, sak[0]


def _anticollision_select(spi, cs, should_cancel=None):
    """Select a single ISO14443A tag and return its 4, 7, or 10-byte UID."""
    uid = bytearray()

    for sel in (0x93, 0x95, 0x97):
        if _is_cancelled(should_cancel):
            return None
        uid_block, sak = _anticollision_level(
            spi, cs, sel, should_cancel=should_cancel
        )
        if uid_block is None:
            return None

        # 0x88 is the cascade tag. It is not part of the actual UID.
        if uid_block[0] == 0x88:
            uid.extend(uid_block[1:4])
        else:
            uid.extend(uid_block)

        log(
            "[nfca] SEL=0x{:02X} block={} SAK=0x{:02X}".format(
                sel, uid_block.hex(), sak
            ),
            level="debug",
        )

        # SAK bit 2 clear means this was the final cascade level.
        if not (sak & 0x04):
            final_uid = bytes(uid)
            log("[nfca] selected UID={}".format(final_uid.hex()), level="info")
            return final_uid

        # A cascade bit requires another anti-collision level. The first two
        # levels should therefore have supplied the 0x88 cascade tag.
        if uid_block[0] != 0x88 and sel != 0x97:
            log("[nfca] cascade SAK without CT", level="warn")

    log("[nfca] UID cascade did not terminate", level="warn")
    return None


# ---------------------------------------------------------------------------
# NTAG/MIFARE-Ultralight block read
# ---------------------------------------------------------------------------

def _read_block(spi, cs, page, should_cancel=None):
    """Send 0x30<page>, return 16 bytes (4 pages) or None."""
    if _is_cancelled(should_cancel):
        return None
    _transmit_with_crc(spi, cs, bytes([0x30, page]))
    if not _wait_txe(spi, cs, timeout_ms=20, should_cancel=should_cancel):
        return None
    data = _receive(spi, cs, timeout_ms=50, should_cancel=should_cancel)
    if data and len(data) >= 16:
        return bytes(data[:16])
    return None


def _read_all_user_data(spi, cs, should_cancel=None):
    """Read NTAG213 user pages 4..39.  None means retry from REQA."""
    out = bytearray()
    for start in range(4, 40, 4):
        if _is_cancelled(should_cancel):
            return None
        chunk = _read_block(spi, cs, start, should_cancel=should_cancel)
        if chunk is None:
            log("[nfca] read failed at page {}".format(start), level="debug")
            return None
        out.extend(chunk)
        if not _sleep_ms_cancelable(5, should_cancel):
            return None
    return bytes(out)


# ---------------------------------------------------------------------------
# NDEF text-record extraction (best-effort)
# ---------------------------------------------------------------------------

def _extract_ndef_text(data):
    """Scan a raw byte buffer for the best NDEF Text Record and decode it.

    Returns the UTF-8 payload as a str, or None if nothing plausible is
    found.  Mirrors the scoring heuristic from 14443a_cleanup so records
    landing in the middle of a 16-byte block are preferred over those
    straddling a boundary (which are usually corrupted).
    """
    best_text  = None
    best_score = 0

    # Scan for the NDEF Text Record signature D1 01 <len> 54 ...
    for i in range(len(data) - 5):
        if data[i] != 0xD1 or data[i+1] != 0x01 or data[i+3] != 0x54:
            continue
        payload_len   = data[i+2]
        payload_start = i + 4
        if payload_start + payload_len > len(data):
            continue

        payload  = data[payload_start:payload_start + payload_len]
        if len(payload) < 2:
            continue
        lang_len = payload[0] & 0x3F
        if lang_len < 1 or lang_len > 5 or len(payload) <= lang_len + 1:
            continue

        try:
            lang_str = payload[1:1+lang_len].decode("ascii")
            if not (lang_str.isalpha() or lang_str.isalnum()):
                continue
            text = payload[lang_len + 1:].decode("utf-8")
            text = text.rstrip("\x00\xfe")
        except Exception:
            continue

        if len(text) < 2:
            continue
        if not all((32 <= ord(c) < 127) or c in ("\t", "\n", "\r", " ")
                   for c in text):
            continue

        # Prefer records that don't straddle a 16-byte block boundary.
        offset = i % 16
        score  = 100 if 4 <= offset <= 12 else (50 if offset in (3, 13) else 0)
        score += len(text)
        if text and text[-1].isdigit():
            score -= 10

        if score > best_score:
            best_text  = text
            best_score = score

    return best_text


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

# Sleep between successive REQA polls when no card is present.  Small
# enough that a user tapping a card feels instant, large enough that we
# don't hammer the SPI bus + RF field pointlessly.
POLL_INTERVAL_MS = 100

DEFAULT_OVERALL_TIMEOUT_MS = 10_000

# Runtime compatibility marker. nfc_runtime checks this before invoking
# the cancellation-aware reader API.
NFCA_READER_API_VERSION = 3


def run_nfca_reader(
    spi,
    cs,
    overall_timeout_ms=DEFAULT_OVERALL_TIMEOUT_MS,
    should_cancel=None,
):
    """Poll for an NFC-A card and read its NDEF payload.

    Args:
        spi, cs:            already-initialised SPI + chip-select for the
                            ST25R3911B.  Chip must have been through
                            main._bring_chip_up() (osc on, VDD measured,
                            antenna calibrated).
        overall_timeout_ms: give up after this many ms even if no card
                            has been presented.  Default 30 s.

    Returns:
        Result dict:
            {
                "ok":         bool,
                "uid":        bytes | None,
                "text":       str   | None,
                "raw":        bytes,
                "elapsed_ms": int,
                "polls":      int,
            }
        A "successful" read (ok=True) requires that we got a UID AND
        pulled at least one page of user data.  Whether the text field
        is populated depends on whether the card actually stores an
        NDEF Text Record.
    """
    result = {
        "ok":         False,
        "uid":        None,
        "text":       None,
        "raw":        b"",
        "elapsed_ms": 0,
        "polls":      0,
        "canceled":   False,
    }

    log("[nfca] entering READER mode (timeout={} ms)"
        .format(overall_timeout_ms), level="info")

    t_start  = time.ticks_ms()
    deadline = time.ticks_add(t_start, overall_timeout_ms)

    try:
        _configure_nfca_106(spi, cs)
        if not _field_on(spi, cs, should_cancel=should_cancel):
            result["canceled"] = True
            return result

        while True:
            if _is_cancelled(should_cancel):
                result["canceled"] = True
                log("[nfca] canceled", level="info")
                return result

            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                log("[nfca] timeout after {} poll(s)".format(result["polls"]),
                    level="info")
                return result

            result["polls"] += 1

            # REQA poll.  Clear FIFO first so any stray bytes from a
            # previous cycle don't contaminate the ATQA read.
            # REQA starts from clean FIFO/IRQ state.  antcl must be
            # enabled for REQA and anticollision framing.
            _modify_reg(spi, cs, REG_ISO14443A_NFC, 0x01, 0x01)
            _modify_reg(spi, cs, REG_NUM_TX_BYTES2, 0x07, 0x00)
            _clear_fifo_and_irqs(spi, cs)
            _transmit_reqa(spi, cs)
            atqa = _receive(
                spi, cs, timeout_ms=20, should_cancel=should_cancel
            )

            if not atqa or len(atqa) < 2:
                # No card - short sleep and poll again.
                if not _sleep_ms_cancelable(POLL_INTERVAL_MS, should_cancel):
                    result["canceled"] = True
                    return result
                continue

            log("[nfca] ATQA={}  (poll #{})"
                .format(bytes(atqa).hex(), result["polls"]), level="info")

            uid = _anticollision_select(
                spi, cs, should_cancel=should_cancel
            )
            if uid is None:
                if _is_cancelled(should_cancel):
                    result["canceled"] = True
                    return result

                # The tag answered REQA but selection failed.  It may now be in
                # READY/ACTIVE rather than IDLE, so an ordinary REQA retry can
                # appear dead.  Remove power and restart the full activation.
                log("[nfca] selection failed; cycling RF field", level="debug")
                if not _restart_field(spi, cs, should_cancel=should_cancel):
                    result["canceled"] = _is_cancelled(should_cancel)
                    return result
                continue

            result["uid"] = uid
            log("[nfca] UID={} - reading data...".format(uid.hex()),
                level="info")

            raw = _read_all_user_data(
                spi, cs, should_cancel=should_cancel
            )

            if raw is None:
                if _is_cancelled(should_cancel):
                    result["canceled"] = True
                    return result

                # A failed Type-2 READ also leaves the tag partially active.
                # Discard this attempt and restart from a fully depowered tag.
                result["uid"] = None
                result["raw"] = b""
                log("[nfca] page read failed; cycling RF field", level="debug")
                if not _restart_field(spi, cs, should_cancel=should_cancel):
                    result["canceled"] = _is_cancelled(should_cancel)
                    return result
                continue

            result["raw"] = raw

            result["text"] = _extract_ndef_text(raw)
            result["ok"]   = True
            log("[nfca] read OK: uid={}  bytes={}  text={!r}"
                .format(uid.hex(), len(raw), result["text"]), level="info")
            return result

    except RuntimeError as e:
        # _field_on() raises this if there's an external field.  Return
        # cleanly so main.py can just print the result and move on.
        log("[nfca] aborted: {}".format(e), level="warn")
        return result

    finally:
        # Every exit path--success, timeout, cancellation, RF collision, or
        # exception--must leave no carrier, receiver, FIFO data, IRQ state, or
        # reader-mode framing behind for the next P2P/sticker operation.
        try:
            _cleanup_nfca(spi, cs)
            log("[nfca] cleanup complete; RF idle", level="debug")
        except Exception as e:
            log("[nfca] cleanup failed: {!r}".format(e), level="error")
            # Last-resort safety: still try to force TX/RX off even if a
            # register write elsewhere in cleanup failed.
            try:
                _modify_reg(
                    spi, cs, REG_OP_CONTROL,
                    OP_CONTROL_TX_EN | OP_CONTROL_RX_EN,
                    0x00,
                )
                _send_cmd(spi, cs, CMD_CLEAR_FIFO)
                _read_irq(spi, cs)
            except Exception:
                pass
        result["elapsed_ms"] = time.ticks_diff(time.ticks_ms(), t_start)
