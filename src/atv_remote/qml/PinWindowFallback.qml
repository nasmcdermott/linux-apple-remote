import QtQuick
import QtQuick.Window

/*
 * Fallback surface for GNOME, X11 and KDE when layer-shell is unavailable or
 * when a force-blur effect (Better Blur DX, Force Blur) is active.
 *
 * In window mode the window is deliberately larger than the card.  The small
 * transparent margin is part of the window, so KWin/ShapeCorners rounds the
 * whole surface and Better Blur DX blurs that rounded area.  The card sits
 * inside it, giving the blur a soft rounded halo instead of a square fringe.
 */
Window {
    id: window

    readonly property int cardWidth: Math.round(360 * guiScale)
    readonly property int cardHeight: Math.round(180 * guiScale)
    readonly property int sideEdge: Math.round(12 * guiScale)
    readonly property int topEdge: Math.round(32 * guiScale)
    readonly property int bottomEdge: Math.round(12 * guiScale)

    width: cardWidth + 2 * sideEdge
    height: cardHeight + topEdge + bottomEdge
    visible: true
    color: "transparent"
    flags: Qt.FramelessWindowHint
        | Qt.WindowStaysOnTopHint
        | Qt.WindowTransparentForInput
        | Qt.WindowDoesNotAcceptFocus
        | Qt.NoDropShadowWindowHint
        | Qt.Tool
    visibility: mode === "fullscreen" ? Window.FullScreen : Window.Windowed
    // KWin places Wayland windows; when it does honour a position, put the
    // window at the screen's top-right corner and let the card sit inside.
    x: mode === "window" ? screen.width - width : 0
    y: 0

    PinCard {
        width: window.cardWidth
        height: window.cardHeight
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: window.topEdge
        anchors.rightMargin: window.sideEdge
        radius: guiRadius
        uiScale: guiScale
        hasBlur: guiBlur
    }
}
