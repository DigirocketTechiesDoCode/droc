from deepgram.utils import verboselogs
 
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    AgentWebSocketEvents,
    SettingsConfigurationOptions,
)
 
def main():
    # Global variables to control state
    global warning_notice, assistant_speaking
    warning_notice = True
    assistant_speaking = False
   
    try:
        # Client configuration with echo cancellation and barge-in enabled
        config: DeepgramClientOptions = DeepgramClientOptions(
            options={
                "keepalive": "true",
                "microphone_record": "true",
                "speaker_playback": "true",
                "speaker_channels": "2",               # Stereo audio output
                "echo_cancellation": "true",           # Enable echo cancellation
                "noise_suppression": "true",           # Enable noise suppression
                "auto_gain_control": "true",           # Enable automatic gain control
                "vad_level": "2",                      # Voice activity detection sensitivity (0-3)
                "barge_in_enabled": "true",            # Enable interruptions/barge-in
                "microphone_always_on": "true",        # Keep microphone on even when assistant is speaking
            },
            # verbose=verboselogs.DEBUG,               # Uncomment for debugging
        )
       
        # Create Deepgram client with your API key
        deepgram: DeepgramClient = DeepgramClient("14164fef1f66a406e3fdd80b27a7c74d9a14187b", config)
 
        # Create a websocket connection to Deepgram
        dg_connection = deepgram.agent.websocket.v("1")
 
        # Event handlers
        def on_open(self, open, **kwargs):
            print(f"\n\n{open}\n\n")
            print("Connection established. Speak to begin conversation...")
 
        def on_binary_data(self, data, **kwargs):
            global warning_notice
            if warning_notice:
                print("Received binary audio data")
                warning_notice = False
 
        def on_welcome(self, welcome, **kwargs):
            print(f"\n\n{welcome}\n\n")
 
        def on_settings_applied(self, settings_applied, **kwargs):
            print(f"\n\n{settings_applied}\n\n")
            print("Settings successfully applied. Ready for conversation.")
            # Print special note about interruption feature
            print("👉 You can interrupt the assistant at any time by speaking while it's talking.")
 
        def on_conversation_text(self, conversation_text, **kwargs):
            try:
                # Access attributes directly instead of using .get()
                if hasattr(conversation_text, 'role') and hasattr(conversation_text, 'content'):
                    role = conversation_text.role
                    content = conversation_text.content
                   
                    if role == "user":
                        print(f"\n👤 You: {content}\n")
                    elif role == "assistant":
                        print(f"\n🤖 Assistant: {content}\n")
                    else:
                        print(f"\n\n{role}: {content}\n\n")
                else:
                    # Fallback to printing the whole object
                    print(f"\n\nConversation Text: {conversation_text}\n\n")
            except Exception as e:
                print(f"Error handling conversation text: {e}")
                # Fallback to just printing the object as-is
                print(f"Raw conversation text: {conversation_text}")
 
        def on_user_started_speaking(self, user_started_speaking, **kwargs):
            global assistant_speaking
           
            if assistant_speaking:
                # User interrupted the assistant
                print("\n✋ You interrupted the assistant...\n")
                # Signal to stop the assistant's speech
                dg_connection.interrupt()
                assistant_speaking = False
            else:
                # Normal listening mode
                print("\n🎤 Listening...\n")
 
        def on_agent_thinking(self, agent_thinking, **kwargs):
            print("\n💭 Assistant is thinking...\n")
 
        def on_function_calling(self, function_calling, **kwargs):
            print(f"\n\n{function_calling}\n\n")
 
        def on_agent_started_speaking(self, agent_started_speaking, **kwargs):
            global assistant_speaking
            assistant_speaking = True
            print("\n🔊 Assistant is speaking...\n")
 
        def on_agent_audio_done(self, agent_audio_done, **kwargs):
            global assistant_speaking
            assistant_speaking = False
            print("\n✅ Assistant finished speaking.\n")
 
        def on_close(self, close, **kwargs):
            print(f"\n\n{close}\n\n")
            print("Connection closed.")
 
        def on_error(self, error, **kwargs):
            print(f"\n❌ Error: {error}\n\n")
 
        # Handle interruption events
        def on_interruption(self, interruption, **kwargs):
            print("\n⚡ Assistant was interrupted!\n")
 
        # Handle the EndOfThought message that appears frequently
        def on_end_of_thought(self, end_of_thought, **kwargs):
            print("\n💡 Assistant finished thinking and is preparing response...\n")
 
        def on_unhandled(self, unhandled, **kwargs):
            # If we still get unhandled messages, print them in a nicer format
            if hasattr(unhandled, 'raw') and isinstance(unhandled.raw, str) and "EndOfThought" in unhandled.raw:
                print("\n💡 Assistant finished thinking and is preparing response...\n")
            elif isinstance(unhandled, dict) and "raw" in unhandled and "EndOfThought" in unhandled["raw"]:
                print("\n💡 Assistant finished thinking and is preparing response...\n")
            elif hasattr(unhandled, 'raw') and isinstance(unhandled.raw, str) and "Interruption" in unhandled.raw:
                print("\n⚡ Assistant was interrupted!\n")
            elif isinstance(unhandled, dict) and "raw" in unhandled and "Interruption" in unhandled["raw"]:
                print("\n⚡ Assistant was interrupted!\n")
            else:
                print(f"\nUnknown event: {unhandled}\n")
 
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
       
        # Try to register specific handlers for special events
        if hasattr(AgentWebSocketEvents, 'EndOfThought'):
            dg_connection.on(AgentWebSocketEvents.EndOfThought, on_end_of_thought)
        else:
            # If not in the enum, try to register it as a string
            dg_connection.on("EndOfThought", on_end_of_thought)
           
        # Register interruption event handler if available
        if hasattr(AgentWebSocketEvents, 'Interruption'):
            dg_connection.on(AgentWebSocketEvents.Interruption, on_interruption)
        else:
            # If not in the enum, try to register it as a string
            dg_connection.on("Interruption", on_interruption)
 
        # Configure settings for the conversation
        options: SettingsConfigurationOptions = SettingsConfigurationOptions()
       
        # Configure the AI model and behavior
        options.agent.think.provider.type = "open_ai"
        options.agent.think.model = "gpt-4o-mini"
        options.agent.think.instructions = """
        You are a sales executive at DigiRocket Technologies, specializing in website optimization and digital marketing. You aim to collect the customer’s email by offering a free website audit report and scheduling a consultation. The conversation should not end until the user provides their email or explicitly refuses multiple times. Answers should not be more than 20 words. Use more filler words in between the conversation to make the conversation more realistic and natural, and have context awareness. And remember to get the customer email id. Take the location and time zone of Dover, United States.
        """
       
        # Configure speech settings
        options.agent.speak.voice = "nova"  # You can choose different voices: nova, shimmer, etc.
        options.agent.speak.rate = 1.0      # Normal speaking rate
       
        # Configure barge-in settings
        options.agent.barge_in = True
       
        # Configure transcription settings for better accuracy
        options.transcription = {
            "model": "nova-2",
            "smart_format": True,
            "diarize": True,
            "language": "en",  # Change this for other languages
            "punctuate": True,
        }
 
        # Start the connection
        if dg_connection.start(options) is False:
            print("Failed to start connection")
            return
 
        print("\n\n==== Deepgram Voice Conversation Started ====")
        print("Talk into your microphone to begin conversation")
        print("You can interrupt the assistant at any time by speaking while it's talking")
        print("Press Enter to stop...\n\n")
        input()
 
        # Close the connection
        dg_connection.finish()
 
        print("Session finished. Thank you for using Deepgram Voice Conversation!")
 
    except ValueError as e:
        print(f"Invalid value encountered: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
 
if __name__ == "__main__":
    main()
