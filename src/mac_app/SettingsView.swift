import SwiftUI
import Foundation

// MARK: - Models
struct UserPrefs: Codable {
    var character: String = "Writing Assistant"
    var tone: String = "Natural"
    var whisper_model: String = "Distil-Whisper Large v3 (English)"
    var current_refiner: String = "Llama 3.2 3B Instruct"
    var custom_dictionary: [String] = []
    
    // Additional settings
    var custom_prompts: [String: String] = [:]
    var sound_enabled: Bool = true
    var vram_timeout: Int = 300
    var silence_timeout_ms: Int = 10000
    var paste_delay_seconds: Int = 0
    var hotkey: String = "ctrl+shift+space"
    
    // Using a dictionary to catch any other keys we don't strictly model here
    private var additionalData: [String: AnyCodable] = [:]
    
    enum CodingKeys: String, CodingKey {
        case character, tone, whisper_model, current_refiner, custom_dictionary,
             custom_prompts, sound_enabled, vram_timeout, silence_timeout_ms, paste_delay_seconds, hotkey
    }
}

func normalizeASRPreference(_ value: String) -> String {
    switch value.trimmingCharacters(in: .whitespacesAndNewlines) {
    case "turbo", "large-v3-turbo":
        return "Whisper Large v3 Turbo (Multilingual)"
    case "distil-large-v3":
        return "Distil-Whisper Large v3 (English)"
    case "small":
        return "OpenAI Whisper Small"
    case "Qwen2-Audio-7B", "qwen2-audio-7b":
        return "Whisper Large v3 Turbo (Multilingual)"
    default:
        return value
    }
}

func normalizeLLMPreference(_ value: String) -> String {
    switch value.trimmingCharacters(in: .whitespacesAndNewlines) {
    case "Standard (Llama 3.2)":
        return "Llama 3.2 3B Instruct"
    case "Multilingual (Qwen 3.5 9B)", "Qwen3.5-9B-Q4_K_M.gguf", "Qwen3-8B-Q4_K_M.gguf":
        return "Multilingual (Qwen 3 8B)"
    case "Multilingual (Qwen 3.5 4B)", "Qwen3.5-4B-Q4_K_M.gguf", "Qwen3-4B-Q4_K_M.gguf":
        return "Multilingual (Qwen 3 4B)"
    case "Qwen2.5-7B-Instruct-Q4_K_M.gguf":
        return "Multilingual (Qwen 2.5 7B)"
    case "Llama-3.2-3B-Instruct-Q4_K_M.gguf":
        return "Llama 3.2 3B Instruct"
    default:
        return value
    }
}

// Fallback for preserving unknown JSON keys
struct AnyCodable: Codable {
    var value: Any
    
    init(_ value: Any) { self.value = value }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let intVal = try? container.decode(Int.self) { value = intVal }
        else if let doubleVal = try? container.decode(Double.self) { value = doubleVal }
        else if let boolVal = try? container.decode(Bool.self) { value = boolVal }
        else if let stringVal = try? container.decode(String.self) { value = stringVal }
        else { value = "UNKNOWN_TYPE" }
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        if let val = value as? Int { try container.encode(val) }
        else if let val = value as? Double { try container.encode(val) }
        else if let val = value as? Bool { try container.encode(val) }
        else if let val = value as? String { try container.encode(val) }
        else { try container.encode("UNKNOWN_TYPE") }
    }
}

struct HotkeyAssessment {
    let level: String
    let message: String
    let color: Color
    let isBlocked: Bool
}

let privoxRecommendedHotkeys = [
    "ctrl+shift+space",
    "cmd+alt+z",
    "cmd+shift+;"
]

func assessHotkey(_ hotkey: String) -> HotkeyAssessment {
    let normalized = normalizeHotkeyString(hotkey)
    let blockedHotkeys: Set<String> = [
        "cmd+space",
        "cmd+tab",
        "cmd+q",
        "cmd+w",
        "cmd+h",
        "cmd+m",
        "cmd+alt+esc",
        "ctrl+space"
    ]

    if normalized.isEmpty || normalized == "..." {
        return HotkeyAssessment(
            level: "Pending",
            message: "Choose a shortcut with at least one modifier key.",
            color: .secondary,
            isBlocked: false
        )
    }

    if !hotkeyHasModifier(normalized) {
        return HotkeyAssessment(
            level: "Blocked",
            message: "Use at least one modifier key so Privox can detect the shortcut reliably.",
            color: .red,
            isBlocked: true
        )
    }

    if blockedHotkeys.contains(normalized) {
        return HotkeyAssessment(
            level: "Blocked",
            message: "This shortcut commonly conflicts with macOS system shortcuts. Pick another one.",
            color: .red,
            isBlocked: true
        )
    }

    if normalized.contains("space") || (normalized.contains("cmd") && !normalized.contains("alt")) {
        return HotkeyAssessment(
            level: "Medium Risk",
            message: "This combo should work, but it may overlap with input methods or app shortcuts on some Macs.",
            color: .orange,
            isBlocked: false
        )
    }

    return HotkeyAssessment(
        level: "Low Risk",
        message: "This combo is a good candidate for a global Privox hotkey.",
        color: .green,
        isBlocked: false
    )
}

struct StatusPill: View {
    let title: String
    let color: Color

    var body: some View {
        Text(title.uppercased())
            .font(.system(size: 10, weight: .bold, design: .rounded))
            .tracking(1)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(color.opacity(0.14))
            .foregroundColor(color)
            .clipShape(Capsule())
    }
}

struct DiagnosticsMetricCard: View {
    let title: String
    let value: String
    let subtitle: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            StatusPill(title: title, color: tint)
            Text(value)
                .font(.system(size: 18, weight: .bold))
                .lineLimit(2)
            Text(subtitle)
                .font(.system(size: 12))
                .foregroundColor(.secondary)
                .lineLimit(2)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.thinMaterial)
        .cornerRadius(14)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(tint.opacity(0.18), lineWidth: 1))
    }
}

struct DiagnosticsHintCard: View {
    let title: String
    let bodyText: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 11, weight: .bold))
                .foregroundColor(tint)
            Text(bodyText)
                .font(.system(size: 12))
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.thinMaterial)
        .cornerRadius(14)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(tint.opacity(0.14), lineWidth: 1))
    }
}

