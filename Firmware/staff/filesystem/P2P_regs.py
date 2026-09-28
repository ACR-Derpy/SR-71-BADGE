"""ST25R3911B register map, bit constants, and low-level SPI helpers.

Everything in here is pure data + tiny SPI accessors.  Higher-level
configuration (calibrate, configure_nfcip1_*, etc.) lives in
``P2P_config``.  A module-level log sink (``log`` / ``set_log_sink``)
is provided so higher layers can redirect diagnostic output away from
``print`` -- e.g. into an OLED log pane -- without touching call sites.
"""

from machine import SPI, Pin  # noqa: F401 (re-exported)
import time                    # noqa: F401 (re-exported)

"""
ST25R3911B - NFCIP-1 (Peer-to-Peer) Configuration
Implements NFCIP-1 active target and initiator modes for peer-to-peer communication.

Based on RFAL library analysis (rfal_rfst25r3911.c lines 864-879).

Key fix: MODE register must be 0x89 for target mode:
  - 0x80: targ_targ (target mode, bit 7)
  - 0x08: om_nfcip1_normal_mode (operation mode bits [6:3])
  - 0x01: nfc_ar (automatic response RF collision avoidance, bit 0)

Previous non-working code used 0x81 (missing om bits, defaulted to bit-rate detection mode=0).

SPI wiring (example for RP2040 / Pico):
  SCK  -> GP6
  MOSI -> GP7
  MISO -> GP4
  CS   -> GP5
  IRQ  -> GP11  (optional, polled here)
  BUTTON -> GP22 (for initiator mode switching)
"""

from machine import SPI, Pin
import time

# ---------------------------------------------------------------------------
# Register addresses  (from st25r3911_com.h)
# ---------------------------------------------------------------------------
REG_IO_CONF1              = 0x00
REG_IO_CONF2              = 0x01
REG_OP_CONTROL            = 0x02
REG_MODE                  = 0x03
REG_BIT_RATE              = 0x04
REG_ISO14443A_NFC         = 0x05
REG_AUX                   = 0x09
REG_RX_CONF1              = 0x0A
REG_RX_CONF2              = 0x0B
REG_RX_CONF3              = 0x0C
REG_RX_CONF4              = 0x0D
REG_MASK_RX_TIMER         = 0x0E
REG_NO_RESPONSE_TIMER1    = 0x0F
REG_NO_RESPONSE_TIMER2    = 0x10
REG_GPT_CONTROL           = 0x11
REG_GPT1                  = 0x12
REG_GPT2                  = 0x13
REG_IRQ_MASK_MAIN         = 0x14
REG_IRQ_MASK_TIMER_NFC    = 0x15
REG_IRQ_MASK_ERROR_WUP    = 0x16
REG_IRQ_MAIN              = 0x17
REG_IRQ_TIMER_NFC         = 0x18
REG_IRQ_ERROR_WUP         = 0x19
REG_FIFO_RX_STATUS1       = 0x1A
REG_FIFO_RX_STATUS2       = 0x1B
REG_NUM_TX_BYTES1         = 0x1D
REG_NUM_TX_BYTES2         = 0x1E
REG_AD_RESULT             = 0x20
REG_ANT_CAL_CONTROL       = 0x21   # bit7 trim_s (0=auto,1=manual); [6:3] manual trim
REG_ANT_CAL_TARGET        = 0x22
REG_ANT_CAL_RESULT        = 0x23   # R  [7:4]=tri_val (calibrated trim), bit3=tri_err
REG_AM_MOD_DEPTH_CONTROL  = 0x24
REG_RFO_AM_ON_LEVEL       = 0x26
REG_RFO_AM_OFF_LEVEL      = 0x27
REG_FIELD_THRESHOLD       = 0x29
REG_REGULATOR_CONTROL     = 0x2A
REG_REGULATOR_RESULT      = 0x2B   # DC regulator readback (lower 4 bits = reg[3:0])
REG_AUX_DISPLAY           = 0x30
REG_AMPLITUDE_MEAS        = 0x35   # result of CMD_MEASURE_AMPLITUDE
REG_PHASE_MEAS            = 0x39   # result of CMD_MEASURE_PHASE
REG_IC_IDENTITY           = 0x3F


