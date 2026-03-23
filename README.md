# Ruva - AI Powered Speech Tutor

Ruva is a modern AI powered speech tutor that targets speech anxiety and provides personalised coaching via native RAG architecture. It focuses on different types of speech problems spanning from stuttering to going blank while speaking. It has 4 different practice modes/rooms and supports both single-player and multiplayer activities. 

## Architecture

- **Frontend**: React + TypeScript + Vite
- **Backend**: Python + FastAPI + WebSocket
- **Database**: MongoDB
- **Cache**: Redis
- **AI**: Google Gemini API
- **Speech Processing**: Whisper, Silero VAD, Parselmouth

## Features

### Personalised coaching 
- The RAG architecture enables users to get personalised training over time. Ruva remembers one's strengths/weaknesses and thus enforces targetted improvements. 

### Four Practice Modes
- **Debate Mode**: 2 players with AI judge OR AI vs one player 
- **Group Discussion**: 2+ players with AI facilitator  
- **JAM Mode**: Single-player Just-A-Minute practice
- **Reading Mode**: Single-player pronunciation practice

### Real-time Capabilities
- Live speech transcription
- Voice activity detection
- Real-time speech analysis
- WebSocket communication
- Multi-user rooms

### Speech Analysis
- Prosodic analysis (pitch, intensity, jitter, shimmer)
- Filler word detection
- Pause analysis
- Sentiment analysis
- Body language analysis (planned)

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Node.js 18+ (for local development)
- Python 3.11+ (for local development)

### Development with Docker (Recommended)

1. Clone the repository
2. Copy environment file:
   ```bash
   cp backend/.env.example backend/.env
   ```
3. Add your Gemini API key to `backend/.env`
4. Start all services:
   ```bash
   npm run dev
   ```

This will start:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- MongoDB: localhost:27017
- Redis: localhost:6379

### Local Development

#### Frontend
```bash
cd frontend
npm install
npm run dev
```

#### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:socket_app --reload
```

## Project Structure

```
breakthrough/
├── frontend/                 # React TypeScript frontend
│   ├── src/
│   │   ├── components/      # React components
│   │   ├── store/          # Redux store and slices
│   │   └── main.tsx        # Application entry point
│   ├── package.json
│   └── vite.config.ts
├── backend/                 # FastAPI Python backend
│   ├── app/
│   │   ├── api/            # API routes
│   │   ├── core/           # Configuration and database
│   │   ├── models/         # Pydantic models
│   │   ├── services/       # Business logic
│   │   └── websocket/      # WebSocket handlers
│   ├── main.py             # Application entry point
│   └── requirements.txt
├── docker-compose.yml       # Development environment
└── README.md
```

## Configuration

### Environment Variables

Create `backend/.env` from `backend/.env.example`:

```env
# Database
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=breakthrough

# Cache
REDIS_URL=redis://localhost:6379

# AI Services
GEMINI_API_KEY=your_gemini_api_key_here

# Audio Processing
WHISPER_MODEL=base
SAMPLE_RATE=16000

# Security
SECRET_KEY=your-secret-key-here
```

## Deployment

### Production Build
```bash
# Build frontend
cd frontend && npm run build

# Build backend Docker image
cd backend && docker build -t breakthrough-backend .
```

### Environment Setup
- Configure production database URLs
- Set secure secret keys
- Configure CORS origins
- Set up SSL certificates

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
