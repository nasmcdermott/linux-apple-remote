#!/usr/bin/env python3
"""Tiny Qt Quick pairing-PIN card, launched by the daemon.

Run it with the *system* Python that has PySide6 (on Fedora:
``python3-pyside6``).  The daemon supplies the PIN, palette, and window mode.
It exits on its own after the TTL; the daemon kills it when pairing succeeds.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--pin", required=True)
    parser.add_argument("--ttl", type=int, default=600)
    parser.add_argument("--mode", choices=("layer", "fullscreen", "window"), default="window")
    parser.add_argument("--bg", default="#141414")
    parser.add_argument("--fg", default="#ffffff")
    parser.add_argument("--cell", default="#1f1f1f")
    parser.add_argument("--cell-fg", default="#ffffff")
    parser.add_argument("--muted", default="#a0a0a0")
    parser.add_argument("--accent", default="#4a90d9")
    parser.add_argument("--font", default="Noto Sans")
    parser.add_argument("--dark", type=int, default=1)
    parser.add_argument("--font-scale", type=float, default=1.0)
    parser.add_argument("--blur", type=int, default=0)
    parser.add_argument("--corner-radius", type=int, default=24)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args(argv)


def _enable_blur_behind(window, radius: int) -> bool:
    """Ask KWin to blur behind this window's rounded shape.

    Qt does not expose the ``org_kde_kwin_blur`` protocol, but the C entry
    point in KWindowSystem takes a QWindow and a QRegion.  This keeps the
    layer-shell surface while letting KWin (Better Blur DX, Force Blur,
    Liquid Glass) do the actual blur.  It is best-effort: on GNOME, X11 without
    KWindowSystem, or an unknown Qt build, the card simply stays translucent.
    """
    try:
        import ctypes

        import shiboken6
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainterPath, QRegion

        lib = ctypes.CDLL("libKF6WindowSystem.so.6")
        enable = lib._ZN14KWindowEffects16enableBlurBehindEP7QWindowbRK7QRegion
        enable.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_void_p]
        enable.restype = None

        path = QPainterPath()
        path.addRoundedRect(
            QRectF(0, 0, window.width(), window.height()), radius, radius
        )
        region = QRegion(path.toFillPolygon().toPolygon())
        # On X11 this clips the window (and its blur) to the rounded shape.
        # Wayland ignores it, but ShapeCorners can still clip the surface.
        try:
            window.setMask(region)
        except Exception as exc:  # noqa: BLE001 - optional X11 clipping
            print(f"pin_gui: window mask unavailable: {exc}", file=sys.stderr)
        enable(
            shiboken6.getCppPointer(window)[0],
            True,
            shiboken6.getCppPointer(region)[0],
        )
        return True
    except Exception as exc:  # noqa: BLE001 - decorative, never fatal
        print(f"pin_gui: blur request unavailable: {exc}", file=sys.stderr)
        return False


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        from PySide6.QtCore import QMargins, QTimer, QUrl
        from PySide6.QtGui import QColor, QGuiApplication, QSurfaceFormat
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuick import QQuickWindow
    except ImportError:
        print(
            "pin_gui: PySide6 is not available; install python3-pyside6",
            file=sys.stderr,
        )
        return 2

    # The card is translucent so the compositor can show its blur behind it.
    # Without an alpha buffer Qt hands the compositor an opaque black surface.
    surface_format = QSurfaceFormat()
    surface_format.setAlphaBufferSize(8)
    QSurfaceFormat.setDefaultFormat(surface_format)
    try:
        QQuickWindow.setDefaultAlphaBuffer(True)
    except AttributeError:  # very old PySide6; the card is simply opaque
        pass

    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("Apple TV Remote PIN")

    qml_dir = Path(__file__).resolve().parent / "qml"
    layer_qml = qml_dir / "PinWindowLayer.qml"
    fallback_qml = qml_dir / "PinWindowFallback.qml"

    def load(engine: QQmlApplicationEngine, path: Path):
        if args.debug:
            engine.warnings.connect(lambda ws: [print("qml:", w.toString()) for w in ws])
        engine.rootContext().setContextProperty("pin", args.pin)
        engine.rootContext().setContextProperty("bgColor", QColor(args.bg))
        engine.rootContext().setContextProperty("fgColor", QColor(args.fg))
        engine.rootContext().setContextProperty("cellColor", QColor(args.cell))
        engine.rootContext().setContextProperty("cellFgColor", QColor(args.cell_fg))
        engine.rootContext().setContextProperty("mutedColor", QColor(args.muted))
        engine.rootContext().setContextProperty("accentColor", QColor(args.accent))
        engine.rootContext().setContextProperty("fontFamily", args.font)
        engine.rootContext().setContextProperty("isDark", bool(args.dark))
        engine.rootContext().setContextProperty("mode", args.mode)
        scale = max(0.85, min(1.6, args.font_scale))
        # Prefix these so they do not collide with the PinCard's own
        # uiScale/hasBlur properties (a same-name binding loops back to self).
        engine.rootContext().setContextProperty("guiScale", scale)
        engine.rootContext().setContextProperty("guiBlur", bool(args.blur))
        engine.rootContext().setContextProperty("guiRadius", max(8, min(40, args.corner_radius)))
        margin = round(24 * scale)
        engine.rootContext().setContextProperty("windowMargins", QMargins(0, margin, margin, 0))
        engine.load(QUrl.fromLocalFile(str(path)))
        return bool(engine.rootObjects())

    engine = QQmlApplicationEngine()
    loaded = False
    if args.mode == "layer":
        loaded = load(engine, layer_qml)
        if not loaded:
            # Layer-shell can be unavailable (GNOME, or a non-KWin compositor).
            # Use a normal window rather than a full-screen overlay so KWin's
            # blur effects cannot blur the whole desktop through it.
            for obj in engine.rootObjects():
                obj.deleteLater()
            engine = QQmlApplicationEngine()
            args.mode = "window"

    if not loaded:
        if not fallback_qml.exists():
            print(f"pin_gui: missing QML: {fallback_qml}", file=sys.stderr)
            return 3
        if not load(engine, fallback_qml):
            print("pin_gui: could not load the PIN window", file=sys.stderr)
            return 4

    if args.blur:
        windows = list(engine.rootObjects())
        radius = max(8, min(40, args.corner_radius))
        if windows:
            # One event-loop turn lets the Wayland surface exist before the
            # compositor is asked for blur behind it.
            QTimer.singleShot(
                0,
                lambda: [_enable_blur_behind(window, radius) for window in windows],
            )

    if args.ttl > 0:
        QTimer.singleShot(args.ttl * 1000, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
