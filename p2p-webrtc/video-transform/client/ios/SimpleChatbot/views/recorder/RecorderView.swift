import SwiftUI
import AVFoundation

struct RecorderView: View {
    @EnvironmentObject var recorder: AudioRecorder
    @State private var modeIndex = 0
    @State private var showingShareSheet = false
    @State private var selectedRecordingIndex: Int?

    var modes = ["Record", "Play & Record"]

    var body: some View {
        VStack(spacing: 20) {
            Picker("Mode", selection: $modeIndex) {
                ForEach(0..<modes.count, id: \.self) { i in
                    Text(modes[i])
                }
            }
            .pickerStyle(SegmentedPickerStyle())
            .padding()

            Button(recorder.isRecording() ? "Stop Recording" : "Start Recording") {
                if recorder.isRecording() {
                    recorder.stopRecording()
                } else {
                    let category: AVAudioSession.Category = (modeIndex == 0) ? .record : .playAndRecord
                    do {
                        try recorder.configureSession(category: category)
                        try recorder.startRecording()
                    } catch {
                        print("Recording failed with error: \(error)")
                        // Show user-friendly error message
                    }
                }
            }
            .font(.title2)
            .padding()

            // Recordings List Section
            if !recorder.recordings.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Recordings")
                        .font(.headline)
                        .padding(.top)

                    List(Array(recorder.recordings.enumerated()), id: \.element) { index, recording in
                        HStack {
                            VStack(alignment: .leading) {
                                Text(recording.lastPathComponent)
                                    .font(.caption)
                                Text(formattedDate(for: recording))
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            }

                            Spacer()

                            // Share button
                            Button("Share") {
                                self.selectedRecordingIndex = index
                                self.showingShareSheet = true
                                print("Selected recorder index \(self.selectedRecordingIndex)")
                            }
                            .buttonStyle(.bordered)
                            .font(.caption)

                            // Delete button
                            Button("Delete") {
                                // Clear selection if we're deleting the selected recording
                                if selectedRecordingIndex == index {
                                    selectedRecordingIndex = nil
                                    showingShareSheet = false
                                }
                                // Adjust index if we're deleting something before the selected item
                                else if let selectedIndex = selectedRecordingIndex, selectedIndex > index {
                                    selectedRecordingIndex = selectedIndex - 1
                                }

                                recorder.deleteRecording(recording)
                            }
                            .buttonStyle(.bordered)
                            .foregroundColor(.red)
                            .font(.caption)
                        }
                        .padding(.vertical, 2)
                    }
                    .frame(maxHeight: 200)
                }
            }
        }
        .padding()
        .sheet(isPresented: $showingShareSheet) {
            if let index = self.selectedRecordingIndex, index < recorder.recordings.count {
                ShareSheet(items: [recorder.recordings[index]])
            }
        }
    }

    private func formattedDate(for url: URL) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .short
        formatter.timeStyle = .short

        do {
            let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
            if let creationDate = attributes[.creationDate] as? Date {
                return formatter.string(from: creationDate)
            }
        } catch {
            print("Error getting file attributes: \(error)")
        }

        return "Unknown"
    }
}

// Share Sheet for iOS
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        let controller = UIActivityViewController(activityItems: items, applicationActivities: nil)
        return controller
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