# ---------------------------------------------------------------------------
# RF tuning knobs (Phase 3: RFO drive strength)
# ---------------------------------------------------------------------------
# The upper nibble of REG_RFO_AM_ON_LEVEL / REG_RFO_AM_OFF_LEVEL is d_res -
# the driver's output series resistance.  d_res=0 = full drive (max field),
# d_res=15 = maximum attenuation (weakest field).  The lower nibble encodes
# the AM depth via the difference between the two registers' low nibbles.
#
# Historical defaults on this project were d_res=13 (0xD?), which produced
# weak on-air amplitude (AMPLITUDE reg ~0x25).  Phase 2 fixed antenna
# resonance via manual trim; Phase 3 raises drive to d_res=8 (~2x more
# amplitude at the receiver) for better link margin at range.
#
# To retune: bump RFO_DRIVE_NIBBLE and reflash.  Nothing else needs to
# change - both configure_nfcip1_target() and configure_nfcip1_initiator()
# read from these, as does the RFO-restore safety path in the target
# response handler.
#
# Sanity check for future tuning:
#   * Keep RFO_TARGET_AM_ON's low nibble = 9 and RFO_TARGET_AM_OFF's low
#     nibble = 0 to preserve the ~14% AM depth needed for reliable OOK
#     demodulation at the peer (RFAL default AM_MOD_DRIVER_LEVEL_DEFAULT).
#   * Initiator uses identical ON and OFF because the digital OOK modulator
#     switches the RFO driver hard off during modulation valleys.
#   * If AMPLITUDE reads > 0xE0 in rf_diagnostics, the driver is saturating
#     and you should back off (raise d_res).
RFO_DRIVE_NIBBLE          = 0x8   # d_res value (0..15), lower = stronger

RFO_TARGET_AM_ON          = (RFO_DRIVE_NIBBLE << 4) | 0x9   # e.g. 0x89
RFO_TARGET_AM_OFF         = (RFO_DRIVE_NIBBLE << 4) | 0x0   # e.g. 0x80
RFO_INITIATOR_AM_ON       = (RFO_DRIVE_NIBBLE << 4) | 0x0   # e.g. 0x80
RFO_INITIATOR_AM_OFF      = (RFO_DRIVE_NIBBLE << 4) | 0x0   # e.g. 0x80

# ---------------------------------------------------------------------------
# Direct commands  (from st25r3911.h)
# ---------------------------------------------------------------------------
CMD_RFON                  = 0xC0  # Turn on RF field (basic command)
CMD_SET_DEFAULT           = 0xC1
CMD_CLEAR_FIFO            = 0xC2
CMD_TRANSMIT_WITH_CRC     = 0xC4
CMD_TRANSMIT_WITHOUT_CRC  = 0xC5
CMD_NFC_INITIAL_RF_COLL   = 0xC8  # NFC Initial Field ON with RF Collision Avoidance (for initiator!)
CMD_RESPONSE_RF_COLL      = 0xC9  # NFC Response RF Collision Avoidance (for target)
CMD_NORMAL_NFC_MODE       = 0xCB  # Switch from bit-rate detection to normal mode
CMD_ANALOG_PRESET         = 0xCC
CMD_UNMASK_RECEIVE_DATA   = 0xD1
CMD_CLEAR_SQUELCH         = 0xD5
CMD_MEASURE_AMPLITUDE     = 0xD3   # measure RF amplitude on RFI (result -> REG_AMPLITUDE_MEAS 0x35)
CMD_ADJUST_REGULATORS     = 0xD6
CMD_CALIBRATE_ANTENNA     = 0xD8
CMD_MEASURE_PHASE         = 0xD9   # measure phase RFO vs RFI       (result -> REG_PHASE_MEAS 0x39)
CMD_MEASURE_VDD           = 0xDF
CMD_START_GP_TIMER        = 0xE0

# ---------------------------------------------------------------------------
# SPI operation mode prefixes  (from st25r3911_com.c)
# ---------------------------------------------------------------------------
_WRITE_MODE = 0x00        # reg | 0x00
_READ_MODE  = 0x40        # reg | 0x40
_FIFO_LOAD  = 0x80        # FIFO write prefix  
_FIFO_READ  = 0xBF        # FIFO read opcode