struct DiagnosticsProgressCard: View {
    let title: String
    let bodyText: String
    let tint: Color
    let progress: Double?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            StatusPill(title: title, color: tint)
            Text(bodyText)
                .font(.system(size: 13))
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if let progress {
                ProgressView(value: progress)
                    .progressViewStyle(.linear)
                    .tint(tint)
                Text("\(Int(progress * 100))%")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundColor(tint)
            } else {
                ProgressView()
                    .progressViewStyle(.linear)
                    .tint(tint)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.thinMaterial)
        .cornerRadius(14)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(tint.opacity(0.16), lineWidth: 1))
    }
}

class SettingsManager: ObservableObject {
    @Published var prefs: UserPrefs = UserPrefs()
    @Published var savedHotkey: String = normalizeHotkeyString(UserPrefs().hotkey)
    private var prefsURL: URL
    
    init() {
        prefsURL = privoxAppDataDirectory().appendingPathComponent(".user_prefs.json")
        
        loadPrefs()
    }
    
    func loadPrefs() {
        do {
            if FileManager.default.fileExists(atPath: prefsURL.path) {
                let data = try Data(contentsOf: prefsURL)
                prefs = try JSONDecoder().decode(UserPrefs.self, from: data)
                let normalizedASR = normalizeASRPreference(prefs.whisper_model)
                let normalizedLLM = normalizeLLMPreference(prefs.current_refiner)
                if normalizedASR != prefs.whisper_model || normalizedLLM != prefs.current_refiner {
                    prefs.whisper_model = normalizedASR
                    prefs.current_refiner = normalizedLLM
                    try JSONEncoder().encode(prefs).write(to: prefsURL)
                }
            }
            savedHotkey = normalizeHotkeyString(prefs.hotkey)
        } catch {
            print("Failed to load prefs: \(error)")
        }
    }
    
    func savePrefs() {
        do {
            try FileManager.default.createDirectory(at: prefsURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            prefs.whisper_model = normalizeASRPreference(prefs.whisper_model)
            prefs.current_refiner = normalizeLLMPreference(prefs.current_refiner)
            let data = try JSONEncoder().encode(prefs)
            try data.write(to: prefsURL)
            savedHotkey = normalizeHotkeyString(prefs.hotkey)
            // Trigger Python backend reload
            BackendManager.shared.sendCommand("RELOAD_CONFIG")
        } catch {
            print("Failed to save prefs: \(error)")
        }
    }
}

// MARK: - Views
struct SettingsView: View {
    @StateObject private var manager = SettingsManager()
    @State private var selectedTab = "AI Models"
    
    let tabs = ["AI Models", "General", "Dictionary"]
    
    var body: some View {
        HStack(spacing: 0) {
            // Sidebar
            VStack(alignment: .leading, spacing: 8) {
                Text("PRIVOX SETTINGS")
                    .font(.system(size: 11, weight: .heavy, design: .rounded))
                    .foregroundColor(.secondary)
                    .tracking(2)
                    .padding(.bottom, 24)
                    .padding(.leading, 10)
                
                ForEach(tabs, id: \.self) { tab in
                    SidebarButton(title: tab, isSelected: selectedTab == tab) {
                        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                            selectedTab = tab
                        }
                    }
                }
                Spacer()
            }
            .padding(.top, 60) // Increased to clear macOS window traffic lights
            .padding(.horizontal, 10)
            .frame(width: 200, alignment: .topLeading)
            .frame(maxHeight: .infinity, alignment: .top)
            .background(.ultraThinMaterial) // Native native frosted sidebar
            
            // Content Area
            VStack(alignment: .leading) {
                switch selectedTab {
                case "AI Models":
                    ModelsView(manager: manager)
                case "General":
                    GeneralView(manager: manager)
                case "Dictionary":
                    DictionaryView(manager: manager)
                default:
                    EmptyView()
                }
            }
            .padding(.top, 50) // Clear traffic lights for content area
            .padding(.horizontal, 40)
            .padding(.bottom, 40)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .frame(width: 800, height: 600) // Hard lock the size to match the NSWindow
        .foregroundColor(.primary)
        .font(.system(size: 14, weight: .medium, design: .rounded))
    }
}

struct SidebarButton: View {
    let title: String
    let isSelected: Bool
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            HStack {
                if isSelected {
                    Rectangle()
                        .fill(Color.white)
                        .frame(width: 3, height: 16)
                        .cornerRadius(1.5)
                } else {
                    Rectangle()
                        .fill(Color.clear)
                        .frame(width: 3, height: 16)
                }
                
                Text(title)
                    .fontWeight(isSelected ? .bold : .medium)
                    .foregroundColor(isSelected ? .white : .primary.opacity(0.6))
                
                Spacer()
            }
            .padding(.vertical, 10)
            .padding(.horizontal, 12)
            .background(isSelected ? Color(red: 0.05, green: 0.7, blue: 0.85) : Color.clear)
            .cornerRadius(10)
            .shadow(color: isSelected ? Color.black.opacity(0.1) : Color.clear, radius: 4, y: 2)
        }
        .buttonStyle(PlainButtonStyle())
        // Native swift hover effect
        .onHover { isHovered in
            if isHovered && !isSelected {
                NSCursor.pointingHand.push()
            } else {
                NSCursor.pop()
            }
        }
    }
}

struct AIModelOption: Hashable {
    let name: String
    let description: String
}

struct ModelSelectionSection: View {
    let title: String
    @Binding var selection: String
    let options: [AIModelOption]
    let fallbackDescription: String
    let pickerWidth: CGFloat

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .foregroundColor(.secondary)

            Picker("", selection: $selection) {
                ForEach(options, id: \.name) { option in
                    Text(option.name).tag(option.name)
                }
            }
            .labelsHidden()
            .pickerStyle(MenuPickerStyle())
            .frame(width: pickerWidth, alignment: .leading)

