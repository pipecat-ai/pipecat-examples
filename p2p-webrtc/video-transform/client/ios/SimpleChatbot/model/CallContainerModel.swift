import SwiftUI

import PipecatClientIOSSmallWebrtc
import PipecatClientIOS

class CallContainerModel: ObservableObject {
    
    @Published var voiceClientStatus: String = TransportState.disconnected.description
    @Published var isInCall: Bool = false
    @Published var isBotReady: Bool = false
    
    @Published var isMicEnabled: Bool = false
    @Published var isCamEnabled: Bool = false
    @Published var localCamId: MediaTrackId? = nil
    @Published var botCamId: MediaTrackId? = nil
    
    @Published var toastMessage: String? = nil
    @Published var showToast: Bool = false
    
    @Published var messages: [LiveMessage] = []
    @Published var liveBotMessage: LiveMessage?
    @Published var liveUserMessage: LiveMessage?
    
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
        PipecatClientIOSSmallWebrtc.setLogLevel(.info)
    }
    
    @MainActor
    func connect(backendURL: String, apiKey: String) {
        self.resetLiveMessages()
        
        let baseUrl = backendURL.trimmingCharacters(in: .whitespacesAndNewlines)
        if(baseUrl.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty){
            self.showError(message: "Need to fill the backendURL")
            return
        }
        
        let currentSettings = SettingsManager.getSettings()
        let pipecatClientOptions = PipecatClientOptions.init(
            transport: SmallWebRTCTransport.init(),
            enableMic: currentSettings.enableMic,
            enableCam: currentSettings.enableCam,
        )
        self.pipecatClientIOS = PipecatClient.init(
            options: pipecatClientOptions
        )
        self.pipecatClientIOS?.delegate = self
        
        let authorizationToken = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        print("authorizationToken: \(authorizationToken)")
        let headers = [["Authorization": "Bearer \(authorizationToken)"]]
        let startParams = APIRequest.init(
            endpoint: URL(string: baseUrl + "/start")!,
            headers: headers,
            requestData: Value.object([
                "enableDefaultIceServers": .boolean(true),
                "transport": .string("webrtc")
            ])
        )
        self.pipecatClientIOS?.startBotAndConnect(startBotParams: startParams) { (result: Result<SmallWebRTCStartBotResult, AsyncExecutionError>) in
            switch result {
            case .failure(let error):
                self.showError(message: error.localizedDescription)
                self.pipecatClientIOS = nil
            case .success(_):
                // Apply initial mic preference
                if let selectedMic = SettingsManager.getSettings().selectedMic {
                    self.selectMic(MediaDeviceId(id: selectedMic))
                }
                // Populate available devices list
                self.availableMics = self.pipecatClientIOS?.getAllMics() ?? []
            }
        }
        self.saveCredentials(backendURL: baseUrl, apiKey: authorizationToken)
    }
    
    @MainActor
    func disconnect() {
        self.pipecatClientIOS?.disconnect(completion: nil)
        self.pipecatClientIOS?.release()
        self.pipecatClientIOS = nil
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
    
    @MainActor
    func toggleCamInput() {
        print("Is cam enabled: \(self.isCamEnabled)")
        self.pipecatClientIOS?.enableCam(enable: !self.isCamEnabled) { result in
            switch result {
            case .success():
                self.isCamEnabled = self.pipecatClientIOS?.isCamEnabled ?? false
            case .failure(let error):
                self.showError(message: error.localizedDescription)
            }
        }
    }
    
    func saveCredentials(backendURL: String, apiKey: String) {
        var currentSettings = SettingsManager.getSettings()
        currentSettings.backendURL = backendURL
        currentSettings.apiKey = apiKey
        // Saving the settings
        SettingsManager.updateSettings(settings: currentSettings)
    }
    
    @MainActor
    func selectMic(_ mic: MediaDeviceId) {
        self.selectedMic = mic
        self.pipecatClientIOS?.updateMic(micId: mic, completion: nil)
    }
    
    private func createLiveMessage(content:String = "", type:MessageType) {
        // Creating a new one
        DispatchQueue.main.async {
            let liveMessage = LiveMessage(content: content, type: type, updatedAt: Date())
            self.messages.append(liveMessage)
            if type == .bot {
                self.liveBotMessage = liveMessage
            } else if type == .user {
                self.liveUserMessage = liveMessage
            }
        }
    }
    
    private func appendTextToLiveMessage(fromBot: Bool, content:String) {
        DispatchQueue.main.async {
            // Updating the last message with the new content
            if fromBot {
                self.liveBotMessage?.content += content
            } else {
                self.liveUserMessage?.content += content
            }
        }
    }
    
    private func resetLiveMessages() {
        DispatchQueue.main.async {
            self.messages = []
        }
    }
}

