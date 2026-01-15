package ai.pipecat.simple_chatbot_client.ui

import ai.pipecat.simple_chatbot_client.CameraView
import ai.pipecat.simple_chatbot_client.HDivider
import ai.pipecat.simple_chatbot_client.VoiceClientManager
import ai.pipecat.simple_chatbot_client.ui.theme.Colors
import ai.pipecat.simple_chatbot_client.ui.theme.TextStyles
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun InCallLayout(voiceClientManager: VoiceClientManager) {

    val localCam by remember { derivedStateOf { voiceClientManager.tracks.value?.local?.video } }
    val botCam by remember { derivedStateOf { voiceClientManager.tracks.value?.bot?.video } }

    Column(Modifier.fillMaxSize().imePadding()) {

        Row(
            verticalAlignment = Alignment.CenterVertically
        ) {
            val rowHeight = 64.dp

            @Composable
            fun VDivider() {
                Box(Modifier.height(64.dp).width(1.dp).background(Colors.textFieldBorder))
            }

            Box(
                modifier = Modifier
                    .weight(1f)
                    .height(rowHeight)
                    .drawBehind {
                        val level = voiceClientManager.botAudioLevel.floatValue
                        drawRect(
                            color = Color.White,
                            size = Size(width = size.width * level, height = size.height)
                        )
                    },
                contentAlignment = Alignment.CenterStart
            ) {
                Text(
                    modifier = Modifier.padding(vertical = 12.dp, horizontal = 24.dp),
                    text = voiceClientManager.state.value?.name?.uppercase() ?: "",
                    fontSize = 16.sp,
                    fontWeight = FontWeight.W700,
                    style = TextStyles.base,
                    color = Color.Black
                )
            }

            VDivider()

            MicButton(
                modifier = Modifier.size(rowHeight),
                onClick = voiceClientManager::toggleMic,
                micEnabled = voiceClientManager.mic.value,
                isTalking = voiceClientManager.userIsTalking,
                audioLevel = voiceClientManager.userAudioLevel
            )

            VDivider()

            CamButton(
                modifier = Modifier.size(rowHeight),
                onClick = voiceClientManager::toggleCamera,
                onLongClick = voiceClientManager::flipCamera,
                camEnabled = voiceClientManager.camera.value,
            )

            VDivider()

            ExitButton(
                modifier = Modifier.size(rowHeight),
                onClick = voiceClientManager::stop
            )
        }

        HDivider()

        val transportType = voiceClientManager.transportType.value
        
        if ((localCam != null || botCam != null) && transportType != null) {
            
            Row(Modifier.weight(1f)) {
                if (localCam != null) {
                    CameraView(
                        modifier = Modifier.weight(1f),
                        track = localCam,
                        transport = transportType
                    )
                }

                if (botCam != null) {
                    CameraView(
                        modifier = Modifier.weight(1f),
                        track = botCam,
                        transport = transportType
                    )
                }
            }
            
            HDivider()
        }

        InCallFooter(
            onSubmitChatText = voiceClientManager::sendText,
            chatHistory = voiceClientManager.chatHistory,
        )
    }
}
