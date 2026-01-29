#!/bin/bash

echo "Starting NLSWin25 Application..."

# Start Ollama service in the background
echo "Starting Ollama service..."
ollama serve &

# Wait for Ollama to be ready
echo "Waiting for Ollama to initialize..."
sleep 10

# Check if Ollama is running
until ollama list > /dev/null 2>&1; do
    echo "Waiting for Ollama to be ready..."
    sleep 2
done

echo "Ollama is ready!"

# Optional: Pull a specific model (uncomment and modify as needed)
# echo "Pulling Ollama model..."
# ollama pull llama2
# or
# ollama pull mistral

# Run your main application
echo "Starting main application..."
python main.py
