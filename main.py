import discord
from discord import app_commands
from discord.ext import commands
import wave
import os
import json
import asyncio
import vosk
import pyaudio
import pyttsx3

TOKEN = "Your Bot Token" 

intents = discord.Intents.all()
intents.voice_states = True
client = commands.Bot(command_prefix="!", intents=intents)

VOSK_MODEL_PATH = "vosk-model-small-en-us-0.15"
if not os.path.exists(VOSK_MODEL_PATH):
    raise FileNotFoundError("Vosk model not found! Download from https://alphacephei.com/vosk/models")
model = vosk.Model(VOSK_MODEL_PATH)

engine = pyttsx3.init()
engine.setProperty('rate', 150)    
engine.setProperty('volume', 1.0)  

voices = engine.getProperty('voices')
if voices:
    engine.setProperty('voice', voices[0].id)

voice_clients = {}

def get_bot_response(text):
    """
    Custom response function that returns appropriate responses based on user input.
    """
    text = text.lower()
    
    responses = {
        "hello": "Hello!",
        "how are you": "I'm doing well, thanks for asking!",
        "what time": "I can't tell you the exact time, but I can help you with other things!",
        "help": "I can understand voice commands and respond to basic questions. Try saying hello!",
        "goodbye": "Goodbye! Have a great day!",
        "weather": "I'm sorry, I don't have access to weather information, but I can help you with other questions!",
    }
    
    for keyword, response in responses.items():
        if keyword in text:
            return response
    
    return "Sorry! I couldn't understand that. Please try again."


@client.tree.command(name="join", description="Joins a voice channel")
async def join(interaction: discord.Interaction):
    try:
        if not interaction.user.voice:
            await interaction.response.send_message("Join a voice channel first!", ephemeral=True)
            return

        channel = interaction.user.voice.channel
        
        if interaction.guild.id in voice_clients:
            await voice_clients[interaction.guild.id].disconnect()
            
        vc = await channel.connect()
        voice_clients[interaction.guild.id] = vc
        await interaction.response.send_message(f"Joined {channel.name}!", ephemeral=True)
    except Exception as e:
        print(f"Error in join command: {e}")
        await interaction.response.send_message("Failed to join the voice channel.", ephemeral=True)

@client.tree.command(name="leave", description="Leaves the voice channel")
async def leave(interaction: discord.Interaction):
    try:
        vc = voice_clients.get(interaction.guild.id)
        if vc:
            await vc.disconnect()
            del voice_clients[interaction.guild.id]
            await interaction.response.send_message("Disconnected!", ephemeral=True)
        else:
            await interaction.response.send_message("I'm not in a voice channel!", ephemeral=True)
    except Exception as e:
        print(f"Error in leave command: {e}")
        await interaction.response.send_message("Failed to leave the voice channel.", ephemeral=True)

@client.tree.command(name="listen", description="Listens and replies in voice")
async def listen(interaction: discord.Interaction):
    try:
        vc = voice_clients.get(interaction.guild.id)
        if not vc:
            await interaction.response.send_message("I'm not in a voice channel!", ephemeral=True)
            return

        await interaction.response.send_message("Listening...", ephemeral=True)
        
        audio_file = await asyncio.to_thread(record_voice)
        if not audio_file:
            await interaction.followup.send("Failed to record audio!", ephemeral=True)
            return

        text = await asyncio.to_thread(transcribe_audio, audio_file)
        if not text:
            await interaction.followup.send("I couldn't understand that!", ephemeral=True)
            return

        print(f"User said: {text}")

        bot_response = get_bot_response(text)

        speech_file = await asyncio.to_thread(generate_speech, bot_response)
        if not speech_file:
            await interaction.followup.send("Failed to generate speech!", ephemeral=True)
            return

        await play_audio(vc, speech_file)

        await interaction.followup.send(f"🎙️ **You said:** {text}\n🔊 **Bot replied:** {bot_response}", ephemeral=True)

    except Exception as e:
        print(f"Error in listen command: {e}")
        await interaction.followup.send("An error occurred while processing your request.", ephemeral=True)


def record_voice():
    """Records 5 seconds of audio from the user."""
    try:
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
        frames = []

        print("Recording...")
        for _ in range(0, int(16000 / 1024 * 5)):  
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)
        print("Finished recording")

        stream.stop_stream()
        stream.close()
        p.terminate()

        file_path = "user_voice.wav"
        wf = wave.open(file_path, "wb")
        wf.setnchannels(1)
        wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
        wf.setframerate(16000)
        wf.writeframes(b''.join(frames))
        wf.close()

        return file_path
    except Exception as e:
        print(f"Error recording voice: {e}")
        return None

def transcribe_audio(file_path):
    """Converts speech to text using Vosk."""
    try:
        if not os.path.exists(file_path):
            print(f"Audio file not found: {file_path}")
            return ""

        wf = wave.open(file_path, "rb")
        rec = vosk.KaldiRecognizer(model, 16000)

        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                return result.get("text", "")

        result = json.loads(rec.FinalResult())
        return result.get("text", "")
    except Exception as e:
        print(f"Error transcribing audio: {e}")
        return ""

def generate_speech(text):
    """Converts text to speech using pyttsx3 (offline)."""
    try:
        file_path = "response.wav"
        engine.save_to_file(text, file_path)
        engine.runAndWait()
        
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            print(f"Speech file created successfully: {file_path}")
            return file_path
        else:
            print("Speech file creation failed")
            return None
    except Exception as e:
        print(f"Error generating speech: {e}")
        return None

async def play_audio(vc, file_path):
    """Plays an audio file in the voice channel."""
    try:
        if vc.is_playing():
            vc.stop()
        
        await asyncio.sleep(0.5)
        
        ffmpeg_path = "C:\\Moonlit Entertainment\\ffmpeg-7.1-full_build\\bin\\ffmpeg.exe"  
        source = discord.FFmpegPCMAudio(file_path, executable=ffmpeg_path)
        vc.play(source, after=lambda e: print(f"Finished playing: {e}" if e else "Finished playing"))
        
        while vc.is_playing():
            await asyncio.sleep(0.1)
            
    except Exception as e:
        print(f"Error playing audio: {e}")
        raise


@client.event
async def on_ready():
    try:
        await client.tree.sync()
        print(f"Logged in as {client.user}")
    except Exception as e:
        print(f"Error during startup: {e}")

client.run(TOKEN)
