using System.Runtime.InteropServices;
using UnityEngine;

/// <summary>
/// iOS-specific audio session configuration for WebRTC echo cancellation.
/// This class provides a workaround for Unity WebRTC's lack of built-in echo cancellation on iOS.
/// </summary>
public static class AVAudioSession
{
#if UNITY_IOS && !UNITY_EDITOR
    [DllImport("__Internal")]
    private static extern void _SetupAudioModeForVideoCall();

    [DllImport("__Internal")]
    private static extern void _RestoreDefaultAudioMode();
#endif

    /// <summary>
    /// Configures the iOS audio session for optimal WebRTC performance with echo cancellation.
    /// This should be called before starting WebRTC audio streaming.
    /// </summary>
    public static void SetupAudioModeForVideoCall()
    {
#if UNITY_IOS && !UNITY_EDITOR
        Debug.Log("🍎 Setting up iOS audio session for WebRTC with echo cancellation");
        _SetupAudioModeForVideoCall();
#else
        Debug.Log("📱 AVAudioSession configuration skipped - not running on iOS");
#endif
    }

    /// <summary>
    /// Restores the default audio session configuration.
    /// This should be called when stopping WebRTC or when the app goes to background.
    /// </summary>
    public static void RestoreDefaultAudioMode()
    {
#if UNITY_IOS && !UNITY_EDITOR
        Debug.Log("🍎 Restoring default iOS audio session configuration");
        _RestoreDefaultAudioMode();
#else
        Debug.Log("📱 AVAudioSession restore skipped - not running on iOS");
#endif
    }
}