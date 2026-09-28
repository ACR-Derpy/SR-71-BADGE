"""ST25R3911B AP2P configuration functions.

Register/bit/command constants and the low-level SPI helpers live in
``P2P_regs`` and are re-exported from here so existing
``from P2P_config import ...`` sites keep working unchanged.
"""

from machine import SPI, Pin
import time

# Re-export every symbol from P2P_regs so consumers can keep importing
# from P2P_config transparently.
from P2P_regs import *  # noqa: F401,F403
from P2P_regs import (  # explicit for tooling that ignores star-imports
    _read_reg, _write_reg, _modify_reg, _send_cmd,
    _write_fifo, _read_fifo, _read_irq,
    log as _real_log,
    log,             # keep the plain name too for external re-imports
    set_log_sink,    # re-export for callers that only import from P2P_config
    set_log_level,
)


# ---------------------------------------------------------------------------
# Bulk-log-level helpers.
#
# The register-dump lines in configure_nfcip1_target / _initiator are only
# useful during hardware bring-up.  In normal operation the interesting
# events happen at a *much* higher level ("TARGET got REQ, INITIATOR got
# no RES"), so we route the per-register chatter through _dbg() at level
# "debug" - suppressed by default via P2P_regs._log_threshold.  Callers
# who want the raw dumps back can call set_log_level("debug") once at
# boot (see main.LOG_LEVEL).
#
# _info() and _warn() are just tiny wrappers so the two configure funcs
# below can promote a small number of milestone lines and a handful of
# WARNING/ERROR lines without every log() call carrying an explicit
# level= argument.
# ---------------------------------------------------------------------------
def _dbg(msg):
    _real_log(msg, "debug")

def _info(msg):
    _real_log(msg, "info")

def _warn(msg):
    _real_log(msg, "warn")

def _err(msg):
    _real_log(msg, "error")



# ---------------------------------------------------------------------------
# Common initialization (shared by both target and initiator modes)
# ---------------------------------------------------------------------------

def reset(spi: SPI, cs: Pin) -> None:
    """Issue CMD_SET_DEFAULT, restoring all registers to power-up state."""
    _send_cmd(spi, cs, CMD_SET_DEFAULT)
    time.sleep_ms(2)


def configure_io(spi: SPI, cs: Pin) -> None:
    """
    Set initial IO register state:
      - OP_CONTROL = 0x00  : all subsystems off
      - IO_CONF1   = 0x08  : osc output pin enabled, HF/LF clocks off
      - IO_CONF2   = 0x98  : sup3V=1 (3.3V supply), MISO pull-downs active
    """
    _write_reg(spi, cs, REG_OP_CONTROL, 0x00)
    _write_reg(spi, cs, REG_IO_CONF1,   0x08)
    _write_reg(spi, cs, REG_IO_CONF2,   0x98)  # Critical: sup3V=1 for 3.3V operation


def check_chip_id(spi: SPI, cs: Pin) -> int:
    """
    Read REG_IC_IDENTITY (0x3F).
    ST25R3911B v2 silicon returns 0x09 or 0x0D.
    Raises RuntimeError on mismatch.
    """
    chip_id = _read_reg(spi, cs, REG_IC_IDENTITY)
    if (chip_id & 0xF8) != 0x08:
        raise RuntimeError(f"Unexpected chip ID: 0x{chip_id:02X} (expected 0x09 or 0x0D)")
    return chip_id


def osc_on(spi: SPI, cs: Pin, timeout_ms: int = 50) -> None:
    """
    Enable oscillator and regulator (OP_CONTROL.en bit7), then poll
    REG_AUX_DISPLAY.osc_ok (bit4) until stable.
    Raises RuntimeError on timeout.
    """
    # Clear any stale interrupts
    _read_irq(spi, cs)

    # Set OP_CONTROL.en
    _modify_reg(spi, cs, REG_OP_CONTROL, OP_CONTROL_EN, OP_CONTROL_EN)

    # Poll osc_ok (do NOT read IRQ_MAIN in loop - it's read-clear!)
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    while True:
        if _read_reg(spi, cs, REG_AUX_DISPLAY) & AUX_DISPLAY_OSC_OK:
            log("Oscillator stable", "debug")
            return

        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise RuntimeError("Oscillator failed to stabilise within timeout")
        time.sleep_ms(2)


def configure_supply(spi: SPI, cs: Pin) -> int:
    """
    Measure VDD with CMD_MEASURE_VDD and set/clear REG_IO_CONF2.sup3V (bit7).
    Returns measured voltage in mV (approximate).
    
    CRITICAL: For 3.3V operation (RP2040/RP2350), sup3V MUST be set to 1.
    """
    _send_cmd(spi, cs, CMD_MEASURE_VDD)
    time.sleep_ms(2)
    adc = _read_reg(spi, cs, REG_AD_RESULT)

    # Rough linear mapping: full scale 0xFF ≈ 6000 mV
    vdd_mv = adc * 23
    
    log(f"VDD measurement: ADC=0x{adc:02X}, calculated={vdd_mv}mV", "debug")

    # For 3.3V operation, SET sup3V (bit 7 = 1)
    # For 5V operation, CLEAR sup3V (bit 7 = 0)
    if vdd_mv < 4000:  # Anything below 4V is 3.3V operation
        log(f"  Setting sup3V=1 for 3.3V operation", "debug")
        _modify_reg(spi, cs, REG_IO_CONF2, 0x80, 0x80)   # set sup3V
    else:
        log(f"  Clearing sup3V=0 for 5V operation", "debug")
        _modify_reg(spi, cs, REG_IO_CONF2, 0x80, 0x00)   # clear sup3V

    # Verify it was set
    io_conf2 = _read_reg(spi, cs, REG_IO_CONF2)
    log(f"  IO_CONF2 after configure_supply: 0x{io_conf2:02X} (sup3V={bool(io_conf2&0x80)})", "debug")


    return vdd_mv


