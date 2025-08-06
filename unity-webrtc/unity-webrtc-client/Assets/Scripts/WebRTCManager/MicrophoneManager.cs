using System;
using System.Collections;
using System.Collections.Generic;
using Unity.WebRTC;
using UnityEngine;
using TMPro;

public class MicrophoneManager : MonoBehaviour
{
    [Header("Audio Settings")]
    [SerializeField] private AudioSource audioSource;
    [SerializeField] private int sampleRate = 48000;
    
    [Header("UI Elements")]
    [SerializeField] private TMP_Dropdown microphoneDropdown;
    
    // Public properties
    public AudioStreamTrack AudioTrack { get; private set; }
    public string SelectedDevice { get; private set; }
    public bool IsRecording { get; private set; }
    
    // Events
    public event Action<string> OnDeviceChanged;
    public event Action<float> OnAudioLevelChanged;
    public event Action<string> OnError;
    
    // Private fields
    private Coroutine monitoringCoroutine;
    
    private void Awake()
    {
        // Get or add AudioSource
        if (audioSource == null)
        {
            audioSource = GetComponent<AudioSource>();
            if (audioSource == null)
            {
                audioSource = gameObject.AddComponent<AudioSource>();
            }
        }
        
        // Initialize dropdown if present
        SetupMicrophoneDropdown();
    }
    
    private void OnEnable()
    {
        // Set up dropdown listener
        if (microphoneDropdown != null)
        {
            microphoneDropdown.onValueChanged.AddListener(OnDropdownValueChanged);
        }
    }
    
    private void OnDisable()
    {
        // Remove dropdown listener
        if (microphoneDropdown != null)
        {
            microphoneDropdown.onValueChanged.RemoveListener(OnDropdownValueChanged);
        }
    }
    
    // Dropdown management
    private void SetupMicrophoneDropdown()
    {
        if (microphoneDropdown == null) return;
        
        RefreshMicrophoneDropdown();
    }
    
    public void RefreshMicrophoneDropdown()
    {
        if (microphoneDropdown == null) return;
        
        microphoneDropdown.ClearOptions();
        
        var devices = GetAvailableDevices();
        var options = new List<TMP_Dropdown.OptionData>();
        
        if (devices.Length == 0)
        {
            options.Add(new TMP_Dropdown.OptionData("No microphones found"));
            SelectedDevice = null;
        }
        else
        {
            int selectedIndex = 0;
            for (int i = 0; i < devices.Length; i++)
            {
                options.Add(new TMP_Dropdown.OptionData(devices[i]));
                
                // Keep current selection if it still exists
                if (devices[i] == SelectedDevice)
                {
                    selectedIndex = i;
                }
            }
            
            microphoneDropdown.AddOptions(options);
            microphoneDropdown.value = selectedIndex;
            
            // Select first device if none selected
            if (string.IsNullOrEmpty(SelectedDevice))
            {
                SelectDevice(devices[0]);
            }
        }
        
        Debug.Log($"Microphone dropdown refreshed. Found {devices.Length} devices.");
    }
    
    private void OnDropdownValueChanged(int index)
    {
        var devices = GetAvailableDevices();
        if (index >= 0 && index < devices.Length)
        {
            SelectDevice(devices[index]);
        }
    }
    
    public void SetDropdownInteractable(bool interactable)
    {
        if (microphoneDropdown != null)
        {
            microphoneDropdown.interactable = interactable;
        }
    }
    
    // Device management
    public string[] GetAvailableDevices()
    {
        return Microphone.devices;
    }
    
    public void SelectDevice(string deviceName)
    {
        if (IsRecording)
        {
            Debug.LogWarning("Cannot change device while recording. Stop recording first.");
            return;
        }
        
        SelectedDevice = deviceName;
        OnDeviceChanged?.Invoke(deviceName);
        Debug.Log($"Selected microphone device: {deviceName}");
    }
    
    public void SelectDeviceByIndex(int index)
    {
        var devices = GetAvailableDevices();
        if (index >= 0 && index < devices.Length)
        {
            SelectDevice(devices[index]);
        }
    }
    
