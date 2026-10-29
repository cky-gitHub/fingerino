// Fingerino's Home window. Layout follows the Windows 11 settings vocabulary
// (docs/ui-direction.md): a navigation pane with Settings pinned to the
// bottom, a single scrolling column capped at ~1000 px, settings as cards
// with the control on the right, and changes that apply immediately.
//
// All state comes from `bridge` (fingerino/shell.py). Nothing here keeps
// state of its own beyond which page is showing.

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: win

    required property QtObject bridge
    property int page: 0
    readonly property bool onWindows: Qt.platform.os === "windows"
    // Segoe Fluent Icons ships with Windows 11; MDL2 Assets is the Windows 10
    // fallback with the same code points. Elsewhere the glyphs are left out.
    readonly property string iconFont: "Segoe Fluent Icons, Segoe MDL2 Assets"

    width: 980
    height: 660
    minimumWidth: 720
    minimumHeight: 480
    visible: false
    title: "Fingerino"

    // Hides the window; Fingerino quits too if tracking is off (shell.py).
    onClosing: bridge.homeClosed()

    // Centred, so the HUD pinned to the top-left corner doesn't cover it.
    Component.onCompleted: {
        x = Screen.virtualX + (Screen.width - width) / 2
        y = Screen.virtualY + (Screen.height - height) / 2
    }

    // ---- reusable pieces ----------------------------------------------------

    component NavItem: ItemDelegate {
        id: nav
        required property int index
        property string glyph
        Layout.fillWidth: true
        highlighted: win.page === index
        onClicked: win.page = index
        contentItem: RowLayout {
            spacing: 12
            Label {
                visible: win.onWindows && nav.glyph !== ""
                text: nav.glyph
                font.family: win.iconFont
                font.pixelSize: 16
            }
            Label {
                text: nav.text
                Layout.fillWidth: true
            }
        }
    }

    // A settings card: title and description on the left, a control on the
    // right. Matches the SettingsCard control in the Windows Community Toolkit.
    component Card: Frame {
        id: card
        property string title
        property string description
        property alias image: pic.source
        default property alias control: slot.data
        Layout.fillWidth: true
        padding: 16
        RowLayout {
            anchors.fill: parent
            spacing: 16
            Image {
                id: pic
                visible: source != ""
                Layout.preferredWidth: 48
                Layout.preferredHeight: 48
                sourceSize.width: 96
                sourceSize.height: 96
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Label {
                    text: card.title
                    font.pixelSize: 14
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                }
                Label {
                    visible: card.description !== ""
                    text: card.description
                    opacity: 0.7
                    font.pixelSize: 12
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                }
            }
            Item {
                id: slot
                implicitWidth: childrenRect.width
                implicitHeight: childrenRect.height
            }
        }
    }

    component SectionHeader: Label {
        font.pixelSize: 14
        font.weight: Font.DemiBold
        topPadding: 16
        bottomPadding: 4
    }

    component PageTitle: Label {
        font.pixelSize: 28
        font.weight: Font.DemiBold
        bottomPadding: 8
    }

    // A scrolling page whose content column stops growing at ~1000 px, so
    // lines stay readable on wide windows.
    component Page_: ScrollView {
        id: scroller
        default property alias content: column.data
        contentWidth: availableWidth
        clip: true
        ColumnLayout {
            id: column
            width: Math.min(scroller.availableWidth - 64, 1000)
            x: 32
            spacing: 4
            Item { implicitHeight: 24 }
        }
    }

    // ---- layout -------------------------------------------------------------

    RowLayout {
        anchors.fill: parent
        spacing: 0

        ColumnLayout {
            Layout.preferredWidth: 240
            Layout.fillHeight: true
            Layout.margins: 8
            spacing: 2

            // The window title already says Fingerino; just leave breathing room.
            Item { implicitHeight: 8 }
            NavItem { index: 0; text: "Home"; glyph: "" }
            NavItem { index: 1; text: "Gestures"; glyph: "" }
            Item { Layout.fillHeight: true }
            NavItem { index: 2; text: "Settings"; glyph: "" }
        }

        // Hairline between the navigation and the page.
        Rectangle {
            Layout.fillHeight: true
            implicitWidth: 1
            color: win.palette.windowText
            opacity: 0.12
        }

        StackLayout {
            currentIndex: win.page
            Layout.fillWidth: true
            Layout.fillHeight: true

            // ---- Home -------------------------------------------------------
            Page_ {
                PageTitle { text: "Home" }

                Frame {
                    visible: !win.bridge.onboarded
                    Layout.fillWidth: true
                    padding: 16
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 8
                        Label {
                            text: "Welcome to Fingerino"
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }
                        Label {
                            Layout.fillWidth: true
                            wrapMode: Text.WordWrap
                            font.pixelSize: 12
                            opacity: 0.7
                            text: "Press Start, then hold one hand up in front of your camera. "
                                + "Steer the pointer with your thumb and point your index finger "
                                + "to click. The Gestures page has the rest.\n\n"
                                + "Your camera stays off until you press Start, and your video "
                                + "is processed on this computer and never leaves it."
                        }
                        Button {
                            text: "Got it"
                            highlighted: true
                            onClicked: win.bridge.dismissWelcome()
                        }
                    }
                }

                Frame {
                    Layout.fillWidth: true
                    padding: 16
                    RowLayout {
                        anchors.fill: parent
                        spacing: 16
                        Rectangle {
                            width: 10
                            height: 10
                            radius: 5
                            color: !win.bridge.running ? "#9a9a9a"
                                 : win.bridge.paused ? "#9a9a9a"
                                 : win.bridge.handSeen ? "#3fb950" : "#d29922"
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Label {
                                text: !win.bridge.running ? "Fingerino is off"
                                    : win.bridge.paused ? "Paused"
                                    : win.bridge.handSeen ? "Tracking your hand"
                                    : "Waiting for your hand"
                                font.pixelSize: 14
                            }
                            Label {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                opacity: 0.7
                                font.pixelSize: 12
                                text: !win.bridge.running
                                    ? "The camera is off. Press Start when you're ready."
                                    : win.bridge.paused
                                    ? "Gestures are off. Resume here, with "
                                      + win.bridge.hotkey + ", or with both palms up."
                                    : win.bridge.handSeen
                                    ? "Gestures are live."
                                    : "Hold one hand up in front of the camera."
                            }
                            Label {
                                visible: win.bridge.error !== ""
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                font.pixelSize: 12
                                color: "#f85149"
                                text: win.bridge.error
                            }
                        }
                        Button {
                            visible: !win.bridge.running
                            text: "Start"
                            highlighted: true
                            onClicked: win.bridge.start()
                        }
                        Button {
                            visible: win.bridge.running && win.bridge.previewHidden
                            text: "Show preview"
                            onClicked: win.bridge.showPreview()
                        }
                        Button {
                            visible: win.bridge.running
                            text: win.bridge.paused ? "Resume" : "Pause"
                            onClicked: win.bridge.togglePause()
                        }
                        Button {
                            visible: win.bridge.running
                            highlighted: true
                            text: "✕  Stop"
                            Accessible.name: "Stop Fingerino"
                            onClicked: win.bridge.stop()
                        }
                    }
                }

                SectionHeader { text: "Good to know" }
                Card {
                    title: "Pause from anywhere"
                    description: "Press " + win.bridge.hotkey
                        + " in any app to pause or resume gestures."
                }
                Card {
                    title: "Your video stays here"
                    description: "Hand tracking runs on this computer. Nothing is "
                        + "recorded or sent anywhere."
                    Button {
                        text: "Privacy details"
                        onClicked: win.bridge.openRepo("#privacy")
                    }
                }
                Item { implicitHeight: 24 }
            }

            // ---- Gestures ---------------------------------------------------
            Page_ {
                PageTitle { text: "Gestures" }
                Label {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    opacity: 0.7
                    text: "Turn off any gesture you don't want. Changes apply "
                        + "immediately, even while tracking, and are remembered."
                }

                Repeater {
                    model: win.bridge.groups
                    delegate: ColumnLayout {
                        id: group
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 4
                        SectionHeader { text: group.modelData.name }
                        Repeater {
                            model: group.modelData.rows
                            delegate: Card {
                                id: row
                                required property var modelData
                                title: modelData.label
                                description: modelData.desc
                                image: modelData.image
                                Switch {
                                    checked: win.bridge.gestureEnabled(row.modelData.icon)
                                    onToggled: win.bridge.setGestureEnabled(
                                        row.modelData.icon, checked)
                                    Accessible.name: row.modelData.label
                                }
                            }
                        }
                    }
                }

                // Premium, announced but not sold yet. Switching gestures on
                // and off stays free: it is an accessibility feature
                // (docs/ui-direction.md, section 5).
                SectionHeader { text: "Your own gestures" }
                Card {
                    title: "Custom gestures"
                    description: "Give any gesture a different job, such as a keyboard "
                        + "shortcut, opening an app or media keys, and teach "
                        + "Fingerino new hand shapes."
                    RowLayout {
                        spacing: 12
                        Label {
                            text: "Premium"
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                            color: win.palette.highlightedText
                            leftPadding: 8
                            rightPadding: 8
                            topPadding: 3
                            bottomPadding: 3
                            background: Rectangle {
                                radius: 4
                                color: win.palette.highlight
                            }
                        }
                        Button {
                            text: "Coming soon"
                            enabled: false
                        }
                    }
                }
                Item { implicitHeight: 24 }
            }

            // ---- Settings ---------------------------------------------------
            Page_ {
                PageTitle { text: "Settings" }

                SectionHeader { text: "Tracking" }
                Card {
                    title: "Start tracking when Fingerino opens"
                    description: "Off: Fingerino opens with the camera off until you press Start."
                    Switch {
                        checked: win.bridge.startOnOpen
                        onToggled: win.bridge.setStartOnOpen(checked)
                        Accessible.name: "Start tracking when Fingerino opens"
                    }
                }
                Card {
                    title: "Keyboard shortcut"
                    description: "Pauses or resumes gestures from any app."
                    Label {
                        text: win.bridge.hotkey
                        font.weight: Font.DemiBold
                    }
                }

                SectionHeader { text: "Data" }
                Card {
                    title: "Fingerino's folder"
                    description: "Settings, the hand model, and reports from "
                        + "--selftest or a crash. Nothing in it is sent anywhere."
                    Button {
                        text: "Open folder"
                        onClicked: win.bridge.openDataFolder()
                    }
                }

                SectionHeader { text: "About" }
                Card {
                    title: "Fingerino " + win.bridge.version
                    description: "Control your computer with hand gestures."
                    Button {
                        text: "Website"
                        onClicked: win.bridge.openRepo("")
                    }
                }
                Card {
                    title: "Report a problem"
                    description: "Opens the bug report form on GitHub."
                    Button {
                        text: "Report"
                        onClicked: win.bridge.openRepo("/issues/new/choose")
                    }
                }
                Card {
                    title: "Third-party licences"
                    description: "The open-source components Fingerino is built on."
                    Button {
                        text: "View"
                        onClicked: win.bridge.openNotices()
                    }
                }
                Card {
                    title: "Quit Fingerino"
                    description: "Stops tracking and closes Fingerino completely."
                    Button {
                        text: "Quit"
                        onClicked: win.bridge.quit()
                    }
                }
                Item { implicitHeight: 24 }
            }
        }
    }
}
