import QtQuick
import QtQuick.Layouts

Item {
    id: root

    property int radius: 24

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
        color: Qt.rgba(bgColor.r, bgColor.g, bgColor.b, isDark ? 0.44 : 0.62)
        border.width: 1
        border.color: isDark ? Qt.rgba(1, 1, 1, 0.28) : Qt.rgba(0, 0, 0, 0.12)

        // Lighter glass wash from top-left to bottom-right.
        Rectangle {
            anchors.fill: parent
            radius: card.radius
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, isDark ? 0.32 : 0.72) }
                GradientStop { position: 0.45; color: Qt.rgba(1, 1, 1, isDark ? 0.14 : 0.24) }
                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, isDark ? 0.05 : 0.04) }
            }
        }

        // Subtle liquid sheen travelling across the glass.
        Rectangle {
            width: card.width * 0.65
            height: card.height * 2.2
            x: -card.width * 0.9
            y: -card.height * 0.55
            rotation: 18
            opacity: 0.55
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.0) }
                GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, isDark ? 0.06 : 0.22) }
                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.0) }
            }
            NumberAnimation on x {
                from: -card.width * 0.9
                to: card.width * 1.25
                duration: 9000
                loops: Animation.Infinite
                easing.type: Easing.InOutSine
            }
        }

        // Hairline highlight along the top edge.
        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: 1
            color: Qt.rgba(1, 1, 1, isDark ? 0.35 : 0.80)
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 22
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Item {
                    Layout.preferredWidth: 36
                    Layout.preferredHeight: 36

                    Rectangle {
                        anchors.fill: parent
                        radius: 12
                        color: Qt.rgba(accentColor.r, accentColor.g, accentColor.b, isDark ? 0.18 : 0.14)
                        border.width: 1
                        border.color: Qt.rgba(accentColor.r, accentColor.g, accentColor.b, 0.28)
                    }

                    // Small television glyph, drawn so it does not depend on an icon theme.
                    Rectangle {
                        width: 21
                        height: 14
                        radius: 3
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: -2
                        color: "transparent"
                        border.width: 1.5
                        border.color: accentColor
                    }
                    Rectangle {
                        width: 11
                        height: 1.5
                        radius: 1
                        color: accentColor
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 7
                    }
                    Rectangle {
                        width: 3
                        height: 1.5
                        radius: 1
                        color: accentColor
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 4.5
                    }
                }

                ColumnLayout {
                    spacing: 1
                    Text {
                        text: "Apple TV Remote"
                        color: fgColor
                        font.family: fontFamily
                        font.pixelSize: 15
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: "PAIRING"
                        color: accentColor
                        font.family: fontFamily
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 1.8
                    }
                }

                Item { Layout.fillWidth: true }

                RowLayout {
                    spacing: 6
                    Rectangle {
                        Layout.preferredWidth: 7
                        Layout.preferredHeight: 7
                        radius: 3.5
                        color: accentColor
                        SequentialAnimation on opacity {
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.25; duration: 900; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 0.95; duration: 900; easing.type: Easing.InOutSine }
                        }
                    }
                    Text {
                        text: "Waiting"
                        color: Qt.rgba(fgColor.r, fgColor.g, fgColor.b, 0.62)
                        font.family: fontFamily
                        font.pixelSize: 10
                    }
                }
            }

            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                spacing: 10

                Repeater {
                    model: pin.length
                    delegate: Rectangle {
                        Layout.preferredWidth: 52
                        Layout.preferredHeight: 58
                        radius: 14
                        color: isDark ? Qt.rgba(1, 1, 1, 0.10) : Qt.rgba(1, 1, 1, 0.55)
                        border.width: 1
                        border.color: isDark ? Qt.rgba(1, 1, 1, 0.24) : Qt.rgba(0, 0, 0, 0.08)

                        Text {
                            anchors.centerIn: parent
                            text: pin.charAt(index)
                            color: fgColor
                            font.family: fontFamily
                            font.pixelSize: 30
                            font.weight: Font.DemiBold
                        }
                    }
                }
            }

            Item { Layout.fillHeight: true }

            Text {
                Layout.alignment: Qt.AlignHCenter
                text: "Enter this PIN on your iPhone"
                color: Qt.rgba(fgColor.r, fgColor.g, fgColor.b, 0.62)
                font.family: fontFamily
                font.pixelSize: 11
            }
        }
    }
}
