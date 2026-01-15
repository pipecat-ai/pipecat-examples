package ai.pipecat.simple_chatbot_client.ui

import ai.pipecat.client.types.SendTextOptions
import ai.pipecat.simple_chatbot_client.ChatHistoryElement
import ai.pipecat.simple_chatbot_client.R
import ai.pipecat.simple_chatbot_client.ui.theme.Colors
import ai.pipecat.simple_chatbot_client.ui.theme.TextStyles
import ai.pipecat.simple_chatbot_client.ui.theme.TextStyles.base
import ai.pipecat.simple_chatbot_client.ui.theme.textFieldColors
import androidx.annotation.DrawableRes
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
private fun FooterButton(
    modifier: Modifier,
    onClick: () -> Unit,
    @DrawableRes icon: Int,
    text: String? = null,
    foreground: Color,
    background: Color,
    border: Color,
) {
    val shape = RoundedCornerShape(12.dp)

    Row(
        modifier
            .border(1.dp, border, shape)
            .clip(shape)
            .background(background)
            .clickable(onClick = onClick)
            .padding(vertical = 10.dp, horizontal = 18.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center
    ) {
        Icon(
            modifier = Modifier.size(24.dp),
            painter = painterResource(icon),
            tint = foreground,
            contentDescription = null
        )

        if (text != null) {
            Spacer(modifier = Modifier.width(8.dp))

            Text(
                text = text,
                style = TextStyles.base,
                fontSize = 14.sp,
                fontWeight = FontWeight.W600,
                color = foreground
            )
        }
    }
}


@Composable
fun ColumnScope.InCallFooter(
    onClickEnd: () -> Unit,
    onSubmitChatText: (String, SendTextOptions) -> Unit,
    chatHistory: SnapshotStateList<ChatHistoryElement>
) {
    var showOptionsPopup by remember { mutableStateOf(false) }
    var sendTextOptions by remember { mutableStateOf(SendTextOptions()) }

    // Chat history

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(90.dp)
            .padding(horizontal = 15.dp),
    ) {
        val listState = rememberLazyListState()

        LaunchedEffect(chatHistory.size, chatHistory.lastOrNull()) {
            listState.animateScrollToItem(listState.layoutInfo.totalItemsCount)
        }

        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .shadow(4.dp, RoundedCornerShape(12.dp))
                .clip(RoundedCornerShape(12.dp))
                .background(Colors.botIndicatorBackground)
                .border(5.dp, Color.White, RoundedCornerShape(12.dp)),
            state = listState
        ) {
            item {
                Spacer(Modifier.height(8.dp))
            }

            items(chatHistory) { item ->
                Text(
                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 1.dp),
                    text = item.text,
                    style = base,
                    color = when (item.type) {
                        ChatHistoryElement.Type.Bot -> Colors.activityBackground
                        ChatHistoryElement.Type.User -> Colors.lightGrey
                        ChatHistoryElement.Type.Log -> Colors.logTextColor
                    },
                    fontSize = 12.sp
                )
            }

            item {
                Spacer(Modifier.height(8.dp))
            }
        }
    }

    Spacer(Modifier.height(15.dp))

    // Text input field

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 15.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        var chatText by remember { mutableStateOf("") }

        val submitChatText = {
            onSubmitChatText(chatText, sendTextOptions)
            chatText = ""
        }

        TextField(
            modifier = Modifier
                .weight(1f)
                .border(1.dp, Colors.textFieldBorder, RoundedCornerShape(12.dp)),
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
            placeholder = {
                Text("Send text message...")
            },
            colors = textFieldColors(),
            shape = RoundedCornerShape(12.dp),
        )

        Spacer(Modifier.width(8.dp))

        Box {
            FooterButton(
                modifier = Modifier,
                onClick = { showOptionsPopup = !showOptionsPopup },
                icon = R.drawable.three_dots,
                text = null,
                foreground = Color.White,
                background = Colors.endButton,
                border = Colors.endButton
            )
            
            DropdownMenu(
                expanded = showOptionsPopup,
                onDismissRequest = { showOptionsPopup = false },
                modifier = Modifier.padding(PaddingValues(end = 16.dp)),
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

        Spacer(Modifier.width(8.dp))

        FooterButton(
            modifier = Modifier,
            onClick = submitChatText,
            icon = R.drawable.send,
            text = null,
            foreground = Color.White,
            background = Colors.endButton,
            border = Colors.endButton
        )
    }


    // End button

    Row(Modifier
        .fillMaxWidth(0.5f)
        .padding(15.dp)
        .align(Alignment.CenterHorizontally)
    ) {
        FooterButton(
            modifier = Modifier.weight(1f),
            onClick = onClickEnd,
            icon = R.drawable.phone_hangup,
            text = "End",
            foreground = Color.White,
            background = Colors.endButton,
            border = Colors.endButton
        )
    }
}

@Composable
@Preview
private fun InCallFooterPreview() {
    Column(
        Modifier
            .fillMaxWidth()
            .background(Colors.activityBackground)
    ) {
        InCallFooter({}, { _, _ -> }, remember { mutableStateListOf(
            ChatHistoryElement(ChatHistoryElement.Type.Bot, "Bot"),
            ChatHistoryElement(ChatHistoryElement.Type.User, "User"),
            ChatHistoryElement(ChatHistoryElement.Type.Log, "Log")
        ) })
    }
}