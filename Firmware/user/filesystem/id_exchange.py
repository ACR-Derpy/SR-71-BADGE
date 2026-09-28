"""Confirmed Active-P2P trade exchange over the ST25R3911B.

The original protocol stopped after one request/response round trip:

    initiator ---[ID_REQ + initiator payload]---> target
    initiator <--[ID_RES + target payload]------- target

That allowed a half-complete trade: the target could accept the request and
return success after transmitting ID_RES even when the initiator never received
that response.  The confirmed protocol adds an acknowledgment and completion
frame:

    initiator ---[ID_REQ  + initiator payload]---> target
    initiator <--[ID_RES  + target payload]------- target
    initiator ---[ID_ACK  + target payload]------> target
    initiator <--[ID_DONE + initiator payload]---- target
    initiator ---[ID_CONFIRM + initiator payload]-> target
    initiator <--[ID_FINAL + initiator payload]--- target

The echoed payloads bind ACK and DONE to the current pair of badge payloads.
The final confirmation round prevents the target from committing merely
because it transmitted ID_DONE; it must prove the initiator received it.

Every frame is 14 bytes before CRC_A:

    byte 0      magic 0xB0
    byte 1      frame type
    bytes 2..13 12-byte payload

The ST25R3911B appends the two CRC_A bytes in hardware.

Public API remains compatible with the trade layer:

    ex = IDExchange(spi, cs, my_id, verbose=True)
    peer_id = ex.initiate(timeout_ms=700)
    peer_id = ex.respond(timeout_ms=400)

Both methods return the peer payload only after the confirmed handshake
completes, otherwise they return None.
"""

import time
import builtins

from P2P_config import (
    REG_OP_CONTROL, REG_NUM_TX_BYTES1, REG_NUM_TX_BYTES2,
    REG_MODE, REG_AUX, REG_RX_CONF1, REG_RX_CONF2, REG_RX_CONF3, REG_RX_CONF4,
    REG_IRQ_MASK_TIMER_NFC,
    CMD_CLEAR_FIFO, CMD_TRANSMIT_WITH_CRC, CMD_ANALOG_PRESET,
    CMD_CLEAR_SQUELCH, CMD_UNMASK_RECEIVE_DATA, CMD_RESPONSE_RF_COLL,
    OP_CONTROL_TX_EN, OP_CONTROL_RX_EN,
    IRQ_TXE, IRQ_CAT, IRQ_CAC,
    AUX_RX_TOL,
    MODE_NFCIP1_TARGET,
    _write_reg, _read_reg, _modify_reg, _send_cmd,
    _write_fifo, _read_irq,
    configure_nfcip1_initiator,
    log,
)

from P2P_listen_worker import ListenWorker
from nfcip1_decode import crc_a
# rf_diagnostics has been moved to Outdated Code/ - it was a bring-up-only
# debug helper (amplitude / phase / regulator snapshots) and is no longer
# imported here.  The `rf_diag` flag on IDExchange is kept as a no-op so
# any old caller that still passes rf_diag=True won't error out.
# from rf_diagnostics import print_rf_diagnostics


# ---------------------------------------------------------------------------
# Wire-format constants
# ---------------------------------------------------------------------------
MAGIC      = 0xB0
VER_REQ    = 0x01
VER_ACK    = 0x02
VER_CONFIRM = 0x03
VER_RES    = 0x81
VER_DONE   = 0x82
VER_FINAL  = 0x83
ID_LEN     = 12
FRAME_LEN  = 2 + ID_LEN            # header + payload, CRC added by hardware

# Match RFAL's ST25R3911_CA_TIMEOUT.
CA_TIMEOUT_MS = 15

# Turnaround and confirmation tuning.  These values intentionally favor
# reliability over shaving a few hundred milliseconds from the trade UI.
TURNAROUND_GUARD_MS = 10
ACK_WAIT_MS = 950
DONE_WAIT_MS = 260
ACK_RETRY_COUNT = 3
CONFIRM_WAIT_MS = 950
FINAL_WAIT_MS = 280
CONFIRM_RETRY_COUNT = 3
FINAL_GRACE_MS = 850


