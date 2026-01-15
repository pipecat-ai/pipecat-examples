package ai.pipecat.simple_chatbot_client

import ai.pipecat.client.daily.VoiceClientVideoView
import ai.pipecat.client.small_webrtc_transport.views.VideoView
import ai.pipecat.client.types.MediaTrackId
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView

@Composable
fun CameraView(
    modifier: Modifier,
    transport: TransportType,
    track: MediaTrackId?
) {
    AndroidView(
        modifier = modifier,
        factory = { context ->
            when (transport) {
                TransportType.Daily -> VoiceClientVideoView(context)
                TransportType.SmallWebrtc -> VideoView(context)
            }
        },
        update = { view ->
            when (transport) {
                TransportType.Daily -> (view as VoiceClientVideoView).voiceClientTrack = track
                TransportType.SmallWebrtc -> (view as VideoView).track = track
            }
        }
    )
}