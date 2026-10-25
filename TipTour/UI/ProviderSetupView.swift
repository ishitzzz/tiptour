import SwiftUI

struct ProviderSetupView: View {
    @ObservedObject var companionManager: CompanionManager

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            ModeSelectionView(companionManager: companionManager)
            if companionManager.selectedMode == .gemini {
                GeminiKeyPoolCard(onKeyChanged: companionManager.refreshProviderKeyStatus)
            } else {
                ProviderKeyCard(mode: companionManager.selectedMode,
                    onKeyChanged: companionManager.refreshProviderKeyStatus)
                    .id(companionManager.selectedMode)
            }
            Text("Your choice is saved. You can switch modes here any time.")
                .font(.system(size: 11))
                .foregroundColor(DS.Colors.textTertiary)
        }
    }
}

struct ModeSelectionView: View {
    @ObservedObject var companionManager: CompanionManager

    var body: some View {
        VStack(spacing: 8) {
            ForEach(TipTourMode.allCases) { mode in
                Button { companionManager.setSelectedMode(mode) } label: {
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: mode.systemImage).frame(width: 18)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(mode == .jev ? "JEV · Text" : "Gemini · Voice")
                                .font(.system(size: 13, weight: .semibold))
                            Text(mode.summary).font(.system(size: 11))
                                .foregroundColor(DS.Colors.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Spacer(minLength: 0)
                        Image(systemName: companionManager.selectedMode == mode ? "checkmark.circle.fill" : "circle")
                    }
                    .foregroundColor(companionManager.selectedMode == mode ? DS.Colors.accent : DS.Colors.textSecondary)
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 10)
                        .fill(companionManager.selectedMode == mode ? DS.Colors.accent.opacity(0.1) : DS.Colors.surface1))
                    .contentShape(RoundedRectangle(cornerRadius: 10))
                }
                .buttonStyle(.plain)
                .pointerCursor()
                .disabled(companionManager.isTextCommandRunning)
                .accessibilityLabel("Select \(mode.title)")
                .accessibilityValue(companionManager.selectedMode == mode ? "Selected" : "Not selected")
            }
        }
    }
}

struct ProviderKeyCard: View {
    private let title: String
    private let detail: String
    private let keyName: String
    private let onKeyChanged: () -> Void
    @State private var input = ""
    @State private var hasSavedKey = false
    @State private var status = ""

    init(mode: TipTourMode, onKeyChanged: @escaping () -> Void = {}) {
        self.init(
            title: mode == .jev ? "JEV / TypeSafe key" : "Gemini key",
            detail: mode.privacySummary,
            keyName: mode.keyName,
            onKeyChanged: onKeyChanged
        )
    }

    /// For keys that are not tied to a mode, such as Elorian's.
    init(title: String, detail: String, keyName: String, onKeyChanged: @escaping () -> Void = {}) {
        self.title = title
        self.detail = detail
        self.keyName = keyName
        self.onKeyChanged = onKeyChanged
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(title).font(.system(size: 14, weight: .semibold))
                Spacer()
                Text(hasSavedKey ? "Key saved" : "Key needed")
                    .font(.system(size: 11))
                    .foregroundColor(hasSavedKey ? DS.Colors.success : DS.Colors.textTertiary)
            }
            Text(detail)
                .font(.system(size: 12))
                .foregroundColor(DS.Colors.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            SecureField(hasSavedKey ? "Paste a replacement key" : "Paste your API key", text: $input)
                .textFieldStyle(.roundedBorder)
                .accessibilityLabel("\(title) API key")
                .onSubmit { save() }
            HStack {
                Button("Save key", action: save)
                    .disabled(input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .pointerCursor()
                Button("Remove key") {
                    if KeychainStore.delete(forKey: keyName) {
                        hasSavedKey = false
                        input = ""
                        status = "Removed"
                        onKeyChanged()
                    } else {
                        status = "Could not remove the key. Try again."
                    }
                }
                .disabled(!hasSavedKey)
                .pointerCursor()

            }
            if !status.isEmpty {
                Text(status).font(.system(size: 11)).foregroundColor(DS.Colors.textSecondary)
            }
            Text("Stored securely in macOS Keychain.")
                .font(.system(size: 10)).foregroundColor(DS.Colors.textTertiary)
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 12).fill(DS.Colors.surface1))
        .onAppear { hasSavedKey = !(KeychainStore.get(forKey: keyName) ?? "").isEmpty }
    }

    private func save() {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        if KeychainStore.set(trimmed, forKey: keyName) {
            hasSavedKey = true
            input = ""
            status = "Saved"
            onKeyChanged()
        } else {
            status = "Could not save to Keychain. Try again."
        }
    }
}

