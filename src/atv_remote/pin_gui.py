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
    parser.add_argument("--accent", default="#4a90d9")
    parser.add_argument("--font", default="Noto Sans")
    parser.add_argument("--dark", type=int, default=1)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        from PySide6.QtCore import QMargins, QTimer, QUrl
        from PySide6.QtGui import QColor, QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
    except ImportError:
        print(
            "pin_gui: PySide6 is not available; install python3-pyside6",
            file=sys.stderr,
        )
        return 2

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
        engine.rootContext().setContextProperty("accentColor", QColor(args.accent))
        engine.rootContext().setContextProperty("fontFamily", args.font)
        engine.rootContext().setContextProperty("isDark", bool(args.dark))
        engine.rootContext().setContextProperty("mode", args.mode)
        engine.rootContext().setContextProperty("windowMargins", QMargins(0, 24, 24, 0))
        engine.load(QUrl.fromLocalFile(str(path)))
        return bool(engine.rootObjects())

    engine = QQmlApplicationEngine()
    loaded = False
    if args.mode == "layer":
        loaded = load(engine, layer_qml)
        if not loaded:
            # Layer-shell can be unavailable (GNOME, or a non-KWin compositor).
            for obj in engine.rootObjects():
                obj.deleteLater()
            engine = QQmlApplicationEngine()
            args.mode = "fullscreen"

    if not loaded:
        if not fallback_qml.exists():
            print(f"pin_gui: missing QML: {fallback_qml}", file=sys.stderr)
            return 3
        if not load(engine, fallback_qml):
            print("pin_gui: could not load the PIN window", file=sys.stderr)
            return 4

    if args.ttl > 0:
        QTimer.singleShot(args.ttl * 1000, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
