import SwiftUI

@main
struct SimpleChatbotApp: App {

    @StateObject var callContainerModel = CallContainerModel()
    @StateObject var audioRecorder = AudioRecorder()

    var body: some Scene {
        WindowGroup {
            if (!callContainerModel.isInCall) {
                PreJoinView().environmentObject(callContainerModel).environmentObject(audioRecorder)
            } else {
                MeetingView().environmentObject(callContainerModel).environmentObject(audioRecorder)
            }
        }
    }

}
