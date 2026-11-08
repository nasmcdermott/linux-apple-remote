import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell

Window {
    id: window

    width: Math.round(360 * guiScale)
    height: Math.round(180 * guiScale)
    visible: true
    color: "transparent"
    flags: Qt.FramelessWindowHint
        | Qt.WindowTransparentForInput
        | Qt.WindowDoesNotAcceptFocus
        | Qt.NoDropShadowWindowHint

    LayerShell.Window.scope: "apple-tv-remote-pin"
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorRight
    LayerShell.Window.margins: windowMargins
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.wantsToBeOnActiveScreen: true

    PinCard {
        anchors.fill: parent
        radius: guiRadius
        uiScale: guiScale
        hasBlur: guiBlur
    }
}
