package ai.pipecat.simple_chatbot_client.ui

import ai.pipecat.simple_chatbot_client.R
import androidx.compose.foundation.clickable
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

@Composable
fun ExitButton(
    onClick: () -> Unit,
    modifier: Modifier,
) {
    Box(
        modifier = modifier.clickable(onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        Icon(
            modifier = Modifier.size(36.dp),
            painter = painterResource(R.drawable.exit_run),
            tint = Color.Black,
            contentDescription = "End call",
        )
    }
}

@Composable
@Preview
fun PreviewExitButton() {
    ExitButton(
        onClick = {},
        modifier = Modifier,
    )
}
