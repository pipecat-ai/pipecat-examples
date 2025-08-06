using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using Unity.WebRTC;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UI;
using TMPro;

public class WHIPClient : MonoBehaviour
{
    [Header("UI Elements")]
    public Button connectionToggleButton;
    public Button muteButton;
    public TextMeshProUGUI statusText;
    
    [Header("Audio Managers")]
    public MicrophoneManager microphoneManager; // Reference to microphone GameObject
    public SpeakerManager speakerManager; // Reference to speaker GameObject
    public bool enableMicrophone = true;
    
    [Header("Connection Settings")]
    public string whipServerUrl = "http://localhost:7860/api/offer";
    
    private MediaStream sendStream;
    private MediaStream receiveStream;
    private RTCPeerConnection peerConnection;
    private RTCDataChannel dataChannel;
    private bool isConnected = false;
    private bool isConnecting = false;
    private bool iceGatheringComplete = false;
    private bool isMuted = true; // Start muted by default
    
    void Start()
    {
        // Initialize WebRTC
        StartCoroutine(WebRTC.Update());
        
        // Validate manager references
        if (microphoneManager == null)
        {
            Debug.LogError("MicrophoneManager not assigned! Please assign it in the Inspector.");
        }
        
        if (speakerManager == null)
        {
            Debug.LogError("SpeakerManager not assigned! Please assign it in the Inspector.");
        }
        
        // Subscribe to events
        if (microphoneManager != null)
        {
            microphoneManager.OnError += HandleMicrophoneError;
            microphoneManager.OnAudioLevelChanged += HandleAudioLevelChanged;
        }
        
        if (speakerManager != null)
        {
            speakerManager.OnError += HandleSpeakerError;
            speakerManager.OnTrackReceived += HandleSpeakerTrackReceived;
        }
        
        // Initialize UI
        UpdateUI();
        UpdateStatus("Ready to connect");
        
        // Set up button listeners
        if (connectionToggleButton != null)
        {
            connectionToggleButton.onClick.AddListener(OnConnectionToggleClicked);
            Debug.Log("✅ Connection toggle button listener added");
        }
        else
        {
            Debug.LogWarning("⚠️ Connection toggle button is null!");
        }
        
        if (muteButton != null)
        {
            muteButton.onClick.AddListener(OnMuteClicked);
            Debug.Log("✅ Mute button listener added");
        }
        else
        {
            Debug.LogWarning("⚠️ Mute button is null!");
        }
    }
    
    void OnMuteClicked()
    {
        Debug.Log("🎤 Mute button clicked!");
        
        if (microphoneManager != null && microphoneManager.AudioTrack != null)
        {
            isMuted = !isMuted;
            microphoneManager.AudioTrack.Enabled = !isMuted;
            Debug.Log($"Microphone {(isMuted ? "muted" : "unmuted")} via WebRTC");
            UpdateUI();
        }
        else
        {
            Debug.LogWarning("⚠️ Cannot mute - microphone manager or audio track is null");
        }
    }
    
    void OnConnectionToggleClicked()
    {
        Debug.Log("🔄 Connection toggle button clicked!");
        
        if (isConnecting)
        {
            Debug.LogWarning("⚠️ Currently connecting, ignoring click");
            return;
        }
        
        if (isConnected)
        {
            // Currently connected - disconnect
            Debug.Log("🔌 Disconnecting...");
            DisconnectFromServer();
        }
        else
        {
            // Currently disconnected - connect
            Debug.Log("🔗 Connecting...");
            StartCoroutine(ConnectToWHIPServer());
        }
    }
    
    void HandleMicrophoneError(string error)
    {
        Debug.LogError($"Microphone error: {error}");
        UpdateStatus($"Microphone error: {error}");
    }
    
    void HandleAudioLevelChanged(float dbLevel)
    {
        // You can use this to update a volume meter UI if needed
        if (dbLevel > -40f)
        {
            Debug.Log($"🎤 Audio level: {dbLevel:F1}dB");
        }
    }
    
    void HandleSpeakerError(string error)
    {
        Debug.LogError($"Speaker error: {error}");
        UpdateStatus($"Speaker error: {error}");
    }
    
    void HandleSpeakerTrackReceived(AudioStreamTrack track)
    {
        Debug.Log("Speaker received audio track successfully");
    }

