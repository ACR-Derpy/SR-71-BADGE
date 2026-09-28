"""Peer-to-peer trade and passive NFC sticker UI.

The badge exposes two NFC operations:

* PEER TO PEER: each user selects exactly one unlocked, tradeable card. Both
  badges run the same symmetric exchange and automatically send one card while
  receiving one card.
* TAG READER: reads an official passive NFC sticker and unlocks the card ID in
  its NDEF Text record.

This module owns only LVGL widgets. BadgeApp owns the NFC backend.
"""

import lvgl as lv

try:
    from badge_config import STICKER_CARD_IDS
except Exception:
    STICKER_CARD_IDS = ()


WIDTH = 240
HEIGHT = 280
MAX_TRADE_CARDS = 1

# ACR cards acquired from staff badges or stickers cannot be redistributed by
# normal attendee badges. Card definitions may also set non_tradeable=True.
NON_TRADEABLE_IDS = (
    "ACR-01",
    "ACR-02",
    "ACR-03",
    "ACR-04",
    "ACR-05",
)

COLORS = {
    "black": 0x03070A,
    "panel": 0x08131A,
    "panel_2": 0x0C2027,
    "green": 0xBF5FFF,
    "green_dim": 0x5C2499,
    "cyan": 0x38E8FF,
    "amber": 0xFFB000,
    "red": 0xFF3B45,
    "white": 0xD8F3E2,
    "muted": 0x6C9384,
    "disabled": 0x263036,
}


def color(name):
    return lv.color_hex(COLORS[name])


def remove_flag_safe(obj, flag):
    try:
        obj.remove_flag(flag)
    except Exception:
        try:
            obj.clear_flag(flag)
        except Exception:
            pass


def make_button_obj(parent):
    if hasattr(lv, "button"):
        return lv.button(parent)
    if hasattr(lv, "btn"):
        return lv.btn(parent)
    return lv.obj(parent)


def plain_obj(parent):
    obj = lv.obj(parent)
    obj.set_style_border_width(0, 0)
    obj.set_style_radius(0, 0)
    obj.set_style_pad_all(0, 0)
    remove_flag_safe(obj, lv.obj.FLAG.SCROLLABLE)
    return obj


def make_label(parent, text, text_color="white"):
    label = lv.label(parent)
    label.set_text(str(text))
    label.set_style_text_color(color(text_color), 0)
    return label


def constrain_label(label, width, height, clip=True):
    label.set_size(width, height)
    try:
        mode = lv.label.LONG_MODE.CLIP if clip else lv.label.LONG_MODE.WRAP
        label.set_long_mode(mode)
    except Exception:
        pass
    return label


def card_id(card):
    return str(card.get("id", "")).strip().upper()


def card_title(card):
    return str(card.get("title") or card.get("name") or card_id(card))


def has_acr_token(value):
    text = str(value).upper().strip()
    if not text:
        return False
    return (
        text == "ACR"
        or text.startswith("ACR-")
        or text.startswith("ACR_")
        or text.startswith("ACR ")
    )


def is_acr_card(card):
    if card.get("acr_designation", False):
        return True
    if card.get("non_tradeable", False):
        return True

    cid = card_id(card)
    if cid in NON_TRADEABLE_IDS:
        return True

    for key in ("id", "title", "subtitle", "designation"):
        if has_acr_token(card.get(key, "")):
            return True
    return False


def is_owned(card):
    if "owned" in card:
        return bool(card.get("owned"))
    return bool(card.get("unlocked", False))


def is_unlocked(card):
    return bool(card.get("unlocked", False))


def is_sticker_card(card):
    return bool(card.get("sticker_only", False)) or (
        card_id(card) in STICKER_CARD_IDS
    )


def is_tradeable(card):
    return (
        is_unlocked(card)
        and is_owned(card)
        and not is_acr_card(card)
        and not is_sticker_card(card)
    )


