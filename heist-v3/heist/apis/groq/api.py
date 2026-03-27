from flask import Flask, request, jsonify
from groq import Groq
from functools import wraps
import logging
from dotenv import dotenv_values
import asyncpg
import asyncio
import os
import requests
import subprocess

config = dotenv_values(".env")

DATA_DB = config["DATA_DB"]
GROQ_KEY = config["GROQ_API_KEY"]

async def get_db_connection():
    return await asyncpg.connect(dsn=DATA_DB)

client = Groq(api_key=GROQ_KEY)

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/api.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def chat_endpoint(prompt: str, model: str = "llama3-8b-8192", api_key: str = None):
    try:    
        chat_completion = await asyncio.to_thread(client.chat.completions.create, 
            messages=[{"role": "user", "content": prompt}],
            model=model
        )
        response = chat_completion.choices[0].message.content
        return {
            'status': 'success',
            'response': response
        }
    except Exception as e:
        raise Exception(f"Error processing request: {str(e)}")

@app.route('/chat', methods=['POST'])
async def chat_route():
    try:
        data = request.json
        if not data or 'prompt' not in data:
            return jsonify({'error': 'Missing prompt in request body'}), 400

        prompt = data['prompt']
        model = data.get('model', 'llama3-8b-8192')

        logger.info(f"Received request for model: {model}")
        logger.info(f"Prompt: {prompt[:100]}...")

        provided_api_key = request.headers.get('X-API-Key')
        response = await chat_endpoint(prompt, model, provided_api_key)
        logger.info("Successfully generated response")
        return jsonify(response)

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/transcribe', methods=['POST'])
async def transcribe_route():
    if request.remote_addr != '127.0.0.1':
        return jsonify({'error': 'This endpoint is restricted to localhost'}), 403
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Missing audio file in request'}), 400

        audio_file = request.files['file']
        if audio_file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        temp_dir = "/heist/temp"
        os.makedirs(temp_dir, exist_ok=True)
        file_extension = os.path.splitext(audio_file.filename)[1].lower()
        temp_filename = os.path.join(temp_dir, "temp_audio")
        original_temp_filename = temp_filename + file_extension
        audio_file.save(original_temp_filename)

        converted_filename = temp_filename + ".m4a"
        subprocess.run([
            'ffmpeg', 
            '-i', original_temp_filename, 
            '-c:a', 'aac', 
            converted_filename
        ], check=True)
        
        files = {
            'file': ('audio.m4a', open(converted_filename, 'rb'))
        }
        
        data = {
            'model': 'whisper-large-v3-turbo'
        }
        
        headers = {
            'Authorization': f'Bearer {GROQ_KEY}'
        }

        response = await asyncio.to_thread(
            requests.post,
            'https://api.groq.com/openai/v1/audio/transcriptions',
            headers=headers,
            data=data,
            files=files
        )

        os.remove(original_temp_filename)
        os.remove(converted_filename)

        if response.status_code == 200:
            logger.info("Successfully transcribed audio")
            return jsonify(response.json())
        else:
            logger.error(f"Groq API error: {response.text}")
            return jsonify({
                'status': 'error',
                'error': response.text
            }), response.status_code

    except Exception as e:
        logger.error(f"Error processing transcription request: {str(e)}")
        for filename in [original_temp_filename, converted_filename]:
            if os.path.exists(filename):
                os.remove(filename)
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5094)