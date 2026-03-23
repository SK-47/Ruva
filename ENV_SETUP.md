# Environment Setup Guide

This guide explains how to set up environment variables for the BreakThrough application.

## Quick Start

### For Docker Compose Setup (Recommended)

1. Copy the root `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and fill in your API keys:
   - `GEMINI_API_KEY`: Get from [Google AI Studio](https://makersuite.google.com/app/apikey)
   - `ELEVENLABS_API_KEY`: Get from [ElevenLabs](https://elevenlabs.io/app/settings/api-keys)
   - `SECRET_KEY`: Generate with `openssl rand -hex 32`

3. Start the application:
   ```bash
   docker-compose up -d
   ```

### For Local Development (Without Docker)

#### Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

3. Edit `backend/.env` and configure:
   - Database URLs (MongoDB and Redis)
   - API keys (Gemini and ElevenLabs)
   - Security settings

4. Install dependencies and run:
   ```bash
   pip install -r requirements.txt
   python main.py
   ```

#### Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

3. Edit `frontend/.env` and configure:
   - Backend API URL
   - WebSocket URL
   - Feature flags

4. Install dependencies and run:
   ```bash
   npm install
   npm run dev
   ```

## Required API Keys

### Google Gemini API Key (REQUIRED)

The Gemini API is used for AI-powered coaching and feedback.

1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the key and add it to your `.env` file

**Free Tier**: Google Gemini offers a generous free tier for development.

**Required**: Yes - the application needs this for AI coaching features.

### ElevenLabs API Key (OPTIONAL)

ElevenLabs provides voice agent functionality for natural conversations.

1. Go to [ElevenLabs](https://elevenlabs.io/)
2. Sign up or sign in
3. Navigate to Settings → API Keys
4. Create a new API key
5. Copy the key and add it to your `.env` file

**Free Tier**: ElevenLabs offers a free tier with limited characters per month.

**Required**: No - the application works without it. Voice agent features will be disabled, but all other features (speech analysis, transcription, text-based AI coaching, reports) work normally.

**See**: [OPTIONAL_FEATURES.md](./OPTIONAL_FEATURES.md) for details on what works without this key.

### Optional: ElevenLabs Voice Agent IDs

For custom voice agents per mode:

1. Go to [ElevenLabs Conversational AI](https://elevenlabs.io/app/conversational-ai)
2. Create voice agents for each mode (JAM, Debate, Discussion, Reading)
3. Copy the agent IDs and add them to your `.env` file

## Environment Variables Reference

### Backend Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `MONGODB_URL` | MongoDB connection string | `mongodb://localhost:27017` | Yes |
| `DATABASE_NAME` | Database name | `breakthrough` | Yes |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` | Yes |
| `GEMINI_API_KEY` | Google Gemini API key | - | **Yes** |
| `ELEVENLABS_API_KEY` | ElevenLabs API key | - | No (optional) |
| `WHISPER_MODEL` | Whisper model size | `base` | No |
| `SECRET_KEY` | JWT secret key | - | Yes |
| `DEBUG` | Debug mode | `true` | No |

### Frontend Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `VITE_API_URL` | Backend API URL | `http://localhost:8000/api` | Yes |
| `VITE_WS_URL` | WebSocket URL | `http://localhost:8000` | Yes |
| `VITE_ENABLE_VOICE_AGENT` | Enable voice agents | `true` | No |
| `VITE_THEME_MODE` | UI theme | `dark` | No |

## Security Best Practices

1. **Never commit `.env` files** to version control
2. **Use strong secret keys** in production (generate with `openssl rand -hex 32`)
3. **Rotate API keys** regularly
4. **Use environment-specific configurations** (dev, staging, prod)
5. **Restrict CORS origins** in production to your actual domain

## Troubleshooting

### MongoDB Connection Issues

If you can't connect to MongoDB:

- **Local**: Ensure MongoDB is running (`mongod` or `brew services start mongodb-community`)
- **Docker**: Use `mongodb://mongo:27017` instead of `localhost`
- **Atlas**: Check your connection string and IP whitelist

### Redis Connection Issues

If you can't connect to Redis:

- **Local**: Ensure Redis is running (`redis-server` or `brew services start redis`)
- **Docker**: Use `redis://redis:6379` instead of `localhost`

### API Key Issues

If API calls fail:

- Verify your API keys are correct
- Check API key quotas and limits
- Ensure no extra spaces or quotes in the `.env` file

### CORS Issues

If frontend can't connect to backend:

- Check `ALLOWED_ORIGINS` in backend `.env`
- Ensure frontend URL is included
- For Docker, use service names instead of `localhost`

## Production Deployment

For production deployment:

1. Set `DEBUG=false`
2. Use strong `SECRET_KEY`
3. Configure proper `ALLOWED_ORIGINS`
4. Use production database URLs
5. Enable HTTPS
6. Set appropriate `LOG_LEVEL`
7. Configure proper `WORKERS` count

## Additional Resources

- [MongoDB Documentation](https://docs.mongodb.com/)
- [Redis Documentation](https://redis.io/documentation)
- [Google Gemini API Docs](https://ai.google.dev/docs)
- [ElevenLabs API Docs](https://elevenlabs.io/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Vite Documentation](https://vitejs.dev/)
