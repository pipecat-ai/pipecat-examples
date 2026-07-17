package ai.pipecat.simple_chatbot_client

import ai.pipecat.client.PipecatClient
import ai.pipecat.client.PipecatClientOptions
import ai.pipecat.client.PipecatEventCallbacks
import ai.pipecat.client.daily.DailyTransport
import ai.pipecat.client.result.Future
import ai.pipecat.client.result.RTVIError
import ai.pipecat.client.small_webrtc_transport.SmallWebRTCTransport
import ai.pipecat.client.types.APIRequest
import ai.pipecat.client.types.BotOutputData
import ai.pipecat.client.types.BotReadyData
import ai.pipecat.client.types.Participant
import ai.pipecat.client.types.PipecatMetrics
import ai.pipecat.client.types.SendTextOptions
import ai.pipecat.client.types.Tracks
import ai.pipecat.client.types.Transcript
import ai.pipecat.client.types.TransportState
import ai.pipecat.client.types.Value
import android.content.Context
import android.util.Log
import androidx.annotation.DrawableRes
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.Stable
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.snapshots.SnapshotStateList

@Immutable
data class Error(val message: String)

data class ClientStartParams(
    val backendUrl: String,
    val apiKey: String
)

enum class TransportType(val label: String, @DrawableRes val icon: Int) {
    Daily("Daily", R.drawable.daily_logo),
    SmallWebrtc("Small WebRTC", R.drawable.webrtc_logo);

    override fun toString() = label

    companion object {
        fun fromString(value: String): TransportType? {
            return when (value) {
                Daily.label -> Daily
                SmallWebrtc.label -> SmallWebrtc
                else -> null
            }
        }
    }
}

@Stable
class VoiceClientManager(private val context: Context) {

    companion object {
        private const val TAG = "VoiceClientManager"
    }

    /**
     * One bot-output segment (typically a sentence) in the bot's current
     * message. [spokenText] tracks how much of it TTS has spoken so far.
     */
    private data class BotSegment(
        val id: Int?,
        val fullText: String,
        var spokenText: String = "",
    )

    private val botSegments = mutableListOf<BotSegment>()

    private val client = mutableStateOf<PipecatClient<*, *>?>(null)

    val state = mutableStateOf<TransportState?>(null)

    val errors = mutableStateListOf<Error>()

    val botReady = mutableStateOf(false)
    val botIsTalking = mutableStateOf(false)
    val userIsTalking = mutableStateOf(false)
    val botAudioLevel = mutableFloatStateOf(0f)
    val userAudioLevel = mutableFloatStateOf(0f)

    val transportType = mutableStateOf<TransportType?>(null)
    val mic = mutableStateOf(false)
    val camera = mutableStateOf(false)
    val tracks = mutableStateOf<Tracks?>(null)

    val chatHistory = SnapshotStateList<ChatHistoryElement>()

    private fun <E> Future<E, RTVIError>.displayErrors() = withErrorCallback {
        Log.e(TAG, "Future resolved with error: ${it.description}", it.exception)
        errors.add(Error(it.description))
    }

