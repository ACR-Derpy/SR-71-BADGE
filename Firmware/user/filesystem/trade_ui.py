"""NFC operations screen wrapper."""

from card_carousel import CARDS


def build_trade_screen(app):
    root = app.make_root()

    try:
        from trade_ops import TradeOperationsView

        app.trade_view = TradeOperationsView(
            root,
            CARDS,
            on_back=app.show_menu,
            on_peer_start=app.begin_peer_trade,
            on_scan_start=app.begin_nfc_tag_scan,
            on_gift_send=app.begin_gift_send,
            on_gift_receive=app.begin_gift_receive,
            on_cancel=app.stop_trade_if_running,
            on_cards=app.show_cards,
        )

    except Exception as exc:
        import sys

        print("NFC UI failed:")
        sys.print_exception(exc)

        app.make_back_button(root)
        app.make_label(root, "// NFC ERROR", 8, 45, 180, 18, "red")
        app.make_label(root, "NFC interface unavailable", 16, 82, 208, 80, "amber")
