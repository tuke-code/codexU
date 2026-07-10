import Carbon.HIToolbox
import Cocoa

struct GlobalShortcut: Equatable {
    static let `default` = GlobalShortcut(
        keyCode: UInt32(kVK_ANSI_U),
        carbonModifiers: UInt32(cmdKey),
        keyLabel: "U"
    )

    static let keyCodeStorageKey = "codexU.globalShortcut.keyCode"
    static let modifiersStorageKey = "codexU.globalShortcut.modifiers"
    static let keyLabelStorageKey = "codexU.globalShortcut.keyLabel"
    static let enabledStorageKey = "codexU.globalShortcut.enabled"

    let keyCode: UInt32
    let carbonModifiers: UInt32
    let keyLabel: String

    var displayName: String {
        var result = ""
        if carbonModifiers & UInt32(controlKey) != 0 { result += "⌃" }
        if carbonModifiers & UInt32(optionKey) != 0 { result += "⌥" }
        if carbonModifiers & UInt32(shiftKey) != 0 { result += "⇧" }
        if carbonModifiers & UInt32(cmdKey) != 0 { result += "⌘" }
        return result + keyLabel
    }

    static func load(defaults: UserDefaults = .standard) -> GlobalShortcut? {
        if defaults.object(forKey: enabledStorageKey) != nil,
           !defaults.bool(forKey: enabledStorageKey) {
            return nil
        }
        guard defaults.object(forKey: keyCodeStorageKey) != nil,
              defaults.object(forKey: modifiersStorageKey) != nil,
              let keyLabel = defaults.string(forKey: keyLabelStorageKey),
              !keyLabel.isEmpty
        else { return .default }

        return GlobalShortcut(
            keyCode: UInt32(defaults.integer(forKey: keyCodeStorageKey)),
            carbonModifiers: UInt32(defaults.integer(forKey: modifiersStorageKey)),
            keyLabel: keyLabel
        )
    }

    func save(defaults: UserDefaults = .standard) {
        defaults.set(true, forKey: Self.enabledStorageKey)
        defaults.set(Int(keyCode), forKey: Self.keyCodeStorageKey)
        defaults.set(Int(carbonModifiers), forKey: Self.modifiersStorageKey)
        defaults.set(keyLabel, forKey: Self.keyLabelStorageKey)
    }

    static func clear(defaults: UserDefaults = .standard) {
        defaults.set(false, forKey: enabledStorageKey)
        defaults.removeObject(forKey: keyCodeStorageKey)
        defaults.removeObject(forKey: modifiersStorageKey)
        defaults.removeObject(forKey: keyLabelStorageKey)
    }

    static func from(event: NSEvent) -> GlobalShortcut? {
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        var modifiers: UInt32 = 0
        if flags.contains(.command) { modifiers |= UInt32(cmdKey) }
        if flags.contains(.option) { modifiers |= UInt32(optionKey) }
        if flags.contains(.shift) { modifiers |= UInt32(shiftKey) }
        if flags.contains(.control) { modifiers |= UInt32(controlKey) }
        guard modifiers != 0 else { return nil }

        let keyCode = UInt32(event.keyCode)
        let label = specialKeyLabels[keyCode]
            ?? event.charactersIgnoringModifiers?.uppercased()
        guard let label, !label.isEmpty else { return nil }
        return GlobalShortcut(keyCode: keyCode, carbonModifiers: modifiers, keyLabel: label)
    }

    private static let specialKeyLabels: [UInt32: String] = [
        UInt32(kVK_Return): "↩",
        UInt32(kVK_Tab): "⇥",
        UInt32(kVK_Space): "Space",
        UInt32(kVK_Delete): "⌫",
        UInt32(kVK_ForwardDelete): "⌦",
        UInt32(kVK_Escape): "⎋",
        UInt32(kVK_Home): "↖",
        UInt32(kVK_End): "↘",
        UInt32(kVK_PageUp): "⇞",
        UInt32(kVK_PageDown): "⇟",
        UInt32(kVK_LeftArrow): "←",
        UInt32(kVK_RightArrow): "→",
        UInt32(kVK_UpArrow): "↑",
        UInt32(kVK_DownArrow): "↓",
        UInt32(kVK_F1): "F1", UInt32(kVK_F2): "F2", UInt32(kVK_F3): "F3",
        UInt32(kVK_F4): "F4", UInt32(kVK_F5): "F5", UInt32(kVK_F6): "F6",
        UInt32(kVK_F7): "F7", UInt32(kVK_F8): "F8", UInt32(kVK_F9): "F9",
        UInt32(kVK_F10): "F10", UInt32(kVK_F11): "F11", UInt32(kVK_F12): "F12"
    ]
}

enum GlobalShortcutError: Equatable {
    case registrationFailed
    case savedShortcutResetToDefault
    case noShortcutAvailable

    func message(language: WidgetLanguage) -> String {
        switch self {
        case .registrationFailed:
            return language.text(
                "无法注册该快捷键，可能已被其他应用占用。",
                "Could not register this shortcut. Another app may be using it."
            )
        case .savedShortcutResetToDefault:
            return language.text(
                "保存的快捷键不可用，已恢复为默认快捷键。",
                "The saved shortcut was unavailable and has been reset to the default."
            )
        case .noShortcutAvailable:
            return language.text(
                "快捷键注册失败，当前未设置全局快捷键。",
                "Shortcut registration failed. No global shortcut is currently set."
            )
        }
    }
}
