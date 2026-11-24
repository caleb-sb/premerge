"""Render the app icon as a macOS .iconset folder (turn it into .icns with `iconutil -c icns`).

Usage: QT_QPA_PLATFORM=offscreen python tools/make_icon.py OUT.iconset [--png preview.png]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from premerge.ui import icons  # noqa: E402
from premerge.ui.theme import NIGHT  # noqa: E402

SIZES = [16, 32, 128, 256, 512]


def render(px: int) -> QImage:
    """The icon at `px`×`px`: a rounded tile with the pull-request glyph (macOS grid: 80% tile)."""
    img = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = px * 0.1
    tile = QRectF(margin, margin, px - 2 * margin, px - 2 * margin)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(NIGHT.bg_dark))
    p.drawRoundedRect(tile, tile.width() * 0.225, tile.width() * 0.225)
    glyph = int(tile.width() * 0.62)
    pm = icons.pixmap("git_pr", NIGHT.accent, glyph)
    pm.setDevicePixelRatio(1.0)
    off = (px - glyph) / 2
    p.drawPixmap(QRectF(off, off, glyph, glyph), pm, QRectF(0, 0, pm.width(), pm.height()))
    p.end()
    return img


def main() -> int:
    QApplication.instance() or QApplication(sys.argv[:1])
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for s in SIZES:
        render(s).save(str(out / f"icon_{s}x{s}.png"))
        render(s * 2).save(str(out / f"icon_{s}x{s}@2x.png"))
    if "--png" in sys.argv:
        render(512).save(sys.argv[sys.argv.index("--png") + 1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