    IEnumerator ConnectToWHIPServer()
    {
        isConnecting = true;
        isConnected = false;
        UpdateUI();
        UpdateStatus("Connecting...");

        // Configure iOS audio session for echo cancellation before starting WebRTC
        #if UNITY_IOS && !UNITY_EDITOR
        AVAudioSession.SetupAudioModeForVideoCall();
        #endif

        // Create peer connection
        var config = new RTCConfiguration
        {
            iceServers = new RTCIceServer[] { }
        };
        peerConnection = new RTCPeerConnection(ref config);

        iceGatheringComplete = false;

        // Create MediaStreams
        sendStream = new MediaStream();
        receiveStream = new MediaStream();
        SetupMediaStreamCallbacks();
        SetupPeerConnectionCallbacks();

        // Set up microphone audio if enabled
        if (enableMicrophone && microphoneManager != null)
        {
            if (!microphoneManager.StartRecording())
            {
                OnConnectionFailed("Failed to start microphone recording");
                yield break;
            }

            // Wait for the AudioTrack to be created by the MicrophoneManager coroutine
            Debug.Log("Waiting for MicrophoneManager to create AudioTrack...");
            float audioTrackTimeout = 10f; // 10 second timeout
            float audioTrackElapsed = 0f;
            
            while (microphoneManager.AudioTrack == null && audioTrackElapsed < audioTrackTimeout)
            {
                audioTrackElapsed += Time.deltaTime;
                yield return null;
            }

            if (microphoneManager.AudioTrack == null)
            {
                OnConnectionFailed($"Timeout waiting for microphone audio track creation ({audioTrackTimeout}s)");
                yield break;
            }
            
            Debug.Log($"✅ AudioTrack created successfully after {audioTrackElapsed:F2}s");
            Debug.Log("Microphone audio track created successfully. Adding to peer connection");
            
            // Verify track properties before adding
            var audioTrack = microphoneManager.AudioTrack;
            Debug.Log($"=== Audio Track Verification ===");
            Debug.Log($"Track Kind: {audioTrack.Kind}");
            Debug.Log($"Track Enabled: {audioTrack.Enabled}");
            Debug.Log($"Track ReadyState: {audioTrack.ReadyState}");
            Debug.Log($"Track ID: {audioTrack.Id}");
            
            // Add track directly to peer connection with stream (Unity WebRTC style)
            var sender = peerConnection.AddTrack(audioTrack, sendStream);
            Debug.Log($"=== Track Addition Results ===");
            Debug.Log($"Sender created: {sender != null}");
            
            // Start muted by default
            audioTrack.Enabled = !isMuted; // isMuted is true by default
            Debug.Log($"🔇 Audio track started in muted state: {isMuted}");
            
            if (sender != null)
            {
                Debug.Log($"Sender track: {sender.Track != null}");
                Debug.Log($"Sender track ID: {sender.Track?.Id}");
                Debug.Log($"Sender transceivers count: {peerConnection.GetTransceivers().Count()}");
                
                // Verify the transceiver was created properly
                var transceivers = peerConnection.GetTransceivers();
                foreach (var transceiver in transceivers)
                {
                    if (transceiver.Sender == sender)
                    {
                        Debug.Log($"Found matching transceiver - Direction: {transceiver.Direction}");
                        Debug.Log($"Transceiver CurrentDirection: {transceiver.CurrentDirection}");
                    }
                }
            }
            else
            {
                Debug.LogError("❌ Failed to create sender for audio track!");
            }
        }
        
        // Add receive-only transceiver for video
        var videoTransceiver = peerConnection.AddTransceiver(TrackKind.Video);
        videoTransceiver.Direction = RTCRtpTransceiverDirection.RecvOnly;
        
        // If no microphone, add receive-only audio transceiver
        if (!enableMicrophone || microphoneManager == null)
        {
            var audioTransceiver = peerConnection.AddTransceiver(TrackKind.Audio);
            audioTransceiver.Direction = RTCRtpTransceiverDirection.RecvOnly;
        }
        
        // Create data channel
        var dataChannelInit = new RTCDataChannelInit();
        dataChannel = peerConnection.CreateDataChannel("app-messages", dataChannelInit);
        SetupDataChannelCallbacks();

        // Create offer
        var op1 = peerConnection.CreateOffer();
        yield return op1;

        if (op1.IsError)
        {
            OnConnectionFailed($"Failed to create offer: {op1.Error.message}");
            yield break;
        }

        // Set local description
        var desc = op1.Desc;
        
        // Debug: Check if audio is in the SDP
        Debug.Log("=== Checking SDP for audio ===");
        if (desc.sdp.Contains("m=audio"))
        {
            Debug.Log("✅ Audio media line found in SDP");
            // Extract audio codec info
            var audioLineIndex = desc.sdp.IndexOf("m=audio");
            var audioLineEnd = desc.sdp.IndexOf("\r\n", audioLineIndex);
            if (audioLineEnd > audioLineIndex)
            {
                var audioLine = desc.sdp.Substring(audioLineIndex, audioLineEnd - audioLineIndex);
                Debug.Log($"Audio line: {audioLine}");
            }
        }
        else
        {
            Debug.LogError("❌ No audio media line found in SDP!");
        }
        
        var op2 = peerConnection.SetLocalDescription(ref desc);
        yield return op2;

        if (op2.IsError)
        {
            OnConnectionFailed($"Failed to set local description: {op2.Error.message}");
            yield break;
        }

        // Wait for ICE gathering
        float timeout = 5f;
        float elapsed = 0f;
        while (!iceGatheringComplete && elapsed < timeout)
        {
            elapsed += Time.deltaTime;
            yield return null;
        }

        if (!iceGatheringComplete)
        {
            Debug.LogWarning("ICE gathering timeout - proceeding anyway");
        }

        // Send offer to server
        yield return StartCoroutine(SendOfferToServer(peerConnection.LocalDescription));
    }
    
