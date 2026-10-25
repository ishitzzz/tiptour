//
//  KeychainStore.swift
//  TipTour
//
//  Minimal Keychain helper for storing sensitive strings (like API keys)
//  that shouldn't live in UserDefaults. Uses kSecClassGenericPassword —
//  the standard macOS pattern for service-scoped secrets.
//
//  Scoped to TipTour's bundle identifier so the entries are isolated
//  from other services. No iCloud sync — these are device-local keys only.
//

import Foundation
import Security

enum KeychainStore {

    private static let serviceName: String = Bundle.main.bundleIdentifier ?? "com.milindsoni.tiptour"

    /// Write (or overwrite) a UTF-8 string for the given key. Returns
    /// true on success. Empty / whitespace-only input is treated as a
    /// delete so callers can implement "clear the key" as just writing
    /// an empty string.
    @discardableResult
    static func set(_ value: String, forKey key: String) -> Bool {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            return delete(forKey: key)
        }
        guard let data = trimmed.data(using: .utf8) else { return false }

        // Baseline query: find the existing item (if any).
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrAccount as String: key
        ]

        let updateAttributes: [String: Any] = [
            kSecValueData as String: data
        ]

        // Try update first; if the item doesn't exist, fall through to add.
        let updateStatus = SecItemUpdate(query as CFDictionary, updateAttributes as CFDictionary)
        if updateStatus == errSecSuccess {
            return true
        }

        // Either no existing item or update failed — try to add fresh.
        var addQuery = query
        addQuery[kSecValueData as String] = data
        // Only accessible after the device has been unlocked (standard
        // behavior for a Mac app — keys shouldn't leak to background
        // processes on a locked machine).
        addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
        return addStatus == errSecSuccess
    }

    /// Read the stored UTF-8 string for the given key. Returns nil if
    /// nothing was ever stored, or if the item exists but isn't valid
    /// UTF-8 (shouldn't happen for keys written via `set`).
    static func get(forKey key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrAccount as String: key,
            kSecReturnData as String:  true,
            kSecMatchLimit as String:  kSecMatchLimitOne
        ]

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess,
              let data = item as? Data,
              let string = String(data: data, encoding: .utf8) else {
            return nil
        }
        return string
    }

    /// Delete the item for the given key. Returns true if deleted OR
    /// if there was nothing to delete (either is "success" from the
    /// caller's perspective — the key is gone).
    @discardableResult
    static func delete(forKey key: String) -> Bool {
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrAccount as String: key
        ]
        let status = SecItemDelete(query as CFDictionary)
        return status == errSecSuccess || status == errSecItemNotFound
    }

    // MARK: - TipTour-specific keys

    /// Legacy single Gemini API key slot. The Gemini key pool migrates
    /// this into `geminiAPIKeys` on first read; kept so existing installs
    /// keep working.
    static var geminiAPIKey: String? {
        get { get(forKey: "geminiAPIKey") }
        set { set(newValue ?? "", forKey: "geminiAPIKey") }
    }

    // MARK: - Gemini key pool

    static let geminiAPIKeysName = "geminiAPIKeys"

    /// All saved Gemini keys in user-managed order. The legacy single-key
    /// slot migrates into the list on first read so existing installs keep
    /// their key without re-pasting.
    static var geminiAPIKeys: [String] {
        get {
            var keys = decodeGeminiAPIKeys()
            if keys.isEmpty, let legacy = geminiAPIKey, !legacy.isEmpty {
                let migrated = [legacy.trimmingCharacters(in: .whitespacesAndNewlines)].filter { !$0.isEmpty }
                // The legacy slot is deleted ONLY after the list write
                // succeeds and reads back intact — a failed Keychain write
                // must never lose the user's only key.
                if !migrated.isEmpty, encodeGeminiAPIKeys(migrated) {
                    delete(forKey: "geminiAPIKey")
                    keys = migrated
                } else {
                    keys = [legacy]
                }
            }
            return keys
        }
        set { setGeminiAPIKeys(newValue) }
    }

    /// Writes the Gemini key list durably. Returns true only when the new
    /// list was stored AND read back intact — callers must not update
    /// in-memory state or show "Saved"/"Removed" on false.
    @discardableResult
    static func setGeminiAPIKeys(_ keys: [String]) -> Bool {
        encodeGeminiAPIKeys(keys)
    }

    private static func decodeGeminiAPIKeys() -> [String] {
        guard let raw = get(forKey: geminiAPIKeysName),
              let data = raw.data(using: .utf8),
              let list = try? JSONDecoder().decode([String].self, from: data) else { return [] }
        return list.filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    }

    @discardableResult
    private static func encodeGeminiAPIKeys(_ keys: [String]) -> Bool {
        let cleaned = keys.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        if cleaned.isEmpty {
            // Empty list means "no keys" — remove the item outright.
            guard delete(forKey: geminiAPIKeysName) else { return false }
            return decodeGeminiAPIKeys().isEmpty
        }
        guard let data = try? JSONEncoder().encode(cleaned),
              let raw = String(data: data, encoding: .utf8),
              set(raw, forKey: geminiAPIKeysName) else { return false }
        return decodeGeminiAPIKeys() == cleaned
    }

    /// TypeSafe API key for JEV text commands.
    static var jevAPIKey: String? {
        get { get(forKey: "jevAPIKey") }
        set { set(newValue ?? "", forKey: "jevAPIKey") }
    }

    /// OpenRouter API key for JEV through OpenRouter. Separate from the TypeSafe key.
    static var openRouterJevAPIKey: String? {
        get { get(forKey: "openRouterJevAPIKey") }
        set { set(newValue ?? "", forKey: "openRouterJevAPIKey") }
    }

    /// Elorian API key for "Learn from a video" tutorial tours. It is not a
    /// mode, so it works alongside whichever mode is selected.
    static let elorianAPIKeyName = "elorianAPIKey"
    static var elorianAPIKey: String? {
        get { get(forKey: elorianAPIKeyName) }
        set { set(newValue ?? "", forKey: elorianAPIKeyName) }
    }

}