            Text(options.first { $0.name == selection }?.description ?? fallbackDescription)
                .font(.caption)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct ModelsView: View {
    @ObservedObject var manager: SettingsManager
    private let modelPickerWidth: CGFloat = 280
    
    let asrOptions: [AIModelOption] = [
        AIModelOption(name: "Distil-Whisper Large v3 (English)", description: "Fast & High Quality. Best accuracy with distilled architecture."),
        AIModelOption(name: "OpenAI Whisper Small", description: "Quick processing for low-resource environments."),
        AIModelOption(name: "Qwen-ASR v3 0.6B", description: "Ultra-fast Qwen v3 ASR with native MLX acceleration on Apple Silicon."),
        AIModelOption(name: "Qwen-ASR v3 1.7B", description: "High-accuracy Qwen v3 ASR with native MLX acceleration on Apple Silicon."),
        AIModelOption(name: "Whisper Large v3 Turbo (Cantonese)", description: "High-speed Cantonese transcription. Reduced hallucination."),
        AIModelOption(name: "Whisper Large v3 Turbo (Korean)", description: "High-performance Korean transcription. Optimized for speed and accuracy."),
        AIModelOption(name: "Whisper Large v3 Turbo (German)", description: "Precision German recognition. Handles technical and colloquial speech."),
        AIModelOption(name: "Whisper Large v3 Turbo (French)", description: "State-of-the-art French transcription with anti-overfitting optimization."),
        AIModelOption(name: "Whisper Large v3 Turbo (Japanese)", description: "Superior Japanese performance with CTranslate2 optimization."),
        AIModelOption(name: "Whisper Large v2 (Hindi)", description: "Fine-tuned for Hindi. Optimized for mixed-code (Hinglish)."),
        AIModelOption(name: "Whisper Large v3 Turbo (Multilingual)", description: "State-of-the-art multilingual model. Excellent for Singlish, Arabic, and diverse accents.")
    ]
    
    let llmOptions: [AIModelOption] = [
        AIModelOption(name: "Llama 3.2 3B Instruct", description: "General purpose balanced refiner for all languages."),
        AIModelOption(name: "Multilingual (Qwen 3 8B)", description: "High-capacity multilingual refiner with stronger reasoning. Best quality when you can spare more memory."),
        AIModelOption(name: "Multilingual (Qwen 3 4B)", description: "Balanced multilingual refiner with better reasoning than lightweight 3B-class models."),
        AIModelOption(name: "Multilingual (Qwen 2.5 7B)", description: "Powerful 7B model with widespread architecture support. Vastly smarter than 3B versions while remaining stable.")
    ]
    
    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    Text("AI Models")
                        .font(.system(size: 28, weight: .heavy))
                        .tracking(-0.5)

                    ModelSelectionSection(
                        title: "Hearing Engine (ASR)",
                        selection: $manager.prefs.whisper_model,
                        options: asrOptions,
                        fallbackDescription: "Select the transcription engine to balance speed and accuracy.",
                        pickerWidth: modelPickerWidth
                    )

                    ModelSelectionSection(
                        title: "Reasoning Engine (LLM Setup)",
                        selection: $manager.prefs.current_refiner,
                        options: llmOptions,
                        fallbackDescription: "Used for post-processing and grammar correction.",
                        pickerWidth: modelPickerWidth
                    )

                    VStack(alignment: .leading, spacing: 16) {
                        HStack(spacing: 20) {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("PERSONA")
                                    .font(.system(size: 11, weight: .bold))
                                    .foregroundColor(.secondary)
                                Picker("", selection: $manager.prefs.character) {
                                    ForEach(["Writing Assistant", "Code Expert", "Academic", "Executive Secretary", "Personal Buddy", "Custom"], id: \.self) { Text($0).tag($0) }
                                }
                                .pickerStyle(MenuPickerStyle())
                                .frame(width: 220, alignment: .leading)
                            }
                            VStack(alignment: .leading, spacing: 8) {
                                Text("TONE")
                                    .font(.system(size: 11, weight: .bold))
                                    .foregroundColor(.secondary)
                                Picker("", selection: $manager.prefs.tone) {
                                    ForEach(["Professional", "Natural", "Polite", "Casual", "Aggressive", "Concise", "Custom"], id: \.self) { Text($0).tag($0) }
                                }
                                .pickerStyle(MenuPickerStyle())
                                .frame(width: 160, alignment: .leading)
                            }
                            Spacer()
                        }

                        Text("CUSTOM INSTRUCTIONS")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(.primary)
                            .padding(.top, 10)

                        let promptKey = "\(manager.prefs.character)|\(manager.prefs.tone)"
                        let binding = Binding<String>(
                            get: { manager.prefs.custom_prompts[promptKey] ?? "" },
                            set: { manager.prefs.custom_prompts[promptKey] = $0 }
                        )

                        TextEditor(text: binding)
                            .font(.system(size: 14))
                            .padding(8)
                            .background(Color.primary.opacity(0.05))
                            .cornerRadius(8)
                            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.primary.opacity(0.1)))
                            .frame(minHeight: 120)
                    }
                    .padding(.top, 4)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.top, 4)
                .padding(.bottom, 20)
            }
            .scrollIndicators(.hidden)

            HStack {
                Spacer(minLength: 0)
                Button("Save Changes") {
                    manager.savePrefs()
                }
                .buttonStyle(PrimaryButtonStyle())
            }
            .padding(.top, 18)
            .padding(.bottom, 10)
            .frame(maxWidth: .infinity, alignment: .trailing)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

struct GeneralView: View {
    @ObservedObject var manager: SettingsManager
    @ObservedObject var diagnostics = PrivoxDiagnosticsStore.shared
    @State private var showingCleanupSheet = false
    @State private var isRecordingHotkey = false
    @State private var eventMonitor: Any?
    @State private var isTestingHotkey = false
    @State private var testEventMonitor: Any?
    @State private var previousHotkey = "ctrl+shift+space"
    @State private var hotkeyStatusMessage = "Recommended default: CTRL+SHIFT+SPACE"
    @State private var hotkeyStatusColor = Color.secondary
    @State private var cleanupModelsSelected = true
    @State private var cleanupLogsSelected = false
    @State private var cleanupPreferencesSelected = false
    @State private var cleanupUsage: [String: Int64] = [:]
    @State private var cleanupStatusMessage = "Privox stores models, logs, and preferences separately so you can clean up only what you need."
    @State private var cleanupStatusColor = Color.secondary
    @State private var showResetAccessibilityAlert = false
    @State private var resetAccessibilityAlertMessage = ""
    @State private var isResettingAccessibility = false