    void SetupMediaStreamCallbacks()
    {
        receiveStream.OnAddTrack = e => {
            Debug.Log($"MediaStream OnAddTrack: {e.Track.Kind}");
            
            if(e.Track is AudioStreamTrack audioTrack)
            {
                Debug.Log("Received audio track - passing to SpeakerManager");
                
                if (speakerManager != null)
                {
                    speakerManager.SetAudioTrack(audioTrack);
                }
                else
                {
                    Debug.LogWarning("No SpeakerManager assigned for audio playback");
                }
            }
            else if (e.Track is VideoStreamTrack videoTrack)
            {
                Debug.Log("Received video track (not handling video yet)");
            }
        };
    }
    
    void SetupPeerConnectionCallbacks()
    {
        peerConnection.OnIceCandidate = candidate =>
        {
            Debug.Log($"ICE Candidate: {candidate.Candidate}");
        };
        
        peerConnection.OnIceGatheringStateChange = state =>
        {
            Debug.Log($"ICE Gathering State: {state}");
            if (state == RTCIceGatheringState.Complete)
            {
                iceGatheringComplete = true;
            }
        };
        
        peerConnection.OnConnectionStateChange = state =>
        {
            Debug.Log($"Connection State: {state}");
            
            switch (state)
            {
                case RTCPeerConnectionState.Connected:
                    OnConnectionEstablished();
                    break;
                case RTCPeerConnectionState.Disconnected:
                case RTCPeerConnectionState.Failed:
                case RTCPeerConnectionState.Closed:
                    OnConnectionLost();
                    break;
            }
        };
        
        peerConnection.OnTrack = trackEvent =>
        {
            Debug.Log($"RTCPeerConnection OnTrack: {trackEvent.Track.Kind}");
            
            if (trackEvent.Track.Kind == TrackKind.Audio)
            {
                Debug.Log("Adding audio track to MediaStream");
                receiveStream.AddTrack(trackEvent.Track);
            }
            else if (trackEvent.Track.Kind == TrackKind.Video)
            {
                Debug.Log("Adding video track to MediaStream");
                receiveStream.AddTrack(trackEvent.Track);
            }
        };
    }
    
    void SetupDataChannelCallbacks()
    {
        if (dataChannel == null) return;
        
        dataChannel.OnOpen = () =>
        {
            Debug.Log("Data channel opened - ready to receive app messages");
        };
        
        dataChannel.OnClose = () =>
        {
            Debug.Log("Data channel closed");
        };
        
        dataChannel.OnMessage = (byte[] data) =>
        {
            string message = System.Text.Encoding.UTF8.GetString(data);
            Debug.Log($"Received app message: {message}");
            HandleAppMessage(message);
        };
    }
    