# ---------------------------------------------------------------------------
# OP_CONTROL bit masks (0x02)
# ---------------------------------------------------------------------------
OP_CONTROL_EN    = 0x80   # oscillator + regulator enable
OP_CONTROL_RX_EN = 0x40   # receiver enable
OP_CONTROL_WU    = 0x04   # wake-up mode
OP_CONTROL_TX_EN = 0x08   # transmitter enable (field on)

# ---------------------------------------------------------------------------
# MODE register bits (0x03) - CRITICAL for NFCIP-1
# ---------------------------------------------------------------------------
MODE_TARG_TARG          = 0x80  # Target mode (bit 7)
MODE_TARG_INIT          = 0x00  # Initiator mode (bit 7 = 0)
MODE_OM_NFC             = 0x00  # NFC mode / bit-rate detection (om bits [6:3] = 0000)
MODE_OM_NFCIP1          = 0x08  # NFCIP-1 normal mode (om bits [6:3] = 0001)
MODE_NFC_AR             = 0x01  # NFC automatic response RF collision avoidance

# Combined modes for NFCIP-1 Active P2P
#
# Since BOTH peers are hard-coded to 106 kbps, we skip the on-chip
# bit-rate detection dance entirely and put the target directly in
# NFCIP-1 NORMAL mode (om = 0x08). The chip will demodulate NFC-A
# frames immediately on EON without needing NFCT to fire.
#
# Target:    targ=1, om=NFCIP1_NORMAL(0x08), nfc_ar=1  →  0x89
# Initiator: targ=0, om=NFCIP1_NORMAL(0x08), nfc_ar=1  →  0x09
MODE_NFCIP1_TARGET    = MODE_TARG_TARG | MODE_OM_NFCIP1 | MODE_NFC_AR  # 0x89
MODE_NFCIP1_INITIATOR = MODE_TARG_INIT | MODE_OM_NFCIP1 | MODE_NFC_AR  # 0x09


# ---------------------------------------------------------------------------
# AUX bit masks (0x09)
# ---------------------------------------------------------------------------
AUX_TR_AM    = 0x20       # AM modulation (set) vs OOK (clear)
AUX_CRC2FIFO = 0x40       # append received CRC to FIFO
AUX_EN_FD    = 0x10       # external field detector enable
AUX_RX_TOL   = 0x04       # receiver tolerance

# ---------------------------------------------------------------------------
# IRQ_MAIN bit masks  (from st25r3911_interrupt.h)
# ---------------------------------------------------------------------------
IRQ_TXE = 0x08            # end of transmission
IRQ_RXE = 0x10            # end of reception
IRQ_RXS = 0x20            # start of reception
IRQ_FWL = 0x40            # FIFO water level
IRQ_COL = 0x04            # bit collision

# IRQ_ERROR_WUP bit masks (register 0x19)
IRQ_CRC  = 0x80           # CRC error         (bit 7)
IRQ_PAR  = 0x40           # parity error      (bit 6)
IRQ_ERR2 = 0x20           # soft framing err  (bit 5)
IRQ_ERR1 = 0x10           # hard framing err  (bit 4)

# IRQ_TIMER_NFC bit masks (register 0x18)
IRQ_NFCT = 0x01           # initiator bit rate recognized (bit 0)
IRQ_CAT  = 0x02           # min guard time expired        (bit 1)
IRQ_CAC  = 0x04           # collision during RFCA         (bit 2)
IRQ_EOF  = 0x08           # external field off            (bit 3)
IRQ_EON  = 0x10           # external field on             (bit 4)
IRQ_GPE  = 0x20           # GPT expired                   (bit 5)
IRQ_NRE  = 0x40           # no-response timer expired     (bit 6)
IRQ_DCT  = 0x80           # termination of direct command (bit 7)

# AUX_DISPLAY bit masks (0x30)
AUX_DISPLAY_OSC_OK = 0x10 # oscillator stable (bit 4)
AUX_DISPLAY_TX_ON  = 0x20 # transmitter on (bit 5)
AUX_DISPLAY_EFD_O  = 0x40 # external field detected output (bit 6)

# ---------------------------------------------------------------------------
# GPT_CONTROL bits (0x11)
# ---------------------------------------------------------------------------
GPT_CONTROL_NRT_STEP = 0x01  # NRT step = 4096/fc (bit 0)
GPT_CONTROL_GPTC_ETX = 0x60  # GPT trigger on end of TX (bits [7:5] = 011)

