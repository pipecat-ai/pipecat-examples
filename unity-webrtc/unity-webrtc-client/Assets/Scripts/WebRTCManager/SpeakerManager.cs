using System;
using System.Collections;
using Unity.WebRTC;
using UnityEngine;

public class SpeakerManager : MonoBehaviour
{
    [Header("Audio Settings")]
    [SerializeField] private AudioSource audioSource;
    [SerializeField] private bool playOnReceive = true;
    [SerializeField] [Range(0f, 1f)] private float volume = 1f;
    
    // Public properties
    public bool IsPlaying { get; private set; }
    public AudioStreamTrack CurrentTrack { get; private set; }
    
    // Events
    public event Action<AudioStreamTrack> OnTrackReceived;
    public event Action OnTrackRemoved;
    public event Action<float> OnVolumeChanged;
    public event Action<string> OnError;
    
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
        
        // Configure AudioSource for receiving
        ConfigureAudioSource();
    }
    
    private void ConfigureAudioSource()
    {
        audioSource.loop = true;
        audioSource.playOnAwake = false;
        audioSource.volume = volume;
        audioSource.spatialBlend = 0f; // 2D sound
    }
    
    // Track management
    public void SetAudioTrack(AudioStreamTrack track)
    {
        if (track == null)
        {
            OnError?.Invoke("Received null audio track");
            return;
        }
        
        try
        {
            Debug.Log("Setting up received audio track");
            
            // Remove previous track if any
            if (CurrentTrack != null)
            {
                RemoveTrack();
            }
            
            CurrentTrack = track;
            audioSource.SetTrack(track);
            
            if (playOnReceive)
            {
                Play();
            }
            
            OnTrackReceived?.Invoke(track);
            Debug.Log("Audio track successfully set up");
        }
        catch (Exception e)
        {
            OnError?.Invoke($"Failed to set audio track: {e.Message}");
            Debug.LogError($"Error setting audio track: {e}");
        }
    }
    
    public void RemoveTrack()
    {
        if (CurrentTrack != null)
        {
            Stop();
            // Don't set null track - just stop playing
            // audioSource.SetTrack(null); // This line causes the error
            CurrentTrack = null;
            OnTrackRemoved?.Invoke();
            Debug.Log("Audio track removed");
        }
    }
    
    // Playback control
    public void Play()
    {
        if (CurrentTrack != null && audioSource != null)
        {
            audioSource.Play();
            IsPlaying = true;
            Debug.Log("Speaker playback started");
        }
        else
        {
            OnError?.Invoke("Cannot play - no audio track set");
        }
    }
    
    public void Stop()
    {
        if (audioSource != null && audioSource.isPlaying)
        {
            audioSource.Stop();
            IsPlaying = false;
            Debug.Log("Speaker playback stopped");
        }
    }
    
    public void Pause()
    {
        if (audioSource != null && audioSource.isPlaying)
        {
            audioSource.Pause();
            IsPlaying = false;
            Debug.Log("Speaker playback paused");
        }
    }
    
    public void UnPause()
    {
        if (audioSource != null && CurrentTrack != null)
        {
            audioSource.UnPause();
            IsPlaying = true;
            Debug.Log("Speaker playback unpaused");
        }
    }
    
    // Volume control
    public void SetVolume(float newVolume)
    {
        volume = Mathf.Clamp01(newVolume);
        if (audioSource != null)
        {
            audioSource.volume = volume;
        }
        OnVolumeChanged?.Invoke(volume);
    }
    
    public float GetVolume()
    {
        return volume;
    }
    
    // Audio monitoring (optional)
    public float GetAudioLevel()
    {
        if (!IsPlaying || audioSource == null || audioSource.clip == null)
            return 0f;
        
        float[] samples = new float[256];
        audioSource.clip.GetData(samples, audioSource.timeSamples);
        
        float sum = 0f;
        foreach (float sample in samples)
        {
            sum += sample * sample;
        }
        
        return Mathf.Sqrt(sum / samples.Length);
    }
    
    // Cleanup
    private void OnDestroy()
    {
        RemoveTrack();
    }
    
    // Inspector utilities
    private void OnValidate()
    {
        if (audioSource != null)
        {
            audioSource.volume = volume;
        }
    }
}