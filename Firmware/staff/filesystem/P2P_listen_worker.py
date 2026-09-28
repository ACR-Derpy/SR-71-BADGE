"""
RFAL-style Listen Mode worker for the ST25R3911B in Active P2P target mode.

This is a Python port of the state machine in
resources/STSW-ST25RFAL001/source/st25r3911/rfal_rfst25r3911.c
- rfalRunListenModeWorker  (POWER_OFF / IDLE state cases)
- rfalListenSetState       (POWER_OFF -> IDLE transition actions)

Prerequisites (already done in P2P_config.configure_nfcip1_target):
- MODE = 0x89  (targ | om=NFCIP1_NORMAL | nfc_ar) - direct 106 kbps mode,
              skipping bit-rate detection since both peers are fixed at 106 kbps
- BIT_RATE = 0x00  (106 kbps)

- ISO14443A_NFC: nfc_f0=0, no_tx_par=0, no_rx_par=0
- AUX.en_fd = 1, AUX.crc_2_fifo = 1
- OP_CONTROL.en = 1, OP_CONTROL.rx_en = 1
- IRQ masks unmasked for NFCT, EON, EOF, RXE, CRC, PAR, ERR1, ERR2
- CMD_ANALOG_PRESET has been applied (RX_CONF1..4 = AP2P listen values)

Usage in target main loop:
    from P2P_listen_worker import ListenWorker
    lw = ListenWorker(spi, cs)
    frame = lw.run(timeout_ms=5000)   # returns raw NFC-A payload bytes or None
"""

import time
from P2P_config import (
    REG_MODE, REG_OP_CONTROL, REG_AUX, REG_AUX_DISPLAY,
    REG_RX_CONF1, REG_ISO14443A_NFC, REG_FIFO_RX_STATUS1,
    CMD_CLEAR_FIFO, CMD_CLEAR_SQUELCH, CMD_UNMASK_RECEIVE_DATA,
    OP_CONTROL_TX_EN,
    AUX_DISPLAY_EFD_O,
    IRQ_RXE, IRQ_NFCT, IRQ_EON, IRQ_EOF,
    IRQ_CRC, IRQ_PAR, IRQ_ERR1, IRQ_ERR2,
    _read_reg, _write_reg, _modify_reg, _send_cmd,
    _read_fifo, _read_irq,
)


ST_POWER_OFF = 0
ST_IDLE      = 1