    // Recording control
    public bool StartRecording()
    {
        if (IsRecording)
        {
            Debug.LogWarning("Already recording");
            return false;
        }
        
        // Start the coroutine version
        StartCoroutine(StartRecordingCoroutine());
        return true; // Optimistically return true, errors will be handled in coroutine
    }
    
    private IEnumerator StartRecordingCoroutine()
    {
        if (string.IsNullOrEmpty(SelectedDevice))
        {
            var devices = GetAvailableDevices();
            if (devices.Length == 0)
            {
                OnError?.Invoke("No microphone devices found");
                yield break;
            }
            SelectedDevice = devices[0];
        }
        
        Debug.Log($"Starting microphone recording with device: {SelectedDevice}");
        
        try
        {
            // Check microphone capabilities
            int minFreq, maxFreq;
            Microphone.GetDeviceCaps(SelectedDevice, out minFreq, out maxFreq);
            Debug.Log($"Microphone capabilities - Min: {minFreq}Hz, Max: {maxFreq}Hz");
            
            // Create AudioSource if not provided
            if (audioSource == null)
            {
                audioSource = gameObject.AddComponent<AudioSource>();
            }
            
            // Configure AudioSource
            audioSource.loop = true;
            audioSource.mute = false; // Unmute so WebRTC can read audio data from AudioSource
            audioSource.volume = 1.0f; // Full volume for optimal WebRTC audio level detection
            audioSource.spatialBlend = 0f; // 2D sound
            
            Debug.Log("🔧 AudioSource configured: unmuted with full volume for optimal WebRTC levels");
            
            // Start microphone
            audioSource.clip = Microphone.Start(SelectedDevice, true, 1, sampleRate);
            
            if (audioSource.clip == null)
            {
                OnError?.Invoke("Failed to create microphone clip");
                yield break;
            }
            
            // Wait for microphone to start
            int timeout = 100; // 10 seconds timeout
            while (!(Microphone.GetPosition(SelectedDevice) > 0) && timeout > 0)
            {
                System.Threading.Thread.Sleep(100);
                timeout--;
            }
            
            if (timeout <= 0)
            {
                OnError?.Invoke("Microphone failed to start within timeout");
                StopRecording();
                yield break;
            }
            
            // Play the AudioSource
            audioSource.Play();
        }
        catch (Exception e)
        {
            OnError?.Invoke($"Failed to start microphone: {e.Message}");
            StopRecording();
            yield break;
        }
        
        // Wait a bit more to ensure audio is actually flowing (outside try-catch)
        Debug.Log("Waiting for microphone to stabilize and produce data...");
        yield return new WaitForSeconds(1f); // Wait 1 second for audio to stabilize
        
        // Verify audio is actually flowing before creating WebRTC track
        bool audioDetected = false;
        for (int attempts = 0; attempts < 10; attempts++) // Try for up to 5 seconds
        {
            var currentPos = Microphone.GetPosition(SelectedDevice);
            if (currentPos > 1024) // Ensure we have enough samples
            {
                float[] testData = new float[512];
                if (audioSource.clip.GetData(testData, currentPos - 512))
                {
                    float sum = 0f;
                    for (int i = 0; i < testData.Length; i++)
                    {
                        sum += testData[i] * testData[i];
                    }
                    float rms = Mathf.Sqrt(sum / testData.Length);
                    Debug.Log($"Pre-WebRTC audio check #{attempts + 1}: RMS = {rms}");
                    
                    if (rms > 0.001f) // Very low threshold
                    {
                        audioDetected = true;
                        Debug.Log("✅ Audio detected before creating WebRTC track");
                        break;
                    }
                }
            }
            yield return new WaitForSeconds(0.5f); // Wait 500ms between checks
        }
        
        if (!audioDetected)
        {
            Debug.LogWarning("⚠️ No audio detected from microphone before creating WebRTC track. This might explain zero WebRTC levels.");
        }
        
        // Create AudioStreamTrack directly from AudioSource
        AudioTrack = new AudioStreamTrack(audioSource);
        Debug.Log($"=== AudioStreamTrack Debug Info ===");
        Debug.Log($"AudioStreamTrack created from AudioSource. Enabled: {AudioTrack.Enabled}");
        Debug.Log($"AudioStreamTrack ReadyState: {AudioTrack.ReadyState}");
        Debug.Log($"AudioStreamTrack Kind: {AudioTrack.Kind}");
        Debug.Log($"AudioStreamTrack ID: {AudioTrack.Id}");
        
        // Debug AudioSource state
        Debug.Log($"=== AudioSource Debug Info ===");
        Debug.Log($"AudioSource isPlaying: {audioSource.isPlaying}");
        Debug.Log($"AudioSource volume: {audioSource.volume}");
        Debug.Log($"AudioSource mute: {audioSource.mute}");
        Debug.Log($"AudioSource clip length: {audioSource.clip?.length}");
        Debug.Log($"AudioSource clip channels: {audioSource.clip?.channels}");
        Debug.Log($"AudioSource clip frequency: {audioSource.clip?.frequency}");
        
        // Check if we can get data from the clip directly
        if (audioSource.clip != null)
        {
            float[] testData = new float[128];
            var currentPos = Microphone.GetPosition(SelectedDevice);
            Debug.Log($"Current microphone position: {currentPos}");
            
            if (currentPos > 128)
            {
                bool gotData = audioSource.clip.GetData(testData, currentPos - 128);
                if (gotData)
                {
                    float sum = 0f;
                    for (int i = 0; i < testData.Length; i++)
                    {
                        sum += testData[i] * testData[i];
                    }
                    float rms = Mathf.Sqrt(sum / testData.Length);
                    Debug.Log($"Test audio data RMS: {rms} (should be > 0 if audio is present)");
                }
                else
                {
                    Debug.LogWarning("Failed to get test audio data from clip");
                }
            }
        }
        
        IsRecording = true;
        
        // Start monitoring
        if (monitoringCoroutine != null)
        {
            StopCoroutine(monitoringCoroutine);
        }
        monitoringCoroutine = StartCoroutine(MonitorAudioLevel());
        
        Debug.Log("Microphone recording started successfully");
    }
    
