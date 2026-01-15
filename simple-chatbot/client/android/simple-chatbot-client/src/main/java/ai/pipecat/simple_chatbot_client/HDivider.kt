package ai.pipecat.simple_chatbot_client

import ai.pipecat.simple_chatbot_client.ui.theme.Colors
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun HDivider() {
    Box(Modifier.fillMaxWidth().height(1.dp).background(Colors.textFieldBorder))
}