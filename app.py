from flask import Flask, render_template, request, jsonify
import pyaudio
import asyncio
import websockets
import os
import json
import threading
import janus
import queue
import sys
import requests
import time
from dotenv import load_dotenv

app = Flask(__name__)

# Load environment variables from .env file
load_dotenv()

# Your Deepgram Voice Agent URL
VOICE_AGENT_URL = "wss://agent.deepgram.com/agent"
# Groq API endpoint for chat completions
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Your Agent prompt
PROMPT = "You are a conversational assistant named Droc from DigiRocket Technologies and you are expert in digital marketing domain. Your response must be limited to 20 words"

# Your Deepgram TTS model
VOICE = "aura-asteria-en"
# Your Deepgram STT model
LISTEN = "nova-2"
# Mistral 7B model from Groq
LLM_MODEL = "llama-3.1-8b-instant"

# Get API keys from .env file
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

USER_AUDIO_SAMPLE_RATE = 16000
USER_AUDIO_SECS_PER_CHUNK = 0.05
USER_AUDIO_SAMPLES_PER_CHUNK = round(USER_AUDIO_SAMPLE_RATE * USER_AUDIO_SECS_PER_CHUNK)

AGENT_AUDIO_SAMPLE_RATE = 16000
AGENT_AUDIO_BYTES_PER_SEC = 2 * AGENT_AUDIO_SAMPLE_RATE

SETTINGS = {
    "type": "SettingsConfiguration",
    "audio": {
        "input": {
            "encoding": "linear16",
            "sample_rate": USER_AUDIO_SAMPLE_RATE,
        },
        "output": {
            "encoding": "linear16",
            "sample_rate": AGENT_AUDIO_SAMPLE_RATE,
            "container": "none",
        },
    },
    "agent": {
        "listen": {
            "model": LISTEN
        },
        "think": {
            "provider": {
              "type": "custom",
              "url": GROQ_URL,
              "headers": [
                {
                  "key": "Authorization",
                  "value": f"Bearer {GROQ_API_KEY}"
                }
              ]
            },
            "model": LLM_MODEL,
            "instructions": PROMPT,
        },
        "speak": {
            "model": VOICE
        },
    },
    "context": {
        "messages": [], # LLM message history (e.g. to restore existing conversation if websocket connection breaks)
        "replay": False # whether to replay the last message, if it is an assistant message
    }
}

# Echo Cancellation implementation from the first code
class EchoCancellation:
    def __init__(self):
        self.is_speaking = False
        self.buffer_duration = 10.0  # Buffer duration in seconds after TTS stops
        self.lock = threading.Lock()
        self.speaking_until = 0

    def mark_speaking_started(self):
        with self.lock:
            self.is_speaking = True

    def mark_speaking_ended(self):
        with self.lock:
            # Keep is_speaking True for buffer_duration seconds to account for audio delay
            self.speaking_until = time.time() + self.buffer_duration
            threading.Timer(self.buffer_duration, self._reset_speaking).start()

    def _reset_speaking(self):
        with self.lock:
            if time.time() >= self.speaking_until:
                self.is_speaking = False

    def should_process_audio(self):
        with self.lock:
            return not self.is_speaking

# Create a global echo_cancellation instance
echo_cancellation = EchoCancellation()

# Modified microphone queue with echo cancellation filtering
mic_audio_queue = asyncio.Queue()

# Global flag to stop the conversation
stop_flag = threading.Event()

def callback(input_data, frame_count, time_info, status_flag):
    # Only add audio to the queue if we're not currently speaking
    if echo_cancellation.should_process_audio():
        mic_audio_queue.put_nowait(input_data)
    return (input_data, pyaudio.paContinue)

async def run():
    if not DEEPGRAM_API_KEY:
        print("DEEPGRAM_API_KEY not found in .env file")
        return

    if not GROQ_API_KEY:
        print("GROQ_API_KEY not found in .env file")
        return

    async with websockets.connect(
        VOICE_AGENT_URL,
        additional_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
    ) as ws:

        async def microphone():
            audio = pyaudio.PyAudio()
            stream = audio.open(
                format=pyaudio.paInt16,
                rate=USER_AUDIO_SAMPLE_RATE,
                input=True,
                frames_per_buffer=USER_AUDIO_SAMPLES_PER_CHUNK,
                stream_callback=callback,
                channels=1
            )

            stream.start_stream()

            while stream.is_active() and not stop_flag.is_set():
                await asyncio.sleep(0.1)

            stream.stop_stream()
            stream.close()

        async def sender(ws):
            await ws.send(json.dumps(SETTINGS))

            try:
                while not stop_flag.is_set():
                    data = await mic_audio_queue.get()
                    await ws.send(data)

            except Exception as e:
                print("Error while sending: " + str(e))
                raise

        async def receiver(ws):
            try:
                speaker = Speaker()
                with speaker:
                    async for message in ws:
                        if stop_flag.is_set():
                            break
                        if type(message) is str:
                            message_data = json.loads(message)
                            print(message)

                            if message_data["type"] == "UserStartedSpeaking":
                                speaker.stop()
                            # Add support for tracking agent's speaking state
                            elif message_data["type"] == "AgentStartedSpeaking":
                                echo_cancellation.mark_speaking_started()
                            elif message_data["type"] == "AgentFinishedSpeaking":
                                echo_cancellation.mark_speaking_ended()

                        elif type(message) is bytes:
                            await speaker.play(message)

            except Exception as e:
                print(e)

        await asyncio.wait(
            [
                asyncio.ensure_future(microphone()),
                asyncio.ensure_future(sender(ws)),
                asyncio.ensure_future(receiver(ws)),
            ]
        )

def _play(audio_out, stream, stop):
    while not stop.is_set():
        try:
            data = audio_out.sync_q.get(True, 0.05)
            stream.write(data)
        except queue.Empty:
            pass

class Speaker:
    def __init__(self):
        self._queue = None
        self._stream = None
        self._thread = None
        self._stop = None

    def __enter__(self):
        audio = pyaudio.PyAudio()
        self._stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=AGENT_AUDIO_SAMPLE_RATE,
            input=False,
            output=True,
        )
        self._queue = janus.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=_play, args=(self._queue, self._stream, self._stop), daemon=True
        )
        self._thread.start()

    def __exit__(self, exc_type, exc_value, traceback):
        self._stop.set()
        self._thread.join()
        self._stream.close()
        self._stream = None
        self._queue = None
        self._thread = None
        self._stop = None

    async def play(self, data):
        # Mark that the agent is speaking when audio is being played
        echo_cancellation.mark_speaking_started()
        return await self._queue.async_q.put(data)

    def stop(self):
        # Mark that the agent has finished speaking when stopping audio output
        echo_cancellation.mark_speaking_ended()
        if self._queue and self._queue.async_q:
            while not self._queue.async_q.empty():
                try:
                    self._queue.async_q.get_nowait()
                except janus.QueueEmpty:
                    break

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start():
    stop_flag.clear()
    asyncio.run(run())
    return jsonify({"status": "started"})

@app.route('/stop', methods=['POST'])
def stop():
    stop_flag.set()
    return jsonify({"status": "stopped"})

if __name__ == '__main__':
    app.run(debug=True)
