# Use a slim Python base image for smaller size
FROM python:3.10-slim-bullseye

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    OLLAMA_HOST=0.0.0.0:11434 \
    PATH="/usr/local/bin:/home/ollama/.local/bin:${PATH}" \
    PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    curl \
    git \
    libgl1-mesa-glx \
    libxext6 \
    libsm6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# --- Install Ollama server ---
RUN set -ex && curl -fsSL https://ollama.com/install.sh | sh

# Set working directory with write permissions
WORKDIR /app
ENV HOME=/app
RUN mkdir -p /app/.cache/whisper && chmod -R 777 /app/.cache
RUN mkdir -p /app/.ollama && chmod -R 777 /app/.ollama
RUN mkdir -p /app/mlruns && chmod -R 777 /app/mlruns
ENV XDG_CACHE_HOME=/app/.cache



# Create .streamlit config directory and disable telemetry
RUN mkdir -p .streamlit
COPY src/config.toml .streamlit/

# Copy requirements.txt and install dependencies
COPY requirements.txt .

# Install parselmouth without deps to avoid googleads
RUN pip install praat-parselmouth
RUN pip install stopit

# Install all other dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application and all relevant assets from src/
COPY src/ .

# Expose default Streamlit and Ollama ports
EXPOSE 8501
EXPOSE 11434

# Start Ollama and Streamlit app
CMD ["sh", "-c", "ollama serve & sleep 10 && ollama pull gemma3n:e2b && exec streamlit run streamlit_app.py --server.port=8501 --server.address=0.0.0.0"]

