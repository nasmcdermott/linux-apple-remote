import QtQuick
import QtQuick.Layouts

/*
 * Pairing PIN card.
 *
 * The card is deliberately a plain translucent surface: the compositor owns
 * the backdrop blur.  KWin effects such as Better Blur DX, Force Blur, Blur
 * Plus, Liquid Glass and ShapeCorners all pick the surface up as a normal
 * window, so the blur follows the card's rounded outline when those effects
 * round the window.  There is no painted-in white sheen to fight them.
 *
 * `hasBlur` is supplied by the launcher after reading kwinrc.  Without a
 * compositor blur effect the card falls back to a nearly opaque fill so the
 * PIN stays legible on GNOME, sway, X11 and plain TTY sessions.
 *
 * The glow is drawn *inside* the card bounds.  That keeps the compositor's
 * blur region exactly the size of the surface (no square halo) and lets the
 * ring keep a constant width while its opacity breathes.
 */
Item {
    id: root

    property int radius: 24
    property real uiScale: 1.0
    property bool hasBlur: false

    readonly property real s: Math.max(0.85, Math.min(1.6, uiScale))
    readonly property color textOutline: isDark
        ? Qt.rgba(0, 0, 0, 0.30)
        : Qt.rgba(1, 1, 1, 0.55)
    // Lift the dark card a little above a dark backdrop, and follow the
    // desktop's button colour for the PIN cells (like Breeze buttons).
    readonly property color cardTint: isDark ? Qt.lighter(bgColor, 1.35) : bgColor
    readonly property color cellTint: isDark ? Qt.lighter(cellColor, 2.0) : cellColor

    function px(value) {
        return Math.round(value * root.s)
    }

    opacity: 0.0
    scale: 0.97
    transformOrigin: Item.TopRight

    ParallelAnimation {
        id: intro
        NumberAnimation {
            target: root
            property: "opacity"
            from: 0.0
            to: 1.0
            duration: 220
            easing.type: Easing.OutCubic
        }
        NumberAnimation {
            target: root
            property: "scale"
            from: 0.97
            to: 1.0
            duration: 280
            easing.type: Easing.OutBack
        }
    }

    Component.onCompleted: intro.start()

    Rectangle {
        id: card
        anchors.fill: parent
        radius: root.radius
        clip: true
        antialiasing: true
        color: Qt.rgba(
            root.cardTint.r,
            root.cardTint.g,
            root.cardTint.b,
            root.hasBlur ? (isDark ? 0.32 : 0.46) : (isDark ? 0.90 : 0.94))
        border.width: 1
        border.color: isDark ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(0, 0, 0, 0.08)

        // Pulsing system-accent glow.  Three constant-width rings make a soft
        // inner halo; the group opacity breathes, so the line never thins.
        Item {
            id: glow
            anchors.fill: parent
            opacity: 0.55
            SequentialAnimation on opacity {
                loops: Animation.Infinite
                NumberAnimation {
                    to: 0.92
                    duration: 2100
                    easing.type: Easing.InOutSine
                }
                NumberAnimation {
                    to: 0.55
                    duration: 2100
                    easing.type: Easing.InOutSine
                }
            }

            Rectangle {
                anchors.fill: parent
                anchors.margins: 1
                radius: Math.max(0, card.radius - 1)
                color: "transparent"
                border.width: Math.max(1, root.px(1.2))
                border.color: accentColor
                opacity: 0.72
                antialiasing: true
            }

            Rectangle {
                anchors.fill: parent
                anchors.margins: 1
                radius: Math.max(0, card.radius - 1)
                color: "transparent"
                border.width: root.px(4)
                border.color: Qt.rgba(accentColor.r, accentColor.g, accentColor.b, 0.26)
                opacity: 0.24
                antialiasing: true
            }

            Rectangle {
                anchors.fill: parent
                anchors.margins: 2
                radius: Math.max(0, card.radius - 2)
                color: "transparent"
                border.width: root.px(9)
                border.color: Qt.rgba(accentColor.r, accentColor.g, accentColor.b, 0.10)
                opacity: 0.12
                antialiasing: true
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: root.px(22)
            spacing: root.px(8)

            RowLayout {
                Layout.fillWidth: true
                spacing: root.px(12)

                Item {
                    Layout.preferredWidth: root.px(36)
                    Layout.preferredHeight: root.px(36)

                    Rectangle {
                        anchors.fill: parent
                        radius: root.px(12)
                        color: Qt.rgba(accentColor.r, accentColor.g, accentColor.b, isDark ? 0.18 : 0.14)
                        border.width: 1
                        border.color: Qt.rgba(accentColor.r, accentColor.g, accentColor.b, 0.28)
                        antialiasing: true
                    }

                    // Small television glyph, drawn so it does not depend on an icon theme.
                    Rectangle {
                        width: root.px(21)
                        height: root.px(14)
                        radius: root.px(3)
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: root.px(-2)
                        color: "transparent"
                        border.width: Math.max(1, root.px(1.5))
                        border.color: accentColor
                        antialiasing: true
                    }
                    Rectangle {
                        width: root.px(11)
                        height: Math.max(1, root.px(1.5))
                        radius: Math.max(1, root.px(1))
                        color: accentColor
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: root.px(7)
                    }
                    Rectangle {
                        width: root.px(3)
                        height: Math.max(1, root.px(1.5))
                        radius: Math.max(1, root.px(1))
                        color: accentColor
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: root.px(4.5)
                    }
                }

                ColumnLayout {
                    spacing: root.px(1)
                    Text {
                        text: "Apple TV Remote"
                        color: fgColor
                        style: Text.Outline
                        styleColor: root.textOutline
                        font.family: fontFamily
                        font.pixelSize: root.px(15)
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: "PAIRING"
                        color: accentColor
                        font.family: fontFamily
                        font.pixelSize: root.px(9)
                        font.weight: Font.Bold
                        font.letterSpacing: root.px(1.8)
                    }
                }

                Item { Layout.fillWidth: true }

                RowLayout {
                    spacing: root.px(6)
                    Rectangle {
                        Layout.preferredWidth: root.px(7)
                        Layout.preferredHeight: root.px(7)
                        radius: root.px(3.5)
                        color: accentColor
                        antialiasing: true
                        SequentialAnimation on opacity {
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.25; duration: 900; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 0.95; duration: 900; easing.type: Easing.InOutSine }
                        }
                    }
                    Text {
                        text: "Waiting"
                        color: mutedColor
                        style: Text.Outline
                        styleColor: root.textOutline
                        font.family: fontFamily
                        font.pixelSize: root.px(10)
                    }
                }
            }

            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                spacing: root.px(10)

                Repeater {
                    model: pin.length
                    delegate: Rectangle {
                        Layout.preferredWidth: root.px(52)
                        Layout.preferredHeight: root.px(58)
                        radius: root.px(14)
                        color: Qt.rgba(
                            root.cellTint.r,
                            root.cellTint.g,
                            root.cellTint.b,
                            isDark ? 0.65 : 0.88)
                        border.width: 1
                        border.color: Qt.rgba(
                            cellFgColor.r,
                            cellFgColor.g,
                            cellFgColor.b,
                            isDark ? 0.22 : 0.10)
                        antialiasing: true

                        Text {
                            anchors.centerIn: parent
                            text: pin.charAt(index)
                            color: cellFgColor
                            font.family: fontFamily
                            font.pixelSize: root.px(30)
                            font.weight: Font.DemiBold
                        }
                    }
                }
            }

            Item { Layout.fillHeight: true }

            Text {
                Layout.alignment: Qt.AlignHCenter
                text: "Enter this PIN on your iPhone"
                color: mutedColor
                style: Text.Outline
                styleColor: root.textOutline
                font.family: fontFamily
                font.pixelSize: root.px(11)
            }
        }
    }
}