    void HandleAppMessage(string jsonMessage)
    {
        try
        {
            var messageData = JsonUtility.FromJson<AppMessage>(jsonMessage);
            
            switch (messageData.type)
            {
                case "status":
                    Debug.Log($"Status message: {messageData.content}");
                    break;
                case "command":
                    Debug.Log($"Command message: {messageData.content}");
                    break;
                case "periodic":
                    Debug.Log($"Periodic message: {messageData.content}");
                    break;
                case "data":
                    Debug.Log($"Data message: {messageData.content}");
                    break;
                default:
                    Debug.Log($"Unknown message type: {messageData.type}");
                    break;
            }
        }
        catch (System.Exception e)
        {
            Debug.LogError($"Failed to parse app message: {e.Message}");
        }
    }
    
    public void SendAppMessage(string message)
    {
        if (dataChannel != null && dataChannel.ReadyState == RTCDataChannelState.Open)
        {
            byte[] data = System.Text.Encoding.UTF8.GetBytes(message);
            dataChannel.Send(data);
            Debug.Log($"Sent app message: {message}");
        }
        else
        {
            Debug.LogWarning("Data channel not available for sending messages");
        }
    }
    
    IEnumerator SendOfferToServer(RTCSessionDescription offer)
    {
        var offerData = new OfferData
        {
            sdp = offer.sdp,
            type = offer.type.ToString().ToLower()
        };

        string jsonData = JsonUtility.ToJson(offerData);
        byte[] bodyRaw = Encoding.UTF8.GetBytes(jsonData);
        
        Debug.Log($"Sending offer to WHIP server: {whipServerUrl}");
        
        using (UnityWebRequest request = new UnityWebRequest(whipServerUrl, "POST"))
        {
            request.uploadHandler = new UploadHandlerRaw(bodyRaw);
            request.downloadHandler = new DownloadHandlerBuffer();
            request.SetRequestHeader("Content-Type", "application/json");
            
            yield return request.SendWebRequest();
            
            if (request.result == UnityWebRequest.Result.Success)
            {
                string responseText = request.downloadHandler.text;
                var answerData = JsonUtility.FromJson<AnswerData>(responseText);
                
                var answer = new RTCSessionDescription
                {
                    type = (RTCSdpType)Enum.Parse(typeof(RTCSdpType), answerData.type, true),
                    sdp = answerData.sdp
                };
                
                var op3 = peerConnection.SetRemoteDescription(ref answer);
                yield return op3;
                
                if (op3.IsError)
                {
                    OnConnectionFailed($"Failed to set remote description: {op3.Error.message}");
                }
                else
                {
                    Debug.Log("Successfully set remote description");
                    UpdateStatus("Establishing connection...");
                }
            }
            else
            {
                OnConnectionFailed($"HTTP request failed: {request.error}");
            }
        }
    }
    
    void DisconnectFromServer()
    {
        Debug.Log("Disconnecting from WHIP server");
        
        // Restore iOS audio session to default configuration
        #if UNITY_IOS && !UNITY_EDITOR
        AVAudioSession.RestoreDefaultAudioMode();
        #endif
        
        // Stop microphone
        if (enableMicrophone && microphoneManager != null)
        {
            microphoneManager.StopRecording();
        }
        
        // Stop speaker
        if (speakerManager != null)
        {
            speakerManager.RemoveTrack();
        }
        
        // Clean up WebRTC
        if (sendStream != null)
        {
            sendStream.Dispose();
            sendStream = null;
        }
        
        if (peerConnection != null)
        {
            peerConnection.Close();
            peerConnection.Dispose();
            peerConnection = null;
        }
        
        if (receiveStream != null)
        {
            receiveStream.Dispose();
            receiveStream = null;
        }
        
        if (dataChannel != null)
        {
            dataChannel.Close();
            dataChannel = null;
        }
        
        OnConnectionStopped();
    }
    
    void OnDestroy()
    {
        // Unsubscribe from events
        if (microphoneManager != null)
        {
            microphoneManager.OnError -= HandleMicrophoneError;
            microphoneManager.OnAudioLevelChanged -= HandleAudioLevelChanged;
        }
        
        if (speakerManager != null)
        {
            speakerManager.OnError -= HandleSpeakerError;
            speakerManager.OnTrackReceived -= HandleSpeakerTrackReceived;
        }
        
        
        if (peerConnection != null)
        {
            peerConnection.Close();
            peerConnection.Dispose();
        }
    }
    
