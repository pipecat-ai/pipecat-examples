#import <AVFAudio/AVAudioSession.h>

/// <summary>
/// Native iOS implementation for configuring AVAudioSession for WebRTC with echo cancellation.
/// This addresses Unity WebRTC's lack of built-in echo cancellation on iOS devices.
/// </summary>

extern "C" void _SetupAudioModeForVideoCall() {
    // Retrieve the shared audio session
    AVAudioSession *audioSession = [AVAudioSession sharedInstance];
    
    NSError *error = nil;
    
    // Set the audio session category to PlayAndRecord with VideoChat mode
    // AVAudioSessionModeVideoChat enables echo cancellation and other optimizations for calls
    BOOL success = [audioSession setCategory:AVAudioSessionCategoryPlayAndRecord 
                                        mode:AVAudioSessionModeVideoChat 
                                     options:AVAudioSessionCategoryOptionAllowBluetooth | AVAudioSessionCategoryOptionDefaultToSpeaker
                                       error:&error];
    
    if (!success || error) {
        NSLog(@"❌ Failed to set the audio session configuration: %@", error);
        return;
    }
    
    // Activate the audio session
    success = [audioSession setActive:YES error:&error];
    
    if (!success || error) {
        NSLog(@"❌ Failed to activate the audio session: %@", error);
        return;
    }
    
    NSLog(@"✅ iOS Audio session configured for WebRTC with echo cancellation");
    NSLog(@"📊 Audio session details:");
    NSLog(@"   Category: %@", audioSession.category);
    NSLog(@"   Mode: %@", audioSession.mode);
    NSLog(@"   Sample rate: %.0f Hz", audioSession.sampleRate);
    NSLog(@"   IO buffer duration: %.3f seconds", audioSession.IOBufferDuration);
}

extern "C" void _RestoreDefaultAudioMode() {
    // Retrieve the shared audio session
    AVAudioSession *audioSession = [AVAudioSession sharedInstance];
    
    NSError *error = nil;
    
    // Restore to default category (usually AVAudioSessionCategorySoloAmbient)
    BOOL success = [audioSession setCategory:AVAudioSessionCategorySoloAmbient 
                                        mode:AVAudioSessionModeDefault 
                                     options:0
                                       error:&error];
    
    if (!success || error) {
        NSLog(@"❌ Failed to restore default audio session configuration: %@", error);
        return;
    }
    
    // Deactivate the audio session with option to notify other apps
    success = [audioSession setActive:NO 
                          withOptions:AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation 
                                error:&error];
    
    if (!success || error) {
        NSLog(@"❌ Failed to deactivate the audio session: %@", error);
        return;
    }
    
    NSLog(@"✅ iOS Audio session restored to default configuration");
}