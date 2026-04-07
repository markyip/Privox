import Foundation
import AppKit

func privoxAppDataDirectory() -> URL {
    let fileManager = FileManager.default
    let legacyURL = fileManager.homeDirectoryForCurrentUser
        .appendingPathComponent(".privox", isDirectory: true)
    let appSupportURL = fileManager.homeDirectoryForCurrentUser
        .appendingPathComponent("Library", isDirectory: true)
        .appendingPathComponent("Application Support", isDirectory: true)
        .appendingPathComponent("Privox", isDirectory: true)
    let legacyMarkers = [".user_prefs.json", "config.json", "models", "swift.log", "privox_app.log"]

    let chosenURL: URL
    if legacyMarkers.contains(where: { fileManager.fileExists(atPath: legacyURL.appendingPathComponent($0).path) }) {
        chosenURL = legacyURL
    } else {
        chosenURL = appSupportURL
    }

    try? fileManager.createDirectory(at: chosenURL, withIntermediateDirectories: true)
    return chosenURL
}

func appLog(_ message: String) {
    let logURL = privoxAppDataDirectory()
        .appendingPathComponent("swift.log")
    
    // Ensure dir exists
    try? FileManager.default.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    
    let timestamp = DateFormatter.localizedString(from: Date(), dateStyle: .short, timeStyle: .medium)
    let logMessage = "[\(timestamp)] \(message)\n"
    
    // Print to console still for terminal debugging
    print(logMessage, terminator: "")
    
    if let handle = try? FileHandle(forWritingTo: logURL) {
        handle.seekToEndOfFile()
        if let data = logMessage.data(using: .utf8) {
            handle.write(data)
        }
        try? handle.close()
    } else {
        try? logMessage.write(to: logURL, atomically: true, encoding: .utf8)
    }
}

class BackendManager {
    static let shared = BackendManager()
    
    private var process: Process?
    private var outputPipe: Pipe?
    private var inputPipe: Pipe?
    private var isRunning = false
    
    // Project root where pixi operates
    private var projectDirectory: String {
        // 1. Check if we are running in the local development build_mac/ folder
        let bundleURL = Bundle.main.bundleURL
        if bundleURL.path.contains("build_mac/Privox.app") {
            return bundleURL.deletingLastPathComponent().deletingLastPathComponent().path
        }
        
        // 2. If we are packaged inside a DMG, the files will be inside Contents/Resources
        if let resourcePath = Bundle.main.resourcePath {
            let srcPath = (resourcePath as NSString).appendingPathComponent("src")
            if FileManager.default.fileExists(atPath: srcPath) {
                return resourcePath
            }
        }
        
        // 3. Otherwise use development paths if launched from local scripts
        if let pwd = ProcessInfo.processInfo.environment["PWD"], pwd != "/" {
            return pwd
        }
        return FileManager.default.currentDirectoryPath
    }
    
    private init() {
        startBackend()
    }
    
    func startBackend() {
        if isRunning, process?.isRunning == true { return }
        isRunning = false
        
        let pythonPath = findPythonExecutable()
        appLog("Attempting to start Python backend via: \(pythonPath)")
        appLog("Project Directory (Cwd): \(projectDirectory)")
        appLog("App Data Directory: \(privoxAppDataDirectory().path)")
        
        process = Process()
        if pythonPath == "/usr/bin/env python" {
            // Workaround for Cocoa Process executableURL which hates arguments inside the path string
            process?.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process?.arguments = ["python", "src/voice_input.py", "--headless"]
        } else {
            process?.executableURL = URL(fileURLWithPath: pythonPath)
            process?.arguments = ["src/voice_input.py", "--headless"]
        }
        process?.currentDirectoryURL = URL(fileURLWithPath: projectDirectory)
        var env = ProcessInfo.processInfo.environment
        env["PRIVOX_APP_DATA_DIR"] = privoxAppDataDirectory().path
        env["PYTHONUNBUFFERED"] = "1"
        process?.environment = env
        
        outputPipe = Pipe()
        inputPipe = Pipe()
        process?.standardOutput = outputPipe
        process?.standardError = outputPipe
        process?.standardInput = inputPipe
        process?.terminationHandler = { process in
            DispatchQueue.main.async {
                BackendManager.shared.isRunning = false
                BackendManager.shared.outputPipe?.fileHandleForReading.readabilityHandler = nil
                BackendManager.shared.outputPipe = nil
                BackendManager.shared.inputPipe = nil
                BackendManager.shared.process = nil
                appLog("Python backend terminated with status: \(process.terminationStatus)")
                NotificationCenter.default.post(
                    name: NSNotification.Name("PrivoxBackendDetail"),
                    object: nil,
                    userInfo: ["detail": "BACKEND_EXITED"]
                )
            }
        }
        
        outputPipe?.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.count > 0, let str = String(data: data, encoding: .utf8) {
                appLog("[PYTHON] \(str.trimmingCharacters(in: .newlines))")
                self?.handlePythonOutput(str)
            }
        }
        