    // Event handlers
    void OnConnectionEstablished()
    {
        Debug.Log("🎉 WebRTC connection established!");
        isConnected = true;
        isConnecting = false;
        UpdateUI();
        UpdateStatus("Connected - Receiving audio");
        
        StartCoroutine(LogAudioStats());
        StartCoroutine(VerifyAudioStreaming());
        StartCoroutine(MonitorWebRTCAudioLevels());
    }
    
    IEnumerator LogAudioStats()
    {
        yield return new WaitForSeconds(2f); // Initial delay
        
        while (isConnected)
        {
            var op = peerConnection.GetStats();
            yield return op;
            
            if (!op.IsError)
            {
                var report = op.Value;
                bool foundAudioStats = false;
                
                foreach (var stat in report.Stats.Values)
                {
                    if (stat.Type == RTCStatsType.OutboundRtp && stat.Dict.ContainsKey("kind") && (string)stat.Dict["kind"] == "audio")
                    {
                        foundAudioStats = true;
                        Debug.Log("=== Audio Outbound Stats ===");
                        
                        if (stat.Dict.TryGetValue("bytesSent", out var bytesSent))
                            Debug.Log($"  Bytes sent: {bytesSent}");
                            
                        if (stat.Dict.TryGetValue("packetsSent", out var packetsSent))
                            Debug.Log($"  Packets sent: {packetsSent}");
                            
                        if (stat.Dict.TryGetValue("timestamp", out var timestamp))
                            Debug.Log($"  Timestamp: {timestamp}");
                            
                        // Log all available stats for debugging
                        foreach (var kvp in stat.Dict)
                        {
                            if (kvp.Key != "kind" && kvp.Key != "bytesSent" && kvp.Key != "packetsSent" && kvp.Key != "timestamp")
                                Debug.Log($"  {kvp.Key}: {kvp.Value}");
                        }
                    }
                }
                
                if (!foundAudioStats)
                {
                    Debug.LogWarning("No outbound audio stats found - audio might not be sending");
                }
            }
            
            yield return new WaitForSeconds(5f);
        }
    }
    
    IEnumerator VerifyAudioStreaming()
    {
        Debug.Log("=== Starting Audio Streaming Verification ===");
        
        if (microphoneManager == null || microphoneManager.AudioTrack == null)
        {
            Debug.LogWarning("Cannot verify audio streaming - MicrophoneManager or AudioTrack is null");
            yield break;
        }
        
        // Wait a bit for everything to settle
        yield return new WaitForSeconds(1f);
        
        var audioTrack = microphoneManager.AudioTrack;
        var lastCheckTime = Time.time;
        var verificationCount = 0;
        
        while (isConnected && verificationCount < 10) // Run 10 checks over 50 seconds
        {
            verificationCount++;
            Debug.Log($"=== Audio Streaming Check #{verificationCount} ===");
            
            // Check track state
            Debug.Log($"Track ReadyState: {audioTrack.ReadyState}");
            Debug.Log($"Track Enabled: {audioTrack.Enabled}");
            Debug.Log($"Track Kind: {audioTrack.Kind}");
            
            // Check microphone manager status
            if (microphoneManager != null)
            {
                Debug.Log($"MicrophoneManager IsRecording: {microphoneManager.IsRecording}");
                Debug.Log($"MicrophoneManager SelectedDevice: {microphoneManager.SelectedDevice}");
                
                // Verify audio is coming through in real-time
                var currentTime = Time.time;
                Debug.Log($"Time since last check: {currentTime - lastCheckTime:F2}s");
                lastCheckTime = currentTime;
                
                // Check if microphone position is advancing (indicates real-time streaming)
                if (!string.IsNullOrEmpty(microphoneManager.SelectedDevice))
                {
                    var micPosition = Microphone.GetPosition(microphoneManager.SelectedDevice);
                    var isRecording = Microphone.IsRecording(microphoneManager.SelectedDevice);
                    
                    Debug.Log($"Unity Microphone.GetPosition: {micPosition}");
                    Debug.Log($"Unity Microphone.IsRecording: {isRecording}");
                    
                    if (isRecording && micPosition > 0)
                    {
                        Debug.Log("✅ Real-time audio confirmed - microphone position is advancing");
                    }
                    else
                    {
                        Debug.LogWarning("⚠️ Audio may not be streaming - microphone not recording or position is 0");
                    }
                }
            }
            
            // Verify track is actually sending data by checking WebRTC stats
            var statsOp = peerConnection.GetStats();
            yield return statsOp;
            
            if (!statsOp.IsError)
            {
                var report = statsOp.Value;
                bool foundActiveAudio = false;
                
                foreach (var stat in report.Stats.Values)
                {
                    if (stat.Type == RTCStatsType.OutboundRtp && 
                        stat.Dict.ContainsKey("kind") && 
                        (string)stat.Dict["kind"] == "audio")
                    {
                        if (stat.Dict.TryGetValue("bytesSent", out var bytesSent) && 
                            stat.Dict.TryGetValue("packetsSent", out var packetsSent))
                        {
                            foundActiveAudio = true;
                            Debug.Log($"✅ Audio actively sending - Bytes: {bytesSent}, Packets: {packetsSent}");
                            
                            // Log framerate info if available
                            if (stat.Dict.TryGetValue("framesEncoded", out var framesEncoded))
                                Debug.Log($"  Frames encoded: {framesEncoded}");
                                
                            // Log media source stats if available  
                            if (stat.Dict.TryGetValue("mediaSourceId", out var mediaSourceId))
                                Debug.Log($"  Media source ID: {mediaSourceId}");
                        }
                    }
                    
                    // Also check for media-source stats to verify input
                    if (stat.Type == RTCStatsType.MediaSource && 
                        stat.Dict.ContainsKey("kind") && 
                        (string)stat.Dict["kind"] == "audio")
                    {
                        Debug.Log("=== Media Source Stats ===");
                        foreach (var kvp in stat.Dict)
                        {
                            Debug.Log($"  {kvp.Key}: {kvp.Value}");
                        }
                    }
                }
                
                if (!foundActiveAudio)
                {
                    Debug.LogWarning("❌ No active outbound audio stats found!");
                }
            }
            
            yield return new WaitForSeconds(5f); // Check every 5 seconds
        }
        
        Debug.Log("=== Audio Streaming Verification Complete ===");
    }
    