    public void StopRecording()
    {
        Debug.Log("Stopping microphone recording");
        
        // Stop monitoring
        if (monitoringCoroutine != null)
        {
            StopCoroutine(monitoringCoroutine);
            monitoringCoroutine = null;
        }
        
        // Stop microphone
        if (!string.IsNullOrEmpty(SelectedDevice) && Microphone.IsRecording(SelectedDevice))
        {
            Microphone.End(SelectedDevice);
        }
        
        // Clean up audio source
        if (audioSource != null)
        {
            audioSource.Stop();
            audioSource.clip = null;
        }
        
        // Dispose track
        if (AudioTrack != null)
        {
            AudioTrack.Dispose();
            AudioTrack = null;
        }
        
        IsRecording = false;
    }
    
    // Monitoring
    private IEnumerator MonitorAudioLevel()
    {
        Debug.Log("Starting audio level monitoring");
        
        yield return new WaitForSeconds(0.5f); // Initial delay
        
        float[] waveData = new float[1024];
        
        while (IsRecording && audioSource != null && !string.IsNullOrEmpty(SelectedDevice))
        {
            int micPosition = Microphone.GetPosition(SelectedDevice);
            
            if (micPosition > 0 && audioSource.clip != null)
            {
                int clipPosition = micPosition - waveData.Length;
                if (clipPosition < 0) clipPosition = 0;
                
                if (audioSource.clip.GetData(waveData, clipPosition))
                {
                    // Calculate RMS
                    float sum = 0f;
                    for (int i = 0; i < waveData.Length; i++)
                    {
                        sum += waveData[i] * waveData[i];
                    }
                    float rms = Mathf.Sqrt(sum / waveData.Length);
                    float db = 20 * Mathf.Log10(rms / 0.1f);
                    
                    OnAudioLevelChanged?.Invoke(db);
                }
            }
            
            yield return new WaitForSeconds(0.1f); // Check every 100ms
        }
        
        Debug.Log("Audio level monitoring stopped");
    }
    
    // Cleanup
    private void OnDestroy()
    {
        StopRecording();
    }
}