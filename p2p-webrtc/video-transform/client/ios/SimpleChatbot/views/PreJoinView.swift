import SwiftUI

struct PreJoinView: View {

    @State var backendURL: String
    @State var apiKey: String

    @EnvironmentObject private var model: CallContainerModel

    init() {
        let currentSettings = SettingsManager.getSettings()
        self.backendURL = currentSettings.backendURL
        self.apiKey = currentSettings.apiKey
    }

    var body: some View {
        VStack(spacing: 20) {
            Image("pipecat")
                .resizable()
                .frame(width: 80, height: 80)
            Text("Pipecat Client iOS.")
                .font(.headline)
            TextField("Server URL", text: $backendURL)
                .textFieldStyle(RoundedBorderTextFieldStyle())
                .frame(maxWidth: .infinity)
                .padding([.bottom, .horizontal])
            SecureField("Authorization token", text: $apiKey)
                .textFieldStyle(RoundedBorderTextFieldStyle())
                .frame(maxWidth: .infinity)
                .padding([.horizontal])
            Button("Connect") {
                Task {
                    self.model.connect(backendURL: self.backendURL, apiKey: self.apiKey)
                }
            }
            .padding()
            .background(Color.black)
            .foregroundColor(.white)
            .cornerRadius(8)
        }
        .padding()
        .frame(maxHeight: .infinity)
        .background(Color.backgroundApp)
        .toast(message: model.toastMessage, isShowing: model.showToast)
    }
}

#Preview {
    PreJoinView().environmentObject(MockCallContainerModel() as CallContainerModel)
}
