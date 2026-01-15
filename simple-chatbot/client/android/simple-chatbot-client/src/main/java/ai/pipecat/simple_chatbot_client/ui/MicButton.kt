package ai.pipecat.simple_chatbot_client.ui

import ai.pipecat.simple_chatbot_client.R
import ai.pipecat.simple_chatbot_client.ui.theme.Colors
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.runtime.FloatState
import androidx.compose.runtime.State
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp

@Composable
fun MicButton(
    onClick: () -> Unit,
    micEnabled: Boolean,
    modifier: Modifier,
    isTalking: State<Boolean>,
    audioLevel: FloatState,
) {
    Box(
        modifier = modifier
            .clickable(onClick = onClick)
            .drawBehind {
                if (micEnabled) {
                    val level = audioLevel.floatValue
                    val height = size.height * level

                    drawRect(
                        color = Color.White,
                        topLeft = Offset(0f, size.height - height),
                        size = Size(size.width, height)
                    )
                }
            },
        contentAlignment = Alignment.Center
    ) {
        Icon(
            modifier = Modifier.size(36.dp),
            painter = painterResource(
                if (micEnabled) {
                    R.drawable.microphone
                } else {
                    R.drawable.microphone_off
                }
            ),
            tint = if (!micEnabled) {
                Colors.mutedMicBackground
            } else if (isTalking.value) {
                Colors.micActive
            } else {
                Color.Black
            },
            contentDescription = if (micEnabled) {
                "Mute microphone"
            } else {
                "Unmute microphone"
            },
        )
    }
}

@Composable
@Preview
fun PreviewMicButton() {
    MicButton(
        onClick = {},
        micEnabled = true,
        modifier = Modifier,
        isTalking = remember { mutableStateOf(false) },
        audioLevel = remember { mutableFloatStateOf(0.0f) }
    )
}

@Composable
@Preview
fun PreviewMicButtonActive() {
    MicButton(
        onClick = {},
        micEnabled = true,
        modifier = Modifier,
        isTalking = remember { mutableStateOf(true) },
        audioLevel = remember { mutableFloatStateOf(0.5f) }
    )
}

@Composable
@Preview
fun PreviewMicButtonMuted() {
    MicButton(
        onClick = {},
        micEnabled = false,
        modifier = Modifier,
        isTalking = remember { mutableStateOf(false) },
        audioLevel = remember { mutableFloatStateOf(0.0f) }
    )
}