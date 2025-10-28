import SwiftUI

import PipecatClientIOSDaily
import PipecatClientIOS

class CallContainerModel: ObservableObject {
    
    @Published var voiceClientStatus: String = TransportState.disconnected.description
    @Published var isInCall: Bool = false
    @Published var isBotReady: Bool = false
    @Published var timerCount = 0
    
    @Published var isMicEnabled: Bool = false
    
    @Published var toastMessage: String? = nil
    @Published var showToast: Bool = false
    
    @Published
    var remoteAudioLevel: Float = 0
    @Published
    var localAudioLevel: Float = 0
    
    private var meetingTimer: Timer?
    
    var pipecatClientIOS: PipecatClient?
    
    @Published var selectedMic: MediaDeviceId? = nil {
        didSet {
            guard let selectedMic else { return } // don't store nil
            var settings = SettingsManager.getSettings()
            settings.selectedMic = selectedMic.id
            SettingsManager.updateSettings(settings: settings)
        }
    }
    @Published var availableMics: [MediaDeviceInfo] = []
    
    init() {
        // Changing the log level
        PipecatClientIOS.setLogLevel(.warn)
    }
    
    @MainActor
    func connect(backendURL: String) {
        let baseUrl = backendURL.trimmingCharacters(in: .whitespacesAndNewlines)
        if(baseUrl.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty){
            self.showError(message: "Need to fill the backendURL. For more info visit: https://bots.daily.co")
            return
        }
        
        let currentSettings = SettingsManager.getSettings()
        let pipecatClientOptions = PipecatClientOptions.init(
            transport: DailyTransport.init(),
            enableMic: currentSettings.enableMic,
            enableCam: false,
        )
        self.pipecatClientIOS = PipecatClient.init(
            options: pipecatClientOptions
        )
        self.pipecatClientIOS?.delegate = self
        let startBotParams = APIRequest.init(endpoint: URL(string: baseUrl + "/start")!)
        self.pipecatClientIOS?.startBotAndConnect(startBotParams: startBotParams) { (result: Result<DailyTransportConnectionParams, AsyncExecutionError>) in
            switch result {
            case .failure(let error):
                self.showError(message: error.localizedDescription)
                self.pipecatClientIOS = nil
            case .success(_):
                // Apply initial mic preference
                if let selectedMic = currentSettings.selectedMic {
                    self.selectMic(MediaDeviceId(id: selectedMic))
                }
                // Populate available devices list
                self.availableMics = self.pipecatClientIOS?.getAllMics() ?? []
            }
        }
        self.saveCredentials(backendURL: baseUrl)
    }
    
    func disconnect() {
        Task { @MainActor in
            try await self.pipecatClientIOS?.disconnect()
            self.pipecatClientIOS?.release()
        }
    }
    
    func showError(message: String) {
        self.toastMessage = message
        self.showToast = true
        // Hide the toast after 5 seconds
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
            self.showToast = false
            self.toastMessage = nil
        }
    }
    
    @MainActor
    func toggleMicInput() {
        self.pipecatClientIOS?.enableMic(enable: !self.isMicEnabled) { result in
            switch result {
            case .success():
                self.isMicEnabled = self.pipecatClientIOS?.isMicEnabled ?? false
            case .failure(let error):
                self.showError(message: error.localizedDescription)
            }
        }
    }
    
    private func startTimer() {
        let currentTime = Int(Date().timeIntervalSince1970)
        self.timerCount = 0
        self.meetingTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { timer in
            DispatchQueue.main.async {
                self.timerCount += 1
            }
        }
    }
    
    private func stopTimer() {
        self.meetingTimer?.invalidate()
        self.meetingTimer = nil
        self.timerCount = 0
    }
    
    func saveCredentials(backendURL: String) {
        var currentSettings = SettingsManager.getSettings()
        currentSettings.backendURL = backendURL
        // Saving the settings
        SettingsManager.updateSettings(settings: currentSettings)
    }
    
    @MainActor
    func selectMic(_ mic: MediaDeviceId) {
        self.selectedMic = mic
        self.pipecatClientIOS?.updateMic(micId: mic, completion: nil)
    }
}

extension CallContainerModel:PipecatClientDelegate {
    private func handleEvent(eventName: String, eventValue: Any? = nil) {
        if let value = eventValue {
            print("RTVI Demo, received event:\(eventName), value:\(value)")
        } else {
            print("RTVI Demo, received event: \(eventName)")
        }
    }
    
    func onTransportStateChanged(state: TransportState) {
        Task { @MainActor in
            self.handleEvent(eventName: "onTransportStateChanged", eventValue: state)
            self.voiceClientStatus = state.description
            self.isInCall = ( state == .connecting || state == .connected || state == .ready || state == .authenticating )
        }
    }
    
    func onBotReady(botReadyData: BotReadyData) {
        Task { @MainActor in
            self.handleEvent(eventName: "onBotReady.")
            self.isBotReady = true
            self.startTimer()
        }
    }
    
    func onConnected() {
        Task { @MainActor in
            self.isMicEnabled = self.pipecatClientIOS?.isMicEnabled ?? false
        }
    }
    
    func onDisconnected() {
        Task { @MainActor in
            self.stopTimer()
            self.isBotReady = false
        }
    }
    
    func onRemoteAudioLevel(level: Float, participant: Participant) {
        Task { @MainActor in
            self.remoteAudioLevel = level
        }
    }
    
    func onLocalAudioLevel(level: Float) {
        Task { @MainActor in
            self.localAudioLevel = level
        }
    }
    
    func onUserTranscript(data: Transcript) {
        Task { @MainActor in
            if (data.final ?? false) {
                self.handleEvent(eventName: "onUserTranscript", eventValue: data.text)
            }
        }
    }
    
    func onBotTranscript(data: BotLLMText) {
        Task { @MainActor in
            self.handleEvent(eventName: "onBotTranscript", eventValue: data)
        }
    }
    
    func onError(message: RTVIMessageInbound) {
        Task { @MainActor in
            self.handleEvent(eventName: "onError", eventValue: message)
            self.showError(message: message.data ?? "")
        }
    }
    
    func onTrackStarted(track: MediaStreamTrack, participant: Participant?) {
        Task { @MainActor in
            self.handleEvent(eventName: "onTrackStarted", eventValue: track)
        }
    }

    func onTrackStopped(track: MediaStreamTrack, participant: Participant?) {
        Task { @MainActor in
            self.handleEvent(eventName: "onTrackStopped", eventValue: track)
        }
    }
    
    func onAvailableMicsUpdated(mics: [MediaDeviceInfo]) {
        Task { @MainActor in
            self.availableMics = mics
        }
    }
    
    func onMicUpdated(mic: MediaDeviceInfo?) {
        Task { @MainActor in
            self.selectedMic = mic?.id
        }
    }
    
    func onMetrics(data: PipecatMetrics) {
        Task { @MainActor in
            self.handleEvent(eventName: "onMetrics", eventValue: data)
        }
    }
}
