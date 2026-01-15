package ai.pipecat.simple_chatbot_client.ui

import ai.pipecat.client.types.SendTextOptions
import ai.pipecat.simple_chatbot_client.ChatHistoryElement
import ai.pipecat.simple_chatbot_client.HDivider
import ai.pipecat.simple_chatbot_client.R
import ai.pipecat.simple_chatbot_client.ui.theme.Colors
import ai.pipecat.simple_chatbot_client.ui.theme.TextStyles
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshots.SnapshotStateList
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp


@Composable
fun ChatArea(
    modifier: Modifier,
    onSubmitChatText: (String, SendTextOptions) -> Unit,
    chatHistory: SnapshotStateList<ChatHistoryElement>
) {
    var showOptionsPopup by remember { mutableStateOf(false) }
    var sendTextOptions by remember { mutableStateOf(SendTextOptions()) }

    Column(
        modifier = modifier
    ) {
        // History

        val listState = rememberLazyListState()

        LaunchedEffect(chatHistory.size, chatHistory.lastOrNull()) {
            listState.animateScrollToItem(listState.layoutInfo.totalItemsCount)
        }

        LazyColumn(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            state = listState
        ) {
            item {
                Spacer(Modifier.height(8.dp))
            }

            items(chatHistory) { item ->

                val prefix = when (item.type) {
                    ChatHistoryElement.Type.Bot -> "Bot: "
                    ChatHistoryElement.Type.User -> "User: "
                    ChatHistoryElement.Type.Log -> ""
                }

                Text(
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 1.dp),
                    text = prefix + item.text,
                    style = TextStyles.base,
                    color = when (item.type) {
                        ChatHistoryElement.Type.Bot -> Color.Black
                        ChatHistoryElement.Type.User -> Colors.unmutedMicBackground
                        ChatHistoryElement.Type.Log -> Colors.logTextColor
                    },
                    fontSize = 14.sp
                )

                Spacer(Modifier.height(8.dp))
            }

            item {
                Spacer(Modifier.height(8.dp))
            }
        }
    }

    HDivider()

    // Text input field

    Row(
        modifier = Modifier.fillMaxWidth(),
    ) {
        val rowHeight = 64.dp

        @Composable
        fun VDivider() {
            Box(
                Modifier
                    .height(64.dp)
                    .width(1.dp)
                    .background(Colors.textFieldBorder)
            )
        }

        var chatText by remember { mutableStateOf("") }

        val submitChatText = {
            onSubmitChatText(chatText, sendTextOptions)
            chatText = ""
        }

        Box(
            modifier = Modifier
                .weight(1f)
                .height(rowHeight)
                .background(Color.White)
                .padding(vertical = 6.dp, horizontal = 12.dp)
        ) {
            BasicTextField(
                modifier = Modifier.fillMaxSize(),
                value = chatText,
                textStyle = TextStyles.base,
                onValueChange = { chatText = it },
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Text,
                    imeAction = ImeAction.Go
                ),
                keyboardActions = KeyboardActions(
                    onGo = { submitChatText() }
                ),
            )

            if (chatText.isEmpty()) {
                Text(
                    text = "Send text message...",
                    style = TextStyles.base,
                    fontSize = 14.sp,
                    color = Colors.unmutedMicBackground
                )
            }
        }

        VDivider()

        Box {
            ToolbarIconButton(
                modifier = Modifier.size(rowHeight),
                icon = R.drawable.three_dots,
                contentDescription = "More options",
            ) {
                showOptionsPopup = !showOptionsPopup
            }

            DropdownMenu(
                expanded = showOptionsPopup,
                onDismissRequest = { showOptionsPopup = false },
                containerColor = Color.White,
            ) {
                DropdownMenuItem(
                    text = {
                        Row(
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Checkbox(
                                checked = sendTextOptions.runImmediately ?: true,
                                onCheckedChange = {
                                    sendTextOptions = sendTextOptions.copy(runImmediately = it)
                                }
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = "Run Immediately",
                                style = TextStyles.base,
                                fontSize = 14.sp,
                                color = Color.Black
                            )
                        }
                    },
                    onClick = {
                        sendTextOptions = sendTextOptions.copy(
                            runImmediately = !(sendTextOptions.runImmediately ?: true)
                        )
                    }
                )

                DropdownMenuItem(
                    text = {
                        Row(
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Checkbox(
                                checked = sendTextOptions.audioResponse ?: true,
                                onCheckedChange = {
                                    sendTextOptions = sendTextOptions.copy(audioResponse = it)
                                }
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = "Audio Response",
                                style = TextStyles.base,
                                fontSize = 14.sp,
                                color = Color.Black
                            )
                        }
                    },
                    onClick = {
                        sendTextOptions = sendTextOptions.copy(
                            audioResponse = !(sendTextOptions.audioResponse ?: true)
                        )
                    }
                )
            }
        }

        VDivider()

        ToolbarIconButton(
            modifier = Modifier.size(rowHeight),
            icon = R.drawable.send,
            contentDescription = "Send",
            onClick = submitChatText
        )
    }
}

@Composable
@Preview
private fun ChatAreaPreview() {
    Column(
        Modifier
            .fillMaxWidth()
            .background(Colors.activityBackground)
    ) {
        ChatArea(Modifier.fillMaxSize(), { _, _ -> }, remember {
            mutableStateListOf(
                ChatHistoryElement(ChatHistoryElement.Type.Bot, "Bot"),
                ChatHistoryElement(ChatHistoryElement.Type.User, "User"),
                ChatHistoryElement(ChatHistoryElement.Type.Log, "Log")
            )
        })
    }
}