class TradeOperationsView:
    GRID_COLS = 3
    GRID_ROWS = 2
    CARDS_PER_PAGE = GRID_COLS * GRID_ROWS
    CELL_W = 74
    CELL_H = 70
    CELL_GAP = 4

    def __init__(
        self,
        parent,
        cards,
        on_back=None,
        on_peer_start=None,
        on_scan_start=None,
        on_gift_send=None,
        on_gift_receive=None,
        on_cancel=None,
        on_cards=None,
    ):
        self.parent = parent
        self.cards = cards
        self.on_back = on_back
        self.on_peer_start = on_peer_start
        self.on_scan_start = on_scan_start
        self.on_gift_send = on_gift_send
        self.on_gift_receive = on_gift_receive
        self.on_cancel = on_cancel
        self.on_cards = on_cards

        self.root = plain_obj(parent)
        self.root.set_size(WIDTH, HEIGHT)
        self.root.set_pos(0, 0)
        self.root.set_style_bg_color(color("black"), 0)
        self.root.set_style_bg_opa(0, 0)

        self.callbacks = []
        self.selected_ids = []
        self.trade_running = False
        self.mode = "choose"
        self.status_label = None
        self.active_status_label = None
        self.start_button = None
        self.start_button_label = None
        self.count_label = None
        self.page_label = None
        self.grid_panel = None
        self._grid_page = 0
        self._grid_cells = []
        self._all_cards = []
        self.picker_mode = "peer"

        self.show_mode_select()

    # --------------------------------------------------------------- helpers

    def clear_root(self):
        try:
            self.root.clean()
        except Exception:
            pass
        self.callbacks = []
        self.status_label = None
        self.active_status_label = None
        self.start_button = None
        self.start_button_label = None
        self.count_label = None
        self.page_label = None
        self.grid_panel = None
        self._grid_cells = []

    def _display_name(self, target_id):
        normalized = str(target_id or "").strip().upper()
        for item in self.cards:
            if card_id(item) == normalized:
                return card_title(item)
        return str(target_id or "UNKNOWN")

    def make_button(self, text, x, y, w, h, callback, theme="normal"):
        btn = make_button_obj(self.root)
        btn.set_size(w, h)
        btn.set_pos(x, y)
        btn.set_style_radius(3, 0)
        btn.set_style_border_width(1, 0)
        btn.set_style_pad_all(2, 0)
        btn.set_style_shadow_width(0, 0)
        remove_flag_safe(btn, lv.obj.FLAG.SCROLLABLE)

        if theme == "danger":
            bg, border, text_color = "panel", "red", "red"
        elif theme == "amber":
            bg, border, text_color = "panel_2", "amber", "amber"
        elif theme == "disabled":
            bg, border, text_color = "disabled", "muted", "muted"
        else:
            bg, border, text_color = "panel_2", "green_dim", "white"

        btn.set_style_bg_color(color(bg), 0)
        btn.set_style_bg_opa(lv.OPA.COVER, 0)
        btn.set_style_border_color(color(border), 0)

        label = make_label(btn, text, text_color)
        label.center()

        def clicked(event):
            del event
            if callback:
                callback()

        self.callbacks.append(clicked)
        btn.add_event_cb(clicked, lv.EVENT.CLICKED, None)
        return btn, label

    def make_back_button(self, callback=None):
        if callback is None:
            callback = self.handle_back

        btn, _label = self.make_button("BACK", 4, 4, 66, 30, callback)
        try:
            btn.set_ext_click_area(16)
        except Exception:
            pass
        try:
            btn.move_foreground()
        except Exception:
            pass
        return btn

    def _make_invisible_hitbox(self, x, y, w, h, callback):
        """Add a transparent touch target without changing visible geometry."""
        hitbox = plain_obj(self.root)
        hitbox.set_pos(x, y)
        hitbox.set_size(w, h)
        hitbox.set_style_bg_opa(0, 0)
        hitbox.set_style_border_width(0, 0)
        hitbox.set_style_pad_all(0, 0)
        remove_flag_safe(hitbox, lv.obj.FLAG.SCROLLABLE)
        try:
            hitbox.add_flag(lv.obj.FLAG.CLICKABLE)
        except Exception:
            pass

        def clicked(event):
            del event
            callback()

        self.callbacks.append(clicked)
        # Edge touches can lose their release sample on this controller.
        # Navigate on the initial press so a valid contact is enough.
        hitbox.add_event_cb(clicked, lv.EVENT.PRESSED, None)
        return hitbox

    def set_status(self, text, text_color="muted"):
        if self.status_label is not None:
            self.status_label.set_text(str(text))
            self.status_label.set_style_text_color(color(text_color), 0)

    def set_active_status(self, text, text_color="muted"):
        if self.active_status_label is not None:
            self.active_status_label.set_text(str(text))
            self.active_status_label.set_style_text_color(color(text_color), 0)

    def make_nfc_locked_notice(
        self, instruction, timing="Normal within 10 seconds."
    ):
        notice = make_label(
            self.root,
            "SCREEN LOCKED - EXPECTED\n"
            + str(instruction)
            + "\n"
            + str(timing),
            "amber",
        )
        notice.set_pos(20, 166)
        constrain_label(notice, 200, 50, clip=False)
        notice.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        return notice

    def handle_back(self):
        self.stop_active_trade()
        if self.on_back:
            self.on_back()

    def stop(self):
        self.stop_active_trade()
        for name in ("delete_async", "del_async", "delete", "del"):
            try:
                getattr(self.root, name)()
                return
            except Exception:
                pass

    # ----------------------------------------------------------- mode chooser

    def show_mode_select(self):
        self.mode = "choose"
        self.selected_ids = []
        self.clear_root()
        self.make_back_button()

        title = make_label(self.root, "NFC OPERATIONS", "white")
        title.set_pos(82, 12)
        constrain_label(title, 150, 18)

        subtitle = make_label(self.root, "Choose an NFC mode", "muted")
        subtitle.set_pos(30, 46)
        constrain_label(subtitle, 180, 20)
        subtitle.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.make_button(
            "PEER TO PEER",
            20,
            72,
            200,
            44,
            self.show_peer_picker,
        )
        self.make_button(
            "GIFT MODE",
            20,
            124,
            200,
            44,
            self.show_gift_mode,
        )
        self.make_button(
            "TAG READER",
            20,
            176,
            200,
            44,
            self.show_scan_wait,
            theme="amber",
        )

        hint = make_label(
            self.root,
            "Trade, gift, or scan a card.",
            "muted",
        )
        hint.set_pos(10, 234)
        constrain_label(hint, 220, 24, clip=False)
        hint.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

    def show_gift_mode(self):
        self.mode = "gift_mode"
        self.selected_ids = []
        self.clear_root()
        self.make_back_button(self.show_mode_select)

        title = make_label(self.root, "GIFT MODE", "white")
        title.set_pos(82, 14)
        constrain_label(title, 145, 18)
        title.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.make_button(
            "SEND A GIFT",
            20,
            54,
            200,
            54,
            self.show_gift_picker,
            theme="normal",
        )
        self.make_button(
            "RECEIVE A GIFT",
            20,
            122,
            200,
            54,
            self.start_gift_receive,
        )

        hint_text = "Sending keeps your card."
        hint = make_label(self.root, hint_text, "muted")
        hint.set_pos(20, 190)
        constrain_label(hint, 200, 24, clip=False)
        hint.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

    # ------------------------------------------------------------- peer picker

    def _total_pages(self):
        if not self._all_cards:
            return 1
        return (len(self._all_cards) + self.CARDS_PER_PAGE - 1) // self.CARDS_PER_PAGE

    def show_peer_picker(self):
        self.mode = "peer_pick"
        self.picker_mode = "peer"
        self.selected_ids = []
        self._grid_page = 0
        self._all_cards = list(self.cards)
        self.clear_root()
        self._build_picker_ui()
        self._draw_grid_page()

    def show_gift_picker(self):
        self.mode = "gift_pick"
        self.picker_mode = "gift"
        self.selected_ids = []
        self._grid_page = 0
        self._all_cards = list(self.cards)
        self.clear_root()
        self._build_picker_ui()
        self._draw_grid_page()

    def _build_picker_ui(self):
        self.make_back_button(
            self.show_gift_mode
            if self.picker_mode == "gift"
            else self.show_mode_select
        )

        title_text = "SELECT GIFT" if self.picker_mode == "gift" else "SELECT ONE CARD"
        title = make_label(self.root, title_text, "white")
        title.set_pos(77, 9)
        constrain_label(title, 125, 17)

        self.count_label = make_label(self.root, "0/1", "cyan")
        self.count_label.set_pos(202, 9)
        constrain_label(self.count_label, 34, 17)

        panel_w = self.GRID_COLS * self.CELL_W + (self.GRID_COLS - 1) * self.CELL_GAP
        panel_h = self.GRID_ROWS * self.CELL_H + (self.GRID_ROWS - 1) * self.CELL_GAP
        panel_x = (WIDTH - panel_w) // 2
        panel_y = 32

        self.grid_panel = plain_obj(self.root)
        self.grid_panel.set_pos(panel_x, panel_y)
        self.grid_panel.set_size(panel_w, panel_h)
        self.grid_panel.set_style_bg_color(color("black"), 0)
        self.grid_panel.set_style_bg_opa(lv.OPA.COVER, 0)

        nav_y = panel_y + panel_h + 5
        prev_btn, _ = self.make_button("<", panel_x, nav_y, 44, 32, self._page_prev)
        next_btn, _ = self.make_button(">", panel_x + panel_w - 44, nav_y, 44, 32, self._page_next)
        self.page_label = make_label(self.root, "", "muted")
        self.page_label.set_pos(panel_x + 50, nav_y + 8)
        self.page_label.set_size(panel_w - 100, 16)
        self.page_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.status_label = make_label(self.root, "Tap one unlocked card.", "muted")
        self.status_label.set_pos(15, 216)
        constrain_label(self.status_label, 210, 18)
        self.status_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.start_button, self.start_button_label = self.make_button(
            "SELECT A CARD",
            20,
            238,
            200,
            38,
            self.show_gift_confirm
            if self.picker_mode == "gift"
            else self.show_peer_confirm,
            theme="disabled",
        )

        # The card grid ends at y=176. These transparent edge targets start at
        # y=177, so they substantially enlarge the arrows without intercepting
        # even the bottom pixel of a selectable card.
        prev_hitbox = self._make_invisible_hitbox(
            0, panel_y + panel_h + 1, 96, 41, self._page_prev
        )
        next_hitbox = self._make_invisible_hitbox(
            112, panel_y + panel_h + 1, WIDTH - 112, 41, self._page_next
        )
        try:
            prev_hitbox.move_foreground()
            next_hitbox.move_foreground()
        except Exception:
            pass

        # The visible footer is deliberately compact, but there are no card or
        # navigation targets below y=219. Use that empty lower region as one
        # forgiving target for Continue. The callback already refuses to
        # advance until exactly one card is selected.
        continue_hitbox = self._make_invisible_hitbox(
            8,
            224,
            WIDTH - 16,
            HEIGHT - 224,
            self.show_gift_confirm
            if self.picker_mode == "gift"
            else self.show_peer_confirm,
        )
        try:
            continue_hitbox.move_foreground()
        except Exception:
            pass

        # Visible buttons remain owned by the LVGL tree.
        del prev_btn, next_btn

    def _draw_grid_page(self):
        for cell in self._grid_cells:
            callback = cell.get("callback")
            if callback is not None:
                try:
                    self.callbacks.remove(callback)
                except Exception:
                    pass
            obj = cell.get("obj")
            for name in ("delete_async", "del_async", "delete", "del"):
                try:
                    getattr(obj, name)()
                    break
                except Exception:
                    pass
        self._grid_cells = []

        total_pages = self._total_pages()
        if self._grid_page >= total_pages:
            self._grid_page = total_pages - 1
        if self._grid_page < 0:
            self._grid_page = 0

        if self.page_label is not None:
            self.page_label.set_text("%d / %d" % (self._grid_page + 1, total_pages))

        panel_x = self.grid_panel.get_x()
        panel_y = self.grid_panel.get_y()
        start = self._grid_page * self.CARDS_PER_PAGE
        page_cards = self._all_cards[start:start + self.CARDS_PER_PAGE]

        for index, card in enumerate(page_cards):
            row = index // self.GRID_COLS
            col = index % self.GRID_COLS
            x = panel_x + col * (self.CELL_W + self.CELL_GAP)
            y = panel_y + row * (self.CELL_H + self.CELL_GAP)
            self._grid_cells.append(self._make_grid_cell(card, x, y))

    def _make_grid_cell(self, card, x, y):
        cid = card_id(card)
        unlocked = is_unlocked(card)
        tradeable = is_tradeable(card)

        obj = make_button_obj(self.root)
        obj.set_size(self.CELL_W, self.CELL_H)
        obj.set_pos(x, y)
        obj.set_style_radius(2, 0)
        obj.set_style_pad_all(0, 0)
        obj.set_style_shadow_width(0, 0)
        remove_flag_safe(obj, lv.obj.FLAG.SCROLLABLE)

        display_name = card_title(card) if unlocked else "LOCKED"
        name_label = make_label(
            obj,
            display_name,
            "cyan" if unlocked else "white",
        )
        name_label.set_width(self.CELL_W - 8)
        name_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        remove_flag_safe(name_label, lv.obj.FLAG.CLICKABLE)
        try:
            name_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        except Exception:
            pass

        # Prefer smaller compiled fonts for long names, but remain compatible
        # with firmware builds that expose only the default LVGL font.
        font_names = ()
        if len(display_name) > 16:
            font_names = (
                "font_montserrat_8",
                "font_unscii_8",
                "font_montserrat_10",
            )
            try:
                name_label.set_style_text_letter_space(-1, 0)
                name_label.set_style_text_line_space(-1, 0)
            except Exception:
                pass
        elif len(display_name) > 10:
            font_names = (
                "font_montserrat_10",
                "font_montserrat_8",
                "font_unscii_8",
            )
            try:
                name_label.set_style_text_letter_space(-1, 0)
                name_label.set_style_text_line_space(-1, 0)
            except Exception:
                pass
        for font_name in font_names:
            try:
                name_label.set_style_text_font(getattr(lv, font_name), 0)
                break
            except Exception:
                pass

        try:
            name_label.set_height(lv.SIZE.CONTENT)
            name_label.center()
        except Exception:
            name_label.set_pos(4, 8)
            name_label.set_size(self.CELL_W - 8, self.CELL_H - 16)

        check = make_label(obj, "", "green")
        check.set_pos(self.CELL_W - 14, 2)
        constrain_label(check, 12, 12)

        cell = {
            "obj": obj,
            "cid": cid,
            "unlocked": unlocked,
            "tradeable": tradeable,
            "check": check,
            "name": name_label,
        }
        self._repaint_cell(cell)

        if tradeable:
            def clicked(event, selected_id=cid):
                del event
                self._select_card(selected_id)

            self.callbacks.append(clicked)
            obj.add_event_cb(clicked, lv.EVENT.CLICKED, None)
            cell["callback"] = clicked
        else:
            remove_flag_safe(obj, lv.obj.FLAG.CLICKABLE)
            cell["callback"] = None

        return cell

    def _repaint_cell(self, cell):
        selected = cell["cid"] in self.selected_ids
        obj = cell["obj"]
        check = cell["check"]

        if not cell["unlocked"]:
            obj.set_style_bg_color(color("panel"), 0)
            obj.set_style_border_width(1, 0)
            obj.set_style_border_color(color("disabled"), 0)
            check.set_text("")
        elif not cell["tradeable"]:
            obj.set_style_bg_color(color("panel"), 0)
            obj.set_style_border_width(1, 0)
            obj.set_style_border_color(color("amber"), 0)
            check.set_text("!")
            check.set_style_text_color(color("amber"), 0)
        elif selected:
            obj.set_style_bg_color(color("panel_2"), 0)
            obj.set_style_border_width(2, 0)
            obj.set_style_border_color(color("green"), 0)
            check.set_text("+")
            check.set_style_text_color(color("green"), 0)
        else:
            obj.set_style_bg_color(color("panel"), 0)
            obj.set_style_border_width(1, 0)
            obj.set_style_border_color(color("green_dim"), 0)
            check.set_text("")

    def _select_card(self, cid):
        # Selecting another card replaces the old selection. This is faster and
        # clearer than forcing the user to deselect first when only one is valid.
        if self.selected_ids == [cid]:
            self.selected_ids = []
        else:
            self.selected_ids = [cid]

        for cell in self._grid_cells:
            self._repaint_cell(cell)
        self._refresh_picker_footer()

    def _refresh_picker_footer(self):
        count = len(self.selected_ids)
        if self.count_label is not None:
            self.count_label.set_text("%d/1" % count)

        if count == 1:
            cid = self.selected_ids[0]
            prefix = "Gifting: " if self.picker_mode == "gift" else "Offering: "
            self.set_status(prefix + self._display_name(cid), "cyan")
            self.start_button_label.set_text("CONTINUE")
            self.start_button.set_style_bg_color(color("panel_2"), 0)
            self.start_button.set_style_border_color(color("green"), 0)
            self.start_button_label.set_style_text_color(color("white"), 0)
        else:
            self.set_status("Tap one unlocked card.", "muted")
            self.start_button_label.set_text("SELECT A CARD")
            self.start_button.set_style_bg_color(color("disabled"), 0)
            self.start_button.set_style_border_color(color("muted"), 0)
            self.start_button_label.set_style_text_color(color("muted"), 0)

    def _page_prev(self):
        if self._grid_page > 0:
            self._grid_page -= 1
            self._draw_grid_page()

    def _page_next(self):
        if self._grid_page < self._total_pages() - 1:
            self._grid_page += 1
            self._draw_grid_page()

    def show_peer_confirm(self):
        if len(self.selected_ids) != 1:
            self.set_status("Select exactly one card.", "amber")
            return

        offered_id = self.selected_ids[0]
        saved_page = self._grid_page
        self.clear_root()

        def return_to_picker():
            self.show_peer_picker()
            self._grid_page = saved_page
            self._draw_grid_page()
            self.selected_ids = [offered_id]
            for cell in self._grid_cells:
                self._repaint_cell(cell)
            self._refresh_picker_footer()

        self.make_back_button(return_to_picker)

        title = make_label(self.root, "CONFIRM P2P", "white")
        title.set_pos(86, 12)
        constrain_label(title, 125, 18)

        label = make_label(self.root, "YOUR CARD", "muted")
        label.set_pos(20, 48)
        constrain_label(label, 100, 16)

        value = make_label(self.root, self._display_name(offered_id), "cyan")
        value.set_pos(20, 72)
        constrain_label(value, 200, 22)
        value.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        instructions = make_label(
            self.root,
            "Both users select a card.\n"
            "Start P2P on both badges.\n"
            "Hold antennas together.\n"
            "Each badge trades one card.",
            "muted",
        )
        instructions.set_pos(20, 122)
        constrain_label(instructions, 200, 68, clip=False)
        instructions.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.make_button(
            "START PEER TRADE",
            20,
            202,
            200,
            48,
            self.start_peer_trade,
        )

    def start_peer_trade(self):
        if self.trade_running or len(self.selected_ids) != 1:
            return

        offered_id = self.selected_ids[0]
        self.trade_running = True
        self.mode = "peer_active"
        self.clear_root()
        title = make_label(self.root, "PEER TO PEER", "white")
        title.set_pos(80, 15)
        constrain_label(title, 145, 18)

        offer = make_label(
            self.root, "Offering: " + self._display_name(offered_id), "cyan"
        )
        offer.set_pos(20, 62)
        constrain_label(offer, 200, 20)
        offer.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.active_status_label = make_label(
            self.root,
            "Starting peer trade...",
            "muted",
        )
        self.active_status_label.set_pos(20, 108)
        constrain_label(self.active_status_label, 200, 54, clip=False)
        self.active_status_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.make_nfc_locked_notice(
            "Keep antennas together.",
            "One exchange; normal within 10 sec.",
        )

        self.make_button(
            "PLEASE WAIT",
            20,
            224,
            200,
            46,
            None,
            theme="disabled",
        )

        if self.on_peer_start:
            self.on_peer_start(offered_id)

    def show_gift_confirm(self):
        if len(self.selected_ids) != 1:
            self.set_status("Select exactly one card.", "amber")
            return

        gift_id = self.selected_ids[0]
        saved_page = self._grid_page
        self.clear_root()

        def return_to_picker():
            self.show_gift_picker()
            self._grid_page = saved_page
            self._draw_grid_page()
            self.selected_ids = [gift_id]
            for cell in self._grid_cells:
                self._repaint_cell(cell)
            self._refresh_picker_footer()

        self.make_back_button(return_to_picker)

        title = make_label(self.root, "CONFIRM GIFT", "white")
        title.set_pos(82, 12)
        constrain_label(title, 145, 18)

        label = make_label(self.root, "GIFTING CARD", "muted")
        label.set_pos(20, 58)
        constrain_label(label, 200, 16)
        label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        value = make_label(self.root, self._display_name(gift_id), "cyan")
        value.set_pos(20, 82)
        constrain_label(value, 200, 22)
        value.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        instructions = make_label(
            self.root,
            "Receiver selects RECEIVE.\n"
            "Hold antennas together.",
            "muted",
        )
        instructions.set_pos(20, 108)
        constrain_label(instructions, 200, 44, clip=False)
        instructions.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.make_button(
            "SEND GIFT",
            20,
            170,
            200,
            48,
            self.start_gift_send,
        )

    def start_gift_send(self):
        if (
            self.trade_running
            or len(self.selected_ids) != 1
        ):
            return

        gift_id = self.selected_ids[0]
        self.trade_running = True
        self.mode = "gift_send_active"
        self.clear_root()

        title = make_label(self.root, "SENDING GIFT", "white")
        title.set_pos(20, 15)
        constrain_label(title, 200, 18)
        title.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        card = make_label(self.root, self._display_name(gift_id), "cyan")
        card.set_pos(20, 62)
        constrain_label(card, 200, 20)
        card.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.active_status_label = make_label(
            self.root, "Looking for gift receiver...", "muted"
        )
        self.active_status_label.set_pos(20, 108)
        constrain_label(self.active_status_label, 200, 54, clip=False)
        self.active_status_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.make_nfc_locked_notice("Keep antennas together.")

        self.make_button(
            "PLEASE WAIT", 20, 224, 200, 46, None, theme="disabled"
        )

        if self.on_gift_send:
            self.on_gift_send(gift_id)

    def start_gift_receive(self):
        if self.trade_running:
            return

        self.trade_running = True
        self.mode = "gift_receive_active"
        self.clear_root()

        title = make_label(self.root, "RECEIVE GIFT", "white")
        title.set_pos(20, 15)
        constrain_label(title, 200, 18)
        title.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.active_status_label = make_label(
            self.root, "Waiting for gift sender...", "muted"
        )
        self.active_status_label.set_pos(20, 92)
        constrain_label(self.active_status_label, 200, 74, clip=False)
        self.active_status_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.make_nfc_locked_notice("Keep antennas together.")

        self.make_button(
            "PLEASE WAIT", 20, 224, 200, 46, None, theme="disabled"
        )

        if self.on_gift_receive:
            self.on_gift_receive()

    # ------------------------------------------------------------- tag reader

    def show_scan_wait(self):
        self.mode = "scan_ready"
        self.selected_ids = []
        self.clear_root()
        self.make_back_button(self.show_mode_select)

        title = make_label(self.root, "TAG READER", "white")
        title.set_pos(86, 15)
        constrain_label(title, 120, 18)

        msg = make_label(
            self.root,
            "Scan an official NFC sticker\nto unlock its exclusive card.",
            "muted",
        )
        msg.set_pos(20, 72)
        constrain_label(msg, 200, 48, clip=False)
        msg.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.make_button(
            "START TAG READER",
            20,
            150,
            200,
            48,
            self.start_scan_tag,
            theme="amber",
        )
        back_btn, _back_label = self.make_button(
            "BACK",
            20,
            214,
            200,
            46,
            self.show_mode_select,
            theme="danger",
        )
        try:
            back_btn.set_ext_click_area(8)
        except Exception:
            pass

    def start_scan_tag(self):
        if self.trade_running:
            return

        self.trade_running = True
        self.mode = "scan_active"
        self.clear_root()
        title = make_label(self.root, "READING TAG", "white")
        title.set_pos(82, 15)
        constrain_label(title, 130, 18)

        self.active_status_label = make_label(
            self.root,
            "Hold sticker near the NFC antenna...",
            "muted",
        )
        self.active_status_label.set_pos(20, 92)
        constrain_label(self.active_status_label, 200, 70, clip=False)
        self.active_status_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.make_nfc_locked_notice("Keep sticker in place.")

        self.make_button(
            "PLEASE WAIT",
            20,
            220,
            200,
            46,
            None,
            theme="disabled",
        )

        if self.on_scan_start:
            self.on_scan_start()

    # --------------------------------------------------------------- results

    def stop_active_trade(self):
        was_running = self.trade_running
        self.trade_running = False
        if was_running and self.on_cancel:
            try:
                self.on_cancel()
            except Exception as exc:
                print("NFC cancel callback failed:", exc)

    def cancel_operation(self):
        self.stop_active_trade()
        self.show_mode_select()

    def complete_peer_trade(self, offered_id, received_id, newly_unlocked=True):
        self.trade_running = False
        self.mode = "peer_complete"
        self.clear_root()
        self.make_back_button(self.show_mode_select)

        title = make_label(self.root, "TRADE COMPLETE", "green")
        title.set_pos(20, 22)
        constrain_label(title, 200, 20)
        title.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        sent = make_label(self.root, "SENT", "muted")
        sent.set_pos(24, 68)
        constrain_label(sent, 80, 16)
        sent_value = make_label(self.root, self._display_name(offered_id), "cyan")
        sent_value.set_pos(24, 90)
        constrain_label(sent_value, 192, 20)
        sent_value.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        received = make_label(self.root, "RECEIVED", "muted")
        received.set_pos(24, 126)
        constrain_label(received, 100, 16)
        received_value = make_label(
            self.root,
            self._display_name(received_id),
            "white",
        )
        received_value.set_pos(24, 148)
        constrain_label(received_value, 192, 20)
        received_value.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        status = "CARD UNLOCKED" if newly_unlocked else "ALREADY OWNED"
        status_color = "green" if newly_unlocked else "amber"
        status_label = make_label(self.root, status, status_color)
        status_label.set_pos(20, 184)
        constrain_label(status_label, 200, 20)
        status_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.make_button(
            "OK",
            20,
            222,
            200,
            44,
            self.on_cards if self.on_cards is not None else self.show_mode_select,
        )

    def complete_gift_send(self, card_id):
        self.trade_running = False
        self.mode = "gift_send_complete"
        self.clear_root()
        self.make_back_button(self.show_gift_mode)

        title = make_label(self.root, "GIFT SENT", "green")
        title.set_pos(20, 20)
        constrain_label(title, 200, 20)
        title.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        card = make_label(self.root, self._display_name(card_id), "cyan")
        card.set_pos(20, 70)
        constrain_label(card, 200, 24)
        card.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.make_button("DONE", 20, 150, 200, 46, self.show_gift_mode)

    def complete_gift_receive(self, card_id, newly_unlocked=True):
        self.trade_running = False
        self.mode = "gift_receive_complete"
        self.clear_root()
        self.make_back_button(self.show_gift_mode)

        title = make_label(self.root, "GIFT RECEIVED", "green")
        title.set_pos(20, 20)
        constrain_label(title, 200, 20)
        title.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        card = make_label(self.root, self._display_name(card_id), "cyan")
        card.set_pos(20, 70)
        constrain_label(card, 200, 24)
        card.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        status_text = "CARD UNLOCKED" if newly_unlocked else "ALREADY OWNED"
        status_color = "green" if newly_unlocked else "amber"
        status = make_label(self.root, status_text, status_color)
        status.set_pos(20, 112)
        constrain_label(status, 200, 20)
        status.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.make_button(
            "OK",
            20,
            164,
            200,
            46,
            self.on_cards if self.on_cards is not None else self.show_gift_mode,
        )

    def complete_tag_scan(self, card_id, newly_unlocked=True):
        self.trade_running = False
        self.mode = "scan_complete"
        self.clear_root()
        self.make_back_button(self.show_mode_select)

        title = make_label(self.root, "TAG READ", "green")
        title.set_pos(20, 25)
        constrain_label(title, 200, 20)
        title.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        card_label = make_label(
            self.root,
            self._display_name(card_id),
            "cyan",
        )
        card_label.set_pos(20, 92)
        constrain_label(card_label, 200, 24)
        card_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        status = "CARD UNLOCKED" if newly_unlocked else "ALREADY OWNED"
        status_color = "green" if newly_unlocked else "amber"
        status_label = make_label(self.root, status, status_color)
        status_label.set_pos(20, 142)
        constrain_label(status_label, 200, 20)
        status_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.make_button(
            "OK",
            20,
            218,
            200,
            46,
            self.on_cards if self.on_cards is not None else self.show_mode_select,
        )

    def complete_trade_error(self, message="NFC operation failed."):
        self.trade_running = False
        self.mode = "error"
        self.clear_root()
        self.make_back_button(self.show_mode_select)

        title = make_label(self.root, "NFC ERROR", "red")
        title.set_pos(88, 25)
        constrain_label(title, 120, 20)

        body = make_label(self.root, message, "amber")
        body.set_pos(22, 82)
        constrain_label(body, 196, 94, clip=False)
        body.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.make_button("TRY AGAIN", 20, 218, 200, 46, self.show_mode_select)
