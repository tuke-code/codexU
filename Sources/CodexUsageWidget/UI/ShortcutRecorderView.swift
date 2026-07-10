import Cocoa
import Carbon.HIToolbox
import SwiftUI

struct ShortcutRecorderView: NSViewRepresentable {
    let shortcut: GlobalShortcut?
    let language: WidgetLanguage
    let onRecord: (GlobalShortcut) -> Void
    let onClear: () -> Void

    func makeNSView(context: Context) -> ShortcutRecorderControl {
        let control = ShortcutRecorderControl()
        control.onRecord = onRecord
        control.onClear = onClear
        control.language = language
        control.shortcut = shortcut
        return control
    }

    func updateNSView(_ control: ShortcutRecorderControl, context: Context) {
        control.onRecord = onRecord
        control.onClear = onClear
        control.language = language
        control.shortcut = shortcut
        control.refresh()
    }
}

final class ShortcutRecorderControl: NSButton {
    var shortcut: GlobalShortcut?
    var language: WidgetLanguage = .automatic
    var onRecord: ((GlobalShortcut) -> Void)?
    var onClear: (() -> Void)?
    private var isRecording = false

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        bezelStyle = .rounded
        setButtonType(.momentaryPushIn)
        target = self
        action = #selector(beginRecording)
        focusRingType = .default
        updateTitle()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override var acceptsFirstResponder: Bool { true }

    @objc private func beginRecording() {
        isRecording = true
        window?.makeFirstResponder(self)
        updateTitle()
    }

    override func keyDown(with event: NSEvent) {
        guard isRecording else {
            super.keyDown(with: event)
            return
        }
        if event.keyCode == UInt16(kVK_Delete) {
            onClear?()
            finishRecording()
            return
        }
        if event.keyCode == UInt16(kVK_Escape) {
            finishRecording()
            return
        }
        guard let candidate = GlobalShortcut.from(event: event) else {
            NSSound.beep()
            return
        }
        onRecord?(candidate)
        finishRecording()
    }

    override func resignFirstResponder() -> Bool {
        isRecording = false
        updateTitle()
        return super.resignFirstResponder()
    }

    private func finishRecording() {
        isRecording = false
        window?.makeFirstResponder(nil)
        updateTitle()
    }

    private func updateTitle() {
        title = isRecording
            ? language.text("请按新快捷键", "Press shortcut")
            : shortcut?.displayName ?? language.text("未设置", "Not set")
        setAccessibilityLabel(language.text("主窗口快捷键", "Main window shortcut"))
        setAccessibilityValue(title)
    }

    func refresh() {
        updateTitle()
    }
}
