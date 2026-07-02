import Foundation

struct CodexDataLocations: Equatable {
    let codexHomePath: String

    var stateDatabaseCandidates: [String] {
        [
            path("state_5.sqlite"),
            path("sqlite/state_5.sqlite")
        ]
    }

    var automationsDirectory: URL {
        URL(fileURLWithPath: path("automations"), isDirectory: true)
    }

    static func current(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        homeDirectory: String = NSHomeDirectory()
    ) -> CodexDataLocations {
        if let override = environment["CODEX_HOME"]?.trimmingCharacters(in: .whitespacesAndNewlines),
           !override.isEmpty {
            return CodexDataLocations(codexHomePath: override)
        }

        return CodexDataLocations(codexHomePath: path(homeDirectory, ".codex"))
    }

    private func path(_ relativePath: String) -> String {
        Self.path(codexHomePath, relativePath)
    }

    private static func path(_ base: String, _ relativePath: String) -> String {
        var url = URL(fileURLWithPath: base, isDirectory: true)
        for component in relativePath.split(separator: "/") {
            url.appendPathComponent(String(component))
        }
        return url.path
    }
}