/// Key pool manager for Gemini mode: a list of user-supplied keys with
/// per-key cooldown status. Keys live in macOS Keychain; only the masked
/// suffix is ever shown.
struct GeminiKeyPoolCard: View {
    @ObservedObject private var pool = GeminiKeyPool.shared
    let onKeyChanged: () -> Void
    @State private var input = ""
    @State private var status = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Gemini keys").font(.system(size: 14, weight: .semibold))
                Spacer()
                Text(pool.entries.isEmpty ? "Key needed" : "\(pool.entries.count) saved")
                    .font(.system(size: 11))
                    .foregroundColor(pool.entries.isEmpty ? DS.Colors.textTertiary : DS.Colors.success)
            }
            Text("Save keys from different Google projects. If a key is blocked or cooling down, the next available key is tried.")
                .font(.system(size: 12))
                .foregroundColor(DS.Colors.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            ForEach(pool.entries) { entry in
                HStack(spacing: 8) {
                    Text(entry.masked)
                        .font(.system(size: 12, design: .monospaced))
                    Spacer(minLength: 0)
                    Text(statusText(for: entry))
                        .font(.system(size: 10))
                        .foregroundColor(DS.Colors.textSecondary)
                        .multilineTextAlignment(.trailing)
                    Button("Remove") {
                        if pool.removeKey(id: entry.id) {
                            status = "Removed."
                            onKeyChanged()
                        } else {
                            status = "Could not remove the key. Try again."
                        }
                    }
                    .font(.system(size: 11))
                    .pointerCursor()
                    .accessibilityLabel("Remove key \(entry.masked)")
                }
            }

            SecureField(pool.entries.isEmpty ? "Paste your Gemini API key" : "Paste another Gemini API key", text: $input)
                .textFieldStyle(.roundedBorder)
                .accessibilityLabel("Gemini API key")
                .onSubmit(add)
            HStack {
                Button("Add key", action: add)
                    .disabled(input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .pointerCursor()
                Button("Reset key states") {
                    pool.resetStates()
                    status = "Key states reset."
                }
                .disabled(pool.entries.isEmpty)
                .pointerCursor()
            }
            if !status.isEmpty {
                Text(status).font(.system(size: 11)).foregroundColor(DS.Colors.textSecondary)
            }
            Text("Stored securely in macOS Keychain. " + TipTourMode.gemini.privacySummary)
                .font(.system(size: 10)).foregroundColor(DS.Colors.textTertiary)
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 12).fill(DS.Colors.surface1))
        .onAppear { pool.reloadKeys() }
    }

    private func add() {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        if pool.entries.contains(where: { $0.key == trimmed }) {
            status = "That key is already saved."
            return
        }
        // The pool persists first and only then updates in memory — a
        // failed Keychain write must never show "Saved".
        if pool.addKey(trimmed) {
            input = ""
            status = "Saved."
            onKeyChanged()
        } else {
            status = "Could not save to Keychain. Try again."
        }
    }

    private func statusText(for entry: GeminiKeyPool.Entry) -> String {
        switch entry.state {
        case .ready:
            return "Ready"
        case .coolingDown(let until, let reason):
            return "\(reason) — retry after \(until.formatted(date: .omitted, time: .shortened))"
        case .parked(let reason):
            return reason
        }
    }
}