# ---------------------------------------------------------------------------
# Frame builders / parsers
# ---------------------------------------------------------------------------

def _pad_id(raw):
    b = bytes(raw)
    if len(b) >= ID_LEN:
        return b[:ID_LEN]
    return b + b"\x00" * (ID_LEN - len(b))


def build_id_req(my_id):
    return bytes([MAGIC, VER_REQ]) + _pad_id(my_id)


def build_id_res(my_id):
    return bytes([MAGIC, VER_RES]) + _pad_id(my_id)


def build_id_ack(responder_id):
    """Acknowledge receipt of ID_RES by echoing the responder payload."""
    return bytes([MAGIC, VER_ACK]) + _pad_id(responder_id)


def build_id_done(requester_id):
    """Confirm ID_ACK by echoing the original requester payload."""
    return bytes([MAGIC, VER_DONE]) + _pad_id(requester_id)


def build_id_confirm(requester_id):
    """Confirm that the initiator received ID_DONE."""
    return bytes([MAGIC, VER_CONFIRM]) + _pad_id(requester_id)


def build_id_final(requester_id):
    """Acknowledge ID_CONFIRM so both roles have a terminal receipt."""
    return bytes([MAGIC, VER_FINAL]) + _pad_id(requester_id)


def parse_id_frame(payload):
    """Return ``(kind, payload)`` or ``(None, None)`` for a bad frame."""
    if payload is None or len(payload) < FRAME_LEN:
        return None, None
    if payload[0] != MAGIC:
        return None, None

    frame_payload = bytes(payload[2:2 + ID_LEN])
    version = payload[1]

    if version == VER_REQ:
        return "req", frame_payload
    if version == VER_RES:
        return "res", frame_payload
    if version == VER_ACK:
        return "ack", frame_payload
    if version == VER_DONE:
        return "done", frame_payload
    if version == VER_CONFIRM:
        return "confirm", frame_payload
    if version == VER_FINAL:
        return "final", frame_payload
    return None, None


# ---------------------------------------------------------------------------
# Exchange session
# ---------------------------------------------------------------------------