    fun start(
        transportType: TransportType,
        params: ClientStartParams,
    ) {
        if (client.value != null) {
            return
        }

        chatHistory.clear()
        botSegments.clear()
        this.transportType.value = transportType

        state.value = TransportState.Disconnected

        val callbacks = object : PipecatEventCallbacks() {
            override fun onTransportStateChanged(state: TransportState) {
                this@VoiceClientManager.state.value = state
            }

            override fun onBackendError(message: String) {
                "Error from backend: $message".let {
                    Log.e(TAG, it)
                    errors.add(Error(it))
                    chatHistory.appendLog(it)
                }
            }

            override fun onServerMessage(data: Value) {
                Log.i(TAG, "onServerMessage: $data")
            }

            override fun onBotReady(data: BotReadyData) {

                Log.i(TAG, "Bot ready. Version ${data.version}")

                botReady.value = true
                chatHistory.appendLog("Bot is ready")
            }

            override fun onMetrics(data: PipecatMetrics) {
                Log.i(TAG, "Bot metrics: $data")
            }

            override fun onUserTranscript(data: Transcript) {
                Log.i(TAG, "User transcript: $data")
                if (data.final) {
                    chatHistory.appendOrUpdateUser(data.text)
                }
            }

            override fun onBotOutput(data: BotOutputData) {
                Log.d(TAG, "Bot output: $data")

                when {
                    // A new segment was announced (or is display-only text). This is
                    // the only event which carries the segment's text for the first
                    // time; later events for the same segmentId just track progress.
                    data.willBeSpoken == false ||
                        data.spokenStatus == BotOutputData.SpokenStatus.New -> {

                        if (chatHistory.lastOrNull()?.type != ChatHistoryElement.Type.Bot) {
                            botSegments.clear()
                        }
                        botSegments.add(
                            BotSegment(
                                id = data.segmentId,
                                fullText = data.text,
                                spokenText = if (data.willBeSpoken == false) data.text else ""
                            )
                        )
                    }

                    // TTS is speaking this segment: reveal the spoken prefix
                    data.spokenStatus == BotOutputData.SpokenStatus.InProgress -> {
                        botSegments.find { it.id == data.segmentId }?.spokenText =
                            data.spokenProgress?.accumulatedText ?: ""
                    }

                    data.spokenStatus == BotOutputData.SpokenStatus.Completed -> {
                        botSegments.find { it.id == data.segmentId }
                            ?.let { it.spokenText = it.fullText }
                    }

                    // Legacy bots (RTVI protocol 1.4.x, no spokenStatus) send
                    // word-aggregated text as it is spoken
                    data.aggregatedBy == "word" -> {
                        chatHistory.appendOrUpdateBot(data.text)
                        return
                    }

                    else -> return
                }

                renderBotMessage()
            }

            override fun onBotStartedSpeaking() {
                Log.i(TAG, "Bot started speaking")
                botIsTalking.value = true
            }

            override fun onBotStoppedSpeaking() {
                Log.i(TAG, "Bot stopped speaking")
                botIsTalking.value = false
            }

            override fun onUserStartedSpeaking() {
                Log.i(TAG, "User started speaking")
                userIsTalking.value = true
            }

            override fun onUserStoppedSpeaking() {
                Log.i(TAG, "User stopped speaking")
                userIsTalking.value = false
            }

            override fun onTracksUpdated(tracks: Tracks) {
                this@VoiceClientManager.tracks.value = tracks
            }

            override fun onInputsUpdated(camera: Boolean, mic: Boolean) {
                this@VoiceClientManager.camera.value = camera
                this@VoiceClientManager.mic.value = mic
            }

            override fun onDisconnected() {
                chatHistory.appendLog("Disconnected")

                botIsTalking.value = false
                userIsTalking.value = false
                state.value = null
                botReady.value = false
                tracks.value = null

                client.value?.release()
                client.value = null
            }

            override fun onUserAudioLevel(level: Float) {
                userAudioLevel.floatValue = level
            }

            override fun onRemoteAudioLevel(level: Float, participant: Participant) {
                botAudioLevel.floatValue = level
            }

            override fun onConnected() {
                Log.i(TAG, "Connected")
            }

            override fun onBotConnected(participant: Participant) {
                Log.i(TAG, "Bot connected: $participant")
            }

            override fun onBotDisconnected(participant: Participant) {
                Log.i(TAG, "Bot disconnected: $participant")
            }

            override fun onParticipantJoined(participant: Participant) {
                Log.i(TAG, "Participant joined: $participant")
            }

            override fun onParticipantLeft(participant: Participant) {
                Log.i(TAG, "Participant left: $participant")
            }
        }

        val options = PipecatClientOptions(
            callbacks = callbacks
        )

        val transport = when (transportType) {
            TransportType.Daily -> DailyTransport(context)
            TransportType.SmallWebrtc -> SmallWebRTCTransport(context)
        }

        val client = PipecatClient(transport, options)

        client.startBotAndConnect(
            APIRequest(
                endpoint = params.backendUrl,
                // Pipecat Cloud uses the /start request body to decide how to run the
                // bot: without these fields it neither creates a Daily room nor waits
                // for a WebRTC offer. Self-hosted runners ignore unknown fields.
                requestData = when (transportType) {
                    TransportType.Daily -> Value.Object(
                        "transport" to Value.Str("daily"),
                        "createDailyRoom" to Value.Bool(true),
                    )
                    TransportType.SmallWebrtc -> Value.Object(
                        "transport" to Value.Str("webrtc"),
                        "enableDefaultIceServers" to Value.Bool(true),
                    )
                },
                headers = listOfNotNull(
                    params.apiKey.trim().takeIf { it.isNotEmpty() }?.let {"Authorization" to "Bearer $it"}
                ).toMap()
            )
        ).displayErrors().withErrorCallback {
            callbacks.onDisconnected()
        }

        this.client.value = client
    }

    private fun renderBotMessage() {
        val text = botSegments
            .map { it.spokenText.trim() }
            .filter { it.isNotEmpty() }
            .joinToString(" ")

        if (text.isNotEmpty()) {
            chatHistory.setOrAddLastBot(text)
        }
    }

    fun enableCamera(enabled: Boolean) {
        client.value?.enableCam(enabled)?.displayErrors()
    }

    fun enableMic(enabled: Boolean) {
        client.value?.enableMic(enabled)?.displayErrors()
    }

    fun toggleCamera() = enableCamera(!camera.value)
    fun toggleMic() = enableMic(!mic.value)

    fun flipCamera() {
        client.value?.let { pipecatClient ->
            val currentCam = pipecatClient.selectedCam?.id
            pipecatClient.getAllCams().withCallback { result ->
                val newCam = result.valueOrNull?.filterNot { it.id == currentCam }?.firstOrNull()
                newCam?.let { pipecatClient.updateCam(it.id) }
            }
        }
    }

    fun stop() {
        client.value?.disconnect()?.displayErrors()
    }

    fun sendText(text: String, options: SendTextOptions = SendTextOptions()) {
        chatHistory.appendOrUpdateUser(text)
        client.value?.sendText(text, options)
    }
}