class ListenWorker:
    def __init__(self, spi, cs, verbose=False, debug=False):
        """
        verbose : print RX events (frame arrival + errors) - default on
        debug   : print every IRQ + every state transition - default OFF
        """
        self.spi = spi
        self.cs = cs
        self.verbose = verbose
        self.debug = debug
        self.state = ST_POWER_OFF

    def _log(self, msg):
        if self.verbose:
            print(msg)

    def _dbg(self, msg):
        if self.debug:
            print(msg)

    # -------- Transition actions --------------------------------------------

    def _enter_idle(self):
        """
        Actions from rfal_rfst25r3911.c:3551-3574 on POWER_OFF -> IDLE.
        The target has just seen EON (external field on) and is preparing to
        actually decode the incoming preamble/frame.
        """
        spi, cs = self.spi, self.cs

        # nfc_ar may have triggered RF Collision Avoidance - disable, clear FIFO, re-enable
        _modify_reg(spi, cs, REG_MODE, 0x01, 0x00)          # clear nfc_ar
        _send_cmd(spi, cs, CMD_CLEAR_FIFO)
        _modify_reg(spi, cs, REG_MODE, 0x01, 0x01)          # set nfc_ar

        # Ensure our own TX field is off (auto-RFCA may have turned it on)
        _modify_reg(spi, cs, REG_OP_CONTROL, OP_CONTROL_TX_EN, 0x00)

        # Load 2nd/3rd stage gain from registers into receiver
        _send_cmd(spi, cs, CMD_CLEAR_SQUELCH)

        # ST25R3911 Errata #1.4: mixer toggle (set / clear / set) on amd_sel
        tmp = _read_reg(spi, cs, REG_RX_CONF1)
        _write_reg(spi, cs, REG_RX_CONF1, tmp | 0x08)       # set amd_sel
        _write_reg(spi, cs, REG_RX_CONF1, tmp & ~0x08)      # clear amd_sel
        _write_reg(spi, cs, REG_RX_CONF1, tmp | 0x08)       # set amd_sel again
        # Small settle after mixer toggle: RFAL waits a few tens of us here
        # before unmasking the receiver.  Without this, the demodulator
        # occasionally misses the first preamble bit and produces either no
        # RXS at all or an RXE with CRC error.  100 us is safe and cheap.
        time.sleep_us(100)

        # Re-enable the receiver
        _send_cmd(spi, cs, CMD_UNMASK_RECEIVE_DATA)

        self.state = ST_IDLE
        self._dbg("  [LM] POWER_OFF -> IDLE  (mixer toggled, receiver unmasked)")

    def _enter_power_off(self):
        """Actions from rfal_rfst25r3911.c:3479-3535 on entry to POWER_OFF.

        Since we are locked at 106 kbps (om = NFCIP1_NORMAL, MODE = 0x89),
        we do NOT drop back to bit-rate-detection mode (om = 0). The chip
        stays in NFCIP-1 normal mode and just waits for the next EON.
        """
        spi, cs = self.spi, self.cs
        _modify_reg(spi, cs, REG_MODE, 0x01, 0x00)          # clear nfc_ar
        _send_cmd(spi, cs, CMD_CLEAR_FIFO)
        _modify_reg(spi, cs, REG_OP_CONTROL, OP_CONTROL_TX_EN, 0x00)
        _modify_reg(spi, cs, REG_ISO14443A_NFC, 0x20, 0x00) # ensure nfc_f0 = 0
        _modify_reg(spi, cs, REG_MODE, 0x01, 0x01)          # re-set nfc_ar
        # Clear any latched IRQs so we get a clean read on the next EON edge.
        # (Earlier experiment kept them latched, but that caused the receiver
        # to jump to IDLE on a *stale* EON from a previous session and start
        # the mixer-toggle settle *before* the peer had actually begun its
        # transmission -- the FIFO then only latched the final few bytes of
        # the response, producing a CRC-error RXE with a truncated payload
        # (e.g. fifo_len=6 RAW="41434b2058cf" -- the tail of a 21-byte
        # ATR_RES).  Clearing here is the right behaviour.)
        _read_irq(spi, cs)
        self.state = ST_POWER_OFF
        self._dbg("  [LM] -> POWER_OFF  (waiting for next EON)")


    # -------- Main worker ---------------------------------------------------

    def run(self, timeout_ms=5000):
        """
        Run the listen-mode state machine until:
          - a valid frame is received (returns the raw NFC-A payload bytes,
            with the 2-byte CRC_A stripped), OR
          - the timeout expires (returns None), OR
          - an unrecoverable error occurs (returns None).

        The RXE payload is what would go to the upper layer in RFAL. In the
        AP2P at 106 kbps case there is no LEN-byte wrapper (nfc_f0 = 0),
        so callers get raw application bytes.
        """
        spi, cs = self.spi, self.cs
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)

        # Always start from POWER_OFF
        self._enter_power_off()

        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            irq_main, irq_timer, irq_err = _read_irq(spi, cs)

            if irq_main or irq_timer or irq_err:
                self._dbg(
                    "  [LM] IRQ  MAIN=0x{:02X} TIMER=0x{:02X} ERR=0x{:02X}".format(
                        irq_main, irq_timer, irq_err))

            if self.state == ST_POWER_OFF:
                if irq_timer & IRQ_EON:
                    self._enter_idle()
                    continue

            elif self.state == ST_IDLE:
                # NFCT is informational only in fixed-rate mode - we're already
                # in NFCIP1_NORMAL (om=1), so no auto-switch is needed.
                if irq_timer & IRQ_NFCT:
                    self._dbg("  [LM] NFCT observed (informational)")

                # End of reception - read the FIFO.
                # IMPORTANT: this must be checked BEFORE the EOF handler.
                # In Active P2P the peer drops its carrier immediately after
                # transmitting, so we typically see RXE and EOF in the SAME
                # IRQ read (TIMER=0x08 EOF + MAIN=0x10 RXE).  If we handled
                # EOF first, we'd go back to POWER_OFF and never drain the
                # FIFO -- causing a spurious "timeout" even though the frame
                # was successfully demodulated.  Diagnosed from an IRQ trace
                # showing "MAIN=0x12 TIMER=0x0A" right before a false timeout.
                if irq_main & IRQ_RXE:
                    # If a CRC / parity / framing error accompanies this RXE,
                    # the FIFO contents are corrupt -- discard the frame and
                    # re-arm the receiver instead of returning garbage to the
                    # upper layer.  Diagnosed from an IRQ trace showing
                    # "MAIN=0x13 TIMER=0x0A ERR=0x80" followed by a garbled
                    # 14-byte frame that was NOT a valid ATR_RES.
                    if irq_err & (IRQ_CRC | IRQ_PAR | IRQ_ERR1 | IRQ_ERR2):
                        fifo_len = _read_reg(spi, cs, REG_FIFO_RX_STATUS1)
                        self._log("  [LM] RXE with error (ERR=0x{:02X}, "
                                  "fifo_len={}) - discarding & re-arming"
                                  .format(irq_err, fifo_len))
                        _send_cmd(spi, cs, CMD_CLEAR_FIFO)
                        _modify_reg(spi, cs, REG_MODE, 0x01, 0x00)   # clear nfc_ar
                        _send_cmd(spi, cs, CMD_UNMASK_RECEIVE_DATA)
                        _modify_reg(spi, cs, REG_MODE, 0x01, 0x01)   # set nfc_ar
                        _modify_reg(spi, cs, REG_OP_CONTROL,
                                    OP_CONTROL_TX_EN, 0x00)
                        # Field probably also went down; return to POWER_OFF
                        # so we cleanly wait for the next EON edge.
                        self._enter_power_off()
                        continue

                    fifo_len = _read_reg(spi, cs, REG_FIFO_RX_STATUS1)
                    if fifo_len == 0:
                        # RXE without data -- fall through to EOF handling
                        # below so we correctly return to POWER_OFF.
                        pass
                    else:
                        data = _read_fifo(spi, cs, fifo_len)
                        self._dbg("  [LM] RXE fifo_len={} RAW={}"
                                  .format(fifo_len, bytes(data).hex()))
                        if len(data) < 2:
                            return None
                        # CRC_A appended to FIFO because AUX.crc_2_fifo = 1
                        return bytes(data[:-2])

                # RX errors without RXE (framing gave up before end-of-frame).
                # Clear FIFO, re-unmask, stay in IDLE.
                if irq_err & (IRQ_CRC | IRQ_PAR | IRQ_ERR1 | IRQ_ERR2):
                    self._log("  [LM] RX error (IRQ_ERR=0x{:02X}) - re-arming"
                              .format(irq_err))
                    _modify_reg(spi, cs, REG_MODE, 0x01, 0x00)   # clear nfc_ar
                    _send_cmd(spi, cs, CMD_CLEAR_FIFO)
                    _send_cmd(spi, cs, CMD_UNMASK_RECEIVE_DATA)
                    _modify_reg(spi, cs, REG_MODE, 0x01, 0x01)   # set nfc_ar
                    _modify_reg(spi, cs, REG_OP_CONTROL, OP_CONTROL_TX_EN, 0x00)
                    continue

                # Field lost - go back to POWER_OFF and keep waiting.
                # (Handled AFTER the RXE check above so we don't drop the
                # last frame's data when the peer's carrier goes down.)
                if irq_timer & IRQ_EOF:
                    self._enter_power_off()
                    continue

            time.sleep_ms(2)

        self._dbg("  [LM] timeout after {} ms".format(timeout_ms))
        return None