def configure_fifo_and_aux(spi: SPI, cs: Pin) -> None:
    """
    - FIFO watermarks: TX low-level at 32 bytes, RX level at 64 bytes
      (fifo_lt=0, fifo_lr=0 in IO_CONF1 bits[5:4])
    - AUX: enable CRC-to-FIFO (bit6) and external field detector (bit4)
    """
    # IO_CONF1 bits 5:4 = 00 → fifo_lt=32bytes, fifo_lr=64bytes
    _modify_reg(spi, cs, REG_IO_CONF1, 0x30, 0x00)

    # AUX: set crc_2_fifo (0x40) and en_fd (0x10)
    _modify_reg(spi, cs, REG_AUX, AUX_CRC2FIFO | AUX_EN_FD,
                                  AUX_CRC2FIFO | AUX_EN_FD)


# Module-level cache of the fresh antenna-calibration result.
# CMD_ANALOG_PRESET (issued later during target/initiator config) clobbers
# REG_ANT_CAL_RESULT, so we snapshot it here immediately after the D8
# command completes and expose it to rf_diagnostics.
LAST_ANT_CAL_RESULT = None   # raw byte from REG_ANT_CAL_RESULT (0x23)


def calibrate(spi: SPI, cs: Pin) -> dict:
    """
    1. Adjust regulators (CMD_ADJUST_REGULATORS).
    2. Calibrate antenna twice — ST25R3911 errata #1.5 requires two runs.
    3. Adjust regulators again with calibrated antenna.

    After the 2nd calibration we snapshot REG_ANT_CAL_RESULT into the
    module-level LAST_ANT_CAL_RESULT so rf_diagnostics can display the
    real tri_val / tri_err even after CMD_ANALOG_PRESET has reloaded
    the register with 0x00.
    """
    global LAST_ANT_CAL_RESULT

    # Pulse reg_s to reset regulator logic
    _modify_reg(spi, cs, REG_REGULATOR_CONTROL, 0x04, 0x04)
    _modify_reg(spi, cs, REG_REGULATOR_CONTROL, 0x04, 0x00)

    _send_cmd(spi, cs, CMD_ADJUST_REGULATORS)
    time.sleep_ms(6)

    # Calibrate antenna (must run twice per errata #1.5)
    _send_cmd(spi, cs, CMD_CALIBRATE_ANTENNA)
    time.sleep_ms(10)
    _send_cmd(spi, cs, CMD_CALIBRATE_ANTENNA)
    time.sleep_ms(10)

    # Snapshot the fresh calibration result BEFORE any CMD_ANALOG_PRESET
    # clobbers it.  Layout: [7:4]=tri_val, bit3=tri_err.
    LAST_ANT_CAL_RESULT = _read_reg(spi, cs, REG_ANT_CAL_RESULT)
    _tri_val = (LAST_ANT_CAL_RESULT >> 4) & 0x0F
    _tri_err = bool(LAST_ANT_CAL_RESULT & 0x08)
    # Antenna cal result stays at 'info' - it's ONE line per boot and the
    # tri_val/tri_err is genuinely useful for spotting hardware issues.
    log(f"Antenna calibration: ANT_CAL_RES=0x{LAST_ANT_CAL_RESULT:02X} "
          f"(tri_val={_tri_val:X}/F, tri_err={int(_tri_err)})")


    # Final regulator adjustment with antenna calibrated
    _send_cmd(spi, cs, CMD_ADJUST_REGULATORS)
    time.sleep_ms(6)

    return {
        "ant_cal_result": LAST_ANT_CAL_RESULT,
        "tri_val": _tri_val,
        "tri_err": _tri_err,
        "ok": (not _tri_err) and _tri_val not in (0x0, 0xF),
    }


def configure_analog_chip_init(spi: SPI, cs: Pin) -> None:
    """
    Apply the default analog settings from rfal_analogConfigTbl.h
    RFAL_ANALOG_CONFIG_TECH_CHIP | RFAL_ANALOG_CONFIG_CHIP_INIT block.
    """
    _modify_reg(spi, cs, REG_OP_CONTROL,           0x30, 0x10)  # default AM
    _modify_reg(spi, cs, REG_IO_CONF1,             0x06, 0x06)  # HF clk off
    _modify_reg(spi, cs, REG_IO_CONF1,             0x07, 0x07)  # LF clk off
    _modify_reg(spi, cs, REG_IO_CONF2,             0x18, 0x18)  # pull-downs
    _modify_reg(spi, cs, REG_RX_CONF4,             0x0F, 0x01)  # PM digitizer window
    _modify_reg(spi, cs, REG_ANT_CAL_TARGET,       0xFF, 0x80)  # 90° target
    _modify_reg(spi, cs, REG_ANT_CAL_CONTROL,      0xF8, 0x00)  # auto trim
    _modify_reg(spi, cs, REG_AM_MOD_DEPTH_CONTROL, 0x40, 0x40)  # fixed AM (am_s)
    _modify_reg(spi, cs, REG_FIELD_THRESHOLD,      0x70, 0x00)  # trg = 75 mV
    _modify_reg(spi, cs, REG_FIELD_THRESHOLD,      0x0F, 0x00)  # rfe = 75 mV