# ---------------------------------------------------------------------------
# Low-level SPI helpers
# ---------------------------------------------------------------------------

def _write_reg(spi: SPI, cs: Pin, reg: int, val: int) -> None:
    cs(0)
    spi.write(bytes([reg | _WRITE_MODE, val]))
    cs(1)


def _read_reg(spi: SPI, cs: Pin, reg: int) -> int:
    buf = bytearray(2)
    cs(0)
    spi.write_readinto(bytes([reg | _READ_MODE, 0x00]), buf)
    cs(1)
    return buf[1]


def _modify_reg(spi: SPI, cs: Pin, reg: int, mask: int, val: int) -> None:
    current = _read_reg(spi, cs, reg)
    current = (current & ~mask) | (val & mask)
    _write_reg(spi, cs, reg, current)


def _send_cmd(spi: SPI, cs: Pin, cmd: int) -> None:
    cs(0)
    spi.write(bytes([cmd]))
    cs(1)


def _write_fifo(spi: SPI, cs: Pin, data: bytes | bytearray) -> None:
    cs(0)
    spi.write(bytes([_FIFO_LOAD]) + bytes(data))
    cs(1)


def _read_fifo(spi: SPI, cs: Pin, length: int) -> bytearray:
    if length == 0:
        return bytearray()
    tx = bytes([_FIFO_READ] + [0x00] * length)
    rx = bytearray(len(tx))
    cs(0)
    spi.write_readinto(tx, rx)
    cs(1)
    return rx[1:]


def _read_irq(spi: SPI, cs: Pin) -> tuple[int, int, int]:
    """Read and clear all three IRQ registers. Returns (main, timer_nfc, error_wup)."""
    main      = _read_reg(spi, cs, REG_IRQ_MAIN)
    timer_nfc = _read_reg(spi, cs, REG_IRQ_TIMER_NFC)
    error_wup = _read_reg(spi, cs, REG_IRQ_ERROR_WUP)
    return main, timer_nfc, error_wup



# ---------------------------------------------------------------------
# Diagnostic log sink.  Default = builtin print; UI code can override
# with set_log_sink() at boot so every diagnostic message flows into
# whatever widget it wants (e.g. an on-device OLED log pane).
# ---------------------------------------------------------------------

_log_sink = print

# Numeric priorities for level-based filtering.  Higher = more severe.
# Anything below _log_threshold is silently dropped.
_LEVEL_PRIORITY = {
    "debug": 10,
    "info":  20,
    "warn":  30,
    "error": 40,
}
_log_threshold = _LEVEL_PRIORITY["info"]

def set_log_sink(fn):
    '''Redirect diagnostic output.  fn(msg:str, level:str='info').'''
    global _log_sink
    _log_sink = fn if fn is not None else print

def set_log_level(level):
    '''Set the minimum level that will be emitted.

    Accepts either a string ('debug' | 'info' | 'warn' | 'error') or an
    int priority (10/20/30/40).  Unknown strings are treated as 'info'.
    Call once at boot from main.py:

        from P2P_config import set_log_level
        set_log_level("info")    # normal operation - hides per-frame chatter
        set_log_level("debug")   # everything, for hardware bring-up
    '''
    global _log_threshold
    if isinstance(level, str):
        _log_threshold = _LEVEL_PRIORITY.get(level.lower(),
                                             _LEVEL_PRIORITY["info"])
    else:
        try:
            _log_threshold = int(level)
        except Exception:
            _log_threshold = _LEVEL_PRIORITY["info"]

def log(msg, level='info'):
    '''Route one diagnostic line to the active sink.

    Default sink is the builtin print(); the level kwarg is silently
    accepted so UI sinks can colour-code messages.  Messages below the
    current log threshold (set_log_level) are dropped BEFORE reaching
    the sink so per-frame chatter can be silenced by callers without
    editing every log() call site.  Never raises -- a broken sink must
    not take the NFC stack down with it.
    '''
    try:
        prio = _LEVEL_PRIORITY.get(level, _LEVEL_PRIORITY["info"])
        if prio < _log_threshold:
            return
        try:
            _log_sink(msg, level)
        except TypeError:
            _log_sink(msg)
    except Exception:
        pass


