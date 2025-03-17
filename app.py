import streamlit as st
from deepgram import DeepgramClient, DeepgramClientOptions, AgentWebSocketEvents, SettingsConfigurationOptions
from deepgram.utils import verboselogs

# Global variables to control state
warning_notice = True
assistant_speaking = False

# Streamlit UI
st.title("Deepgram Voice Conversation")
st.write("Talk into your microphone to begin the conversation. You can interrupt the assistant at any time by speaking while it's talking.")

# Placeholder for displaying conversation text
conversation_placeholder = st.empty()

def main():
    global warning_notice, assistant_speaking

    try:
        # Client configuration with echo cancellation and barge-in enabled
        config = DeepgramClientOptions(
            options={
                "keepalive": "true",
                "microphone_record": "true",
                "speaker_playback": "true",
                "speaker_channels": "2",
                "echo_cancellation": "true",
                "noise_suppression": "true",
                "auto_gain_control": "true",
                "vad_level": "2",
                "barge_in_enabled": "true",
                "microphone_always_on": "true",
            },
        )

        # Create Deepgram client with your API key
        deepgram = DeepgramClient("YOUR_DEEPGRAM_API_KEY", config)

        # Create a websocket connection to Deepgram
        dg_connection = deepgram.agent.websocket.v("1")

        # Event handlers
        def on_open(self, open, **kwargs):
            st.write("Connection established. Speak to begin conversation...")

        def on_binary_data(self, data, **kwargs):
            global warning_notice
            if warning_notice:
                st.write("Received binary audio data")
                warning_notice = False

        def on_welcome(self, welcome, **kwargs):
            st.write(f"{welcome}")

        def on_settings_applied(self, settings_applied, **kwargs):
            st.write("Settings successfully applied. Ready for conversation.")
            st.write("👉 You can interrupt the assistant at any time by speaking while it's talking.")

        def on_conversation_text(self, conversation_text, **kwargs):
            try:
                if hasattr(conversation_text, 'role') and hasattr(conversation_text, 'content'):
                    role = conversation_text.role
                    content = conversation_text.content

                    if role == "user":
                        conversation_placeholder.write(f"👤 You: {content}")
                    elif role == "assistant":
                        conversation_placeholder.write(f"🤖 Assistant: {content}")
                    else:
                        conversation_placeholder.write(f"{role}: {content}")
                else:
                    conversation_placeholder.write(f"Conversation Text: {conversation_text}")
            except Exception as e:
                st.write(f"Error handling conversation text: {e}")
                conversation_placeholder.write(f"Raw conversation text: {conversation_text}")

        def on_user_started_speaking(self, user_started_speaking, **kwargs):
            global assistant_speaking

            if assistant_speaking:
                st.write("✋ You interrupted the assistant...")
                dg_connection.interrupt()
                assistant_speaking = False
            else:
                st.write("🎤 Listening...")

        def on_agent_thinking(self, agent_thinking, **kwargs):
            st.write("💭 Assistant is thinking...")

        def on_function_calling(self, function_calling, **kwargs):
            st.write(f"{function_calling}")

        def on_agent_started_speaking(self, agent_started_speaking, **kwargs):
            global assistant_speaking
            assistant_speaking = True
            st.write("🔊 Assistant is speaking...")

        def on_agent_audio_done(self, agent_audio_done, **kwargs):
            global assistant_speaking
            assistant_speaking = False
            st.write("✅ Assistant finished speaking.")

        def on_close(self, close, **kwargs):
            st.write(f"{close}")
            st.write("Connection closed.")

        def on_error(self, error, **kwargs):
            st.write(f"❌ Error: {error}")

        def on_interruption(self, interruption, **kwargs):
            st.write("⚡ Assistant was interrupted!")

        def on_end_of_thought(self, end_of_thought, **kwargs):
            st.write("💡 Assistant finished thinking and is preparing response...")

        def on_unhandled(self, unhandled, **kwargs):
            if hasattr(unhandled, 'raw') and isinstance(unhandled.raw, str) and "EndOfThought" in unhandled.raw:
                st.write("💡 Assistant finished thinking and is preparing response...")
            elif isinstance(unhandled, dict) and "raw" in unhandled and "EndOfThought" in unhandled["raw"]:
                st.write("💡 Assistant finished thinking and is preparing response...")
            elif hasattr(unhandled, 'raw') and isinstance(unhandled.raw, str) and "Interruption" in unhandled.raw:
                st.write("⚡ Assistant was interrupted!")
            elif isinstance(unhandled, dict) and "raw" in unhandled and "Interruption" in unhandled["raw"]:
                st.write("⚡ Assistant was interrupted!")
            else:
                st.write(f"Unknown event: {unhandled}")

        # Register event handlers
        dg_connection.on(AgentWebSocketEvents.Open, on_open)
        dg_connection.on(AgentWebSocketEvents.AudioData, on_binary_data)
        dg_connection.on(AgentWebSocketEvents.Welcome, on_welcome)
        dg_connection.on(AgentWebSocketEvents.SettingsApplied, on_settings_applied)
        dg_connection.on(AgentWebSocketEvents.ConversationText, on_conversation_text)
        dg_connection.on(AgentWebSocketEvents.UserStartedSpeaking, on_user_started_speaking)
        dg_connection.on(AgentWebSocketEvents.AgentThinking, on_agent_thinking)
        dg_connection.on(AgentWebSocketEvents.FunctionCalling, on_function_calling)
        dg_connection.on(AgentWebSocketEvents.AgentStartedSpeaking, on_agent_started_speaking)
        dg_connection.on(AgentWebSocketEvents.AgentAudioDone, on_agent_audio_done)
        dg_connection.on(AgentWebSocketEvents.Close, on_close)
        dg_connection.on(AgentWebSocketEvents.Error, on_error)
        dg_connection.on(AgentWebSocketEvents.Unhandled, on_unhandled)

        if hasattr(AgentWebSocketEvents, 'EndOfThought'):
            dg_connection.on(AgentWebSocketEvents.EndOfThought, on_end_of_thought)
        else:
            dg_connection.on("EndOfThought", on_end_of_thought)

        if hasattr(AgentWebSocketEvents, 'Interruption'):
            dg_connection.on(AgentWebSocketEvents.Interruption, on_interruption)
        else:
            dg_connection.on("Interruption", on_interruption)

        # Configure settings for the conversation
        options = SettingsConfigurationOptions()
        options.agent.think.provider.type = "open_ai"
        options.agent.think.model = "gpt-4o-mini"
        options.agent.think.instructions = """
        You are a sales executive at DigiRocket Technologies, specializing in website optimization and digital marketing. You aim to collect the customer’s email by offering a free website audit report and scheduling a consultation. The conversation should not end until the user provides their email or explicitly refuses multiple times. Answers should not be more than 20 words. Use more filler words in between the conversation to make the conversation more realistic and natural, and have context awareness. And remember to get the customer email id. Take the location and time zone of Dover, United States.
        """
        options.agent.speak.voice = "nova"
        options.agent.speak.rate = 1.0
        options.agent.barge_in = True
        options.transcription = {
            "model": "nova-2",
            "smart_format": True,
            "diarize": True,
            "language": "en",
            "punctuate": True,
        }

        # Start the connection
        if dg_connection.start(options) is False:
            st.write("Failed to start connection")
            return

        st.write("==== Deepgram Voice Conversation Started ====")
        st.write("Talk into your microphone to begin conversation")
        st.write("You can interrupt the assistant at any time by speaking while it's talking")
        st.write("Press the 'Stop' button to end the session.")

        # Button to stop the conversation
        if st.button("Stop", key="stop_button", help="Click to stop the conversation"):
            dg_connection.finish()
            st.write("Session finished. Thank you for using Deepgram Voice Conversation!")

    except ValueError as e:
        st.write(f"Invalid value encountered: {e}")
    except Exception as e:
        st.write(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
