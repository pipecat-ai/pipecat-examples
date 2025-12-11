import Foundation
import AVFoundation

class AudioRecorder: NSObject, ObservableObject, AVAudioRecorderDelegate {

    private var audioRecorder: AVAudioRecorder?
    @Published var audioFileURL: URL?
    @Published var recordings: [URL] = []

    func loadRecordings() {
        let documentsPath = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        do {
            let files = try FileManager.default.contentsOfDirectory(at: documentsPath, includingPropertiesForKeys: nil)
            recordings = files.filter { $0.pathExtension == "m4a" || $0.pathExtension == "wav" }
                .sorted { url1, url2 in
                    // Sort by creation date, newest first
                    let date1 = getCreationDate(for: url1) ?? Date.distantPast
                    let date2 = getCreationDate(for: url2) ?? Date.distantPast
                    return date1 > date2
                }
        } catch {
            print("Error loading recordings: \(error)")
        }
    }
    
    func isRecording() -> Bool {
        return self.audioRecorder?.isRecording ?? false
    }

    func deleteRecording(_ recording: URL) {
        do {
            try FileManager.default.removeItem(at: recording)
            print("Recording deleted successfully")
            // Reload recordings to update the UI
            DispatchQueue.main.async {
                self.loadRecordings()
            }
        } catch {
            print("Error deleting recording: \(error)")
        }
    }

    private func getCreationDate(for url: URL) -> Date? {
        do {
            let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
            return attributes[.creationDate] as? Date
        } catch {
            return nil
        }
    }

    func configureSession(category: AVAudioSession.Category) throws {
        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(
                category,
                mode: .measurement,
                options: [.allowBluetooth, .mixWithOthers]
            )
        } catch let e{
            print("Error configuring audio session \(e)")
        }
        try session.setActive(true)
    }

    private func createFileURL() -> URL {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let filename = "recording_\(Date().timeIntervalSince1970).wav"
        return documents.appendingPathComponent(filename)
    }

    func startRecording() throws {
        let url = createFileURL()
        self.audioFileURL = url

        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatLinearPCM),
            AVSampleRateKey: 48000,
            AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsFloatKey: false,
            AVLinearPCMIsNonInterleaved: false
        ]

        audioRecorder = try AVAudioRecorder(url: url, settings: settings)
        audioRecorder?.delegate = self

        guard audioRecorder?.record() == true else {
            throw NSError(domain: "AudioRecorderError", code: -1,
                     userInfo: [NSLocalizedDescriptionKey: "Failed to start recording"])
        }
    }

    func stopRecording() {
        audioRecorder?.stop()
        audioRecorder = nil
    }

    override init() {
        super.init()
        loadRecordings()
    }

    // MARK: - AVAudioRecorderDelegate
    func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        if flag {
            print("Recording finished successfully")
            // Reload recordings to update the UI
            DispatchQueue.main.async {
                self.loadRecordings()
            }
        } else {
            print("Recording failed")
        }
    }

    func audioRecorderEncodeErrorDidOccur(_ recorder: AVAudioRecorder, error: Error?) {
        print("Recording encode error: \(error?.localizedDescription ?? "Unknown error")")
    }
}
