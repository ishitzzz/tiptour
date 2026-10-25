import SwiftUI

struct ProviderSetupView: View {
    @ObservedObject var companionManager: CompanionManager

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            ModeSelectionView(companionManager: companionManager)
            if companionManager.selectedMode == .jev {
                JevConnectionPicker(companionManager: companionManager)
            }
            ProviderKeyCard(mode: companionManager.selectedMode,
                onKeyChanged: companionManager.refreshProviderKeyStatus)
                .id("\(companionManager.selectedMode.rawValue)-\(companionManager.jevConnection.rawValue)")
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

struct JevConnectionPicker: View {
    @ObservedObject var companionManager: CompanionManager

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("JEV connection").font(.system(size: 13, weight: .semibold))
            ForEach(JevConnection.allCases) { connection in
                let isSelected = companionManager.jevConnection == connection
                Button { companionManager.setJevConnection(connection) } label: {
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: isSelected ? "checkmark.circle.fill" : "circle").frame(width: 18)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(connection.title).font(.system(size: 12, weight: .semibold))
                            Text(connection.summary).font(.system(size: 11))
                                .foregroundColor(DS.Colors.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Spacer(minLength: 0)
                    }
                    .foregroundColor(isSelected ? DS.Colors.accent : DS.Colors.textSecondary)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 10)
                        .fill(isSelected ? DS.Colors.accent.opacity(0.1) : DS.Colors.surface1))
                    .contentShape(RoundedRectangle(cornerRadius: 10))
                }
                .buttonStyle(.plain)
                .pointerCursor()
                .disabled(companionManager.isTextCommandRunning)
                .accessibilityLabel("Use \(connection.title) for JEV")
                .accessibilityValue(isSelected ? "Selected" : "Not selected")
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
            title: mode == .jev ? JevConnection.saved.keyTitle : "Gemini key",
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