class IDExchange:
    """Owns the SPI/CS and a ListenWorker; drives one REQ or one RES."""

    def __init__(self, spi, cs, my_id, verbose=False, debug=False,
                 rf_diag=False):
        self.spi = spi
        self.cs  = cs
        self.my_id = _pad_id(my_id)
        self.verbose = verbose
        self.debug = debug
        # If True, grab an on-chip amplitude / phase / regulator snapshot
        # at the one instant we know the field is guaranteed to be on:
        # right after IRQ_TXE fires on our own transmission.  This is the
        # only time in the whole flow when we can trust the readings.
        self.rf_diag = rf_diag
        self.lw = ListenWorker(spi, cs, verbose=False, debug=debug)

    # -- logging helpers ----------------------------------------------------

    def _log(self, msg):
        if self.verbose:
            log("[IDX] " + msg)

    def _dbg(self, msg):
        if self.debug:
            log("[IDX] " + msg)

    def _quiet(self, fn, *a, **kw):
        """Run fn with print() silenced unless debug=True."""
        if self.debug:
            return fn(*a, **kw)
        saved = builtins.print
        try:
            builtins.print = lambda *a, **kw: None
            return fn(*a, **kw)
        finally:
            builtins.print = saved

    # -- low-level primitives (adapted from InitiatorSession/TargetSession) -

    def _field_off(self):
        _modify_reg(self.spi, self.cs, REG_OP_CONTROL, OP_CONTROL_TX_EN, 0x00)

    def _tx_with_field_on(self, payload, tag):
        """Transmit `payload` with our own carrier already on (initiator TX).

        Returns True on I_txe, False on timeout.  Drops TX_EN afterwards so
        the peer can key its response carrier.  Includes the same 3 ms
        post-I_txe hold-off the ATR/DEP path uses.
        """
        spi, cs = self.spi, self.cs
        _send_cmd(spi, cs, CMD_CLEAR_FIFO)
        _write_fifo(spi, cs, payload)
        bits = len(payload) * 8
        _write_reg(spi, cs, REG_NUM_TX_BYTES2, bits & 0xFF)
        _write_reg(spi, cs, REG_NUM_TX_BYTES1, (bits >> 8) & 0xFF)
        _read_irq(spi, cs)

        # RF snapshot BEFORE we start modulating.  configure_nfcip1_initiator
        # has already asserted TX_EN so the carrier is up and stable, but
        # CMD_TRANSMIT_WITH_CRC hasn't started keying the OOK envelope yet.
        # This is the only window where the ~5 ms measurement commands
        # have time to complete against a real, unmodulated carrier.
        # (AUX_DISPLAY.tx_on stays 0 here because that bit tracks the
        # modulator, not the driver - which is exactly what we want.)
        # RF diagnostics moved to Outdated Code/ - snapshot call removed.
        # if self.rf_diag:
        #     print_rf_diagnostics(spi, cs,
        #                          label="initiator carrier pre-TX " + tag)

        self._log("TX {} ({}B): {}".format(tag, len(payload), payload.hex()))
        _send_cmd(spi, cs, CMD_TRANSMIT_WITH_CRC)

        deadline = time.ticks_add(time.ticks_ms(), 50)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            m, _, _ = _read_irq(spi, cs)
            if m & IRQ_TXE:
                # Let the target's demodulator finish the frame before we
                # cut the carrier.  3 ms covers frame tail + CRC check.
                time.sleep_ms(3)
                _modify_reg(spi, cs, REG_OP_CONTROL, OP_CONTROL_TX_EN, 0x00)
                self._dbg("  I_txe (crc {})".format(crc_a(payload).hex()))
                return True
            time.sleep_us(500)
        self._log("  TX TIMEOUT")
        return False

    def _key_own_carrier(self):
        """Fire CMD_RESPONSE_RF_COLL and wait for I_CAT.  Target-side TX prep."""
        spi, cs = self.spi, self.cs
        _modify_reg(spi, cs, REG_IRQ_MASK_TIMER_NFC, IRQ_CAC | IRQ_CAT, 0x00)
        _read_irq(spi, cs)
        _send_cmd(spi, cs, CMD_RESPONSE_RF_COLL)
        deadline = time.ticks_add(time.ticks_ms(), CA_TIMEOUT_MS)
        result = None
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            _, t, _ = _read_irq(spi, cs)
            if t & IRQ_CAC:
                result = "collision"
                break
            if t & IRQ_CAT:
                result = "field_on"
                break
            time.sleep_us(200)
        _modify_reg(spi, cs, REG_IRQ_MASK_TIMER_NFC,
                    IRQ_CAC | IRQ_CAT, IRQ_CAC | IRQ_CAT)
        if result != "field_on":
            self._log("  RFCA: no CAT ({})".format(result or "timeout"))
            return False
        # Settle after CAT so the modulator sees a stable carrier before
        # CMD_TRANSMIT_WITH_CRC drives the OOK envelope, AND so the peer's
        # RX AGC/DC-offset have time to adapt to our carrier before the
        # first modulated bit arrives.  Without enough settle we
        # intermittently see the peer's demod reporting a parity error on
        # the first byte (observed initiator IRQ: MAIN=0x20 ERR=0x80 --
        # RXS fires but no RXE ever comes, framing aborted).
        #
        # RFAL waits its full ST25R3911_CA_TIMEOUT (~10 ms) before TX,
        # which is what makes it robust.  1 ms was too short; 5 ms hits
        # the sweet spot -- long enough for AGC, short enough that we're
        # still well inside a reasonable response window.
        time.sleep_ms(5)
        self._dbg("  RFCA: I_CAT (carrier up)")
        return True

    def _tx_with_own_carrier(self, payload, tag):
        """Target-side: key carrier via RFCA, then transmit."""
        spi, cs = self.spi, self.cs
        _send_cmd(spi, cs, CMD_CLEAR_FIFO)
        _write_fifo(spi, cs, payload)
        bits = len(payload) * 8
        _write_reg(spi, cs, REG_NUM_TX_BYTES2, bits & 0xFF)
        _write_reg(spi, cs, REG_NUM_TX_BYTES1, (bits >> 8) & 0xFF)

        if not self._key_own_carrier():
            _modify_reg(spi, cs, REG_OP_CONTROL, OP_CONTROL_TX_EN, 0x00)
            return False

        # RF snapshot BEFORE modulation starts.  _key_own_carrier() has
        # fired CMD_RESPONSE_RF_COLL, I_CAT confirmed the carrier is up,
        # and the 5 ms settle inside it has already elapsed.  That means
        # right now we have a stable unmodulated carrier - the ideal
        # (and only) window for the ~5 ms amplitude/phase measurement.
        # RF diagnostics moved to Outdated Code/ - snapshot call removed.
        # if self.rf_diag:
        #     print_rf_diagnostics(spi, cs,
        #                          label="target carrier pre-TX " + tag)

        _read_irq(spi, cs)
        self._log("TX {} ({}B): {}".format(tag, len(payload), payload.hex()))
        _send_cmd(spi, cs, CMD_TRANSMIT_WITH_CRC)

        deadline = time.ticks_add(time.ticks_ms(), 50)
        txe = False
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            m, _, _ = _read_irq(spi, cs)
            if m & IRQ_TXE:
                txe = True
                break
            time.sleep_us(500)
        if txe:
            time.sleep_ms(3)
        _modify_reg(spi, cs, REG_OP_CONTROL, OP_CONTROL_TX_EN, 0x00)
        self._dbg("  {}".format("I_txe" if txe else "TX TIMEOUT"))
        return txe

    def _enter_listen_mode(self):
        """Same fast override sequence InitiatorSession uses to prepare for
        the target's active response.  MUST run after our TX has dropped.

        IMPORTANT: clear the FIFO before re-enabling RX.  Otherwise the
        just-transmitted frame remains in the FIFO/receive path and is
        delivered back to us as a spurious ID_REQ RX.  Symptom seen on
        hardware: `[IDX] RX bad frame: b00102441ff701c...` where the
        payload is byte-for-byte identical to what we just TX'd (peer
        never actually responded; we heard ourselves).
        """
        spi, cs = self.spi, self.cs
        _modify_reg(spi, cs, REG_OP_CONTROL, OP_CONTROL_TX_EN, 0x00)
        _send_cmd(spi, cs, CMD_CLEAR_FIFO)
        _write_reg(spi, cs, REG_MODE, MODE_NFCIP1_TARGET)
        _send_cmd(spi, cs, CMD_ANALOG_PRESET)
        time.sleep_ms(2)
        _modify_reg(spi, cs, REG_RX_CONF1, 0x7F, 0x45)
        _modify_reg(spi, cs, REG_RX_CONF3, 0x88, 0x88)
        _modify_reg(spi, cs, REG_AUX,      AUX_RX_TOL, AUX_RX_TOL)
        _modify_reg(spi, cs, REG_RX_CONF4, 0x30, 0x10)
        _modify_reg(spi, cs, REG_RX_CONF3, 0x70, 0x40)
        _write_reg(spi, cs, REG_RX_CONF2, 0x1A)
        _modify_reg(spi, cs, REG_OP_CONTROL, OP_CONTROL_RX_EN, OP_CONTROL_RX_EN)
        # Mixer toggle (errata) + settle + unmask receive
        tmp = _read_reg(spi, cs, REG_RX_CONF1)
        _write_reg(spi, cs, REG_RX_CONF1, tmp | 0x08)
        _write_reg(spi, cs, REG_RX_CONF1, tmp & ~0x08)
        _write_reg(spi, cs, REG_RX_CONF1, tmp | 0x08)
        time.sleep_us(100)
        _send_cmd(spi, cs, CMD_CLEAR_SQUELCH)
        _send_cmd(spi, cs, CMD_UNMASK_RECEIVE_DATA)
        _read_irq(spi, cs)

    def _listen_for_frame(self, timeout_ms):
        """Enter a clean target/listen state and receive one frame."""
        self._enter_listen_mode()
        return self.lw.run(timeout_ms=timeout_ms)

    def _send_after_turnaround(self, payload, tag):
        """Give the peer time to enter listen mode, then transmit."""
        time.sleep_ms(TURNAROUND_GUARD_MS)
        return self._tx_with_own_carrier(payload, tag)

    def _wait_for_ack(
        self, requester_payload, response_payload, response_frame, ack_validator=None
    ):
        """Wait for a matching ACK, re-sending ID_RES on duplicate requests."""
        deadline = time.ticks_add(time.ticks_ms(), ACK_WAIT_MS)

        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            remaining = time.ticks_diff(deadline, time.ticks_ms())
            frame = self._listen_for_frame(remaining)
            if frame is None:
                return None

            kind, payload = parse_id_frame(frame)

            if kind == "ack":
                valid = payload == response_payload
                if ack_validator is not None:
                    try:
                        valid = bool(ack_validator(payload))
                    except Exception:
                        valid = False
                if valid:
                    self._log("RX ID_ACK for payload={}".format(payload.hex()))
                    return payload

            if kind == "req" and payload == requester_payload:
                self._log("RX duplicate ID_REQ; re-sending ID_RES")
                if not self._send_after_turnaround(response_frame, "ID_RES retry"):
                    return None
                continue

            self._dbg("ignoring frame while waiting for ACK: {}".format(frame.hex()))

        return None

    def _wait_for_confirm(self, requester_payload, done_frame, ack_payload):
        """Wait until the initiator proves it received ID_DONE."""
        deadline = time.ticks_add(time.ticks_ms(), CONFIRM_WAIT_MS)

        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            remaining = time.ticks_diff(deadline, time.ticks_ms())
            frame = self._listen_for_frame(remaining)
            if frame is None:
                return False

            kind, payload = parse_id_frame(frame)
            if kind == "confirm" and payload == requester_payload:
                return True

            if kind == "ack" and payload == ack_payload:
                self._log("RX duplicate ID_ACK; re-sending ID_DONE")
                if not self._send_after_turnaround(done_frame, "ID_DONE retry"):
                    return False

        return False

    def _final_grace(self, requester_payload, final_frame):
        """Re-send ID_FINAL when the initiator repeats ID_CONFIRM."""
        deadline = time.ticks_add(time.ticks_ms(), FINAL_GRACE_MS)

        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            remaining = time.ticks_diff(deadline, time.ticks_ms())
            frame = self._listen_for_frame(remaining)
            if frame is None:
                return

            kind, payload = parse_id_frame(frame)
            if kind == "confirm" and payload == requester_payload:
                if not self._send_after_turnaround(final_frame, "ID_FINAL retry"):
                    return

    # -- public flows -------------------------------------------------------

    def initiate(self, timeout_ms=500, ack_builder=None):
        """Run the initiator side of REQ/RES/ACK/DONE.

        Returns the target payload only after ID_DONE and ID_FINAL are received.
        """
        self._quiet(configure_nfcip1_initiator, self.spi, self.cs)
        time.sleep_ms(2)

        request_frame = build_id_req(self.my_id)
        if not self._tx_with_field_on(request_frame, "ID_REQ"):
            self._field_off()
            return None

        frame = self._listen_for_frame(timeout_ms)
        self._field_off()

        if frame is None:
            self._log("RX ID_RES timeout after {} ms".format(timeout_ms))
            return None

        kind, peer_payload = parse_id_frame(frame)
        if kind != "res":
            self._log("RX bad frame while waiting for ID_RES: {}".format(frame.hex()))
            return None

        self._log(
            "RX ID_RES ({}B) peer_payload={}".format(
                len(frame), peer_payload.hex()
            )
        )

        ack_payload = peer_payload
        if ack_builder is not None:
            try:
                ack_payload = bytes(ack_builder(peer_payload))
            except Exception as exc:
                self._log("ID_ACK payload builder failed: {}".format(exc))
                return None
            if len(ack_payload) != ID_LEN:
                self._log("ID_ACK payload builder returned wrong length")
                return None
        ack_frame = build_id_ack(ack_payload)

        for attempt in range(ACK_RETRY_COUNT):
            tag = "ID_ACK" if attempt == 0 else "ID_ACK retry {}".format(attempt)

            if not self._send_after_turnaround(ack_frame, tag):
                self._dbg("ACK transmit failed on attempt {}".format(attempt + 1))
                continue

            done = self._listen_for_frame(DONE_WAIT_MS)
            self._field_off()

            if done is None:
                self._log(
                    "RX ID_DONE timeout; retrying ACK ({}/{})".format(
                        attempt + 1, ACK_RETRY_COUNT
                    )
                )
                continue

            done_kind, done_payload = parse_id_frame(done)

            if done_kind == "done" and done_payload == self.my_id:
                confirm_frame = build_id_confirm(self.my_id)

                for confirm_attempt in range(CONFIRM_RETRY_COUNT):
                    tag = (
                        "ID_CONFIRM"
                        if confirm_attempt == 0
                        else "ID_CONFIRM retry {}".format(confirm_attempt)
                    )
                    if not self._send_after_turnaround(confirm_frame, tag):
                        continue

                    final = self._listen_for_frame(FINAL_WAIT_MS)
                    self._field_off()
                    if final is None:
                        continue

                    final_kind, final_payload = parse_id_frame(final)
                    if final_kind == "final" and final_payload == self.my_id:
                        self._log("RX ID_FINAL; exchange confirmed")
                        return peer_payload

                    if final_kind == "done" and final_payload == self.my_id:
                        continue

                self._log("ID_DONE received but ID_FINAL was not confirmed")
                return None

            if done_kind == "res" and done_payload == peer_payload:
                # The target re-sent its response after seeing a duplicate
                # request.  Sending the same ACK again is the correct action.
                self._log("RX duplicate ID_RES while waiting for ID_DONE")
                continue

            self._log("RX bad completion frame: {}".format(done.hex()))

        self._log("ID_ACK sent but ID_DONE was not confirmed")
        return None

    def respond(
        self,
        timeout_ms=200,
        response_builder=None,
        ack_validator=None,
        return_ack_payload=False,
    ):
        """Run the target side of REQ/RES/ACK/DONE.

        Returns the requester payload only after receiving ID_ACK and
        ID_CONFIRM, then transmitting ID_FINAL and serving its retry grace.
        """
        frame = self.lw.run(timeout_ms=timeout_ms)
        if frame is None:
            return None

        kind, requester_payload = parse_id_frame(frame)
        if kind != "req":
            self._dbg("ignoring non-ID_REQ frame: {}".format(frame.hex()))
            return None

        self._log(
            "RX ID_REQ ({}B) requester_payload={}".format(
                len(frame), requester_payload.hex()
            )
        )

        response_payload = self.my_id
        if response_builder is not None:
            try:
                response_payload = bytes(response_builder(requester_payload))
            except Exception as exc:
                self._log("ID_RES payload builder failed: {}".format(exc))
                return None
            if len(response_payload) != ID_LEN:
                self._log("ID_RES payload builder returned wrong length")
                return None
        response_frame = build_id_res(response_payload)
        if not self._send_after_turnaround(response_frame, "ID_RES"):
            self._log("ID_RES transmit failed")
            return None

        ack_payload = self._wait_for_ack(
            requester_payload,
            response_payload,
            response_frame,
            ack_validator=ack_validator,
        )
        if ack_payload is None:
            self._log("ID_ACK was not received; exchange not committed")
            return None

        done_frame = build_id_done(requester_payload)
        if not self._send_after_turnaround(done_frame, "ID_DONE"):
            # One immediate retry is cheap and avoids treating a transient RFCA
            # collision as a failed confirmed exchange.
            time.sleep_ms(TURNAROUND_GUARD_MS)
            if not self._tx_with_own_carrier(done_frame, "ID_DONE retry"):
                self._log("ID_DONE transmit failed")
                return None

        if not self._wait_for_confirm(requester_payload, done_frame, ack_payload):
            self._log("ID_CONFIRM was not received; exchange not committed")
            return None

        final_frame = build_id_final(requester_payload)
        if not self._send_after_turnaround(final_frame, "ID_FINAL"):
            time.sleep_ms(TURNAROUND_GUARD_MS)
            if not self._tx_with_own_carrier(final_frame, "ID_FINAL retry"):
                self._log("ID_FINAL transmit failed")
                return None

        self._final_grace(requester_payload, final_frame)
        self._log("exchange confirmed")
        if return_ack_payload:
            return requester_payload, ack_payload
        return requester_payload
