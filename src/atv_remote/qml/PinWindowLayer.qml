import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell

Window {
    id: window

    width: 360
    height: 180
    visible: true
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus

    LayerShell.Window.scope: "apple-tv-remote-pin"
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorRight
    LayerShell.Window.margins: windowMargins
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.wantsToBeOnActiveScreen: true

    PinCard {
        anchors.fill: parent
    }
}
