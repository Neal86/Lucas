from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

APP_USER_MODEL_ID = "Lucas.Node.Settings"


def set_windows_app_id(app_id: str = APP_USER_MODEL_ID) -> None:
    """Give Windows a Lucas identity instead of inheriting python/pythonw.exe."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def make_square_icon(status: str | None = None, size: int = 64) -> Any:
    """Return the Lucas octopus icon used by Windows, the settings window, and tray."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    inset = max(1, size // 64)
    radius = max(4, round(size * 11 / 64))
    draw.rounded_rectangle(
        (inset, inset, size - 2, size - 2),
        radius=radius,
        fill=(255, 255, 255, 255),
        outline=(224, 228, 235, 255),
        width=max(1, size // 64),
    )
    try:
        asset = Path(__file__).with_name("assets") / "lucas-logo-square.png"
        source = Image.open(asset).convert("RGBA")
        # Fill most of the Windows icon tile so the mark remains legible at 32/48 px.
        logo_size = max(16, round(size * 58 / 64))
        source.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
        image.alpha_composite(source, ((size - source.width) // 2, (size - source.height) // 2))
    except Exception:
        draw = ImageDraw.Draw(image)
        pad = max(4, round(size * 8 / 64))
        draw.rounded_rectangle((pad, pad, size - pad - 1, size - pad - 1), radius=radius, fill=(21, 94, 239, 255))
        try:
            font = ImageFont.truetype("arialbd.ttf", max(12, round(size * 30 / 64)))
        except Exception:
            font = ImageFont.load_default()
        box = draw.textbbox((0, 0), "L", font=font)
        draw.text(
            ((size - (box[2] - box[0])) / 2, (size - (box[3] - box[1])) / 2 - 2),
            "L",
            font=font,
            fill=(255, 255, 255, 255),
        )

    if status:
        palette = {
            "Online": (33, 180, 92, 255),
            "Connecting": (245, 166, 35, 255),
            "Reconnecting": (245, 166, 35, 255),
            "Disconnected": (120, 126, 137, 255),
            "Offline": (120, 126, 137, 255),
        }
        outer = round(size * 18 / 64)
        inner = round(size * 11 / 64)
        cx = round(size * 54.5 / 64)
        cy = cx
        draw = ImageDraw.Draw(image)
        draw.ellipse((cx - outer // 2, cy - outer // 2, cx + outer // 2, cy + outer // 2), fill=(255, 255, 255, 255))
        draw.ellipse((cx - inner // 2, cy - inner // 2, cx + inner // 2, cy + inner // 2), fill=palette.get(status, palette["Offline"]))
    return image
