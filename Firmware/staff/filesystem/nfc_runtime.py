"""Single-core NFC service for the LVGL badge.

The LED runtime already owns MicroPython's secondary core. NFC operations are
therefore run synchronously on the main core after BadgeApp has displayed the
active NFC screen. The screen remains static during the blocking RF operation
and is replaced with the result screen when the call returns.
"""

from machine import Pin, SPI


NFC_SPI_ID = 0
NFC_BAUDRATE = 10_000_000
NFC_SCK_PIN = 6
NFC_MOSI_PIN = 7
NFC_MISO_PIN = 4
NFC_CS_PIN = 5
NFC_IRQ_PIN = 11
NFC_LOG_LEVEL = "error"
NFC_OPERATION_TIMEOUT_MS = 10_000
NFCA_READER_API_REQUIRED = 3


class NFCRuntime:
    def __init__(self):
        self.spi = None
        self.cs = None
        self.irq = None
        self.my_id = None
        self.initialized = False
        self.available = True
        self.init_error = None
        self._pc = None

        self._cancel_requested = False
        self._job_id = 0
        message = "NFC service ready."
        self._state = {
            "job_id": 0,
            "mode": None,
            "running": False,
            "done": False,
            "message": message,
            "result": None,
            "error": None,
        }

    # ------------------------------------------------------------------ state

    def _update_state(self, **updates):
        state = dict(self._state)
        state.update(updates)
        self._state = state

    def snapshot(self):
        return dict(self._state)

    # --------------------------------------------------------------- hardware

    def initialize(self):
        """Initialize synchronously; mainly useful from the REPL."""
        if self.initialized:
            return True
        return self._initialize_hardware()

    def _initialize_hardware(self):
        if self.initialized:
            return True
        if not self.available:
            return False

        try:
            import P2P_config as pc

            self._pc = pc
            pc.set_log_level(NFC_LOG_LEVEL)

            self.spi = SPI(
                NFC_SPI_ID,
                baudrate=NFC_BAUDRATE,
                polarity=0,
                phase=1,
                sck=NFC_SCK_PIN,
                mosi=NFC_MOSI_PIN,
                miso=NFC_MISO_PIN,
            )
            self.cs = Pin(NFC_CS_PIN, Pin.OUT, value=1)
            self.irq = Pin(NFC_IRQ_PIN, Pin.IN, Pin.PULL_UP)

            pc.reset(self.spi, self.cs)
            pc.configure_io(self.spi, self.cs)
            chip_id = pc.check_chip_id(self.spi, self.cs)
            pc.osc_on(self.spi, self.cs)
            vdd_mv = pc.configure_supply(self.spi, self.cs)
            pc.configure_fifo_and_aux(self.spi, self.cs)
            pc.configure_analog_chip_init(self.spi, self.cs)
            calibration = pc.calibrate(self.spi, self.cs)

            try:
                uid = pc.get_device_id()
            except Exception:
                uid = b""
            self.my_id = (bytes(uid) + b"\x00" * 12)[:12]

            self.initialized = True
            self.init_error = None
            self.teardown()
            self._update_state(
                message="NFC ready.",
                error=None,
                result={
                    "chip_id": chip_id,
                    "vdd_mv": vdd_mv,
                    "calibration": calibration,
                },
            )
            print("NFC ready")
            return True

        except Exception as exc:
            self.initialized = False
            self.available = False
            self.init_error = str(exc)
            self._update_state(
                message="NFC initialization failed: {}".format(exc),
                error=self.init_error,
            )
            try:
                self.close()
            except Exception:
                pass
            print("NFC initialization failed:", exc)
            return False

    def teardown(self, disable_chip=False):
        """Drop TX and RX and clear transient NFC state between operations."""
        if self.spi is None or self.cs is None or self._pc is None:
            return

        pc = self._pc
        try:
            pc._modify_reg(
                self.spi,
                self.cs,
                pc.REG_OP_CONTROL,
                pc.OP_CONTROL_TX_EN | pc.OP_CONTROL_RX_EN,
                0x00,
            )
        except Exception:
            pass

        try:
            pc._send_cmd(self.spi, self.cs, pc.CMD_CLEAR_FIFO)
        except Exception:
            pass

        try:
            pc._read_irq(self.spi, self.cs)
        except Exception:
            pass

        if disable_chip:
            try:
                pc._modify_reg(
                    self.spi,
                    self.cs,
                    pc.REG_OP_CONTROL,
                    pc.OP_CONTROL_EN,
                    0x00,
                )
            except Exception:
                pass

    def close(self):
        """Disable NFC hardware and release the SPI and GPIO resources."""
        self._cancel_requested = True

        try:
            self.teardown(disable_chip=True)
        except Exception:
            pass

        # Release the bus before its chip-select and IRQ pins. Not every
        # MicroPython Pin implementation exposes deinit(), so each resource is
        # handled independently and references are cleared unconditionally.
        spi = self.spi
        cs = self.cs
        irq = self.irq
        self.spi = None
        self.cs = None
        self.irq = None
        self._pc = None
        self.initialized = False

        for resource in (spi, cs, irq):
            if resource is None:
                continue
            try:
                resource.deinit()
            except (AttributeError, TypeError):
                pass
            except Exception as exc:
                try:
                    print("NFC resource release failed:", exc)
                except Exception:
                    pass

    # -------------------------------------------------------------- lifecycle

    def _is_cancel_requested(self):
        return bool(self._cancel_requested)

    def cancel(self):
        self._cancel_requested = True
        running = bool(self._state.get("running"))
        if running:
            self._update_state(message="Canceling NFC operation...")
        return running

    def _start(self, mode, payload):
        if not self.available:
            message = self.init_error or "NFC service unavailable."
            self._update_state(
                mode=mode,
                running=False,
                done=True,
                message=message,
                result=None,
                error=message,
            )
            return False

        if self._state.get("running"):
            return False

        self._job_id += 1
        job_id = self._job_id
        self._cancel_requested = False
        self._state = {
            "job_id": job_id,
            "mode": mode,
            "running": True,
            "done": False,
            "message": "Starting NFC...",
            "result": None,
            "error": None,
        }

        try:
            self._worker_entry(job_id, mode, payload)
            return True
        except Exception as exc:
            self._update_state(
                running=False,
                done=True,
                message="Could not run NFC operation: {}".format(exc),
                result={
                    "ok": False,
                    "canceled": False,
                    "error": str(exc),
                },
                error=str(exc),
            )
            try:
                import sys
                sys.print_exception(exc)
            except Exception:
                pass
            return False

    def start_peer_trade(
        self,
        offered_card_id,
        known_card_ids,
        owned_card_ids,
        received_card_ids=None,
    ):
        return self._start(
            "peer",
            {
                "offered_card_id": str(offered_card_id),
                "known_card_ids": list(known_card_ids),
                "owned_card_ids": list(owned_card_ids),
                "received_card_ids": list(
                    received_card_ids
                    if received_card_ids is not None
                    else known_card_ids
                ),
            },
        )

    def start_tag_scan(self, known_card_ids):
        return self._start("scan", {"known_card_ids": list(known_card_ids)})

    def start_gift_send(self, card_id, known_card_ids):
        return self._start(
            "gift_send",
            {
                "card_id": str(card_id),
                "known_card_ids": list(known_card_ids),
            },
        )

    def start_gift_receive(self, known_card_ids):
        return self._start(
            "gift_receive",
            {"known_card_ids": list(known_card_ids)},
        )

    # ------------------------------------------------------------- operation

    def _progress(self, text):
        self._update_state(message=str(text))

    def _load_nfca_reader(self):
        """Reload the filesystem module and reject stale reader versions.

        MicroPython caches imported modules in ``sys.modules``. Copying a new
        nfca_reader.py onto a running badge does not replace the already-loaded
        function until reset or an explicit reload. Remove that cached entry so
        every scan uses the file currently stored on the badge.
        """
        import gc
        import sys

        try:
            del sys.modules["nfca_reader"]
        except Exception:
            pass

        gc.collect()
        import nfca_reader

        version = getattr(nfca_reader, "NFCA_READER_API_VERSION", 0)
        if version < NFCA_READER_API_REQUIRED:
            location = getattr(nfca_reader, "__file__", "unknown location")
            raise RuntimeError(
                "Outdated nfca_reader loaded from {} (API {}, need {}). "
                "Replace nfca_reader.py and hard-reset the badge.".format(
                    location, version, NFCA_READER_API_REQUIRED
                )
            )

        return nfca_reader.run_nfca_reader

    def _worker_entry(self, job_id, mode, payload):
        result = None
        error = None

        try:
            if not self.initialized:
                self._progress("Initializing NFC hardware...")
                if not self._initialize_hardware():
                    raise RuntimeError(self.init_error or "NFC initialization failed.")

            if mode == "peer":
                from id_exchange import IDExchange
                from trade import run_peer_trade

                idx = IDExchange(
                    self.spi,
                    self.cs,
                    self.my_id,
                    verbose=False,
                    debug=False,
                    rf_diag=False,
                )
                result = run_peer_trade(
                    idx,
                    payload.get("offered_card_id"),
                    payload.get("known_card_ids", []),
                    owned_card_ids=payload.get("owned_card_ids", []),
                    received_card_ids=payload.get("received_card_ids", []),
                    overall_timeout_ms=NFC_OPERATION_TIMEOUT_MS,
                    should_cancel=self._is_cancel_requested,
                    progress_cb=self._progress,
                )

            elif mode in ("gift_send", "gift_receive"):
                from gift import run_gift_receive, run_gift_send
                from id_exchange import IDExchange

                idx = IDExchange(
                    self.spi,
                    self.cs,
                    self.my_id,
                    verbose=False,
                    debug=False,
                    rf_diag=False,
                )
                if mode == "gift_send":
                    result = run_gift_send(
                        idx,
                        payload.get("card_id"),
                        payload.get("known_card_ids", []),
                        overall_timeout_ms=NFC_OPERATION_TIMEOUT_MS,
                        should_cancel=self._is_cancel_requested,
                        progress_cb=self._progress,
                    )
                else:
                    result = run_gift_receive(
                        idx,
                        payload.get("known_card_ids", []),
                        overall_timeout_ms=NFC_OPERATION_TIMEOUT_MS,
                        should_cancel=self._is_cancel_requested,
                        progress_cb=self._progress,
                    )

            elif mode == "scan":
                run_nfca_reader = self._load_nfca_reader()
                from trade import card_id_from_tag_text

                self._progress("Hold NFC sticker near badge...")

                # Pass optional arguments positionally. This avoids keyword API
                # mismatches on older MicroPython builds while the version check
                # above guarantees the loaded reader supports all four values.
                reader_result = run_nfca_reader(
                    self.spi,
                    self.cs,
                    NFC_OPERATION_TIMEOUT_MS,
                    self._is_cancel_requested,
                )
                result = {
                    "ok": False,
                    "canceled": bool(reader_result.get("canceled", False)),
                    "error": None,
                    "card_id": None,
                    "reader": reader_result,
                }

                if result["canceled"]:
                    result["error"] = "Tag scan canceled."
                elif not reader_result.get("ok"):
                    result["error"] = "No readable NFC sticker found."
                else:
                    card_id = card_id_from_tag_text(
                        reader_result.get("text"),
                        payload.get("known_card_ids", []),
                    )
                    if card_id is None:
                        result["error"] = "Sticker does not contain a sticker-card ID."
                    else:
                        result["ok"] = True
                        result["card_id"] = card_id

            else:
                raise ValueError("Unknown NFC mode: {}".format(mode))

        except Exception as exc:
            error = str(exc)
            result = {
                "ok": False,
                "canceled": self._is_cancel_requested(),
                "error": error,
            }
            try:
                import sys

                print("NFC operation failed:")
                sys.print_exception(exc)
            except Exception:
                print("NFC operation failed:", exc)

        finally:
            try:
                self.teardown()
            except Exception as exc:
                if error is None:
                    error = "NFC teardown failed: {}".format(exc)

            ok = bool(result and result.get("ok"))
            canceled = bool(result and result.get("canceled"))
            if ok:
                message = "NFC operation complete."
            elif canceled:
                message = "NFC operation canceled."
            else:
                message = (result or {}).get("error") or error or "NFC operation failed."

            if self._state.get("job_id") == job_id:
                self._update_state(
                    running=False,
                    done=True,
                    message=message,
                    result=result,
                    error=error or ((result or {}).get("error")),
                )