    var body: some View {
        let currentHotkey = normalizeHotkeyString(manager.prefs.hotkey)
        let savedHotkey = normalizeHotkeyString(manager.savedHotkey)
        let assessment = assessHotkey(currentHotkey)
        let listenerColor: Color = diagnostics.listenerActive ? .green : .orange
        let accessibilityColor: Color = diagnostics.accessibilityGranted ? .green : .orange
        let staleAccessibility = diagnostics.accessibilityGranted && !diagnostics.listenerActive
        let microphonePermissionColor: Color = diagnostics.microphonePermissionGranted ? .green : .orange
        let audioStreamColor: Color = diagnostics.audioStreamActive ? .green : .red
        let backendColor: Color = diagnostics.backendStatus == "ERROR" ? .red : (diagnostics.backendStatus == "RECORDING" ? .pink : .cyan)
        let hotkeySaved = currentHotkey == savedHotkey

        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("General Settings")
                    .font(.system(size: 28, weight: .heavy))
                    .tracking(-0.5)
                
                // Hotkey settings
                VStack(alignment: .leading, spacing: 18) {
                HStack {
                    VStack(alignment: .leading) {
                        Text("RECORDING HOTKEY")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundColor(.secondary)
                        Text(manager.prefs.hotkey == "..." ? "..." : hotkeyDisplayString(currentHotkey))
                            .font(.system(size: 32, weight: .heavy))
                    }
                    Spacer()
                }

                HStack(spacing: 12) {
                    Button(isRecordingHotkey ? "PRESS HOTKEY..." : "Record New") {
                        if isRecordingHotkey {
                            stopRecording()
                        } else {
                            startRecording()
                        }
                    }
                    .font(.system(size: 12, weight: .bold))
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(isRecordingHotkey ? Color.red.opacity(0.8) : Color.primary.opacity(0.1))
                    .foregroundColor(isRecordingHotkey ? .white : .primary)
                    .cornerRadius(6)

                    Button(isTestingHotkey ? "WAITING..." : "Test Hotkey") {
                        if isTestingHotkey {
                            stopTesting()
                        } else {
                            startTesting()
                        }
                    }
                    .font(.system(size: 12, weight: .bold))
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(isTestingHotkey ? Color.cyan.opacity(0.9) : Color.primary.opacity(0.08))
                    .foregroundColor(isTestingHotkey ? .white : .primary)
                    .cornerRadius(6)

                    Button("Use Recommended") {
                        stopRecording()
                        stopTesting()
                        applyHotkeyChange("ctrl+shift+space", message: "Set to recommended hotkey: CTRL+SHIFT+SPACE")
                    }
                    .font(.system(size: 12, weight: .bold))
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(Color.primary.opacity(0.08))
                    .foregroundColor(.primary)
                    .cornerRadius(6)
                }

                HStack(spacing: 10) {
                    StatusPill(title: assessment.level, color: assessment.color)
                    StatusPill(title: hotkeySaved ? "Saved" : "Unsaved", color: hotkeySaved ? .green : .orange)
                    StatusPill(title: hotkeySaved ? "Active Now" : "Save to Apply", color: hotkeySaved ? .cyan : .orange)
                    if diagnostics.listenerActive {
                        StatusPill(title: "Listener Ready", color: .green)
                    } else {
                        StatusPill(title: "Needs Attention", color: .orange)
                    }
                }

                Text(assessment.message)
                    .font(.system(size: 13))
                    .foregroundColor(.secondary)

                Text(hotkeySaved
                    ? "Privox is currently listening for \(hotkeyDisplayString(savedHotkey))."
                    : "The displayed hotkey has changed, but the active listener is still using \(hotkeyDisplayString(savedHotkey)).")
                    .font(.system(size: 13))
                    .foregroundColor(hotkeySaved ? .secondary : .orange)

                Text(hotkeyStatusMessage)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(hotkeyStatusColor)

                Text("Recommended combinations: \(privoxRecommendedHotkeys.map { hotkeyDisplayString($0) }.joined(separator: "  •  "))")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                }
                .padding(24)
                .background(.regularMaterial)
                .cornerRadius(16)
                .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.primary.opacity(0.05), lineWidth: 0.5))
                
                VStack(alignment: .leading, spacing: 16) {
                HStack {
                    VStack(alignment: .leading) {
                        Text("HOTKEY DIAGNOSTICS")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundColor(.cyan)
                        Text("Live health status for permissions, the global listener, and the most recent detected shortcut.")
                            .font(.system(size: 13))
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                    
                    StatusPill(title: diagnostics.backendStatus, color: backendColor)
                }

                if diagnostics.backendStatus == "DOWNLOADING" || diagnostics.backendStatus == "INITIALIZING" {
                    DiagnosticsProgressCard(
                        title: diagnostics.backendStatus == "DOWNLOADING" ? "MODEL DOWNLOAD" : "STARTUP",
                        bodyText: diagnostics.downloadStatus,
                        tint: diagnostics.backendStatus == "DOWNLOADING" ? .blue : .cyan,
                        progress: diagnostics.backendStatus == "DOWNLOADING" ? diagnostics.downloadProgress : nil
                    )
                }

                HStack(spacing: 14) {
                    DiagnosticsMetricCard(
                        title: "Accessibility",
                        value: diagnostics.accessibilityGranted ? "Granted" : "Missing",
                        subtitle: diagnostics.accessibilityGranted ? "Global keyboard access is available." : "Privox cannot capture the hotkey until you allow Accessibility.",
                        tint: accessibilityColor
                    )
                    DiagnosticsMetricCard(
                        title: "Listener",
                        value: diagnostics.listenerActive ? "Active" : "Inactive",
                        subtitle: diagnostics.listenerStatus,
                        tint: listenerColor
                    )
                }

                if !diagnostics.accessibilityGranted {
                    DiagnosticsHintCard(
                        title: "WHY THIS CAN HAPPEN",
                        bodyText: "macOS Accessibility permission is granted to the exact app build you launched. If you rebuilt Privox, macOS may treat the new build as a different app even if the name is the same. Use \"Reset Accessibility Access\" below to clear the old permission, then quit and relaunch to grant access for this version.",
                        tint: .orange
                    )
                }

                if staleAccessibility {
                    DiagnosticsHintCard(
                        title: "STALE ACCESSIBILITY PERMISSION",
                        bodyText: "Accessibility shows as Granted but the hotkey listener could not start. This often happens after updating Privox. Use \"Reset Accessibility Access\" below, then quit and relaunch the app to grant access for this version.",
                        tint: .orange
                    )
                }

                if !diagnostics.accessibilityGranted || !diagnostics.microphonePermissionGranted || !diagnostics.listenerActive {
                    DiagnosticsHintCard(
                        title: "RECOVERY FLOW",
                        bodyText: diagnostics.permissionRecoveryStatus,
                        tint: !diagnostics.accessibilityGranted || !diagnostics.microphonePermissionGranted ? .orange : .cyan
                    )
                }

                HStack(spacing: 14) {
                    DiagnosticsMetricCard(
                        title: "Mic Permission",
                        value: diagnostics.microphonePermissionGranted ? "Granted" : "Missing",
                        subtitle: diagnostics.microphonePermissionStatus,
                        tint: microphonePermissionColor
                    )
                    DiagnosticsMetricCard(
                        title: "Audio Stream",
                        value: diagnostics.audioStreamActive ? "Live" : "Offline",
                        subtitle: diagnostics.audioStreamStatus,
                        tint: audioStreamColor
                    )
                }

                HStack(spacing: 14) {
                    DiagnosticsMetricCard(
                        title: "Last Seen",
                        value: diagnostics.lastDetectedHotkey,
                        subtitle: "Last event at \(diagnostics.lastEventTimestamp)",
                        tint: .cyan
                    )
                    DiagnosticsMetricCard(
                        title: "Last Trigger",
                        value: diagnostics.lastTriggeredHotkey,
                        subtitle: diagnostics.backendDetail,
                        tint: backendColor
                    )
                }

                HStack(spacing: 12) {
                    Button("Open Accessibility Settings") {
                        let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!
                        NSWorkspace.shared.open(url)
                    }
                    .buttonStyle(SecondaryCapsuleButtonStyle())

                    Button("Reveal Current App") {
                        NSWorkspace.shared.activateFileViewerSelecting([Bundle.main.bundleURL])
                    }
                    .buttonStyle(SecondaryCapsuleButtonStyle())

                    Button("Open Microphone Settings") {
                        let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone")!
                        NSWorkspace.shared.open(url)
                    }
                    .buttonStyle(SecondaryCapsuleButtonStyle())

                    Button("Check Permissions Now") {
                        if let appDelegate = NSApplication.shared.delegate as? AppDelegate {
                            appDelegate.refreshPermissionsAndRecoveryState()
                        }
                    }
                    .buttonStyle(SecondaryCapsuleButtonStyle())

                    Button("Refresh Listener") {
                        if let appDelegate = NSApplication.shared.delegate as? AppDelegate {
                            appDelegate.refreshGlobalHotkeyListener(force: true)
                        }
                    }
                    .buttonStyle(SecondaryCapsuleButtonStyle())

                    Button(isResettingAccessibility ? "Resetting…" : "Reset Accessibility Access") {
                        guard let appDelegate = NSApplication.shared.delegate as? AppDelegate else { return }
                        isResettingAccessibility = true
                        appDelegate.resetAccessibilityAccess { success, message in
                            resetAccessibilityAlertMessage = message
                            showResetAccessibilityAlert = true
                            isResettingAccessibility = false
                            if success {
                                let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!
                                NSWorkspace.shared.open(url)
                            }
                        }
                    }
                    .buttonStyle(SecondaryCapsuleButtonStyle())
                    .background(staleAccessibility ? Color.orange.opacity(0.2) : Color.clear)
                    .cornerRadius(8)
                    .disabled(isResettingAccessibility)
                }
                .alert("Reset Accessibility", isPresented: $showResetAccessibilityAlert) {
                    Button("OK", role: .cancel) {}
                } message: {
                    Text(resetAccessibilityAlertMessage)
                }

                VStack(alignment: .leading, spacing: 10) {
                    Text("DIRECT PIPELINE TEST")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(.secondary)

                    Text("Bypass the global hotkey listener and send the same toggle command straight to the backend. Use this to verify recording and transcription separately from keyboard detection.")
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)

                    HStack(spacing: 12) {
                        let directPipelineStatus = diagnostics.backendStatus
                        let isPipelineBusy = isDirectPipelineBusy(directPipelineStatus)
                        let directPipelineButtonTitle = directPipelineTitle(for: directPipelineStatus)
                        let directPipelineDescription = directPipelineDescription(for: directPipelineStatus)

                        Button(directPipelineButtonTitle) {
                            guard !isPipelineBusy else { return }
                            hotkeyStatusMessage = diagnostics.backendStatus == "RECORDING"
                                ? "Direct test sent: stopping the active recording."
                                : "Direct test sent: starting recording without the hotkey listener."
                            hotkeyStatusColor = .cyan
                            BackendManager.shared.sendCommand("TOGGLE")
                        }
                        .buttonStyle(PrimaryButtonStyle())
                        .disabled(isPipelineBusy)

                        Text(directPipelineDescription)
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                    }
                }
                .padding(18)
                .background(.thinMaterial)
                .cornerRadius(14)
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.cyan.opacity(0.14), lineWidth: 1))
                }
                .padding(24)
                .background(.regularMaterial)
                .cornerRadius(16)
                .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.primary.opacity(0.05), lineWidth: 0.5))
                
                // Timeouts & Switches Group
                VStack(alignment: .leading, spacing: 16) {
                Toggle("Play Sound Effects (Beeps)", isOn: $manager.prefs.sound_enabled)
                    .toggleStyle(SwitchToggleStyle(tint: .blue))
                
                Divider().opacity(0.5)
                
                HStack(spacing: 30) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("VRAM TIMEOUT (SEC)")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundColor(.secondary)
                        
                        let vramBinding = Binding<String>(
                            get: { String(manager.prefs.vram_timeout) },
                            set: { if let val = Int($0) { manager.prefs.vram_timeout = val } }
                        )
                        TextField("Seconds", text: vramBinding)
                            .textFieldStyle(RoundedBorderTextFieldStyle())
                            .frame(width: 80)
                    }
                    
                    VStack(alignment: .leading, spacing: 8) {
                        Text("AUTO-STOP (SEC)")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundColor(.secondary)
                        
                        let stopBinding = Binding<String>(
                            get: { String(manager.prefs.silence_timeout_ms / 1000) },
                            set: { if let val = Int($0) { manager.prefs.silence_timeout_ms = val * 1000 } }
                        )
                        TextField("Seconds", text: stopBinding)
                            .textFieldStyle(RoundedBorderTextFieldStyle())
                            .frame(width: 80)
                    }

                    VStack(alignment: .leading, spacing: 8) {
                        Text("PASTE DELAY (SEC)")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundColor(.secondary)

                        let pasteDelayBinding = Binding<String>(
                            get: { String(manager.prefs.paste_delay_seconds) },
                            set: { if let val = Int($0) { manager.prefs.paste_delay_seconds = max(0, val) } }
                        )
                        TextField("Seconds", text: pasteDelayBinding)
                            .textFieldStyle(RoundedBorderTextFieldStyle())
                            .frame(width: 80)
                    }
                }

                Text("After transcription is ready, Privox waits this many seconds before pasting so you can switch back to the target text field.")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                }
                .padding(24)
                .background(.regularMaterial)
                .cornerRadius(16)
                .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.primary.opacity(0.05), lineWidth: 0.5))
                
                VStack(alignment: .leading, spacing: 16) {
                HStack {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("CLEANUP & UNINSTALL")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundColor(.red)
                        Text("Review what Privox stores locally, clean selected data safely, or generate a guided uninstall helper.")
                            .font(.system(size: 13))
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                }

                HStack(spacing: 14) {
                    DiagnosticsMetricCard(
                        title: "Models",
                        value: formatByteCount(cleanupUsage["models"] ?? 0),
                        subtitle: "Downloaded ASR and LLM files",
                        tint: .red
                    )
                    DiagnosticsMetricCard(
                        title: "Logs",
                        value: formatByteCount(cleanupUsage["logs"] ?? 0),
                        subtitle: "Runtime diagnostics and crash clues",
                        tint: .orange
                    )
                    DiagnosticsMetricCard(
                        title: "Preferences",
                        value: formatByteCount(cleanupUsage["preferences"] ?? 0),
                        subtitle: "Hotkey, prompts, and app settings",
                        tint: .pink
                    )
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Current data folder")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(.secondary)
                    Text(privoxAppDataDirectory().path)
                        .font(.system(size: 12, weight: .medium, design: .monospaced))
                        .foregroundColor(.secondary)
                        .textSelection(.enabled)
                }

                HStack(spacing: 12) {
                    Button("Select Cleanup...") {
                        refreshCleanupMetrics()
                        showingCleanupSheet = true
                    }
                    .buttonStyle(PrimaryButtonStyle())

                    Button("Reveal Data Folder") {
                        NSWorkspace.shared.activateFileViewerSelecting([privoxAppDataDirectory()])
                    }
                    .buttonStyle(SecondaryCapsuleButtonStyle())

                    Button("Create Uninstall Script") {
                        createUninstallScript()
                    }
                    .buttonStyle(SecondaryCapsuleButtonStyle())
                }

                Text(cleanupStatusMessage)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(cleanupStatusColor)
                }
                .padding(24)
                .background(Color.red.opacity(0.08))
                .cornerRadius(16)
                .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.red.opacity(0.24), lineWidth: 0.5))
                
                HStack {
                    Spacer()
                    Button("Save Changes") {
                        manager.savePrefs()
                    }
                    .buttonStyle(PrimaryButtonStyle())
                }
            }
            .padding(.bottom, 8)
        }
        .scrollIndicators(.hidden)
        .sheet(isPresented: $showingCleanupSheet) {
            cleanupSheetView
        }
        .onAppear {
            refreshCleanupMetrics()
        }
        .onDisappear {
            stopRecording()
            stopTesting()
        }
    }
    
    // MARK: - Hotkey Logic
    private func startRecording() {
        stopTesting()
        isRecordingHotkey = true
        previousHotkey = normalizeHotkeyString(manager.prefs.hotkey)
        manager.prefs.hotkey = "..."
        hotkeyStatusMessage = "Press the full shortcut now, for example CTRL+SHIFT+SPACE."
        hotkeyStatusColor = .secondary
        
        eventMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            handleKeyPress(event)
            return nil // Consume the event so it doesn't type into textfields
        }
    }
    
    private func stopRecording() {
        isRecordingHotkey = false
        if let monitor = eventMonitor {
            NSEvent.removeMonitor(monitor)
            eventMonitor = nil
        }
        if manager.prefs.hotkey == "..." {
            manager.prefs.hotkey = previousHotkey.isEmpty ? "ctrl+shift+space" : previousHotkey
        }
    }

    private func isDirectPipelineBusy(_ status: String) -> Bool {
        ["PROCESSING", "DOWNLOADING", "INITIALIZING"].contains(status)
    }

    private func directPipelineTitle(for status: String) -> String {
        switch status {
        case "RECORDING":
            return "Stop Recording Directly"
        case "PROCESSING":
            return "Finishing Recording..."
        case "DOWNLOADING":
            return "Downloading Models..."
        case "INITIALIZING":
            return "Preparing Privox..."
        default:
            return "Start Recording Directly"
        }
    }

    private func directPipelineDescription(for status: String) -> String {
        switch status {
        case "PROCESSING":
            return "Privox is transcribing the last recording now. Wait for it to return to Ready before starting again."
        case "DOWNLOADING":
            return "Privox is downloading required AI models for first use. This can take a while and recording is disabled until the download finishes."
        case "INITIALIZING":
            return "Privox is still starting the backend and warming up audio or models. Recording will unlock automatically when startup completes."
        default:
            return "This uses the same backend recording path, but skips hotkey capture."
        }
    }

    private func applyHotkeyChange(_ hotkey: String, message: String, color: Color = .green) {
        manager.prefs.hotkey = normalizeHotkeyString(hotkey)
        manager.savePrefs()
        hotkeyStatusMessage = message
        hotkeyStatusColor = color
        if let appDelegate = NSApplication.shared.delegate as? AppDelegate {
            appDelegate.refreshGlobalHotkeyListener(force: false)
        }
    }
    
    private func handleKeyPress(_ event: NSEvent) {
        guard let candidate = hotkeyString(from: event) else { return }
        let assessment = assessHotkey(candidate)

        if assessment.isBlocked {
            hotkeyStatusMessage = assessment.message
            hotkeyStatusColor = .red
            stopRecording()
            return
        }

        applyHotkeyChange(
            candidate,
            message: "Captured hotkey: \(hotkeyDisplayString(candidate))",
            color: assessment.color
        )
        stopRecording()
    }

    private func startTesting() {
        stopRecording()
        isTestingHotkey = true
        hotkeyStatusMessage = "Press \(hotkeyDisplayString(manager.prefs.hotkey)) now to verify detection."
        hotkeyStatusColor = .cyan

        testEventMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            handleTestKeyPress(event)
            return nil
        }
    }

    private func stopTesting() {
        isTestingHotkey = false
        if let monitor = testEventMonitor {
            NSEvent.removeMonitor(monitor)
            testEventMonitor = nil
        }
    }

    private func handleTestKeyPress(_ event: NSEvent) {
        guard let candidate = hotkeyString(from: event) else { return }
        let expected = normalizeHotkeyString(manager.prefs.hotkey)

        if candidate == expected {
            hotkeyStatusMessage = "Hotkey test passed: \(hotkeyDisplayString(candidate))"
            hotkeyStatusColor = .green
        } else {
            hotkeyStatusMessage = "Detected \(hotkeyDisplayString(candidate)), but expected \(hotkeyDisplayString(expected))."
            hotkeyStatusColor = .orange
        }

        stopTesting()
    }

    // MARK: - App logic
    private var cleanupSheetView: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Cleanup Privox Data")
                .font(.system(size: 24, weight: .heavy))

            Text("Choose what to remove. Privox will restart its backend after cleanup so the app stays usable.")
                .font(.system(size: 13))
                .foregroundColor(.secondary)

            VStack(alignment: .leading, spacing: 14) {
                Toggle(isOn: $cleanupModelsSelected) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Downloaded models")
                        Text("\(formatByteCount(cleanupUsage["models"] ?? 0)) currently stored for ASR and LLM inference.")
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                    }
                }

                Toggle(isOn: $cleanupLogsSelected) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Logs")
                        Text("\(formatByteCount(cleanupUsage["logs"] ?? 0)) of diagnostic output. Fresh logs may be created again after cleanup.")
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                    }
                }

                Toggle(isOn: $cleanupPreferencesSelected) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Preferences")
                        Text("\(formatByteCount(cleanupUsage["preferences"] ?? 0)) of saved settings, prompts, and hotkey preferences.")
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                    }
                }
            }
            .toggleStyle(SwitchToggleStyle(tint: .red))

            VStack(alignment: .leading, spacing: 6) {
                Text("Estimated reclaimed space")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundColor(.secondary)
                Text(formatByteCount(selectedCleanupBytes()))
                    .font(.system(size: 28, weight: .heavy))
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.thinMaterial)
            .cornerRadius(14)
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.red.opacity(0.14), lineWidth: 1))

            HStack {
                Spacer()
                Button("Cancel") {
                    showingCleanupSheet = false
                }
                .buttonStyle(SecondaryCapsuleButtonStyle())

                Button("Clean Selected Data") {
                    performCleanup()
                    showingCleanupSheet = false
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(selectedCleanupBytes() == 0)
            }
        }
        .padding(24)
        .frame(width: 560)
        .background(.regularMaterial)
    }

    private func performCleanup() {
        let fileManager = FileManager.default
        var removedDescriptions: [String] = []
        var removedSomething = false

        BackendManager.shared.stopBackend()

        if cleanupModelsSelected {
            let modelsURL = privoxAppDataDirectory().appendingPathComponent("models")
            if fileManager.fileExists(atPath: modelsURL.path) {
                try? fileManager.removeItem(at: modelsURL)
                removedDescriptions.append("models")
                removedSomething = true
            }
        }

        if cleanupLogsSelected {
            var removedLogs = false
            let logURLs = [
                privoxAppDataDirectory().appendingPathComponent("swift.log"),
                privoxAppDataDirectory().appendingPathComponent("privox_app.log")
            ]
            for url in logURLs where fileManager.fileExists(atPath: url.path) {
                try? fileManager.removeItem(at: url)
                removedLogs = true
                removedSomething = true
            }
            if removedLogs {
                removedDescriptions.append("logs")
            }
        }

        if cleanupPreferencesSelected {
            var removedPreferences = false
            let prefsURLs = [
                privoxAppDataDirectory().appendingPathComponent(".user_prefs.json"),
                privoxAppDataDirectory().appendingPathComponent("config.json")
            ]
            for url in prefsURLs where fileManager.fileExists(atPath: url.path) {
                try? fileManager.removeItem(at: url)
                removedPreferences = true
                removedSomething = true
            }
            manager.prefs = UserPrefs()
            if removedPreferences {
                removedDescriptions.append("preferences")
            }
        }

        BackendManager.shared.startBackend()
        refreshCleanupMetrics()

        if removedSomething {
            cleanupStatusMessage = "Cleanup completed for \(removedDescriptions.joined(separator: ", "))."
            cleanupStatusColor = .green
        } else {
            cleanupStatusMessage = "Nothing needed cleaning in the selected categories."
            cleanupStatusColor = .secondary
        }
    }

    private func createUninstallScript() {
        let desktopURL = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Desktop", isDirectory: true)
        let scriptURL = desktopURL.appendingPathComponent("Uninstall Privox.command")
        let script = """
        #!/bin/zsh
        set -e

        APP_SUPPORT="$HOME/Library/Application Support/Privox"
        LEGACY="$HOME/.privox"

        echo "Privox uninstall helper"
        echo
        echo "This will remove downloaded models, logs, and preferences from:"
        echo "  $APP_SUPPORT"
        echo "  $LEGACY"
        echo
        read '?Continue? [y/N] ' reply
        echo
        if [[ ! "$reply" =~ ^[Yy]$ ]]; then
          echo "Cancelled."
          exit 0
        fi

        pkill -f "/Privox.app/Contents/MacOS/Privox" >/dev/null 2>&1 || true
        rm -rf "$APP_SUPPORT" "$LEGACY"

        echo "Privox data removed."
        echo "You can now drag Privox.app to the Trash if you no longer need it."
        read '?Press Enter to close.'
        """

        do {
            try FileManager.default.createDirectory(at: desktopURL, withIntermediateDirectories: true)
            try script.write(to: scriptURL, atomically: true, encoding: .utf8)
            try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: scriptURL.path)
            NSWorkspace.shared.activateFileViewerSelecting([scriptURL])
            cleanupStatusMessage = "Created uninstall helper on your Desktop."
            cleanupStatusColor = .green
        } catch {
            cleanupStatusMessage = "Failed to create uninstall helper: \(error.localizedDescription)"
            cleanupStatusColor = .red
        }
    }

    private func selectedCleanupBytes() -> Int64 {
        var total: Int64 = 0
        if cleanupModelsSelected {
            total += cleanupUsage["models"] ?? 0
        }
        if cleanupLogsSelected {
            total += cleanupUsage["logs"] ?? 0
        }
        if cleanupPreferencesSelected {
            total += cleanupUsage["preferences"] ?? 0
        }
        return total
    }

    private func refreshCleanupMetrics() {
        cleanupUsage = [
            "models": directorySize(at: privoxAppDataDirectory().appendingPathComponent("models")),
            "logs": fileSizes(at: [
                privoxAppDataDirectory().appendingPathComponent("swift.log"),
                privoxAppDataDirectory().appendingPathComponent("privox_app.log")
            ]),
            "preferences": fileSizes(at: [
                privoxAppDataDirectory().appendingPathComponent(".user_prefs.json"),
                privoxAppDataDirectory().appendingPathComponent("config.json")
            ])
        ]
    }

    private func fileSizes(at urls: [URL]) -> Int64 {
        urls.reduce(0) { partialResult, url in
            partialResult + fileSize(at: url)
        }
    }

    private func fileSize(at url: URL) -> Int64 {
        guard
            let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
            let size = attributes[.size] as? NSNumber
        else {
            return 0
        }
        return size.int64Value
    }

    private func directorySize(at url: URL) -> Int64 {
        guard let enumerator = FileManager.default.enumerator(
            at: url,
            includingPropertiesForKeys: [.isRegularFileKey, .fileSizeKey],
            options: [.skipsHiddenFiles]
        ) else {
            return 0
        }

        var total: Int64 = 0
        for case let fileURL as URL in enumerator {
            guard
                let values = try? fileURL.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey]),
                values.isRegularFile == true
            else {
                continue
            }
            total += Int64(values.fileSize ?? 0)
        }
        return total
    }

    private func formatByteCount(_ bytes: Int64) -> String {
        let formatter = ByteCountFormatter()
        formatter.allowedUnits = [.useKB, .useMB, .useGB, .useTB]
        formatter.countStyle = .file
        formatter.includesUnit = true
        formatter.isAdaptive = true
        return formatter.string(fromByteCount: bytes)
    }
}

