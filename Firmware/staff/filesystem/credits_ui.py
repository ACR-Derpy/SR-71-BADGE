"""Credits screen wrapper."""


def build_credits_screen(app):
    root = app.make_root(with_background=False)
    app.credits_view = CreditsView(root, on_back=app.show_menu)


import lvgl as lv
from card_carousel import color

WIDTH  = 240
HEIGHT = 280

# ── Edit here ─────────────────────────────────────────────────────────────────
CREDITS_ENTRIES = [
    "CHALLENGE DESIGN",
    ("Christmas Cipher", "@SynapticRodeo"),
    ("Crossword", "@SynapticRodeo"),
    ("Postcard from Hell", "@SynapticRodeo"),
    ("Too Many Letters", "@SynapticRodeo"),
    ("Martin's Secret", "@SoFi"),
    ("AdventureTime", "@Ophren"),
    ("Transmission for Cosmo", "@myx"),
    ("Property of Playtronics", "@ArizonaRanger"),
    ("Skyfall's Cipher: Ballistic Recovery", "@Shifu"), 
    ("Bishop's Treasure Hunt", "@SoFi"),
    ("My Voice is My Passport", "@Numbers"), 
    ("Voice Mail Villains", "@SynapticRodeo"),
    ("Black Box Keys", "@myx"),
    ("Cosmo's Diary", "@SoFi"),
    ("Janek's Lost Design", "@Nyquist"),
    ("Finger Guns", "@RiskyBlooky"),

    "BADGE HARDWARE",
    ("PCB Design", "@Nyquist"),
    ("STL/PCB Design", "@Broske"),

    "BADGE SOFTWARE",
    ("Dev", "@Phlux"),
    ("Dev", "@ArizonaRanger"),

    "DISCORD BOT",
    ("Dev", "@Beans"),
    ("Dev", "@RiskyBlooky"),

    "ART & ASSETS",
    ("Graphic Design", "@SoFi"),

    "ELDER COUNCIL",
    ("Da Boss", "@Sharpie"),
    ("Kind of Tech Lead", "@Shifu"),
    ("Local Fellow", "@SynapticRodeo"),

    "SPECIAL THANKS",
    ("Lockheed Martin", "Emerging Tech"),
    ("Lockheed Martin", "Skunk Works"),
    ("All participants", "You!"),
]
# ─────────────────────────────────────────────────────────────────────────────


def _lv_btn(parent):
    if hasattr(lv, "button"):
        return lv.button(parent)
    if hasattr(lv, "btn"):
        return lv.btn(parent)
    return lv.obj(parent)


class CreditsView:
    """Scrollable credits screen.

    Instantiate with a parent LVGL object.  Pass on_back= to receive a
    callback when the user taps < BACK.
    """

    def __init__(self, parent, on_back=None):
        self.parent    = parent
        self.on_back   = on_back
        self.callbacks = []
        self._build()

    # ------------------------------------------------------------------ build

    def _build(self):
        self.root = lv.obj(self.parent)
        self.root.set_size(WIDTH, HEIGHT)
        self.root.set_pos(0, 0)
        self.root.set_style_bg_color(color("black"), 0)
        self.root.set_style_bg_opa(lv.OPA.COVER, 0)
        self.root.set_style_border_width(0, 0)
        self.root.set_style_radius(0, 0)
        self.root.set_style_pad_all(0, 0)
        self.root.remove_flag(lv.obj.FLAG.SCROLLABLE)

        self._build_header()
        self._build_scroll_area()

    def _build_header(self):
        hdr = lv.obj(self.root)
        hdr.set_size(WIDTH, 37)
        hdr.set_pos(0, 0)
        hdr.set_style_bg_color(color("panel"), 0)
        hdr.set_style_bg_opa(lv.OPA.COVER, 0)
        hdr.set_style_border_width(0, 0)
        hdr.set_style_radius(0, 0)
        hdr.set_style_pad_all(0, 0)
        hdr.remove_flag(lv.obj.FLAG.SCROLLABLE)

        btn = _lv_btn(hdr)
        btn.set_size(80, 33)
        btn.set_pos(2, 2)
        btn.set_style_bg_color(color("panel_2"), 0)
        btn.set_style_bg_opa(lv.OPA.COVER, 0)
        btn.set_style_border_color(color("green_dim"), 0)
        btn.set_style_border_width(1, 0)
        btn.set_style_radius(2, 0)
        btn.set_style_shadow_width(0, 0)
        btn.remove_flag(lv.obj.FLAG.SCROLLABLE)
        try:
            btn.set_ext_click_area(16)
        except Exception:
            pass
        back_lbl = lv.label(btn)
        back_lbl.set_text("< BACK")
        back_lbl.set_style_text_color(color("white"), 0)
        back_lbl.center()
        back_cb = lambda e: self.on_back() if self.on_back else None
        self.callbacks.append(back_cb)
        btn.add_event_cb(back_cb, lv.EVENT.CLICKED, None)

        title = lv.label(hdr)
        title.set_text("// CREDITS")
        title.set_style_text_color(color("green"), 0)
        title.set_pos(100, 12)
        title.set_size(136, 16)
        try:
            title.set_long_mode(lv.label.LONG_MODE.CLIP)
        except Exception:
            pass

        # Green separator line at bottom of header
        sep = lv.obj(self.root)
        sep.set_pos(0, 36)
        sep.set_size(WIDTH, 1)
        sep.set_style_bg_color(color("green"), 0)
        sep.set_style_bg_opa(lv.OPA.COVER, 0)
        sep.set_style_border_width(0, 0)
        sep.set_style_radius(0, 0)
        sep.set_style_pad_all(0, 0)

    def _build_scroll_area(self):
        # Scrollable container. Children placed at absolute y positions that
        # extend beyond the visible height — LVGL scrolls automatically.
        scroll = lv.obj(self.root)
        scroll.set_pos(0, 37)
        scroll.set_size(WIDTH, HEIGHT - 37)
        scroll.set_style_bg_color(color("black"), 0)
        scroll.set_style_bg_opa(lv.OPA.COVER, 0)
        scroll.set_style_border_width(0, 0)
        scroll.set_style_radius(0, 0)
        scroll.set_style_pad_all(0, 0)
        try:
            scroll.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
            scroll.set_scroll_dir(lv.DIR.VER)
        except Exception:
            pass

        lines = ["ACR SR-71 BADGE", "------------------------", ""]
        for entry in CREDITS_ENTRIES:
            if isinstance(entry, str):
                if lines[-1] != "":
                    lines.append("")
                lines.append(entry)
                lines.append("------------------------")
            else:
                role, name = entry
                lines.append(str(role))
                for name_line in str(name).split("\n"):
                    lines.append("  " + name_line.strip())
                lines.append("")
        lines.extend(("", "// END OF LINE", ""))

        content = lv.label(scroll)
        content.set_text("\n".join(lines))
        content.set_style_text_color(color("green"), 0)
        content.set_pos(14, 14)
        content.set_width(WIDTH - 28)
        try:
            content.set_long_mode(lv.label.LONG_MODE.WRAP)
        except Exception:
            pass

    # ------------------------------------------------------------------ public

    def delete(self):
        try:
            self.root.add_flag(lv.obj.FLAG.HIDDEN)
        except Exception:
            pass
        for method in ("delete_async", "del_async", "delete", "del_"):
            try:
                getattr(self.root, method)()
                return
            except Exception:
                pass
