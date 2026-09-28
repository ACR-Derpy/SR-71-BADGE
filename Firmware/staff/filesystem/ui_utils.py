"""Small LVGL helpers shared by app/views."""

import lvgl as lv


def delete_obj(obj):
    if obj is None:
        return

    try:
        obj.add_flag(lv.obj.FLAG.HIDDEN)
    except Exception:
        pass

    for name in ("delete_async", "del_async", "delete", "del"):
        try:
            getattr(obj, name)()
            return
        except Exception:
            pass


def create_lv_button(parent):
    if hasattr(lv, "button"):
        return lv.button(parent)
    if hasattr(lv, "btn"):
        return lv.btn(parent)
    return lv.obj(parent)
