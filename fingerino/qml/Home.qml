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
import QtQuick.Dialogs

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

    // ---- what a sign does ---------------------------------------------------

    // One editor for every sign: pick a kind of action, fill in its one
    // field, try it, save. Saving applies at once, even while tracking.
    Dialog {
        id: actionEditor
        property string sign
        property string kind: "builtin"
        property string target: ""
        anchors.centerIn: parent
        width: Math.min(win.width - 64, 520)
        modal: true
        title: "What should this sign do?"
        padding: 20

        function edit(sign, how) {
            var info = win.bridge.actionInfo(sign)
            actionEditor.sign = sign
            howLabel.text = how
            kind = info.kind === "" ? "builtin" : info.kind
            target = info.target
            nameField.text = info.name
            message.text = ""
            kindBox.currentIndex = kindBox.indexOfValue(kind)
            builtinBox.currentIndex = Math.max(0, builtinBox.indexOfValue(target))
            mediaBox.currentIndex = Math.max(0, mediaBox.indexOfValue(target))
            keysField.text = kind === "hotkey" ? win.bridge.comboLabel(target) : ""
            pathField.text = (kind === "open_app" || kind === "open") ? target : ""
            commandField.text = kind === "command" ? target : ""
            open()
        }

        function currentTarget() {
            switch (kind) {
            case "builtin": return builtinBox.currentValue
            case "hotkey": return keysField.text
            case "media": return mediaBox.currentValue
            case "command": return commandField.text
            default: return pathField.text
            }
        }

        FileDialog {
            id: fileDialog
            title: actionEditor.kind === "open_app" ? "Choose an app" : "Choose a file"
            onAccepted: {
                var path = decodeURIComponent(selectedFile.toString().replace(
                    /^file:\/{2}/, ""))
                // file:///C:/x -> C:/x on Windows; file:///home/x -> /home/x elsewhere.
                if (/^\/[A-Za-z]:/.test(path))
                    path = path.substring(1)
                pathField.text = path
            }
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 10

            Label {
                id: howLabel
                opacity: 0.7
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
            ComboBox {
                id: kindBox
                Layout.fillWidth: true
                model: win.bridge.actionKinds
                textRole: "label"
                valueRole: "kind"
                Accessible.name: "Kind of action"
                onActivated: { actionEditor.kind = currentValue; message.text = "" }
            }
            ComboBox {
                id: builtinBox
                visible: actionEditor.kind === "builtin"
                Layout.fillWidth: true
                model: win.bridge.builtinActions
                textRole: "label"
                valueRole: "id"
                Accessible.name: "Fingerino action"
            }
            // A recorder, not a text field (ui-direction section 5): click,
            // press the shortcut, done.
            TextField {
                id: keysField
                visible: actionEditor.kind === "hotkey"
                Layout.fillWidth: true
                readOnly: true
                placeholderText: "Click here, then press the shortcut"
                Accessible.name: "Keyboard shortcut"
                Keys.onPressed: (event) => {
                    var combo = win.bridge.comboFromKey(event.key, event.modifiers)
                    if (combo !== "")
                        text = combo
                    event.accepted = true
                }
            }
            ComboBox {
                id: mediaBox
                visible: actionEditor.kind === "media"
                Layout.fillWidth: true
                model: win.bridge.mediaKeys
                textRole: "label"
                valueRole: "id"
                Accessible.name: "Media key"
            }
            RowLayout {
                visible: actionEditor.kind === "open_app" || actionEditor.kind === "open"
                Layout.fillWidth: true
                TextField {
                    id: pathField
                    Layout.fillWidth: true
                    placeholderText: actionEditor.kind === "open_app"
                        ? "The app to open" : "https://… or a file"
                    Accessible.name: actionEditor.kind === "open_app"
                        ? "App to open" : "Web address or file"
                }
                Button {
                    text: "Browse…"
                    onClicked: fileDialog.open()
                }
            }
            TextField {
                id: commandField
                visible: actionEditor.kind === "command"
                Layout.fillWidth: true
                placeholderText: "The command to run"
                font.family: "monospace"
                Accessible.name: "Command to run"
            }
            Label {
                visible: actionEditor.kind === "command"
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                font.pixelSize: 12
                opacity: 0.7
                text: "Runs exactly as typed, through your system's shell, each time "
                    + "the sign is made. Only use a command you trust."
            }
            TextField {
                id: nameField
                visible: actionEditor.kind !== "builtin"
                Layout.fillWidth: true
                placeholderText: "Name on screen (optional)"
                Accessible.name: "Name on screen"
            }
            Label {
                id: message
                visible: text !== ""
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                font.pixelSize: 12
                color: "#f85149"
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 8
                spacing: 8
                Button {
                    text: "Try it"
                    onClicked: message.text = win.bridge.testAction(
                        actionEditor.kind, actionEditor.currentTarget(), nameField.text)
                }
                Button {
                    text: "Reset"
                    Accessible.name: "Reset to what this sign did originally"
                    onClicked: { win.bridge.resetAction(actionEditor.sign); actionEditor.close() }
                }
                Button {
                    text: "Do nothing"
                    onClicked: { win.bridge.clearAction(actionEditor.sign); actionEditor.close() }
                }
                Item { Layout.fillWidth: true }
                Button {
                    text: "Cancel"
                    onClicked: actionEditor.close()
                }
                Button {
                    text: "Save"
                    highlighted: true
                    onClicked: {
                        var err = win.bridge.setAction(actionEditor.sign, actionEditor.kind,
                                                       actionEditor.currentTarget(),
                                                       nameField.text)
                        if (err === "")
                            actionEditor.close()
                        else
                            message.text = err
                    }
                }
            }
        }
    }

    // ---- recording a sign ---------------------------------------------------

    Dialog {
        id: recordDialog
        property int countdown: 0
        readonly property string phase: countdown > 0 ? "countdown"
            : win.bridge.recordState === "idle" ? "intro" : win.bridge.recordState
        anchors.centerIn: parent
        width: Math.min(win.width - 64, 520)
        modal: true
        title: "Record a sign"
        padding: 20

        function begin() {
            win.bridge.cancelRecording()
            countdown = 0
            signName.text = ""
            saveError.text = ""
            open()
        }
        function startCountdown() {
            // The camera needs a moment to open; the countdown covers it.
            if (!win.bridge.running)
                win.bridge.start()
            saveError.text = ""
            win.bridge.holdGestures(true)    // the hand is busy; nothing should fire
            win.bridge.cancelRecording()
            countdown = win.bridge.recordCountdown
            countdownTimer.start()
        }
        onClosed: {
            countdownTimer.stop()
            countdown = 0
            win.bridge.holdGestures(false)
            win.bridge.cancelRecording()
        }

        Timer {
            id: countdownTimer
            interval: 1000
            repeat: true
            onTriggered: {
                recordDialog.countdown -= 1
                if (recordDialog.countdown <= 0) {
                    stop()
                    win.bridge.captureSign()
                }
            }
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 10

            Label {
                visible: recordDialog.phase === "intro"
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: "Make the sign with one hand where the camera can see it, and hold it for "
                    + win.bridge.recordSeconds + " seconds. While you hold it, tilt it a "
                    + "little and move it nearer and farther, so Fingerino learns its range.\n\n"
                    + "Only the positions of your finger joints are kept, never a picture."
            }
            Label {
                visible: recordDialog.phase === "countdown"
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                font.pixelSize: 28
                text: "Get ready\u2026 " + recordDialog.countdown
            }
            Label {
                visible: recordDialog.phase === "capturing"
                text: "Hold the sign\u2026"
                font.pixelSize: 16
            }
            ProgressBar {
                visible: recordDialog.phase === "capturing"
                Layout.fillWidth: true
                value: win.bridge.recordProgress
            }
            Label {
                visible: recordDialog.phase === "failed"
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: "#f85149"
                text: win.bridge.recordMessage
            }
            Label {
                visible: recordDialog.phase === "review"
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: "Got it. Give your sign a name."
            }
            Label {
                visible: recordDialog.phase === "review" && win.bridge.recordWarning !== ""
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                font.pixelSize: 12
                color: "#d29922"
                text: win.bridge.recordWarning
            }
            TextField {
                id: signName
                visible: recordDialog.phase === "review"
                Layout.fillWidth: true
                placeholderText: "e.g. Thumbs up"
                maximumLength: 40
                Accessible.name: "Sign name"
                onAccepted: saveButton.clicked()
            }
            Label {
                id: saveError
                visible: text !== ""
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                font.pixelSize: 12
                color: "#f85149"
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 8
                spacing: 8
                Button {
                    visible: recordDialog.phase === "review"
                    text: "Record again"
                    onClicked: recordDialog.startCountdown()
                }
                Item { Layout.fillWidth: true }
                Button {
                    text: "Cancel"
                    onClicked: recordDialog.close()
                }
                Button {
                    visible: recordDialog.phase === "intro" || recordDialog.phase === "failed"
                    text: recordDialog.phase === "failed" ? "Try again" : "Start recording"
                    highlighted: true
                    onClicked: recordDialog.startCountdown()
                }
                Button {
                    id: saveButton
                    visible: recordDialog.phase === "review"
                    text: "Save and choose what it does"
                    highlighted: true
                    onClicked: {
                        var name = signName.text
                        var r = win.bridge.saveSign(name)
                        if (r.error) {
                            saveError.text = r.error
                            return
                        }
                        recordDialog.close()
                        actionEditor.edit(r.id, "When you make \u201c" + name.trim() + "\u201d")
                    }
                }
            }
        }
    }

    Dialog {
        id: renameDialog
        property string signId
        anchors.centerIn: parent
        width: Math.min(win.width - 64, 420)
        modal: true
        title: "Rename sign"
        standardButtons: Dialog.Save | Dialog.Cancel
        function ask(id, name) { signId = id; renameField.text = name; open() }
        onAccepted: if (renameField.text.trim() !== "")
                        win.bridge.renameSign(signId, renameField.text)
        TextField {
            id: renameField
            width: parent.width
            maximumLength: 40
            Accessible.name: "Sign name"
        }
    }

    Dialog {
        id: deleteDialog
        property string signId
        property string signName
        anchors.centerIn: parent
        width: Math.min(win.width - 64, 420)
        modal: true
        title: "Delete \u201c" + signName + "\u201d?"
        standardButtons: Dialog.Ok | Dialog.Cancel
        function ask(id, name) { signId = id; signName = name; open() }
        onAccepted: win.bridge.deleteSign(signId)
        Label {
            width: parent.width
            wrapMode: Text.WordWrap
            text: "The sign and what it does are removed. This can't be undone."
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
                            text: "Press Start, then hold one hand up in front of your camera "
                                + "and make a shaka (thumb and little finger out) to try a sign. "
                                + "The Gestures page lists the rest, lets you change what each "
                                + "sign does, and has the switch for controlling the cursor.\n\n"
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
                    text: "Turn off any gesture you don't want, or press Change to give a "
                        + "sign a different job: a shortcut, a media key, an app, a website "
                        + "or a command. Changes apply immediately, even while tracking, "
                        + "and are remembered."
                }

                Repeater {
                    model: win.bridge.groups
                    delegate: ColumnLayout {
                        id: group
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 4
                        SectionHeader { text: group.modelData.name }
                        // The cursor module's master switch, at the head of
                        // the group it controls. Off by default.
                        Card {
                            visible: group.modelData.cursor
                            title: "Control the cursor with your hand"
                            description: win.bridge.cursorEnabled
                                ? "On: your hand moves the pointer, clicks, drags and scrolls."
                                : "Off: Fingerino never moves the mouse, and pointing or two "
                                  + "fingers are free to use as your own signs."
                            Switch {
                                checked: win.bridge.cursorEnabled
                                onToggled: win.bridge.setCursorEnabled(checked)
                                Accessible.name: "Control the cursor with your hand"
                            }
                        }
                        Repeater {
                            model: group.modelData.rows
                            delegate: Card {
                                id: row
                                required property var modelData
                                // Shown, not hidden, while the cursor is off,
                                // and greyed out to say why (ui-direction 6.3).
                                enabled: !modelData.cursor || win.bridge.cursorEnabled
                                // A sign's card is titled by what it does now,
                                // which the user may have changed.
                                title: modelData.sign
                                    ? (win.bridge.bindingsVersion,
                                       win.bridge.actionInfo(modelData.icon).label)
                                    : modelData.label
                                description: modelData.desc
                                image: modelData.image
                                RowLayout {
                                    spacing: 12
                                    Button {
                                        visible: row.modelData.sign
                                        text: "Change"
                                        Accessible.name: "Change what " + row.modelData.desc
                                            + " does"
                                        onClicked: actionEditor.edit(row.modelData.icon,
                                                                     row.modelData.desc)
                                    }
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
                }

                // ---- the user's own signs ----
                SectionHeader { text: "Your own signs" }
                Label {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    opacity: 0.7
                    text: "Teach Fingerino a hand sign of your own and choose what it does. "
                        + "Hold the sign for a moment to use it."
                }
                Repeater {
                    model: win.bridge.customSigns
                    delegate: Card {
                        id: mine
                        required property var modelData
                        property bool recognised: false
                        title: modelData.name
                        description: (recognised ? "\u2713 Recognised just now \u00b7 " : "")
                            + "Does: " + modelData.action
                        Connections {
                            target: win.bridge
                            function onSignFired(id) {
                                if (id === mine.modelData.id) {
                                    mine.recognised = true
                                    recognisedTimer.restart()
                                }
                            }
                        }
                        Timer {
                            id: recognisedTimer
                            interval: 2500
                            onTriggered: mine.recognised = false
                        }
                        RowLayout {
                            spacing: 8
                            // A quiet "!" when this sign may never fire: it looks
                            // like a built-in, or like another of your signs.
                            Rectangle {
                                visible: mine.modelData.warning !== ""
                                implicitWidth: 18
                                implicitHeight: 18
                                radius: 9
                                color: "transparent"
                                border.width: 1.5
                                border.color: "#d29922"
                                Accessible.role: Accessible.StaticText
                                Accessible.name: mine.modelData.warning
                                Label {
                                    anchors.centerIn: parent
                                    text: "!"
                                    font.pixelSize: 11
                                    font.bold: true
                                    color: "#d29922"
                                }
                                HoverHandler { id: warnHover }
                                ToolTip {
                                    visible: warnHover.hovered
                                    delay: 250
                                    text: mine.modelData.warning
                                }
                            }
                            Button {
                                text: "Change"
                                Accessible.name: "Change what " + mine.modelData.name + " does"
                                onClicked: actionEditor.edit(mine.modelData.id,
                                    "When you make \u201c" + mine.modelData.name + "\u201d")
                            }
                            Button {
                                text: "Rename"
                                Accessible.name: "Rename " + mine.modelData.name
                                onClicked: renameDialog.ask(mine.modelData.id, mine.modelData.name)
                            }
                            Button {
                                text: "Delete"
                                Accessible.name: "Delete " + mine.modelData.name
                                onClicked: deleteDialog.ask(mine.modelData.id, mine.modelData.name)
                            }
                            Switch {
                                checked: mine.modelData.enabled
                                onToggled: win.bridge.setSignEnabled(mine.modelData.id, checked)
                                Accessible.name: mine.modelData.name
                            }
                        }
                    }
                }
                Card {
                    title: "Add a sign"
                    description: "Hold a hand shape in front of the camera for a few seconds, "
                        + "name it, and choose what it does."
                    Button {
                        text: "Record a sign"
                        highlighted: true
                        onClicked: recordDialog.begin()
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
