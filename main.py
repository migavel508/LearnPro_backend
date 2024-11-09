"""import os
import logging
from flask import Flask, request, jsonify
from pydub import AudioSegment
from pydub.silence import split_on_silence
import speech_recognition as sr

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Initialize the recognizer
recognizer = sr.Recognizer()

# Set ffmpeg path (path to ffmpeg executable)
AudioSegment.converter = "C:/Users/migavel/Downloads/ffmpeg-2024-09-26-git-f43916e217-essentials_build/ffmpeg-2024-09-26-git-f43916e217-essentials_build/bin/ffmpeg.exe"

# Function to reduce noise from audio using pydub
def reduce_noise(audio_segment):
    return audio_segment.low_pass_filter(3000)

# Function to convert wav to text in chunks
def wav_to_text_in_chunks(wav_file):
    try:
        # Load the audio file
        sound = AudioSegment.from_file(wav_file)

        # Reduce noise from the audio
        sound = reduce_noise(sound)

        # Split audio where silence is 500ms or more and keep the silence for 500ms
        chunks = split_on_silence(sound,
                                  min_silence_len=500,
                                  silence_thresh=sound.dBFS - 14,
                                  keep_silence=500)

        folder_name = "audio_chunks"
        if not os.path.exists(folder_name):
            os.mkdir(folder_name)

        full_text = ""

        # Process each audio chunk
        for i, audio_chunk in enumerate(chunks):
            chunk_filename = os.path.join(folder_name, f"chunk{i}.wav")
            audio_chunk.export(chunk_filename, format="wav")

            with sr.AudioFile(chunk_filename) as source:
                recognizer.adjust_for_ambient_noise(source)
                audio_data = recognizer.record(source)

                try:
                    text = recognizer.recognize_google(audio_data)
                except sr.UnknownValueError:
                    text = ""
                except sr.RequestError as e:
                    text = f"[API Error: {e}]"

                full_text += f"{text} "

        return full_text.strip()

    except Exception as e:
        return f"Error processing the audio file: {e}"

@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    if 'file' not in request.files:
        logging.error("No file part in the request")
        return jsonify({'error': 'No file part in the request'}), 400

    file = request.files['file']

    if file.filename == '':
        logging.error("No selected file")
        return jsonify({'error': 'No selected file'}), 400

    # Save the file to a temporary location
    try:
        temp_dir = os.path.join(os.environ.get('TEMP', '/tmp'))
        wav_file = os.path.join(temp_dir, f"output_audio_{file.filename}")
        file.save(wav_file)
        logging.debug(f"Audio file saved to {wav_file}")
    except Exception as e:
        logging.error(f"Failed to save audio file: {str(e)}")
        return jsonify({'error': 'Failed to save audio file'}), 500

    # Load and process the audio file in chunks
    try:
        transcription = wav_to_text_in_chunks(wav_file)

    except Exception as e:
        logging.error(f"Error processing audio file: {str(e)}")
        return jsonify({'error': 'Error processing audio file'}), 500

    # Clean up the saved file
    try:
        os.remove(wav_file)
        logging.debug(f"Temporary file {wav_file} removed successfully")
    except Exception as e:
        logging.error(f"Error removing temporary file: {str(e)}")

    return jsonify({'message': 'Audio processed successfully', 'transcription': transcription}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)"""


import os
import hashlib
import logging
import time
from flask import Flask, request, jsonify
from pydub import AudioSegment
from pydub.silence import split_on_silence
import speech_recognition as sr

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

recognizer = sr.Recognizer()
AudioSegment.converter = "C:/Users/migavel/Downloads/ffmpeg-2024-09-26-git-f43916e217-essentials_build/ffmpeg-2024-09-26-git-f43916e217-essentials_build/bin/ffmpeg.exe"

# In-memory cache for storing file hashes and transcriptions
transcription_cache = {}

# Helper function to generate a unique hash ID for each file
def generate_file_hash(file):
    hash_md5 = hashlib.md5()
    for chunk in iter(lambda: file.read(4096), b""):
        hash_md5.update(chunk)
    file.seek(0)
    return hash_md5.hexdigest()

# Function to reduce noise from audio
def reduce_noise(audio_segment):
    return audio_segment.low_pass_filter(3000)

# Function to transcribe audio in chunks with retries (self-healing)
def transcribe_audio_chunks(wav_file, max_retries=3):
    retries = 0
    transcription = ""

    while retries < max_retries:
        try:
            # Load and preprocess the audio file
            sound = AudioSegment.from_file(wav_file)
            sound = reduce_noise(sound)
            chunks = split_on_silence(sound, min_silence_len=500, silence_thresh=sound.dBFS - 14, keep_silence=500)
            
            # Process and transcribe each chunk
            for i, audio_chunk in enumerate(chunks):
                with sr.AudioFile(audio_chunk.export(format="wav")) as source:
                    recognizer.adjust_for_ambient_noise(source)
                    audio_data = recognizer.record(source)
                    try:
                        text = recognizer.recognize_google(audio_data)
                    except (sr.UnknownValueError, sr.RequestError):
                        text = ""
                    transcription += f"{text} "

            # Store successful transcription in cache and return it
            return transcription.strip()
        except Exception as e:
            retries += 1
            logging.warning(f"Retry {retries}/{max_retries} - Error during transcription: {e}")
            time.sleep(1)

    logging.error("Transcription failed after multiple attempts.")
    return None

@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    if 'file' not in request.files:
        logging.error("No file part in the request")
        return jsonify({'error': 'No file part in the request'}), 400

    file = request.files['file']

    if file.filename == '':
        logging.error("No selected file")
        return jsonify({'error': 'No selected file'}), 400

    # Generate hash ID for the file
    file_id = generate_file_hash(file)

    # Check if the transcription exists in cache
    if file_id in transcription_cache:
        logging.info("Loaded transcription from cache")
        return jsonify({'message': 'Audio processed successfully (from cache)', 'transcription': transcription_cache[file_id]}), 200

    # Save the audio file temporarily
    try:
        temp_dir = os.path.join(os.environ.get('TEMP', '/tmp'))
        wav_file = os.path.join(temp_dir, f"output_audio_{file.filename}")
        file.save(wav_file)
        logging.debug(f"Audio file saved to {wav_file}")
    except Exception as e:
        logging.error(f"Failed to save audio file: {str(e)}")
        return jsonify({'error': 'Failed to save audio file'}), 500

    # Transcribe the audio in chunks
    transcription = transcribe_audio_chunks(wav_file)

    # Clean up the saved file
    try:
        os.remove(wav_file)
        logging.debug(f"Temporary file {wav_file} removed successfully")
    except Exception as e:
        logging.error(f"Error removing temporary file: {str(e)}")

    # Cache the transcription and return it to the client
    if transcription:
        transcription_cache[file_id] = transcription
        return jsonify({'message': 'Audio processed successfully', 'transcription': transcription}), 200
    else:
        return jsonify({'error': 'Transcription failed.'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)


#Hello 👍