    IEnumerator MonitorWebRTCAudioLevels()
    {
        Debug.Log("=== Starting WebRTC Audio Level Monitoring ===");
        
        // Wait a bit for connection to stabilize
        yield return new WaitForSeconds(2f);
        
        while (isConnected)
        {
            var statsOp = peerConnection.GetStats();
            yield return statsOp;
            
            if (!statsOp.IsError)
            {
                var report = statsOp.Value;
                bool foundMediaSource = false;
                
                foreach (var stat in report.Stats.Values)
                {
                    // Look specifically for media-source stats with audio kind
                    if (stat.Type == RTCStatsType.MediaSource && 
                        stat.Dict.ContainsKey("kind") && 
                        (string)stat.Dict["kind"] == "audio")
                    {
                        foundMediaSource = true;
                        
                        // Extract audio level and other key metrics
                        var audioLevel = stat.Dict.TryGetValue("audioLevel", out var level) ? level : "N/A";
                        var totalAudioEnergy = stat.Dict.TryGetValue("totalAudioEnergy", out var energy) ? energy : "N/A";
                        var totalSamplesDuration = stat.Dict.TryGetValue("totalSamplesDuration", out var duration) ? duration : "N/A";
                        var trackIdentifier = stat.Dict.TryGetValue("trackIdentifier", out var trackId) ? trackId : "N/A";
                        
                        Debug.Log($"🔊 WebRTC Audio Levels - Level: {audioLevel}, Energy: {totalAudioEnergy}, Duration: {totalSamplesDuration}s");
                        
                        // Convert audioLevel to a more readable format if it's a number
                        if (audioLevel?.ToString() != "N/A" && double.TryParse(audioLevel.ToString(), out double levelValue))
                        {
                            // WebRTC audioLevel is typically between 0.0 and 1.0
                            var levelPercent = levelValue * 100;
                            var levelDb = levelValue > 0 ? 20 * Math.Log10(levelValue) : -60; // Convert to dB
                            
                            Debug.Log($"🎚️ WebRTC Audio Level: {levelPercent:F1}% ({levelDb:F1}dB)");
                            
                            if (levelValue > 0.01) // If there's detectable audio
                            {
                                Debug.Log("✅ WebRTC is detecting audio input");
                            }
                            else
                            {
                                Debug.LogWarning("⚠️ WebRTC audio level is very low or zero");
                            }
                        }
                        
                        // Also get microphone manager level for comparison
                        if (microphoneManager != null)
                        {
                            // Get the latest audio level from microphone manager
                            Debug.Log($"🎤 For comparison - MicrophoneManager is recording: {microphoneManager.IsRecording}");
                            
                            // Check if Unity's microphone is actually capturing audio
                            if (!string.IsNullOrEmpty(microphoneManager.SelectedDevice))
                            {
                                var micPosition = Microphone.GetPosition(microphoneManager.SelectedDevice);
                                var isRecording = Microphone.IsRecording(microphoneManager.SelectedDevice);
                                Debug.Log($"🎤 Unity Microphone - Recording: {isRecording}, Position: {micPosition}");
                            }
                        }
                        
                        // Log timestamp for correlation
                        if (stat.Dict.TryGetValue("timestamp", out var timestamp))
                        {
                            Debug.Log($"⏰ WebRTC Stats Timestamp: {timestamp}");
                        }
                        
                        break; // We found the audio media source, no need to continue
                    }
                }
                
                if (!foundMediaSource)
                {
                    Debug.LogWarning("❌ No audio media-source stats found in WebRTC report");
                    
                    // Debug: List all available stat types
                    var availableTypes = report.Stats.Values.Select(s => s.Type.ToString()).Distinct();
                    Debug.Log($"Available stat types: {string.Join(", ", availableTypes)}");
                }
            }
            else
            {
                Debug.LogError($"Failed to get WebRTC stats: {statsOp.Error.message}");
            }
            
            yield return new WaitForSeconds(2f); // Check every 2 seconds as requested
        }
        
        Debug.Log("=== WebRTC Audio Level Monitoring Stopped ===");
    }
    