struct DictionaryView: View {
    @ObservedObject var manager: SettingsManager
    @State private var newWord = ""
    
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("Custom Dictionary")
                .font(.system(size: 28, weight: .heavy))
                .tracking(-0.5)
            
            Text("Enhance AI accuracy for specific names, terms, or brands.")
                .foregroundColor(.secondary)
            
            HStack {
                TextField("Type a word and press Enter...", text: $newWord, onCommit: addWord)
                    .textFieldStyle(PlainTextFieldStyle())
                    .padding(12)
                    .background(Color.primary.opacity(0.05))
                    .cornerRadius(8)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.primary.opacity(0.1)))
                
                Button("ADD") { addWord() }
                    .font(.system(size: 11, weight: .bold))
                    .padding(.horizontal, 20)
                    .padding(.vertical, 12)
                    .background(Color.primary.opacity(0.1))
                    .cornerRadius(6)
            }
            
            ScrollView {
                VStack(spacing: 8) {
                    ForEach(manager.prefs.custom_dictionary, id: \.self) { word in
                        HStack {
                            Text(word)
                            Spacer()
                            Button("✕") {
                                manager.prefs.custom_dictionary.removeAll(where: { $0 == word })
                            }
                            .foregroundColor(.secondary)
                        }
                        .padding()
                        .background(.regularMaterial)
                        .cornerRadius(12)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.primary.opacity(0.05), lineWidth: 0.5))
                    }
                }
            }
            
            HStack {
                Spacer()
                Button("Save Changes") {
                    manager.savePrefs()
                }
                .buttonStyle(PrimaryButtonStyle())
            }
        }
    }
    
    private func addWord() {
        let trimmed = newWord.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty && !manager.prefs.custom_dictionary.contains(trimmed) {
            manager.prefs.custom_dictionary.append(trimmed)
            newWord = ""
        }
    }
}

// MARK: - Styles

struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 14, weight: .bold, design: .rounded))
            .foregroundColor(.white)
            .padding(.horizontal, 28)
            .padding(.vertical, 14)
            .background(
                configuration.isPressed ? Color(red: 0.03, green: 0.57, blue: 0.7) : Color(red: 0.05, green: 0.7, blue: 0.85) // Using the recommended Cyan (#0891B2 -> #22D3EE)
            )
            .cornerRadius(12)
            .shadow(color: Color.black.opacity(0.2), radius: 6, x: 0, y: 3)
            .scaleEffect(configuration.isPressed ? 0.96 : 1.0)
            .animation(.spring(response: 0.3, dampingFraction: 0.6), value: configuration.isPressed)
    }
}

struct SecondaryCapsuleButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .semibold, design: .rounded))
            .foregroundColor(.primary)
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            .background(Color.primary.opacity(configuration.isPressed ? 0.14 : 0.08))
            .cornerRadius(10)
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(Color.primary.opacity(0.08), lineWidth: 0.8)
            )
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
            .animation(.easeOut(duration: 0.18), value: configuration.isPressed)
    }
}
