import SwiftUI
import AppKit
import AVFoundation

let privoxModifierOrder = ["cmd", "ctrl", "alt", "shift"]
let privoxModifierAliases: [String: String] = [
    "cmd": "cmd", "command": "cmd", "⌘": "cmd",
    "ctrl": "ctrl", "control": "ctrl", "⌃": "ctrl",
    "alt": "alt", "option": "alt", "opt": "alt", "⌥": "alt",
    "shift": "shift", "⇧": "shift"
]
let privoxSpecialKeyMap: [UInt16: String] = [
    36: "enter", 48: "tab", 49: "space", 51: "backspace", 53: "esc",
    96: "f5", 97: "f6", 98: "f7", 99: "f3", 100: "f8", 101: "f9", 103: "f11",
    105: "f13", 106: "f16", 107: "f14", 109: "f10", 111: "f12", 113: "f15",
    114: "help", 115: "home", 116: "page_up", 117: "delete", 118: "f4", 119: "end",
    120: "f2", 121: "page_down", 122: "f1", 123: "left", 124: "right", 125: "down", 126: "up"
]

func normalizeHotkeyString(_ hotkey: String) -> String {
    let rawParts = hotkey
        .lowercased()
        .split(separator: "+")
        .map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }

    var modifiers = Set<String>()
    var key: String?

    for part in rawParts {
        if let alias = privoxModifierAliases[part] {
            modifiers.insert(alias)
        } else {
            key = part
        }
    }

    let orderedModifiers = privoxModifierOrder.filter { modifiers.contains($0) }
    let normalizedParts = key.map { orderedModifiers + [$0] } ?? orderedModifiers
    return normalizedParts.joined(separator: "+")
}

func hotkeyHasModifier(_ hotkey: String) -> Bool {
    let normalized = normalizeHotkeyString(hotkey)
    return privoxModifierOrder.contains { normalized.split(separator: "+").contains(Substring($0)) }
}

func hotkeyDisplayString(_ hotkey: String) -> String {
    normalizeHotkeyString(hotkey)
        .split(separator: "+")
        .map { $0.uppercased() }
        .joined(separator: "+")
}

func hotkeyString(from event: NSEvent) -> String? {
    var parts: [String] = []
    let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)

    if flags.contains(.command) { parts.append("cmd") }
    if flags.contains(.control) { parts.append("ctrl") }
    if flags.contains(.option) { parts.append("alt") }
    if flags.contains(.shift) { parts.append("shift") }

    let key: String?
    if let special = privoxSpecialKeyMap[event.keyCode] {
        key = special
    } else if let chars = event.charactersIgnoringModifiers?.lowercased(), !chars.isEmpty {
        key = chars
    } else {
        key = nil
    }

    guard let key, !key.isEmpty else { return nil }
    parts.append(key)
    return normalizeHotkeyString(parts.joined(separator: "+"))
}

final class PrivoxDiagnosticsStore: ObservableObject {
    static let shared = PrivoxDiagnosticsStore()

    @Published var accessibilityGranted = false
    @Published var microphonePermissionGranted = false
    @Published var listenerActive = false
    @Published var audioStreamActive = false
    @Published var listenerStatus = "Waiting for permissions"
    @Published var microphonePermissionStatus = "Checking microphone permission"
    @Published var audioStreamStatus = "Waiting for backend audio"
    @Published var lastDetectedHotkey = "None"
    @Published var lastTriggeredHotkey = "None"
    @Published var backendStatus = "INITIALIZING"
    @Published var backendDetail = "Starting backend"
    @Published var lastEventTimestamp = "Not yet"
    @Published var permissionRecoveryStatus = "Privox will monitor permissions and recover automatically when possible."
    @Published var downloadProgress: Double? = nil
    @Published var downloadStatus = "Waiting for model downloads"

    private init() {}

    func setAccessibilityGranted(_ value: Bool) {
        DispatchQueue.main.async {
            self.accessibilityGranted = value
        }
    }

    func setMicrophonePermission(granted: Bool, status: String) {
        DispatchQueue.main.async {
            self.microphonePermissionGranted = granted
            self.microphonePermissionStatus = status
        }
    }

    func setListener(active: Bool, status: String) {
        DispatchQueue.main.async {
            self.listenerActive = active
            self.listenerStatus = status
        }
    }

    func setAudioStream(active: Bool, status: String) {
        DispatchQueue.main.async {
            self.audioStreamActive = active
            self.audioStreamStatus = status
        }
    }