extension CallContainerModel:PipecatClientDelegate {
    
    private func handleEvent(eventName: String, eventValue: Any? = nil) {
        if let value = eventValue {
            print("Pipecat Demo, received event: \(eventName), value:\(value)")
        } else {
            print("Pipecat Demo, received event: \(eventName)")
        }
    }
    
    func onTransportStateChanged(state: TransportState) {
        Task { @MainActor in
            self.handleEvent(eventName: "onTransportStateChanged", eventValue: state)
            self.voiceClientStatus = state.description
            self.isInCall = ( state == .connecting || state == .connected || state == .ready || state == .authenticating )
            self.createLiveMessage(content: state.description, type: .system)
        }
    }
    
    func onBotReady(botReadyData: BotReadyData) {
        Task { @MainActor in
            self.handleEvent(eventName: "onBotReady")
            self.isBotReady = true
        }
    }
    
    func onConnected() {
        Task { @MainActor in
            self.handleEvent(eventName: "onConnected")
            self.isMicEnabled = self.pipecatClientIOS?.isMicEnabled ?? false
            self.isCamEnabled = self.pipecatClientIOS?.isCamEnabled ?? false
        }
    }
    
    func onDisconnected() {
        Task { @MainActor in
            self.handleEvent(eventName: "onDisconnected")
            self.isBotReady = false
        }
    }
    
    func onError(message: RTVIMessageInbound) {
        Task { @MainActor in
            self.handleEvent(eventName: "onError", eventValue: message)
            self.showError(message: message.data ?? "")
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
    
    func onTrackStarted(track: MediaStreamTrack, participant: Participant?) {
        Task { @MainActor in
            self.handleEvent(eventName: "onTrackStarted", eventValue: track)
            
            guard track.kind == .video else { return }
            
            // Use optional binding to simplify the check for local participant
            if participant?.local ?? true {
                self.localCamId = track.id
            } else {
                self.botCamId = track.id
            }
        }
    }

    func onTrackStopped(track: MediaStreamTrack, participant: Participant?) {
        Task { @MainActor in
            self.handleEvent(eventName: "onTrackStopped", eventValue: track)
            
            guard track.kind == .video else { return }
            
            // Use optional binding to simplify the check for local participant
            if participant?.local ?? true {
                self.localCamId = nil
            } else {
                self.botCamId = nil
            }
        }
    }
    
    func onUserStartedSpeaking() {
        self.handleEvent(eventName: "onUserStartedSpeaking")
        self.createLiveMessage(type: .user)
    }
    
    func onUserStoppedSpeaking() {
        self.handleEvent(eventName: "onUserStoppedSpeaking")
    }
    
    func onBotStartedSpeaking() {
        self.handleEvent(eventName: "onBotStartedSpeaking")
    }
    
    func onBotStoppedSpeaking() {
        self.handleEvent(eventName: "onBotStoppedSpeaking")
    }
    
    func onUserTranscript(data: Transcript) {
        if data.final ?? false {
            self.handleEvent(eventName: "onUserTranscript", eventValue: data.text)
            self.appendTextToLiveMessage(fromBot: false, content: data.text)
        }
    }
    
    func onBotOutput(data: BotOutputData) {
        if data.aggregatedBy == .sentence {
            self.createLiveMessage(type: .bot)
        } else if data.aggregatedBy == .word {
            self.handleEvent(eventName: "onBotOutput", eventValue: data)
            self.appendTextToLiveMessage(fromBot: true, content: data.text + " ")
        }
    }
    
}
