FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install CPU-only PyTorch first (much smaller than CUDA version)
RUN pip install --no-cache-dir torch==2.1.1+cpu torchaudio==2.1.1+cpu --index-url https://download.pytorch.org/whl/cpu

# Install setuptools first, then whisper without build isolation so pkg_resources is available
RUN pip install --no-cache-dir setuptools && \
    pip install --no-cache-dir --no-build-isolation openai-whisper==20231117

# Install other Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create uploads directory
RUN mkdir -p uploads

# Expose port (Cloud Run uses $PORT, but we'll expose 8000 as a default)
EXPOSE 8000

# Run the application using a shell to expand $PORT
CMD ["sh", "-c", "uvicorn main:socket_app --host 0.0.0.0 --port ${PORT:-8000} --forwarded-allow-ips='*'"]