    func recordDetectedHotkey(_ hotkey: String, matched: Bool) {
        let display = hotkeyDisplayString(hotkey)
        let timestamp = DateFormatter.localizedString(from: Date(), dateStyle: .none, timeStyle: .medium)
        DispatchQueue.main.async {
            self.lastDetectedHotkey = display
            self.lastEventTimestamp = timestamp
            if matched {
                self.lastTriggeredHotkey = display
            }
        }
    }

    func setBackendStatus(_ status: String) {
        DispatchQueue.main.async {
            self.backendStatus = status
        }
    }

    func setBackendDetail(_ detail: String) {
        DispatchQueue.main.async {
            self.backendDetail = detail
        }
    }

    func setPermissionRecoveryStatus(_ status: String) {
        DispatchQueue.main.async {
            self.permissionRecoveryStatus = status
        }
    }

    func setDownloadState(progress: Double?, status: String) {
        DispatchQueue.main.async {
            self.downloadProgress = progress
            self.downloadStatus = status
        }
    }

    func clearDownloadState() {
        DispatchQueue.main.async {
            self.downloadProgress = nil
            self.downloadStatus = "Waiting for model downloads"
        }
    }
}

// A wrapper for macOS Liquid Glass (NSVisualEffectView)
struct LiquidGlassView: NSViewRepresentable {
    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        // Stronger blur material for true liquid glass aesthetic
        view.material = .underWindowBackground
        view.blendingMode = .behindWindow
        view.state = .active
        return view
    }

    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {}
}

final class PrivoxSwiftAudioRecorder {
    private let engine = AVAudioEngine()
    private var audioFile: AVAudioFile?
    private(set) var isRecording = false
    private(set) var currentFileURL: URL?

    func startRecording() throws -> URL {
        if isRecording, let currentFileURL {
            return currentFileURL
        }

        let recordingsDir = privoxAppDataDirectory().appendingPathComponent("recordings", isDirectory: true)
        try FileManager.default.createDirectory(at: recordingsDir, withIntermediateDirectories: true)

        let fileURL = recordingsDir.appendingPathComponent("recording-\(UUID().uuidString).wav")
        let inputNode = engine.inputNode
        let inputFormat = inputNode.inputFormat(forBus: 0)
        guard let outputFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: 16_000,
            channels: 1,
            interleaved: true
        ), let converter = AVAudioConverter(from: inputFormat, to: outputFormat) else {
            throw NSError(domain: "PrivoxAudio", code: 1, userInfo: [NSLocalizedDescriptionKey: "Could not create 16 kHz mono audio converter"])
        }
        let file = try AVAudioFile(forWriting: fileURL, settings: outputFormat.settings)

        inputNode.removeTap(onBus: 0)
        inputNode.installTap(onBus: 0, bufferSize: 2048, format: inputFormat) { [weak self] buffer, _ in
            do {
                let ratio = outputFormat.sampleRate / inputFormat.sampleRate
                let capacity = max(1, AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 8)
                guard let converted = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else {
                    return
                }
                var didProvideInput = false
                var convertError: NSError?
                converter.convert(to: converted, error: &convertError) { _, status in
                    if didProvideInput {
                        status.pointee = .noDataNow
                        return nil
                    }
                    didProvideInput = true
                    status.pointee = .haveData
                    return buffer
                }
                if let convertError {
                    appLog("Swift audio conversion failed: \(convertError.localizedDescription)")
                    return
                }
                if converted.frameLength > 0 {
                    try self?.audioFile?.write(from: converted)
                }
            } catch {
                appLog("Swift audio write failed: \(error.localizedDescription)")
            }
        }

        audioFile = file
        currentFileURL = fileURL
        engine.prepare()
        try engine.start()
        isRecording = true
        appLog("Swift microphone recording started: \(fileURL.path)")
        return fileURL
    }

    func stopRecording() -> URL? {
        guard isRecording else { return nil }
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        audioFile = nil
        isRecording = false
        let url = currentFileURL
        appLog("Swift microphone recording stopped: \(url?.path ?? "none")")
        return url
    }
}

@main
struct PrivoxApp: App {
    // AppDelegate handles the MenuBar (Tray) icon to mimic pystray behaviour natively
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    
    var body: some Scene {
        // We use Settings instead of WindowGroup so it doesn't open a blank window on launch
        Settings {
            SettingsView()
                .frame(minWidth: 900, minHeight: 700)
                .background(LiquidGlassView()) // The requested native macOS theme
                .edgesIgnoringSafeArea(.all)
        }
    }
}