        do {
            try process?.run()
            isRunning = true
            appLog("Python daemon started successfully in headless mode.")
        } catch {
            appLog("Failed to start Python backend: \(error)")
        }
    }
    
    func sendCommand(_ command: String) {
        appLog("Sending IPC Command: \(command)")
        if !isRunning || process?.isRunning != true || inputPipe == nil {
            appLog("Backend is not available. Restarting before retrying command: \(command)")
            startBackend()
        }

        guard isRunning, process?.isRunning == true, let pipe = inputPipe else {
            appLog("Unable to send IPC command because backend is unavailable: \(command)")
            return
        }

        let payload = command + "\n"
        guard let data = payload.data(using: .utf8) else { return }

        do {
            try pipe.fileHandleForWriting.write(contentsOf: data)
        } catch {
            appLog("IPC write failed for command '\(command)': \(error)")
            isRunning = false
            startBackend()

            guard isRunning, process?.isRunning == true, let retryPipe = inputPipe else {
                appLog("Retry aborted because backend did not restart successfully.")
                return
            }

            do {
                try retryPipe.fileHandleForWriting.write(contentsOf: data)
                appLog("IPC retry succeeded for command: \(command)")
            } catch {
                appLog("IPC retry failed for command '\(command)': \(error)")
            }
        }
    }
    
    func stopBackend() {
        sendCommand("QUIT")
        process?.terminate()
        isRunning = false
    }
    
    private func handlePythonOutput(_ output: String) {
        // Parse line-by-line because Python logs often batch multiple messages together.
        let lines = output.components(separatedBy: .newlines)
        for rawLine in lines {
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !line.isEmpty else { continue }

            if let statusRange = line.range(of: "STATUS: ") {
                let status = line[statusRange.upperBound...]
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                    .components(separatedBy: .whitespacesAndNewlines)
                    .first ?? ""
                guard !status.isEmpty else { continue }
                appLog("Broadcasting Status Update: \(status)")
                DispatchQueue.main.async {
                    NotificationCenter.default.post(name: NSNotification.Name("PrivoxStatusChanged"), object: nil, userInfo: ["status": status])
                }
            }

            if let detailRange = line.range(of: "DETAIL: ") {
                let detail = String(line[detailRange.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
                guard !detail.isEmpty else { continue }
                DispatchQueue.main.async {
                    NotificationCenter.default.post(name: NSNotification.Name("PrivoxBackendDetail"), object: nil, userInfo: ["detail": detail])
                }
            }
        }
    }
    
    private func findPythonExecutable() -> String {
        let fileManager = FileManager.default
        let appData = privoxAppDataDirectory()

        // 1. User-configured path: env PRIVOX_PYTHON (use local MLX / system Python)
        if let envPython = ProcessInfo.processInfo.environment["PRIVOX_PYTHON"],
           !envPython.isEmpty,
           fileManager.fileExists(atPath: envPython) {
            return envPython
        }

        // 2. User-configured path file (e.g. set by setup script)
        let pythonPathFile = appData.appendingPathComponent("python_path")
        if let pathContent = try? String(contentsOf: pythonPathFile, encoding: .utf8),
           let firstLine = pathContent.split(separator: "\n").first {
            let candidate = String(firstLine).trimmingCharacters(in: .whitespaces)
            if !candidate.isEmpty && candidate.hasPrefix("/") && fileManager.fileExists(atPath: candidate) {
                return candidate
            }
        }

        // 3. Standard "Privox venv" locations (user installs MLX here to avoid bundled env)
        let venvCandidates = [
            appData.appendingPathComponent("venv/bin/python").path,
            (fileManager.homeDirectoryForCurrentUser.path as NSString).appendingPathComponent("Library/Application Support/Privox/venv/bin/python"),
        ]
        for venvPython in venvCandidates {
            if fileManager.fileExists(atPath: venvPython) {
                return venvPython
            }
        }

        // 4. Bundled .pixi inside app (full DMG)
        if let resourcePath = Bundle.main.resourcePath {
            let bundledPython = (resourcePath as NSString).appendingPathComponent(".pixi/envs/default/bin/python")
            if fileManager.fileExists(atPath: bundledPython) {
                return bundledPython
            }
        }

        // 5. Development path (local .pixi)
        let localPython = (projectDirectory as NSString).appendingPathComponent(".pixi/envs/default/bin/python")
        if fileManager.fileExists(atPath: localPython) {
            return localPython
        }

        // 6. Fallback: system python from PATH
        return "/usr/bin/env python"
    }
}