# ---------------------------------------------------------------------------
# NFCIP-1 Target Mode Configuration
# ---------------------------------------------------------------------------

def configure_nfcip1_target(spi: SPI, cs: Pin) -> dict:
    """
    Configure ST25R3911B for NFCIP-1 active target mode.
    
    Based on RFAL rfalSetMode(RFAL_MODE_LISTEN_ACTIVE_P2P) from
    rfal_rfst25r3911.c lines 864-879.
    
    Key steps:
    1. Set MODE register to 0x89 (targ=1, om=NFCIP1, nfc_ar=1)
    2. Configure GPT to turn off field after TX
    3. Enable external field detector
    4. Apply analog preset
    5. Set RFO drive levels
    6. Enable receiver (but NOT transmitter - target waits for initiator field)
    """
    # Shadow the imported log() with a debug-defaulting version.  Every
    # register-dump line in this function is diagnostic-only noise during
    # normal operation, so it lives at level "debug".  Milestone lines
    # ("configured successfully!") go through _info(), and the two
    # WARNING/ERROR paths use _warn()/_err() so they still surface even
    # when the global log threshold is set to "info" (the default).
    def log(msg, level="debug"):
        _real_log(msg, level)

    _info("Configuring NFCIP-1 TARGET mode...")

    # Step 0: CRITICAL - Check and preserve sup3V before analog preset

    io_conf2_before = _read_reg(spi, cs, REG_IO_CONF2)
    log(f"  IO_CONF2 at start: 0x{io_conf2_before:02X} (sup3V={bool(io_conf2_before&0x80)})")
    
    # Step 1: Set MODE register directly to NFCIP-1 normal mode (om=1).
    # Since both peers use a fixed bit rate of 106 kbps, we bypass the
    # chip's bit-rate-detection state (om=0) that requires NFCT to fire.
    # MODE = 0x89 = targ_targ(0x80) | om_nfcip1_normal(0x08) | nfc_ar(0x01)
    _write_reg(spi, cs, REG_MODE, MODE_NFCIP1_TARGET)
    mode_rb = _read_reg(spi, cs, REG_MODE)
    log(f"  MODE register: 0x{mode_rb:02X} (expect 0x89 - NFCIP-1 normal, target)")

    
    # Step 2: Set BIT_RATE to 106 kbps per RFAL Errata #1.3 workaround.
    # In bit-rate detection mode the chip auto-detects the rate at NFCT IRQ,
    # but the register itself MUST be 106 kbps to get correct parity handling.
    # (rfal_rfst25r3911.c:3525)
    _write_reg(spi, cs, REG_BIT_RATE, 0x00)
    bit_rate_rb = _read_reg(spi, cs, REG_BIT_RATE)
    log(f"  BIT_RATE: 0x{bit_rate_rb:02X} = 106 kbps (Errata #1.3 - detector will lock to actual rate)")

    # Step 2b: CRITICAL - CLEAR nfc_f0, no_tx_par, no_rx_par per RFAL.
    # For Active P2P at 106 kbps the framer uses standard NFC-A (SoF + parity + CRC_A),
    # NOT the NFC-F LEN-prefixed transport format. Setting nfc_f0=1 was wrong.
    # (rfal_rfst25r3911.c:3237: ClrRegisterBits(no_tx_par | no_rx_par | nfc_f0))
    _modify_reg(spi, cs, REG_ISO14443A_NFC, 0x30, 0x00)  # clear no_tx_par(0x10) + nfc_f0(0x20)
    _modify_reg(spi, cs, REG_ISO14443A_NFC, 0x40, 0x00)  # clear no_rx_par(0x40)
    nfc_reg = _read_reg(spi, cs, REG_ISO14443A_NFC)
    log(f"  ISO14443A_NFC: 0x{nfc_reg:02X} (nfc_f0={bool(nfc_reg&0x20)} - must be 0 for AP2P)")
    
    # Step 3: Configure GPT to start after end of TX
    # GPT is used to timeout field switching off after transmission
    # RFAL uses: RFAL_AP2P_FIELDOFF_TCMDOFF ≈ 100-200 µs
    # GPT step = 8/fc ≈ 0.59 µs, so 0x00A9 ≈ 100 µs
    _write_reg(spi, cs, REG_GPT1, 0x00)
    _write_reg(spi, cs, REG_GPT2, 0xA9)
    
    # Set GPT to trigger on end of TX NFC (gptc_etx_nfc)
    _modify_reg(spi, cs, REG_GPT_CONTROL, 0xE0, GPT_CONTROL_GPTC_ETX)
    
    # Step 4: MRT in bit-rate detection mode filters incoming frames during MRT
    # after EON, in 512/fc steps. RFAL_LM_GT ≈ 5 ms → ~ 0x35.
    # (rfal_rfst25r3911.c:3234)
    _write_reg(spi, cs, REG_MASK_RX_TIMER, 0x35)
    
    # No Response Timer: step = 4096/fc when nrt_step=1
    # Set to ≈ 10 ms (0x0021)
    _write_reg(spi, cs, REG_NO_RESPONSE_TIMER1, 0x00)
    _write_reg(spi, cs, REG_NO_RESPONSE_TIMER2, 0x21)
    _modify_reg(spi, cs, REG_GPT_CONTROL, 0x03, GPT_CONTROL_NRT_STEP)
    
    # Step 5: Enable external field detector (critical for target mode!)
    _modify_reg(spi, cs, REG_AUX, AUX_EN_FD, AUX_EN_FD)
    
    # Step 6: Enable CRC-to-FIFO
    _modify_reg(spi, cs, REG_AUX, AUX_CRC2FIFO, AUX_CRC2FIFO)
    
    # Step 7: Apply chip's analog preset (loads defaults for MODE.om).
    # NOTE: with om=0 (bit-rate detection) this loads *default/chip-init*
    # values, NOT the AP2P listen values. RFAL applies the listen-AP2P
    # analog config in software from rfal_analogConfigTbl.h - we do the
    # same explicitly below.
    _send_cmd(spi, cs, CMD_ANALOG_PRESET)
    time.sleep_ms(5)

    # Step 7b: RESTORE sup3V if CMD_ANALOG_PRESET cleared it
    io_conf2_after = _read_reg(spi, cs, REG_IO_CONF2)
    if (io_conf2_before & 0x80) and not (io_conf2_after & 0x80):
        _warn(f"  WARNING: CMD_ANALOG_PRESET cleared sup3V! Restoring...")
        _modify_reg(spi, cs, REG_IO_CONF2, 0x80, 0x80)
        io_conf2_after = _read_reg(spi, cs, REG_IO_CONF2)
        log(f"  IO_CONF2 restored: 0x{io_conf2_after:02X}")


    # -------------------------------------------------------------------
    # Step 7c: RFAL Listen-AP2P analog config
    # (rfal_analogConfigTbl.h lines 360-420)
    #
    # This is the RX front-end configuration required for the bit-rate
    # detector to actually lock onto an incoming Active-P2P NFC-A signal.
    # Without this the receiver is running in default/poll-mode settings
    # and NFCT (bit-rate recognized) will never fire.
    # -------------------------------------------------------------------
    log("  Applying LISTEN_AP2P analog config (RFAL table)...")

    # CHIP_LISTEN_ON block (line 360-365) - front end enters listen mode
    #   RX_CONF1[6:0] = 0x45  : filter / bandwidth for listen mode
    #   RX_CONF3.lim = 1, RX_CONF3.rg_nfc = 1  (mask 0x88, value 0x88)
    #   AUX.rx_tol = 1                          (mask 0x04, value 0x04)
    #   RX_CONF4.rg2_am = 1 << shift            (mask 0x30, value 0x10)
    _modify_reg(spi, cs, REG_RX_CONF1, 0x7F, 0x45)
    _modify_reg(spi, cs, REG_RX_CONF3, 0x88, 0x88)
    _modify_reg(spi, cs, REG_AUX,      AUX_RX_TOL, AUX_RX_TOL)
    _modify_reg(spi, cs, REG_RX_CONF4, 0x30, 0x10)

    # LISTEN + AP2P + 106 kbps + RX (line 410-412)
    #   RX_CONF3.rg1_am = 0xC0 (masked to 0x70 → 0x40)
    _modify_reg(spi, cs, REG_RX_CONF3, 0x70, 0x40)

    # LISTEN + AP2P + 106 kbps + TX (line 391-393)
    #   AUX.tr_am = 0 (OOK at 106k)
    _modify_reg(spi, cs, REG_AUX, AUX_TR_AM, 0x00)

    # LISTEN + AP2P COMMON TX (line 387-389)
    #   RFO_AM_ON_LEVEL = AM_MOD_DRIVER_LEVEL_DEFAULT (RFAL default: 0xB9)
    # We use RFO_TARGET_AM_ON / _OFF from the tunable block at the top of
    # this file (Phase 3: d_res raised from 13 to 8 for ~2x amplitude).
    _write_reg(spi, cs, REG_RFO_AM_ON_LEVEL,  RFO_TARGET_AM_ON)
    _write_reg(spi, cs, REG_RFO_AM_OFF_LEVEL, RFO_TARGET_AM_OFF)

    rx1  = _read_reg(spi, cs, REG_RX_CONF1)
    rx3  = _read_reg(spi, cs, REG_RX_CONF3)
    rx4  = _read_reg(spi, cs, REG_RX_CONF4)
    auxr = _read_reg(spi, cs, REG_AUX)
    rfoOn = _read_reg(spi, cs, REG_RFO_AM_ON_LEVEL)
    log(f"    RX_CONF1=0x{rx1:02X} (want 0x45)")
    log(f"    RX_CONF3=0x{rx3:02X} (want lim+rg_nfc+rg1_am=0x40 → 0xC8)")
    log(f"    RX_CONF4=0x{rx4:02X} (rg2_am nibble = 0x10)")
    log(f"    AUX=0x{auxr:02X} (rx_tol=1, tr_am=0 for OOK)")
    log(f"    RFO_AM_ON=0x{rfoOn:02X} (~14% AM driver)")

    # Step 10: Enable oscillator + receiver, and FIX the RX channel selection.
    #
    # CRITICAL BUG the register dump exposed:
    #   OP_CONTROL was ending up as 0xF0 = en | rx_en | rx_chn | rx_man
    #   - bit 5 (rx_chn) = 1  → PM channel selected (for 212/424 kbps NFC-F)
    #   - bit 4 (rx_man) = 1  → forces the manually-selected channel
    #   At 106 kbps NFC-A / Active P2P the receiver MUST use the AM channel
    #   (ASK/OOK modulation). With PM forced, the demodulator sees no valid
    #   signal at all - which is exactly what we observed:
    #   EON/EOF fire perfectly, but ZERO RXS/RXE/framing-error IRQs.
    #
    # Fix: set rx_man=1, rx_chn=0 → manually pin to AM channel.
    #      Also make sure wake-up bits (wu / wu_a / wu_ph = bits 2,1,0) are 0.
    #      Also make sure tx_en (bit 3) is 0 - target must not radiate.
    #
    # Final target OP_CONTROL = 0xD0 (en | rx_en | rx_man, everything else 0).
    _modify_reg(spi, cs, REG_OP_CONTROL,
                0xFF,                                                # touch every bit
                OP_CONTROL_EN | OP_CONTROL_RX_EN | 0x10)             # 0xD0
    op_ctrl_dbg = _read_reg(spi, cs, REG_OP_CONTROL)
    log(f"  OP_CONTROL forced to 0x{op_ctrl_dbg:02X} "
          f"(expect 0xD0: en+rx_en+rx_man=AM, no rx_chn, no wu*, no tx_en)")



    # Step 11: Enable IRQs required by the listen-mode worker (rfal_rfst25r3911.c:3508)
    # Unmasked: NFCT, EON, EOF, RXE, CRC, PAR, ERR1, ERR2
    # IRQ_MASK_MAIN  (0x14): unmask RXE (bit4)  → 0xEF
    # IRQ_MASK_TIMER_NFC (0x15): unmask NFCT(bit0), EOF(bit3), EON(bit4) → 0xE6
    # IRQ_MASK_ERROR_WUP (0x16): unmask CRC(bit7), PAR(bit6), ERR2(bit5), ERR1(bit4) → 0x0F
    _write_reg(spi, cs, REG_IRQ_MASK_MAIN,      0xEF)
    _write_reg(spi, cs, REG_IRQ_MASK_TIMER_NFC, 0xE6)
    _write_reg(spi, cs, REG_IRQ_MASK_ERROR_WUP, 0x0F)

    # Step 12: Clear any stale IRQs (read-to-clear)
    _read_irq(spi, cs)

    # NOTE: CMD_CLEAR_SQUELCH, mixer-toggle (Errata #1.4) and CMD_UNMASK_RECEIVE_DATA
    # are NOT done here. They belong in the POWER_OFF -> IDLE transition, i.e. after
    # the target has actually detected the initiator's field (EON IRQ).
    # See rfal_rfst25r3911.c lines 3557-3574. Doing them at init has no effect
    # because there is no incoming signal yet.
    
    op_ctrl = _read_reg(spi, cs, REG_OP_CONTROL)
    aux_disp = _read_reg(spi, cs, REG_AUX_DISPLAY)
    io_conf2_final = _read_reg(spi, cs, REG_IO_CONF2)
    log(f"  OP_CONTROL: 0x{op_ctrl:02X} (EN={bool(op_ctrl&0x80)}, RX_EN={bool(op_ctrl&0x40)}, TX_EN={bool(op_ctrl&0x08)})")
    log(f"  IO_CONF2 final: 0x{io_conf2_final:02X} (sup3V={bool(io_conf2_final&0x80)})")
    log(f"  AUX_DISPLAY: 0x{aux_disp:02X}")
    log(f"    - osc_ok (bit4): {bool(aux_disp&0x10)}")
    log(f"    - tx_on  (bit5): {bool(aux_disp&0x20)}")
    log(f"    - rx_on  (bit3): {bool(aux_disp&0x08)}")
    log(f"    - efd_o  (bit6): {bool(aux_disp&0x40)}")
    
    # NOTE: rx_on (bit 3) will remain 0 until an external initiator field is detected.
    # This is expected behavior for NFCIP-1 target in low-power wait mode.
    
    _info("NFCIP-1 TARGET mode configured successfully!")
    return {
        "mode": "target",

        "op_control": op_ctrl,
        "aux_display": aux_disp,
        "io_conf2": io_conf2_final,
        "osc_ok": bool(aux_disp & 0x10),
        "tx_on":   bool(aux_disp & 0x20),
        "rx_on":   bool(aux_disp & 0x08),
        "efd_o":   bool(aux_disp & 0x40),
        "ok":      bool(op_ctrl & 0x80),  # chip enabled
    }


