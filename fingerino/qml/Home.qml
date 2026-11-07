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
    // Fluent follows the Windows theme, so every colour of our own comes in a
    // pair, each at least 4.5:1 on that theme's cards (tests/test_home_colors.py).
    readonly property bool dark: palette.window.hslLightness < 0.5
    // "This may not work as you expect": the sign badge and recording warnings.
    readonly property color warnColor: dark ? "#f2cc40" : "#9d5d00"
    readonly property color errorColor: dark ? "#ff7b72" : "#c42b1c"
    readonly property color okColor: dark ? "#6ccb5f" : "#0f7b0f"
    // Windows' Accessibility > Text size, which Qt doesn't apply by itself.
    readonly property real textScale: bridge ? bridge.textScale : 1.0
    function fs(px) { return Math.round(px * textScale) }
    font.pixelSize: fs(14)

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
                font.pixelSize: win.fs(16)
            }
            Label {
                text: nav.text
                Layout.fillWidth: true
            }
        }
    }

    // A section's rows in one container, Windows 11 Settings style. Each row
    // draws a hairline above itself; the column is nudged up one pixel under
    // a clip, so the first visible row's line is hidden whatever is shown.
    component Group: Frame {
        default property alias rows: groupColumn.data
        Layout.fillWidth: true
        // Every side by name: the Fluent style sets them one by one, which
        // a plain `padding: 0` doesn't override.
        padding: 0
        topPadding: 0
        bottomPadding: 0
        leftPadding: 0
        rightPadding: 0
        clip: true
        ColumnLayout {
            id: groupColumn
            anchors.fill: parent
            anchors.topMargin: -1
            spacing: 0
        }
    }

    // One row: title and description on the left, a control on the right.
    // Matches the SettingsCard control in the Windows Community Toolkit.
    component Card: Control {
        id: card
        property string title
        property string description
        property alias image: pic.source
        default property alias control: slot.data
        Layout.fillWidth: true
        padding: 16
        background: Item {
            Rectangle {
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                height: 1
                color: win.palette.windowText
                opacity: 0.1
            }
        }
        contentItem: RowLayout {
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
                    font.pixelSize: win.fs(14)
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                }
                Label {
                    visible: card.description !== ""
                    text: card.description
                    opacity: 0.7
                    font.pixelSize: win.fs(12)
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                }
            }
            Item {
                id: slot
                implicitWidth: childrenRect.width
                implicitHeight: childrenRect.height
                // Never squeezed below its controls: the text column wraps
                // instead, or the buttons slide over it and off the row.
                Layout.minimumWidth: implicitWidth
            }
        }
    }

    component SectionHeader: Label {
        font.pixelSize: win.fs(14)
        font.weight: Font.DemiBold
        topPadding: 16
        bottomPadding: 4
    }

    component PageTitle: Label {
        font.pixelSize: win.fs(28)
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
        objectName: "actionEditor"
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
            trialHint.text = ""
            kindBox.currentIndex = kindBox.indexOfValue(kind)
            builtinBox.currentIndex = Math.max(0, builtinBox.indexOfValue(target))
            mediaBox.currentIndex = Math.max(0, mediaBox.indexOfValue(target))
            keysField.text = kind === "hotkey" ? win.bridge.comboLabel(target) : ""
            pathField.text = (kind === "open_app" || kind === "open") ? target : ""
            commandField.text = kind === "command" ? target : ""
            open()
        }

        // Nothing acts while the editor is open (only the sign under "Try
        // it", with its new action), and the trial ends when it closes,
        // however it closes. Held from aboutToShow, so a sign just recorded
        // goes straight from the record dialog's hold into this one.
        onAboutToShow: win.bridge.holdGestures("editor", true)
        onClosed: {
            win.bridge.endTrial()
            win.bridge.holdGestures("editor", false)
        }

        Connections {
            target: win.bridge
            function onSignFired(id) {
                if (actionEditor.opened && trialHint.text !== "" && id === actionEditor.sign)
                    trialHint.text = "✓ Recognised. That's what it will do. Save to keep it."
            }
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
            // The dialog's width, never the content's: a wide row wraps or
            // clips inside rather than pushing everything past the edge.
            width: actionEditor.availableWidth
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
                font.pixelSize: win.fs(12)
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
                id: trialHint
                visible: text !== ""
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                font.pixelSize: win.fs(12)
                opacity: 0.85
            }
            Label {
                id: message
                visible: text !== ""
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                font.pixelSize: win.fs(12)
                color: win.errorColor
            }
            // Four controls, not six: the rarer choices sit in a menu so the
            // row fits the dialog (five buttons ran past its right edge).
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 8
                spacing: 8
                Button {
                    text: "Try it"
                    ToolTip.visible: hovered
                    ToolTip.delay: 400
                    ToolTip.text: "Make the sign to run this action. Other gestures pause until you close this."
                    onClicked: {
                        var err = win.bridge.tryAction(actionEditor.sign, actionEditor.kind,
                                                       actionEditor.currentTarget(), nameField.text)
                        message.text = err
                        trialHint.text = err !== "" ? ""
                            : "Make the sign now. Only this sign works, with this action, "
                              + "until you save or cancel."
                    }
                }
                ToolButton {
                    id: editorMore
                    text: "⋯"
                    font.pixelSize: win.fs(20)
                    flat: true
                    Accessible.name: "More choices"
                    ToolTip.visible: hovered
                    ToolTip.delay: 400
                    ToolTip.text: "Reset or do nothing"
                    onClicked: editorMenu.popup(editorMore, 0, editorMore.height)
                    Menu {
                        id: editorMenu
                        MenuItem {
                            text: "Reset to original"
                            onTriggered: {
                                win.bridge.resetAction(actionEditor.sign)
                                actionEditor.close()
                            }
                        }
                        MenuItem {
                            text: "Do nothing"
                            onTriggered: {
                                win.bridge.clearAction(actionEditor.sign)
                                actionEditor.close()
                            }
                        }
                    }
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
        objectName: "recordDialog"
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
            signNameField.text = ""
            saveError.text = ""
            open()
        }
        function startCountdown() {
            // The camera needs a moment to open; the countdown covers it.
            if (!win.bridge.running)
                win.bridge.start()
            saveError.text = ""
            win.bridge.holdGestures("record", true)    // the hand is busy; nothing should fire
            win.bridge.cancelRecording()
            countdown = win.bridge.recordCountdown
            countdownTimer.start()
        }
        onClosed: {
            countdownTimer.stop()
            countdown = 0
            win.bridge.holdGestures("record", false)
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
                font.pixelSize: win.fs(28)
                text: "Get ready\u2026 " + recordDialog.countdown
            }
            Label {
                visible: recordDialog.phase === "capturing"
                text: "Hold the sign\u2026"
                font.pixelSize: win.fs(16)
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
                color: win.errorColor
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
                font.pixelSize: win.fs(12)
                color: win.warnColor
                text: win.bridge.recordWarning
            }
            TextField {
                id: signNameField
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
                font.pixelSize: win.fs(12)
                color: win.errorColor
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
                        var name = signNameField.text
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
        objectName: "renameDialog"
        property string signId
        anchors.centerIn: parent
        width: Math.min(win.width - 64, 420)
        modal: true
        title: "Rename sign"
        standardButtons: Dialog.Save | Dialog.Cancel
        // Qualified on purpose: a bare name can resolve to an element id
        // elsewhere in this file instead of the property (ids win).
        function ask(sid, name) {
            renameDialog.signId = sid
            renameField.text = name
            renameDialog.open()
        }
        onAccepted: if (renameField.text.trim() !== "")
                        win.bridge.renameSign(renameDialog.signId, renameField.text)
        TextField {
            id: renameField
            width: parent.width
            maximumLength: 40
            Accessible.name: "Sign name"
        }
    }

    Dialog {
        id: deleteDialog
        objectName: "deleteDialog"
        property string signId
        property string signName
        anchors.centerIn: parent
        width: Math.min(win.width - 64, 420)
        modal: true
        title: "Delete \u201c" + deleteDialog.signName + "\u201d?"
        standardButtons: Dialog.Ok | Dialog.Cancel
        // Qualified: a bare `signName` once resolved to the record dialog's
        // text field id, so the assignment threw and the dialog never opened.
        function ask(sid, name) {
            deleteDialog.signId = sid
            deleteDialog.signName = name
            deleteDialog.open()
        }
        onAccepted: win.bridge.deleteSign(deleteDialog.signId)
        Label {
            width: parent.width
            wrapMode: Text.WordWrap
            text: "The sign and what it does are removed. This can't be undone."
        }
    }

    // The pause shortcut, recorded the same way as a sign's shortcut.
    Dialog {
        id: hotkeyDialog
        objectName: "hotkeyDialog"
        property string combo: ""
        anchors.centerIn: parent
        width: Math.min(win.width - 64, 420)
        modal: true
        title: "Pause shortcut"
        padding: 20
        function ask() {
            combo = ""
            hotkeyField.text = ""
            hotkeyError.text = ""
            open()
            hotkeyField.forceActiveFocus()
        }
        ColumnLayout {
            width: hotkeyDialog.availableWidth
            spacing: 10
            Label {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                opacity: 0.7
                text: "Pauses or resumes gestures from any app. Now: " + win.bridge.hotkey
            }
            TextField {
                id: hotkeyField
                Layout.fillWidth: true
                readOnly: true
                placeholderText: "Click here, then press the new shortcut"
                Accessible.name: "New pause shortcut"
                Keys.onPressed: (event) => {
                    var combo = win.bridge.keyCombo(event.key, event.modifiers)
                    if (combo !== "") {
                        hotkeyDialog.combo = combo
                        text = win.bridge.comboLabel(combo)
                    }
                    event.accepted = true
                }
            }
            Label {
                id: hotkeyError
                visible: text !== ""
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                font.pixelSize: win.fs(12)
                color: win.errorColor
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 8
                Item { Layout.fillWidth: true }
                Button {
                    text: "Cancel"
                    onClicked: hotkeyDialog.close()
                }
                Button {
                    text: "Save"
                    highlighted: true
                    enabled: hotkeyDialog.combo !== ""
                    onClicked: {
                        var err = win.bridge.setHotkey(hotkeyDialog.combo)
                        if (err === "")
                            hotkeyDialog.close()
                        else
                            hotkeyError.text = err
                    }
                }
            }
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
                            font.pixelSize: win.fs(14)
                            font.weight: Font.DemiBold
                        }
                        Label {
                            Layout.fillWidth: true
                            wrapMode: Text.WordWrap
                            font.pixelSize: win.fs(12)
                            opacity: 0.7
                            text: "Press Start, then hold one hand up in front of your camera "
                                + "and make a shaka (thumb and little finger out) to try a sign. "
                                + "Then teach Fingerino a sign of your own: any hand shape, "
                                + "doing whatever you like.\n\n"
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

                // Status, and everything that starts or stops Fingerino.
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
                                 : win.bridge.handSeen ? win.okColor : win.warnColor
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Label {
                                text: !win.bridge.running ? "Fingerino is off"
                                    : win.bridge.paused ? "Paused"
                                    : win.bridge.handSeen ? "Tracking your hand"
                                    : "Waiting for your hand"
                                font.pixelSize: win.fs(14)
                            }
                            Label {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                opacity: 0.7
                                font.pixelSize: win.fs(12)
                                text: !win.bridge.running
                                    ? "The camera is off. Press Start when you're ready."
                                    : win.bridge.paused
                                    ? "Gestures are off. Resume here, with "
                                      + win.bridge.hotkey + ", or with both palms up."
                                    : (win.bridge.handSeen ? "Gestures are live. "
                                                           : "Hold one hand up in front of the camera. ")
                                      + "Pause any time with " + win.bridge.hotkey + "."
                            }
                            Label {
                                visible: win.bridge.error !== ""
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                font.pixelSize: win.fs(12)
                                color: win.errorColor
                                text: win.bridge.error
                            }
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
                            visible: !win.bridge.running
                            text: "Start"
                            highlighted: true
                            onClicked: win.bridge.start()
                        }
                        Button {
                            visible: win.bridge.running
                            highlighted: true
                            text: "✕  Stop"
                            Accessible.name: "Stop Fingerino"
                            onClicked: win.bridge.stop()
                        }
                        ToolButton {
                            text: "Quit"
                            flat: true
                            Accessible.name: "Quit Fingerino"
                            ToolTip.visible: hovered
                            ToolTip.delay: 400
                            ToolTip.text: "Stop tracking and close Fingerino completely"
                            onClicked: win.bridge.quit()
                        }
                    }
                }

                // The thing Fingerino is for: your own signs.
                Frame {
                    Layout.fillWidth: true
                    Layout.topMargin: 8
                    padding: 16
                    RowLayout {
                        anchors.fill: parent
                        spacing: 16
                        Image {
                            source: win.bridge.groups[1].rows[0].image
                            Layout.preferredWidth: 56
                            Layout.preferredHeight: 56
                            sourceSize.width: 112
                            sourceSize.height: 112
                            fillMode: Image.PreserveAspectFit
                            mipmap: true
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Label {
                                text: "Make your own sign"
                                font.pixelSize: win.fs(16)
                                font.weight: Font.DemiBold
                            }
                            Label {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                opacity: 0.7
                                font.pixelSize: win.fs(12)
                                text: win.bridge.customSigns.length === 0
                                    ? "Show Fingerino any hand shape for a few seconds and choose "
                                      + "what it does: a shortcut, an app, a website."
                                    : "You have " + win.bridge.customSigns.length
                                      + (win.bridge.customSigns.length === 1 ? " sign" : " signs")
                                      + " of your own. Add another, or change them on the "
                                      + "Gestures page."
                            }
                        }
                        Button {
                            text: "Record a sign…"
                            // The main action whenever Start isn't.
                            highlighted: win.bridge.running
                            onClicked: recordDialog.begin()
                        }
                    }
                }

                SectionHeader { text: "Good to know" }
                Group {
                    Card {
                        title: "Your video stays here"
                        description: "Hand tracking runs on this computer. Nothing is "
                            + "recorded or sent anywhere."
                        Button {
                            text: "Privacy details"
                            onClicked: win.bridge.openRepo("#privacy")
                        }
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
                    text: "Teach Fingerino your own signs, change what any sign does, or "
                        + "switch off the ones you don't want. Changes apply at once, even "
                        + "while tracking."
                }

                // ---- the user's own signs, first: they are the point ----
                SectionHeader { text: "Your own signs" }
                Group {
                    Repeater {
                        model: win.bridge.customSigns
                        delegate: Card {
                            id: mine
                            required property var modelData
                            property bool recognised: false
                            title: modelData.name
                            description: (recognised ? "✓ Recognised just now · " : "")
                                + modelData.action
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
                                // A quiet "!" when this sign may never fire: it
                                // looks like a built-in, or like another sign.
                                Rectangle {
                                    visible: mine.modelData.warning !== ""
                                    implicitWidth: 18
                                    implicitHeight: 18
                                    radius: 9
                                    color: "transparent"
                                    border.width: 1.5
                                    border.color: win.warnColor
                                    Accessible.role: Accessible.StaticText
                                    Accessible.name: mine.modelData.warning
                                    Label {
                                        anchors.centerIn: parent
                                        text: "!"
                                        font.pixelSize: win.fs(11)
                                        font.bold: true
                                        color: win.warnColor
                                    }
                                    HoverHandler { id: warnHover }
                                    ToolTip {
                                        id: warnTip
                                        visible: warnHover.hovered
                                        delay: 250
                                        text: mine.modelData.warning
                                        contentItem: Label {
                                            text: warnTip.text
                                            color: win.warnColor
                                            wrapMode: Text.WordWrap
                                        }
                                    }
                                }
                                Button {
                                    text: "Change…"
                                    Accessible.name: "Change what " + mine.modelData.name + " does"
                                    onClicked: actionEditor.edit(mine.modelData.id,
                                        "When you make “" + mine.modelData.name + "”")
                                }
                                // Rename and Delete live in a menu, so the row
                                // stays short enough to fit a narrow window.
                                ToolButton {
                                    id: moreButton
                                    text: "⋯"
                                    font.pixelSize: win.fs(20)
                                    flat: true
                                    Accessible.name: "More for " + mine.modelData.name
                                    ToolTip.visible: hovered
                                    ToolTip.delay: 400
                                    ToolTip.text: "Rename or delete"
                                    onClicked: moreMenu.popup(moreButton, 0, moreButton.height)
                                    Menu {
                                        id: moreMenu
                                        MenuItem {
                                            text: "Rename…"
                                            onTriggered: renameDialog.ask(mine.modelData.id,
                                                                          mine.modelData.name)
                                        }
                                        MenuItem {
                                            text: "Delete…"
                                            onTriggered: deleteDialog.ask(mine.modelData.id,
                                                                          mine.modelData.name)
                                        }
                                    }
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
                        title: win.bridge.customSigns.length === 0
                            ? "Record your first sign" : "Record another sign"
                        description: "Hold any hand shape in front of the camera for a few "
                            + "seconds, name it, and choose what it does."
                        Button {
                            text: "Record a sign…"
                            highlighted: true
                            onClicked: recordDialog.begin()
                        }
                    }
                }

                Repeater {
                    model: win.bridge.groups
                    delegate: ColumnLayout {
                        id: group
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 4
                        SectionHeader { text: group.modelData.name }
                        Group {
                            // The cursor module's master switch, at the head
                            // of the group it controls. Off by default.
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
                                    // Shown, not hidden, while the cursor is
                                    // off, and greyed out to say why.
                                    enabled: !modelData.cursor || win.bridge.cursorEnabled
                                    // Titled by the sign; what it does goes
                                    // underneath, as for your own signs.
                                    title: modelData.title
                                    description: modelData.sign
                                        ? modelData.desc + " · "
                                          + (win.bridge.bindingsVersion,
                                             win.bridge.actionInfo(modelData.icon).label)
                                        : modelData.desc
                                    image: modelData.image
                                    RowLayout {
                                        spacing: 12
                                        Button {
                                            visible: row.modelData.sign
                                            text: "Change…"
                                            Accessible.name: "Change what " + row.modelData.title
                                                + " does"
                                            onClicked: actionEditor.edit(row.modelData.icon,
                                                "When you make a " + row.modelData.title.toLowerCase()
                                                + " (" + row.modelData.desc.toLowerCase() + ")")
                                        }
                                        Switch {
                                            id: rowSwitch
                                            objectName: "switch-" + row.modelData.icon
                                            // A pointer gesture shows off while the
                                            // cursor is off, whatever it is set to,
                                            // and its own setting again once it's on.
                                            function shown() {
                                                return (!row.modelData.cursor || win.bridge.cursorEnabled)
                                                    && win.bridge.gestureEnabled(row.modelData.icon)
                                            }
                                            checked: shown()
                                            onToggled: {
                                                win.bridge.setGestureEnabled(row.modelData.icon, checked)
                                                checked = Qt.binding(shown)
                                            }
                                            Accessible.name: row.modelData.title
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                Item { implicitHeight: 24 }
            }

            // ---- Settings ---------------------------------------------------
            Page_ {
                PageTitle { text: "Settings" }

                SectionHeader { text: "Tracking" }
                Group {
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
                        title: "Show the hand skeleton"
                        description: "Draws the joints Fingerino tracks over your hand in the "
                            + "preview. Always shown while you record a sign."
                        Switch {
                            checked: win.bridge.showSkeleton
                            onToggled: win.bridge.setShowSkeleton(checked)
                            Accessible.name: "Show the hand skeleton"
                        }
                    }
                    Card {
                        title: "Pause shortcut"
                        description: "Pauses or resumes gestures from any app: "
                            + win.bridge.hotkey + "."
                        Button {
                            text: "Change…"
                            Accessible.name: "Change the pause shortcut"
                            onClicked: hotkeyDialog.ask()
                        }
                    }
                }

                SectionHeader { text: "Appearance" }
                Group {
                    Card {
                        title: "Theme"
                        description: "Light or dark, or the same as Windows."
                        ComboBox {
                            objectName: "themeBox"
                            model: [
                                { value: "system", text: "Use system setting" },
                                { value: "light", text: "Light" },
                                { value: "dark", text: "Dark" }
                            ]
                            textRole: "text"
                            valueRole: "value"
                            implicitWidth: 200
                            currentIndex: indexOfValue(win.bridge.theme)
                            onActivated: win.bridge.setTheme(currentValue)
                            Accessible.name: "Theme"
                        }
                    }
                }

                SectionHeader { text: "Data" }
                Group {
                    Card {
                        title: "Fingerino's folder"
                        description: "Settings, the hand model, and reports from "
                            + "--selftest or a crash. Nothing in it is sent anywhere."
                        Button {
                            text: "Open folder"
                            onClicked: win.bridge.openDataFolder()
                        }
                    }
                }

                SectionHeader { text: "About" }
                Group {
                    Card {
                        title: "Fingerino " + win.bridge.version
                        description: "Control your computer with hand signs."
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
                }
                Item { implicitHeight: 24 }
            }
        }
    }
}