class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    /// Launched from PyInstaller tray: only show SwiftUI settings; no menu-bar duplicate, no second Python process.
    private var isSwiftSettingsOnly: Bool {
        ProcessInfo.processInfo.environment["PRIVOX_SWIFT_SETTINGS_ONLY"] == "1"
    }

    var statusItem: NSStatusItem!
    var settingsWindowController: NSWindowController?
    var globalEventMonitor: Any?
    private var hotkeyRecoveryTimer: Timer?
    private var eventTapRunLoopSource: CFRunLoopSource?
    private var lastAudioReconnectAttempt = Date.distantPast
    private var isPermissionPanelVisible = false
    private var hasShownPermissionPanelThisSession = false
    private static let installHintDefaultsKey = "PrivoxInstallLocationHintSuppressed"
    private let audioRecorder = PrivoxSwiftAudioRecorder()
    
    // Animation state
    private var animationTimer: Timer?
    private var animationFrame = 0
    private var currentStatus = "READY"

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Force-Initialize BackendManager (starts Python unless PRIVOX_SWIFT_SETTINGS_ONLY=1)
        _ = BackendManager.shared

        if isSwiftSettingsOnly {
            NSApp.setActivationPolicy(.regular)
            DispatchQueue.main.async { [weak self] in
                self?.showSettings()
            }
            return
        }
        
        // Listen for status updates from Python via BackendManager
        NotificationCenter.default.addObserver(self, selector: #selector(handleStatusChange), name: NSNotification.Name("PrivoxStatusChanged"), object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(handleBackendDetail), name: NSNotification.Name("PrivoxBackendDetail"), object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(handleApplicationDidBecomeActive), name: NSApplication.didBecomeActiveNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(handleApplicationDidResignActive), name: NSApplication.didResignActiveNotification, object: nil)

        syncMicrophonePermission(triggerReconnectIfNeeded: false)
        
        // Request Microphone access explicitly on launch
        AVCaptureDevice.requestAccess(for: .audio) { granted in
            if granted {
                appLog("Microphone access granted.")
                PrivoxDiagnosticsStore.shared.setMicrophonePermission(granted: true, status: "Microphone permission granted")
                PrivoxDiagnosticsStore.shared.setBackendDetail("Microphone permission granted")
                PrivoxDiagnosticsStore.shared.setPermissionRecoveryStatus("Microphone access is available. Privox will reconnect audio automatically.")
                PrivoxDiagnosticsStore.shared.setAudioStream(active: true, status: "Swift owns microphone capture")
            } else {
                appLog("Microphone access denied. Transcription will not work.")
                PrivoxDiagnosticsStore.shared.setMicrophonePermission(granted: false, status: "Microphone permission denied")
                PrivoxDiagnosticsStore.shared.setBackendDetail("Microphone permission denied")
                PrivoxDiagnosticsStore.shared.setPermissionRecoveryStatus("Open Microphone settings, allow Privox, then return to the app. Privox will retry automatically.")
            }
        }
        
        // Request Accessibility access for Global Hotkey
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
        let isTrusted = AXIsProcessTrustedWithOptions(options)
        appLog("Accessibility process trusted: \(isTrusted)")
        PrivoxDiagnosticsStore.shared.setAccessibilityGranted(isTrusted)
        updatePermissionRecoveryStatus()
        
        // Start Global Hotkey Listener
        refreshGlobalHotkeyListener(force: true)
        startHotkeyRecoveryWatcher()
        
        // 1. Setup Menu Bar Icon
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        updateStatusIcon()

        // 2. Setup the Dropdown Menu (Replica of PyQt setup)
        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "Settings", action: #selector(showSettings), keyEquivalent: "s"))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Quit Privox", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))

        statusItem.menu = menu
        
        // Hide dock icon since we are a menu bar app
        NSApp.setActivationPolicy(.accessory)

        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
            self?.suggestApplicationsFolderIfNeeded()
        }
    }

    private func isRunningFromRecommendedApplicationsFolder() -> Bool {
        let bundlePath = (Bundle.main.bundlePath as NSString).standardizingPath
        let systemApps = ("/Applications" as NSString).standardizingPath
        let userApps = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Applications", isDirectory: true).path
        let userAppsNorm = (userApps as NSString).standardizingPath
        return bundlePath.hasPrefix(systemApps + "/") || bundlePath.hasPrefix(userAppsNorm + "/")
    }

    /// Nudge users to copy the app into /Applications so TCC permissions survive updates more reliably.
    private func suggestApplicationsFolderIfNeeded() {
        guard !isSwiftSettingsOnly else { return }
        if ProcessInfo.processInfo.environment["PRIVOX_SKIP_INSTALL_HINT"] == "1" { return }
        if UserDefaults.standard.bool(forKey: Self.installHintDefaultsKey) { return }
        if isRunningFromRecommendedApplicationsFolder() { return }

        let alert = NSAlert()
        alert.messageText = "建議安裝位置"
        alert.informativeText = "將 Privox 放在「應用程式」資料夾，隱私權限在更新後較容易延續。請結束程式後拖移 Privox.app 再開啟。"
        alert.addButton(withTitle: "開啟「應用程式」")
        alert.addButton(withTitle: "在 Finder 顯示")
        alert.addButton(withTitle: "不再提示")
        let response = alert.runModal()
        switch response {
        case .alertFirstButtonReturn:
            NSWorkspace.shared.open(URL(fileURLWithPath: "/Applications", isDirectory: true))
        case .alertSecondButtonReturn:
            NSWorkspace.shared.activateFileViewerSelecting([Bundle.main.bundleURL])
        default:
            UserDefaults.standard.set(true, forKey: Self.installHintDefaultsKey)
        }
    }

    @objc private func handleStatusChange(_ notification: Notification) {
        if let status = notification.userInfo?["status"] as? String {
            currentStatus = status
            PrivoxDiagnosticsStore.shared.setBackendStatus(status)
            switch status {
            case "INITIALIZING":
                PrivoxDiagnosticsStore.shared.setDownloadState(progress: nil, status: "Preparing Privox backend")
            case "DOWNLOADING":
                if PrivoxDiagnosticsStore.shared.downloadProgress == nil {
                    PrivoxDiagnosticsStore.shared.setDownloadState(progress: 0, status: "Downloading required AI models")
                }
            case "READY", "ERROR":
                PrivoxDiagnosticsStore.shared.clearDownloadState()
            default:
                break
            }
            updateStatusIcon()
        }
    }

    @objc private func handleBackendDetail(_ notification: Notification) {
        if let detail = notification.userInfo?["detail"] as? String {
            appLog("Backend detail: \(detail)")
            if detail.hasPrefix("DOWNLOAD_PROGRESS|") {
                let parts = detail.components(separatedBy: "|")
                let percent = parts.count > 1 ? Double(parts[1]) : nil
                let status = parts.count > 2 ? parts.dropFirst(2).joined(separator: "|") : "Downloading required AI models"
                let normalizedProgress = percent == nil || percent == -1 ? nil : max(0, min(100, percent!)) / 100
                PrivoxDiagnosticsStore.shared.setDownloadState(progress: normalizedProgress, status: status)
                PrivoxDiagnosticsStore.shared.setBackendDetail(status)
                return
            }
            if detail.hasPrefix("PASTE_TEXT_B64|") {
                handlePasteTextDetail(detail)
                return
            }
            switch detail {
            case "BACKEND_EXITED":
                PrivoxDiagnosticsStore.shared.setAudioStream(active: false, status: "Backend process exited")
            case "MICROPHONE_STREAM_ACTIVE":
                PrivoxDiagnosticsStore.shared.setAudioStream(active: true, status: "Audio stream is active")
            case "MICROPHONE_STREAM_INACTIVE":
                PrivoxDiagnosticsStore.shared.setAudioStream(active: false, status: "Audio stream is inactive")
            case "MICROPHONE_RECONNECTING":
                PrivoxDiagnosticsStore.shared.setAudioStream(active: false, status: "Attempting to reconnect microphone")
            case "MICROPHONE_UNAVAILABLE":
                PrivoxDiagnosticsStore.shared.setAudioStream(active: false, status: "Backend could not open the microphone")
            default:
                break
            }
            PrivoxDiagnosticsStore.shared.setBackendDetail(detail)
        }
    }

    private func handlePasteTextDetail(_ detail: String) {
        let encoded = String(detail.dropFirst("PASTE_TEXT_B64|".count))
        guard
            let data = Data(base64Encoded: encoded),
            let text = String(data: data, encoding: .utf8)
        else {
            appLog("Invalid PASTE_TEXT_B64 payload from backend.")
            PrivoxDiagnosticsStore.shared.setBackendDetail("Paste payload decode failed")
            return
        }
        pasteTextFromSwift(text)
    }

    private func pasteTextFromSwift(_ text: String) {
        let pasteboard = NSPasteboard.general
        let previousString = pasteboard.string(forType: .string)
        pasteboard.clearContents()
        pasteboard.setString(text, forType: .string)

        let src = CGEventSource(stateID: .hidSystemState)
        let keyDown = CGEvent(keyboardEventSource: src, virtualKey: 0x09, keyDown: true) // V
        let keyUp = CGEvent(keyboardEventSource: src, virtualKey: 0x09, keyDown: false)
        keyDown?.flags = .maskCommand
        keyUp?.flags = .maskCommand
        keyDown?.post(tap: .cghidEventTap)
        keyUp?.post(tap: .cghidEventTap)

        PrivoxDiagnosticsStore.shared.setBackendDetail("Pasted transcript via Swift")

        // Give the target app time to consume the pasteboard before restoring it.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
            if let previousString {
                pasteboard.clearContents()
                pasteboard.setString(previousString, forType: .string)
            }
        }
    }

    @objc private func handleApplicationDidBecomeActive() {
        appLog("Privox became active. Refreshing permissions and listener state.")
        refreshPermissionRecoveryState(forceListenerRefresh: true)
    }

    @objc private func handleApplicationDidResignActive() {
        PrivoxDiagnosticsStore.shared.setPermissionRecoveryStatus("If you are changing permissions in System Settings, return to Privox afterwards and it will refresh automatically.")
    }

    private func updateStatusIcon() {
        guard let button = statusItem.button else { return }
        
        // Stop current animation timer if it exists
        animationTimer?.invalidate()
        animationTimer = nil
        
        switch currentStatus {
        case "RECORDING":
            startPulseAnimation()
        case "PROCESSING", "DOWNLOADING", "INITIALIZING":
            startSpinAnimation()
        case "ERROR":
            button.image = NSImage(systemSymbolName: "waveform.circle.fill", accessibilityDescription: "Error")
            button.contentTintColor = .systemRed
        case "SLEEP":
            button.image = NSImage(systemSymbolName: "waveform", accessibilityDescription: "Sleep")
            button.contentTintColor = .secondaryLabelColor
        default: // READY
            button.image = NSImage(systemSymbolName: "waveform", accessibilityDescription: "Ready")
            button.contentTintColor = nil // Use system default (black/white)
        }
    }

    private func startPulseAnimation() {
        animationFrame = 0
        animationTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            guard let self = self, let button = self.statusItem.button else { return }
            self.animationFrame += 1
            
            // Toggle between symbol variations or scale
            let symbol = (self.animationFrame % 2 == 0) ? "waveform.circle" : "waveform.circle.fill"
            button.image = NSImage(systemSymbolName: symbol, accessibilityDescription: "Recording")
            button.contentTintColor = .systemRed
        }
    }

    private func startSpinAnimation() {
        animationFrame = 0
        animationTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            guard let self = self, let button = self.statusItem.button else { return }
            self.animationFrame += 1
            
            // For a simple native spinner, we cycle different symbols
            let symbols = ["circle.dashed", "circle.dotted", "circle.circle"]
            let symbol = symbols[self.animationFrame % symbols.count]
            button.image = NSImage(systemSymbolName: symbol, accessibilityDescription: "Processing")
            button.contentTintColor = .systemBlue
        }
    }

    @objc func showSettings() {
        // Bring app to front
        NSApp.activate(ignoringOtherApps: true)
        
        if settingsWindowController == nil {
            let view = SettingsView().background(LiquidGlassView()).edgesIgnoringSafeArea(.all)
            let hostingController = NSHostingController(rootView: view)
            let window = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 900, height: 700),
                styleMask: [.titled, .closable, .miniaturizable, .fullSizeContentView],
                backing: .buffered,
                defer: false
            )
            
            // Clean titlebar for premium glass look
            window.titlebarAppearsTransparent = true
            window.titleVisibility = .hidden
            window.isOpaque = false
            window.backgroundColor = .clear
            
            window.contentViewController = hostingController
            
            // Explicitly force the window size to prevent auto-shrinking from SwiftUI inner contents
            window.setContentSize(NSSize(width: 800, height: 600))
            window.minSize = NSSize(width: 800, height: 600)
            
            window.center()
            window.setFrameAutosaveName("PrivoxSettings")

            if isSwiftSettingsOnly {
                window.delegate = self
            }
            
            settingsWindowController = NSWindowController(window: window)
        }
        
        settingsWindowController?.showWindow(nil)
    }

    func windowWillClose(_ notification: Notification) {
        guard isSwiftSettingsOnly else { return }
        NSApp.terminate(nil)
    }
    
    // MARK: - Global Hotkey Listener (CGEventTap)
    private var eventTap: CFMachPort?

    func setupGlobalHotkeyListener() {
        let isTrusted = AXIsProcessTrusted()
        appLog("Attempting to setup CGEventTap. Accessibility Trusted: \(isTrusted)")
        
        if eventTap != nil {
            appLog("CGEventTap already exists. Skipping recreation.")
            return
        }
        
        let mask = (1 << CGEventType.keyDown.rawValue)
        let tap = CGEvent.tapCreate(
            tap: .cghidEventTap,
            place: .headInsertEventTap,
            options: .listenOnly,
            eventsOfInterest: CGEventMask(mask),
            callback: { (proxy, type, event, refcon) -> Unmanaged<CGEvent>? in
                if let refcon = refcon {
                    let mySelf = Unmanaged<AppDelegate>.fromOpaque(refcon).takeUnretainedValue()
                    if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
                        appLog("CGEventTap was disabled by the system. Re-enabling...")
                        if let tap = mySelf.eventTap {
                            CGEvent.tapEnable(tap: tap, enable: true)
                        }
                        return Unmanaged.passUnretained(event)
                    }
                    if type == .keyDown {
                        if let nsEvent = NSEvent(cgEvent: event) {
                            mySelf.handleGlobalEvent(nsEvent)
                        }
                    }
                }
                return Unmanaged.passUnretained(event)
            },
            userInfo: UnsafeMutableRawPointer(Unmanaged.passUnretained(self).toOpaque())
        )
        
        guard let validTap = tap else {
            appLog("CGEventTap creation failed. Accessibility trust likely still False.")
            PrivoxDiagnosticsStore.shared.setListener(active: false, status: "Listener unavailable")
            presentMissingPermissionPanelIfNeeded(force: true)
            return
        }
        
        eventTap = validTap
        let runLoopSource = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, validTap, 0)
        eventTapRunLoopSource = runLoopSource
        CFRunLoopAddSource(CFRunLoopGetCurrent(), runLoopSource, .commonModes)
        CGEvent.tapEnable(tap: validTap, enable: true)
        appLog("CGEventTap Hotkey Listener Successfully Registered.")
        PrivoxDiagnosticsStore.shared.setListener(active: true, status: "Listening globally")
    }

    private func teardownGlobalHotkeyListener() {
        if let tap = eventTap {
            CGEvent.tapEnable(tap: tap, enable: false)
        }
        if let source = eventTapRunLoopSource {
            CFRunLoopRemoveSource(CFRunLoopGetCurrent(), source, .commonModes)
        }
        eventTapRunLoopSource = nil
        eventTap = nil
        PrivoxDiagnosticsStore.shared.setListener(active: false, status: "Listener reset")
    }

    func refreshGlobalHotkeyListener(force: Bool = false) {
        let isTrusted = AXIsProcessTrusted()
        PrivoxDiagnosticsStore.shared.setAccessibilityGranted(isTrusted)
        if force {
            teardownGlobalHotkeyListener()
        }
        guard isTrusted else {
            appLog("Skipping listener setup because Accessibility permission is still missing.")
            PrivoxDiagnosticsStore.shared.setListener(active: false, status: "Grant Accessibility to enable hotkey")
            updatePermissionRecoveryStatus()
            presentMissingPermissionPanelIfNeeded(force: true)
            return
        }
        if eventTap == nil {
            setupGlobalHotkeyListener()
        }
        updatePermissionRecoveryStatus()
    }

    private func openPrivacyPane(_ pane: String) {
        guard let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?\(pane)") else { return }
        NSWorkspace.shared.open(url)
    }

    private func revealCurrentAppInFinder() {
        // Prefer the .app bundle path so user can add the correct target in Input Monitoring.
        NSWorkspace.shared.activateFileViewerSelecting([Bundle.main.bundleURL])
    }

    private func presentMissingPermissionPanelIfNeeded(force: Bool = false) {
        let accessibilityMissing = !AXIsProcessTrusted()
        // Heuristic: AX granted but listener still unavailable -> Input Monitoring likely missing.
        let inputMonitoringLikelyMissing = !accessibilityMissing && (eventTap == nil)
        let hasMissing = accessibilityMissing || inputMonitoringLikelyMissing
        guard hasMissing else { return }
        if isPermissionPanelVisible { return }
        if hasShownPermissionPanelThisSession && !force { return }

        isPermissionPanelVisible = true
        hasShownPermissionPanelThisSession = true
        defer { isPermissionPanelVisible = false }

        while true {
            var actions: [(title: String, pane: String?)] = []
            if accessibilityMissing {
                actions.append(("開啟「輔助使用」", "Privacy_Accessibility"))
            }
            if inputMonitoringLikelyMissing {
                actions.append(("開啟「輸入監控」", "Privacy_ListenEvent"))
                actions.append(("顯示目前 App 檔案", nil))
            }
            guard !actions.isEmpty else { break }

            let alert = NSAlert()
            alert.messageText = "Privox 需要權限"
            alert.informativeText = "請開啟缺少的權限。"
            alert.alertStyle = .warning
            for action in actions {
                alert.addButton(withTitle: action.title)
            }
            alert.addButton(withTitle: "完成")
            alert.addButton(withTitle: "取消")

            let response = alert.runModal()
            let idx = Int(response.rawValue - NSApplication.ModalResponse.alertFirstButtonReturn.rawValue)
            if idx >= 0 && idx < actions.count {
                if let pane = actions[idx].pane {
                    openPrivacyPane(pane)
                } else {
                    revealCurrentAppInFinder()
                }
                continue
            }
            break
        }
    }

    private func startHotkeyRecoveryWatcher() {
        hotkeyRecoveryTimer?.invalidate()
        hotkeyRecoveryTimer = Timer.scheduledTimer(withTimeInterval: 1.5, repeats: true) { [weak self] timer in
            guard let self = self else {
                timer.invalidate()
                return
            }
            self.refreshPermissionRecoveryState(forceListenerRefresh: false)
        }
    }

    private func syncMicrophonePermission(triggerReconnectIfNeeded: Bool) {
        let micAuthStatus = AVCaptureDevice.authorizationStatus(for: .audio)
        switch micAuthStatus {
        case .authorized:
            PrivoxDiagnosticsStore.shared.setMicrophonePermission(granted: true, status: "Microphone permission granted")
            let enoughTimeElapsed = Date().timeIntervalSince(lastAudioReconnectAttempt) > 4
            if triggerReconnectIfNeeded && !PrivoxDiagnosticsStore.shared.audioStreamActive && enoughTimeElapsed {
                appLog("Microphone permission available. Swift owns microphone capture; marking audio ready.")
                lastAudioReconnectAttempt = Date()
                PrivoxDiagnosticsStore.shared.setAudioStream(active: true, status: "Swift owns microphone capture")
            }
        case .denied, .restricted:
            PrivoxDiagnosticsStore.shared.setMicrophonePermission(granted: false, status: "Microphone permission denied")
            PrivoxDiagnosticsStore.shared.setAudioStream(active: false, status: "Grant microphone access to restore audio input")
        case .notDetermined:
            PrivoxDiagnosticsStore.shared.setMicrophonePermission(granted: false, status: "Awaiting microphone permission prompt")
        @unknown default:
            PrivoxDiagnosticsStore.shared.setMicrophonePermission(granted: false, status: "Microphone permission status unknown")
        }
    }

    private func refreshPermissionRecoveryState(forceListenerRefresh: Bool) {
        syncMicrophonePermission(triggerReconnectIfNeeded: true)

        let isTrusted = AXIsProcessTrusted()
        PrivoxDiagnosticsStore.shared.setAccessibilityGranted(isTrusted)

        if isTrusted {
            if forceListenerRefresh || eventTap == nil {
                appLog("Accessibility permission available. Refreshing hotkey listener.")
                refreshGlobalHotkeyListener(force: true)
            }
        } else if eventTap != nil {
            appLog("Accessibility permission appears to have been removed. Tearing down hotkey listener.")
            teardownGlobalHotkeyListener()
        } else {
            PrivoxDiagnosticsStore.shared.setListener(active: false, status: "Grant Accessibility to enable hotkey")
        }

        updatePermissionRecoveryStatus()
    }

    func refreshPermissionsAndRecoveryState() {
        refreshPermissionRecoveryState(forceListenerRefresh: true)
    }

    /// Resets the macOS TCC permissions Privox relies on so the user can grant fresh access (e.g. after an update).
    /// Caller should show an alert and optionally open System Settings; user should quit and relaunch to complete the flow.
    func resetAccessibilityAccess(completion: @escaping (Bool, String) -> Void) {
        let bundleId = Bundle.main.bundleIdentifier ?? "ai.privox.app"
        DispatchQueue.global(qos: .userInitiated).async {
            let services = [
                ("Accessibility", "Accessibility"),
                ("ListenEvent", "Input Monitoring"),
                ("AppleEvents", "Automation"),
                ("Microphone", "Microphone")
            ]
            var resetLabels: [String] = []
            var failures: [String] = []

            for (service, label) in services {
                let process = Process()
                process.executableURL = URL(fileURLWithPath: "/usr/bin/tccutil")
                process.arguments = ["reset", service, bundleId]
                do {
                    try process.run()
                    process.waitUntilExit()
                    if process.terminationStatus == 0 {
                        resetLabels.append(label)
                    } else {
                        failures.append("\(label) exited with code \(process.terminationStatus)")
                    }
                } catch {
                    failures.append("\(label): \(error.localizedDescription)")
                }
            }

            let success = failures.isEmpty
            let message: String
            if success {
                message = "Reset Privox privacy permissions for \(resetLabels.joined(separator: ", ")). Quit Privox and relaunch it, then grant Accessibility, Input Monitoring, Microphone, and any requested Automation permission for this signed app."
            } else if !resetLabels.isEmpty {
                message = "Partially reset Privox privacy permissions for \(resetLabels.joined(separator: ", ")). Some resets failed: \(failures.joined(separator: "; ")). If issues continue, remove Privox manually from System Settings → Privacy & Security for Accessibility, Input Monitoring, Automation, and Microphone, then relaunch."
            } else {
                message = "Could not reset Privox privacy permissions: \(failures.joined(separator: "; ")). Open System Settings → Privacy & Security and remove Privox from Accessibility, Input Monitoring, Automation, and Microphone, then relaunch."
            }

            DispatchQueue.main.async { completion(success, message) }
        }
    }

    private func updatePermissionRecoveryStatus() {
        let accessibilityGranted = AXIsProcessTrusted()
        let microphoneGranted = AVCaptureDevice.authorizationStatus(for: .audio) == .authorized

        let status: String
        if !accessibilityGranted && !microphoneGranted {
            status = "Privox is waiting for Accessibility and Microphone access. If hotkeys still fail after Accessibility is granted, also allow Privox in Input Monitoring."
        } else if !accessibilityGranted {
            status = "Accessibility is missing. Open System Settings, allow Privox, then return to the app. If the listener still cannot start, also grant Input Monitoring."
        } else if !microphoneGranted {
            status = "Microphone access is missing. Open System Settings, allow Privox, then return to the app. Audio will reconnect automatically."
        } else {
            status = "Permissions look healthy. If macOS changes them while Privox is running, the app will refresh and recover automatically."
        }

        PrivoxDiagnosticsStore.shared.setPermissionRecoveryStatus(status)
    }
    
    private func handleGlobalEvent(_ event: NSEvent) {
        let prefsURL = privoxAppDataDirectory().appendingPathComponent(".user_prefs.json")
        var expected = "ctrl+shift+space"
        do {
            if !FileManager.default.fileExists(atPath: prefsURL.path) {
                appLog("Config file NOT FOUND at: \(prefsURL.path)")
            } else {
                let data = try Data(contentsOf: prefsURL)
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    if let h = json["hotkey"] as? String {
                        expected = normalizeHotkeyString(h)
                    } else {
                        appLog("JSON found but 'hotkey' key is missing. Keys: \(json.keys.joined(separator: ", "))")
                    }
                }
            }
        } catch {
            appLog("Failed to read/parse prefs at \(prefsURL.path): \(error)")
        }
        
        if let parsedStr = hotkeyString(from: event) {
            PrivoxDiagnosticsStore.shared.recordDetectedHotkey(parsedStr, matched: parsedStr == expected)

            if parsedStr == expected {
                PrivoxDiagnosticsStore.shared.setBackendDetail("Hotkey matched and Swift audio toggle started")
                toggleSwiftRecording()
            }
        }
    }

    private func toggleSwiftRecording() {
        guard AVCaptureDevice.authorizationStatus(for: .audio) == .authorized else {
            PrivoxDiagnosticsStore.shared.setBackendDetail("Microphone permission is required before recording")
            syncMicrophonePermission(triggerReconnectIfNeeded: false)
            return
        }

        if audioRecorder.isRecording {
            guard let fileURL = audioRecorder.stopRecording() else {
                currentStatus = "READY"
                updateStatusIcon()
                PrivoxDiagnosticsStore.shared.setBackendStatus("READY")
                return
            }
            currentStatus = "PROCESSING"
            updateStatusIcon()
            PrivoxDiagnosticsStore.shared.setBackendStatus("PROCESSING")
            PrivoxDiagnosticsStore.shared.setBackendDetail("Swift recording saved; sending to backend")
            BackendManager.shared.sendCommand("TRANSCRIBE_FILE|\(fileURL.path)")
        } else {
            do {
                _ = try audioRecorder.startRecording()
                currentStatus = "RECORDING"
                updateStatusIcon()
                PrivoxDiagnosticsStore.shared.setBackendStatus("RECORDING")
                PrivoxDiagnosticsStore.shared.setAudioStream(active: true, status: "Recording via Swift microphone capture")
            } catch {
                appLog("Could not start Swift microphone recording: \(error.localizedDescription)")
                currentStatus = "ERROR"
                updateStatusIcon()
                PrivoxDiagnosticsStore.shared.setBackendStatus("ERROR")
                PrivoxDiagnosticsStore.shared.setBackendDetail("Swift microphone failed: \(error.localizedDescription)")
            }
        }
    }
}
