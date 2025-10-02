package ai.pipecat.simple_chatbot_client.ui

import ai.pipecat.simple_chatbot_client.VoiceClientManager
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun InCallLayout(voiceClientManager: VoiceClientManager) {

    val localCam by remember { derivedStateOf { voiceClientManager.tracks.value?.local?.video } }

    Column(Modifier.fillMaxSize().imePadding()) {

        InCallHeader(expiryTime = null)

        Box(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            contentAlignment = Alignment.Center
        ) {
            Column(
                modifier = Modifier.fillMaxWidth(),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically)
            ) {
                BotIndicator(
                    modifier = Modifier,
                    isReady = voiceClientManager.botReady.value,
                    isTalking = voiceClientManager.botIsTalking,
                    audioLevel = voiceClientManager.botAudioLevel
                )

                Row(
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    UserMicButton(
                        onClick = voiceClientManager::toggleMic,
                        micEnabled = voiceClientManager.mic.value,
                        modifier = Modifier,
                        isTalking = voiceClientManager.userIsTalking,
                        audioLevel = voiceClientManager.userAudioLevel
                    )

                    UserCamButton(
                        onClick = voiceClientManager::toggleCamera,
                        onLongClick = voiceClientManager::flipCamera,
                        camEnabled = voiceClientManager.camera.value,
                        camTrackId = localCam,
                        modifier = Modifier
                    )
                }
            }
        }

        InCallFooter(
            onClickEnd = voiceClientManager::stop,
            onSubmitChatText = voiceClientManager::sendText,
            chatHistory = voiceClientManager.chatHistory,
        )
    }
}
