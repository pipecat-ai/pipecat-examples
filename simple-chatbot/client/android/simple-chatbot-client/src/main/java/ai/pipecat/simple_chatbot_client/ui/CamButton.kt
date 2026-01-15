package ai.pipecat.simple_chatbot_client.ui

import ai.pipecat.simple_chatbot_client.R
import ai.pipecat.simple_chatbot_client.ui.theme.Colors
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun CamButton(
    onClick: () -> Unit,
    onLongClick: () -> Unit,
    camEnabled: Boolean,
    modifier: Modifier,
) {
    Box(
        modifier = modifier
            .combinedClickable(
                onClick = onClick,
                onLongClick = onLongClick
            )
            .background(if (camEnabled) {
                Color.Transparent
            } else {
                Colors.mutedMicBackground
            }),
        contentAlignment = Alignment.Center
    ) {
        Icon(
            modifier = Modifier.size(36.dp),
            painter = painterResource(
                if (camEnabled) {
                    R.drawable.video
                } else {
                    R.drawable.video_off
                }
            ),
            tint = if (camEnabled) {
                Color.Black
            } else {
                Color.White
            },
            contentDescription = if (camEnabled) {
                "Turn camera off"
            } else {
                "Turn camera on"
            },
        )
    }
}

@Composable
@Preview
fun PreviewCamButton() {
    CamButton(
        onClick = {},
        onLongClick = {},
        camEnabled = true,
        modifier = Modifier,
    )
}

@Composable
@Preview
fun PreviewCamButtonMuted() {
    CamButton(
        onClick = {},
        onLongClick = {},
        camEnabled = false,
        modifier = Modifier,
    )
}