package ai.pipecat.simple_chatbot_client

import ai.pipecat.client.PipecatClient
import ai.pipecat.client.PipecatClientOptions
import ai.pipecat.client.PipecatEventCallbacks
import ai.pipecat.client.daily.DailyTransport
import ai.pipecat.client.daily.DailyTransportConnectParams
import ai.pipecat.client.daily.PipecatClientDaily
import ai.pipecat.client.result.Future
import ai.pipecat.client.result.RTVIError
import ai.pipecat.client.types.APIRequest
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
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.Stable
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.snapshots.SnapshotStateList

@Immutable
data class Error(val message: String)

@Stable
class VoiceClientManager(private val context: Context) {

    companion object {
        private const val TAG = "VoiceClientManager"
    }

    private val client = mutableStateOf<PipecatClientDaily?>(null)

    val state = mutableStateOf<TransportState?>(null)

    val errors = mutableStateListOf<Error>()

    val botReady = mutableStateOf(false)
    val botIsTalking = mutableStateOf(false)
    val userIsTalking = mutableStateOf(false)
    val botAudioLevel = mutableFloatStateOf(0f)
    val userAudioLevel = mutableFloatStateOf(0f)

    val mic = mutableStateOf(false)
    val camera = mutableStateOf(false)
    val tracks = mutableStateOf<Tracks?>(null)

    val chatHistory = SnapshotStateList<ChatHistoryElement>()

    private fun <E> Future<E, RTVIError>.displayErrors() = withErrorCallback {
        Log.e(TAG, "Future resolved with error: ${it.description}", it.exception)
        errors.add(Error(it.description))
    }

    fun start(baseUrl: String) {

        if (client.value != null) {
            return
        }

        chatHistory.clear()

        val url = if (baseUrl.endsWith("/")) {
            baseUrl
        } else {
            "$baseUrl/"
        } + "start"

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

            override fun onBotTranscript(text: String) {
                Log.i(TAG, "Bot transcript: $text")
                chatHistory.appendOrUpdateBot(text)
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

        val client = PipecatClient(DailyTransport(context), options)

        client.startBotAndConnect(
            APIRequest(
                endpoint = url,
                requestData = Value.Object()
            )
        ).displayErrors().withErrorCallback {
            callbacks.onDisconnected()
        }

        this.client.value = client
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