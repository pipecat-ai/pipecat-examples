import SwiftUI

import PipecatClientIOSDaily
import PipecatClientIOS
import CoreLocation

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
    let locationManager = LocationManager()
    
    init() {
        // Changing the log level
        PipecatClientIOS.setLogLevel(.warn)
        self.locationManager.requestLocationPermission()
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
        let startBotParams = APIRequest.init(endpoint: URL(string: baseUrl + "/connect")!)
        self.pipecatClientIOS?.startBotAndConnect(startBotParams: startBotParams) { (result: Result<DailyTransportConnectionParams, AsyncExecutionError>) in
            if case .failure(let error) = result {
                self.showError(message: error.localizedDescription)
                self.pipecatClientIOS = nil
            }
        }
        // Selecting the mic based on the preferences
        if let selectedMic = currentSettings.selectedMic {
            self.pipecatClientIOS?.updateMic(micId: MediaDeviceId(id:selectedMic), completion: nil)
        }
        self.saveCredentials(backendURL: baseUrl)
    }
    
    @MainActor
    func disconnect() {
        self.pipecatClientIOS?.disconnect(completion: nil)
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
        self.handleEvent(eventName: "onTransportStateChanged", eventValue: state)
        self.voiceClientStatus = state.description
        self.isInCall = ( state == .connecting || state == .connected || state == .ready || state == .authenticating )
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
        self.stopTimer()
        self.isBotReady = false
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
    
    private func openGoogleMaps(fullAddress: String) {
        DispatchQueue.main.async {
            // Not using the latitude and longitude that we are receiving, they don't see to be matching the address
            // &center=\(latitude),\(longitude)
            let googleMapsURL = "comgooglemaps://?q=\(fullAddress)&zoom=14"
            print("googleMapsURL \(googleMapsURL)")
            if let url = URL(string: googleMapsURL) {
                if UIApplication.shared.canOpenURL(url) {
                    UIApplication.shared.open(url, options: [:], completionHandler: nil)
                } else {
                    // Google Maps not installed, fallback to web
                    if let webURL = URL(string: "https://www.google.com/maps/search/?api=1&query=\(fullAddress)") {
                        UIApplication.shared.open(webURL, options: [:], completionHandler: nil)
                    }
                }
            }
        }
    }
    
    private func handleRestaurantLocation(restaurantInfo:Value) {
        var restaurantName: String? = nil
        var longitude: Double? = nil
        var latitude: Double? = nil
        var fullAddress: String = ""
        
        if case .object(let dictionary) = restaurantInfo {
            if let restaurantValue = dictionary["restaurant"],
               case .string(let name) = restaurantValue {
                restaurantName = name
            }
            if let lonValue = dictionary["lon"],
               case .string(let lon) = lonValue {
                longitude = Double(lon)
            }
            if let latValue = dictionary["lat"],
               case .string(let lat) = latValue {
                latitude = Double(lat)
            }
            if let addressValue = dictionary["address"],
               case .string(let address) = addressValue {
                fullAddress = address
            }
        }
        
        if let restaurant = restaurantName,
           let lon = longitude,
           let lat = latitude {
            print("Restaurant: \(restaurant), Longitude: \(lon), Latitude: \(lat)")
            print("Restaurant: \(fullAddress)")
            self.openGoogleMaps(fullAddress: fullAddress)
        } else {
            print("One or more properties are missing for the restaurant location.")
        }
    }
    
    private func handleGetCurrentLocation() async -> Value {
        do {
            let location = try await locationManager.fetchLocation()
            print("Location: \(location.coordinate.latitude), \(location.coordinate.longitude)")
            return Value.object([
                "lat": .string(String(location.coordinate.latitude)),
                "lon": .string(String(location.coordinate.longitude))
            ])
        } catch {
            return Value.string("Failed to get current location!")
        }
    }
    
    func onLLMFunctionCall(functionCallData: LLMFunctionCallData, onResult: ((Value) async -> Void)) async {
        print("onLLMFunctionCall \(functionCallData.functionName)")
        var result = Value.object([:])
        if let selectedFunction = ToolsFunctions(rawValue: functionCallData.functionName) {
            // Use a switch to handle the different enum cases
            switch selectedFunction {
            case .getMyCurrentLocation:
                result = await self.handleGetCurrentLocation()
            case .setRestaurantLocation:
                print("Restaurant location: \(functionCallData.args)")
                self.handleRestaurantLocation(restaurantInfo: functionCallData.args)
                result = .string("success")
            }
        } else {
            print("Invalid function received \(functionCallData.functionName)")
        }
        await onResult(result)
    }
}

enum ToolsFunctions: String {
    case getMyCurrentLocation = "get_my_current_location"
    case setRestaurantLocation = "set_restaurant_location"
}