# ---------------------------------------------------------------------------
# NFCIP-1 Initiator Mode Configuration
# ---------------------------------------------------------------------------

def configure_nfcip1_initiator(spi: SPI, cs: Pin, probe: bool = False) -> dict:
    """
    Configure ST25R3911B for NFCIP-1 active initiator mode.
    
    Similar to target mode but with targ=0 (initiator) and TX enabled.

    If probe=True, takes an amplitude + phase measurement after each
    significant configuration step and prints a one-line summary.  This
    is diagnostic-only - lets us identify exactly which register write
    causes the initiator-mode phase-vs-sweep disagreement observed on
    Board A (sweep predicts phase near 0x80, in-frame phase is 0x1B).
    The probe adds ~10 ms per checkpoint due to the two D3/D9 commands,
    but has no effect on the final register state.  Off by default.
    """
    # Same shadow-trick as configure_nfcip1_target: every register-dump
    # log() call below is diagnostic-only ("debug"), and we promote
    # milestones / warnings via the module-level _info/_warn helpers.
    def log(msg, level="debug"):
        _real_log(msg, level)

    _info("\nConfiguring NFCIP-1 INITIATOR mode...")


    # -----------------------------------------------------------------
    # Local diagnostic probe.  Previously imported _measure_amplitude /
    # _measure_phase from rf_diagnostics (bring-up-only helper module,
    # unused in production).  rf_diagnostics is no longer imported here;
    # _probe() is now unconditionally a no-op so the probe=True branch
    # would need to be re-enabled (and the import restored) to trace
    # phase-vs-step again during future hardware bring-up.
    # -----------------------------------------------------------------
    # if probe:
    #     from rf_diagnostics import _measure_amplitude, _measure_phase
    #
    #     def _probe(step_label):
    #         # Only meaningful once TX_EN is on and the carrier is up.
    #         # Before that the reading will be near zero, which is itself
    #         # useful ("checkpoint before field-on" == 0x00 expected).
    #         amp = _measure_amplitude(spi, cs)
    #         ph  = _measure_phase(spi, cs)
    #         op_ctrl = _read_reg(spi, cs, REG_OP_CONTROL)
    #         aux_disp = _read_reg(spi, cs, REG_AUX_DISPLAY)
    #         log("  [probe] {:<40s}  AMP=0x{:02X}  PHASE=0x{:02X} (dev={:+d})  "
    #               "TX_EN={}  TX_MOD={}"
    #               .format(step_label, amp, ph, ph - 0x80,
    #                       int(bool(op_ctrl & OP_CONTROL_TX_EN)),
    #                       int(bool(aux_disp & AUX_DISPLAY_TX_ON))))
    # else:
    #     def _probe(step_label):
    #         pass
    def _probe(step_label):
        pass
    
    # Step 0: CRITICAL - FORCE sup3V=1 for 3.3V operation AND recalibrate regulators
    # This bit gets cleared and MUST be set for TX to work on 3.3V boards!
    # After changing sup3V, regulators MUST be recalibrated!
    _probe("entry (before any init writes)")
    log("  Setting IO_CONF2.sup3V=1 for 3.3V operation (CRITICAL!)...")
    _modify_reg(spi, cs, REG_IO_CONF2, 0x80, 0x80)  # SET sup3V bit
    
    io_conf2_orig = _read_reg(spi, cs, REG_IO_CONF2)
    log(f"  IO_CONF2 after forcing sup3V: 0x{io_conf2_orig:02X} (sup3V={bool(io_conf2_orig&0x80)})")
    
    if not (io_conf2_orig & 0x80):
        raise RuntimeError("CRITICAL: Cannot set sup3V bit! TX will not work!")
    
    # CRITICAL: Recalibrate regulators after changing sup3V
    # The internal voltage regulators need to adjust for 3.3V vs 5V operation
    log("  Recalibrating regulators for 3.3V operation...")
    _modify_reg(spi, cs, REG_REGULATOR_CONTROL, 0x04, 0x04)  # Pulse reg_s
    _modify_reg(spi, cs, REG_REGULATOR_CONTROL, 0x04, 0x00)
    _send_cmd(spi, cs, CMD_ADJUST_REGULATORS)
    time.sleep_ms(6)
    _probe("after CMD_ADJUST_REGULATORS (regs re-tuned for 3.3V)")
    
    reg_result = _read_reg(spi, cs, 0x2B)  # REG_REGULATOR_RESULT
    log(f"  Regulator result after recalibration: 0x{reg_result:02X}")
    
    # Step 1: Set MODE register directly to NFCIP-1 NORMAL mode (initiator).
    #   MODE = targ_targ(0)=0 | om_nfcip1_normal=0x08 | nfc_ar=0x01 => 0x09
    # Previously we used 0x01 (om=0, bit-rate-detection) - wrong for AP2P TX.
    # NOTE: CMD_ANALOG_PRESET below may re-apply defaults for the current MODE.
    # We'll set MODE again _after_ CMD_ANALOG_PRESET, and the TX script will
    # also re-assert MODE right before each TX in case CMD_NFC_INITIAL_RF_COLL
    # clobbers it.
    _write_reg(spi, cs, REG_MODE, MODE_NFCIP1_INITIATOR)  # 0x09
    mode_rb = _read_reg(spi, cs, REG_MODE)
    log(f"  MODE register: 0x{mode_rb:02X} (expect 0x09 - NFCIP-1 normal, initiator)")
    _probe("after MODE=0x09 (initiator NFCIP-1)")

    
    # Step 2: Set bit rate to 106 kbps to match target's bit-rate-detect starting point.
    # RFAL's POLL_ACTIVE_P2P analog config is filled per-rate; 106 kbps is the
    # simplest and lets a target's on-chip bit-rate detector lock reliably.
    # BIT_RATE = 0x00: TX=106, RX=106
    _write_reg(spi, cs, REG_BIT_RATE, 0x00)
    bit_rate_rb = _read_reg(spi, cs, REG_BIT_RATE)
    log(f"  BIT_RATE: 0x{bit_rate_rb:02X} = 106 kbps (both TX and RX)")

    # Step 3: CLEAR nfc_f0 / no_tx_par / no_rx_par for AP2P at 106 kbps.
    # At 106 kbps Active P2P uses standard NFC-A framing (SoF + parity + CRC_A),
    # NOT the NFC-F LEN-prefixed transport format. nfc_f0 MUST be 0.
    # (This matches rfal_rfst25r3911.c:3237.)
    _modify_reg(spi, cs, REG_ISO14443A_NFC, 0x30, 0x00)  # clear no_tx_par + nfc_f0
    _modify_reg(spi, cs, REG_ISO14443A_NFC, 0x40, 0x00)  # clear no_rx_par
    nfc_reg = _read_reg(spi, cs, REG_ISO14443A_NFC)
    log(f"  ISO14443A_NFC: 0x{nfc_reg:02X} (nfc_f0={bool(nfc_reg&0x20)} - must be 0 for AP2P 106k)")
    
    # Step 4: Apply analog preset for current MODE
    aux_before_preset = _read_reg(spi, cs, REG_AUX)
    log(f"  AUX before CMD_ANALOG_PRESET: 0x{aux_before_preset:02X}")
    
    _send_cmd(spi, cs, CMD_ANALOG_PRESET)
    time.sleep_ms(5)
    _probe("after CMD_ANALOG_PRESET (may clobber trim/RFO/AUX)")
    
    aux_after_preset = _read_reg(spi, cs, REG_AUX)
    log(f"  AUX after CMD_ANALOG_PRESET: 0x{aux_after_preset:02X}")
    
    # CRITICAL: Restore AUX.en_fd (bit 4) if CMD_ANALOG_PRESET cleared it
    if not (aux_after_preset & AUX_EN_FD):
        _warn(f"  WARNING: CMD_ANALOG_PRESET cleared en_fd! Restoring...")
        _modify_reg(spi, cs, REG_AUX, AUX_EN_FD, AUX_EN_FD)

        aux_restored = _read_reg(spi, cs, REG_AUX)
        log(f"  AUX after restore: 0x{aux_restored:02X}")
    
    # Step 5: RESTORE sup3V bit if it was cleared by CMD_ANALOG_PRESET
    io_conf2_after = _read_reg(spi, cs, REG_IO_CONF2)
    if (io_conf2_orig & 0x80) and not (io_conf2_after & 0x80):
        _warn(f"  WARNING: CMD_ANALOG_PRESET cleared sup3V! Restoring...")

        _modify_reg(spi, cs, REG_IO_CONF2, 0x80, 0x80)
        io_conf2_after = _read_reg(spi, cs, REG_IO_CONF2)
        log(f"  IO_CONF2 restored: 0x{io_conf2_after:02X}")
    
    # Step 6: Set RFO drive levels (AFTER analog preset).
    # For AP2P 106 kbps the initiator uses OOK (AUX.tr_am = 0 below), so the
    # ON/OFF levels are only used during on-time. Historically RFAL POLL_AP2P
    # defaults are 0xD0 / 0xD0 - the digital OOK modulator will switch the
    # RFO driver fully off during modulation valleys.  We use the tunable
    # RFO_INITIATOR_AM_ON / _OFF from the top of this file (Phase 3: raised
    # drive strength via d_res=8 for ~2x amplitude).
    _write_reg(spi, cs, REG_RFO_AM_OFF_LEVEL, RFO_INITIATOR_AM_OFF)
    _write_reg(spi, cs, REG_RFO_AM_ON_LEVEL,  RFO_INITIATOR_AM_ON)
    _probe("after RFO drive levels re-written")

    
    rfo_off = _read_reg(spi, cs, REG_RFO_AM_OFF_LEVEL)
    rfo_on  = _read_reg(spi, cs, REG_RFO_AM_ON_LEVEL)
    log(f"  RFO levels: OFF=0x{rfo_off:02X}, ON=0x{rfo_on:02X}")
    
    # Step 7: Configure timers (CRITICAL - DISABLE GPT to keep field on!)
    # PROBLEM: Even max GPT timeout (0xFFFF ≈ 38.6ms) is too short!
    # The I_eof IRQ still fires (field drops) before target can receive.
    # 
    # SOLUTION: DISABLE GPT trigger entirely by setting gptc[7:5]=0 (no trigger)
    # This keeps the initiator field ON indefinitely until we manually turn it off.
    # We'll implement protocol-level timeout in application code instead.
    
    # Set GPT value to max (unused, but keeps timer valid)
    _write_reg(spi, cs, REG_GPT1, 0xFF)
    _write_reg(spi, cs, REG_GPT2, 0xFF)
    
    # CRITICAL: Clear gptc bits [7:5] to DISABLE GPT trigger
    # This prevents automatic field-off after TX
    gpt_ctrl = _read_reg(spi, cs, REG_GPT_CONTROL)
    gpt_ctrl &= ~0xE0  # Clear bits [7:5] = no trigger (disabled)
    gpt_ctrl |= 0x01   # Keep nrt_step=1 for NRT operation
    _write_reg(spi, cs, REG_GPT_CONTROL, gpt_ctrl)
    
    gpt_ctrl_rb = _read_reg(spi, cs, REG_GPT_CONTROL)
    log(f"  GPT_CONTROL: 0x{gpt_ctrl_rb:02X} (gptc[7:5]={(gpt_ctrl_rb>>5)&0x07} = {'DISABLED' if ((gpt_ctrl_rb>>5)&0x07)==0 else 'ENABLED'})")
    log(f"  GPT timeout mechanism: DISABLED - field stays on until manual turn-off")
    
    # Step 8: Configure AUX register for NFCIP-1 Active P2P initiator TX.
    #
    # CRITICAL: At 106 kbps NFC-A / Active P2P the initiator must use OOK
    # (carrier fully off during modulation valleys), NOT AM. That means
    # AUX.tr_am (bit 5) MUST be 0. This matches the RFAL POLL_AP2P_106_TX
    # analog config (rfal_analogConfigTbl.h line 253: AUX mask=0x20, val=0x00)
    # and the target's LISTEN_AP2P_106_TX config we already apply.
    #
    # A previous version set tr_am=1 which produced AM at only ~12% depth
    # from RFO=0xF0/0xD0 - too weak for the target's demodulator to trigger.
    #
    # We still want en_fd (bit 4) and crc_2_fifo (bit 6) set.
    _modify_reg(spi, cs, REG_AUX, AUX_TR_AM, 0x00)              # OOK modulation
    _modify_reg(spi, cs, REG_AUX, AUX_EN_FD | AUX_CRC2FIFO,
                                  AUX_EN_FD | AUX_CRC2FIFO)
    _probe("after AUX write (tr_am=0 OOK, en_fd, crc2fifo)")
    aux_final = _read_reg(spi, cs, REG_AUX)
    log(f"  AUX final: 0x{aux_final:02X}")
    log(f"    tr_am (bit5): {bool(aux_final&AUX_TR_AM)} - MUST be 0 (OOK) for AP2P 106 kbps")
    log(f"    en_fd (bit4): {bool(aux_final&AUX_EN_FD)}")
    log(f"    crc2fifo (bit6): {bool(aux_final&AUX_CRC2FIFO)}")

    
    # Step 9: Configure receiver settings
    _write_reg(spi, cs, REG_RX_CONF1, 0x08)
    _write_reg(spi, cs, REG_RX_CONF2, 0x2D)
    _write_reg(spi, cs, REG_RX_CONF3, 0x18)
    _modify_reg(spi, cs, REG_RX_CONF4, 0xF0, 0x20)
    _probe("after RX_CONF1..4 written")
    
    # Step 10: Check for external field BEFORE turning on TX (collision avoidance)
    aux_before = _read_reg(spi, cs, REG_AUX_DISPLAY)
    if aux_before & AUX_DISPLAY_EFD_O:
        _err("  ERROR: External field detected - cannot turn on initiator TX!")
        return {"mode": "initiator", "ok": False,
                "error": "external_field_pre_tx",
                "aux_display": aux_before}

    
    # Step 11: SIMPLE FIELD ON - Just like the working ISO14443A code!
    # Skip CMD_NFC_INITIAL_RF_COLL complexity. Just:
    # 1. Check for external field (collision avoidance)
    # 2. Set TX_EN
    # 3. Clear IRQs  
    # 4. Set RX_EN
    # 5. Wait 5ms
    
    log("  SIMPLE field-on sequence (like working ISO14443A code):")
    
    # Check for external field FIRST (collision avoidance)
    aux_efd = _read_reg(spi, cs, REG_AUX_DISPLAY)
    if aux_efd & AUX_DISPLAY_EFD_O:
        _err("    ERROR: External field detected - aborting field-on")

        return {"mode": "initiator", "ok": False,
                "error": "external_field_at_fieldon",
                "aux_display": aux_efd}
    
    # Turn on TX field (tx_en) - FIRST
    log("    1. Setting TX_EN...")
    _modify_reg(spi, cs, REG_OP_CONTROL, OP_CONTROL_TX_EN, OP_CONTROL_TX_EN)
    _probe("after TX_EN asserted (field coming up)")
    
    # Clear any stale field-event IRQs
    log("    2. Clearing IRQs...")
    _read_irq(spi, cs)
    
    # Enable receiver (rx_en) - SECOND
    log("    3. Setting RX_EN...")
    _modify_reg(spi, cs, REG_OP_CONTROL, OP_CONTROL_RX_EN, OP_CONTROL_RX_EN)
    
    # Guard time: minimum 5 ms before first command
    log("    4. Guard time (5ms)...")
    time.sleep_ms(5)
    _probe("after 5ms guard time (field fully stable)")
    
    # Check if TX_ON asserted
    aux_after = _read_reg(spi, cs, REG_AUX_DISPLAY)
    
    op_ctrl = _read_reg(spi, cs, REG_OP_CONTROL)
    aux_disp = _read_reg(spi, cs, REG_AUX_DISPLAY)
    io_conf2 = _read_reg(spi, cs, REG_IO_CONF2)
    log(f"  OP_CONTROL: 0x{op_ctrl:02X} (EN={bool(op_ctrl&0x80)}, RX_EN={bool(op_ctrl&0x40)}, TX_EN={bool(op_ctrl&0x08)})")
    log(f"  IO_CONF2: 0x{io_conf2:02X} (sup3V={bool(io_conf2&0x80)})")
    log(f"  AUX_DISPLAY: 0x{aux_disp:02X} (TX_ON={bool(aux_disp&AUX_DISPLAY_TX_ON)})")
    
    # Note: TX_ON=0 at idle is NORMAL for NFCIP-1 active mode.
    # The RF field only generates during actual transmission.
    if aux_disp & AUX_DISPLAY_TX_ON:
        log("  ✓ TX_ON asserted")
    
    _info("NFCIP-1 INITIATOR mode configured!")
    return {
        "mode": "initiator",

        "op_control": op_ctrl,
        "aux_display": aux_disp,
        "io_conf2": io_conf2,
        "tx_en":  bool(op_ctrl & 0x08),
        "rx_en":  bool(op_ctrl & 0x40),
        "tx_on":  bool(aux_disp & AUX_DISPLAY_TX_ON),
        "ok":     bool(op_ctrl & 0x88),  # EN + TX_EN
    }


# --------------------------------------------------------------------
# ID / device-identity helpers used by main.py
# --------------------------------------------------------------------

def get_device_id() -> bytes:
    """Get unique device ID (uses MCU unique ID)."""
    try:
        from machine import unique_id
        return unique_id()
    except:
        # Fallback for testing
        return b"TEST_DEVICE_ID"
