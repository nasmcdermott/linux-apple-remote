import QtQuick
import QtQuick.Window

Window {
    id: window

    width: 360
    height: 180
    visible: true
    color: "transparent"
    flags: Qt.FramelessWindowHint
        | Qt.WindowStaysOnTopHint
        | Qt.WindowTransparentForInput
        | Qt.WindowDoesNotAcceptFocus
        | Qt.Tool
    visibility: mode === "fullscreen" ? Window.FullScreen : Window.Windowed
    x: mode === "window" ? screen.width - width - 24 : 0
    y: mode === "window" ? 24 : 0

    PinCard {
        width: 360
        height: 180
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: mode === "fullscreen" ? 24 : 0
    }
}