    void OnConnectionFailed(string error)
    {
        Debug.LogError($"❌ WebRTC connection failed: {error}");
        isConnected = false;
        isConnecting = false;
        UpdateUI();
        UpdateStatus($"Connection failed: {error}");
        
        // Stop microphone if it was started
        if (enableMicrophone && microphoneManager != null)
        {
            microphoneManager.StopRecording();
        }
        
        // Clean up
        if (peerConnection != null)
        {
            peerConnection.Close();
            peerConnection.Dispose();
            peerConnection = null;
        }
    }
    
    void OnConnectionLost()
    {
        Debug.Log("📡 WebRTC connection lost");
        OnConnectionStopped();
    }
    
    void OnConnectionStopped()
    {
        Debug.Log("🛑 WebRTC connection stopped");
        isConnected = false;
        isConnecting = false;
        UpdateUI();
        UpdateStatus("Disconnected");
    }
    
    void UpdateUI()
    {
        // Update connection toggle button
        if (connectionToggleButton != null)
        {
            connectionToggleButton.interactable = !isConnecting;
            
            var buttonText = connectionToggleButton.GetComponentInChildren<TextMeshProUGUI>();
            if (buttonText != null)
            {
                if (isConnecting)
                {
                    buttonText.text = "Connecting...";
                }
                else if (isConnected)
                {
                    buttonText.text = "Disconnect";
                }
                else
                {
                    buttonText.text = "Connect";
                }
            }
        }
        
        // Update mute button
        if (muteButton != null && microphoneManager != null)
        {
            muteButton.interactable = isConnected && enableMicrophone;
            var buttonText = muteButton.GetComponentInChildren<TextMeshProUGUI>();
            if (buttonText != null)
            {
                buttonText.text = isMuted ? "Unmute" : "Mute";
            }
        }
        
        // Update microphone dropdown interactability through the manager
        if (microphoneManager != null)
        {
            microphoneManager.SetDropdownInteractable(!isConnected);
        }
    }
    
    void UpdateStatus(string message)
    {
        if (statusText != null)
        {
            statusText.text = message;
        }
        Debug.Log($"Status: {message}");
    }
    
    [System.Serializable]
    private class OfferData
    {
        public string sdp;
        public string type;
    }
    
    [System.Serializable] 
    private class AnswerData
    {
        public string sdp;
        public string type;
    }
    
    [System.Serializable]
    private class AppMessage
    {
        public string type;
        public string content;
        public string timestamp;
    }
}