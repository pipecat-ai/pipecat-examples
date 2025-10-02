package ai.pipecat.simple_chatbot_client

import androidx.compose.runtime.snapshots.SnapshotStateList

data class ChatHistoryElement(
    val type: Type,
    val text: String,
) {
    enum class Type {
        Bot,
        User,
        Log
    }
}

fun SnapshotStateList<ChatHistoryElement>.append(
    type: ChatHistoryElement.Type,
    text: String
) {
    add(ChatHistoryElement(type, text.trim()))
}

fun SnapshotStateList<ChatHistoryElement>.appendOrUpdate(
    type: ChatHistoryElement.Type,
    text: String
) {
    val last = lastOrNull()
    if (last != null && last.type == type) {
        removeAt(lastIndex)
        add(ChatHistoryElement(type, last.text + " " + text.trim()))

    } else {
        add(ChatHistoryElement(type, text.trim()))
    }
}

fun SnapshotStateList<ChatHistoryElement>.appendLog(text: String) {
    append(ChatHistoryElement.Type.Log, text)
}

fun SnapshotStateList<ChatHistoryElement>.appendOrUpdateUser(text: String) {
    appendOrUpdate(ChatHistoryElement.Type.User, text)
}

fun SnapshotStateList<ChatHistoryElement>.appendOrUpdateBot(text: String) {
    appendOrUpdate(ChatHistoryElement.Type.Bot, text)
}