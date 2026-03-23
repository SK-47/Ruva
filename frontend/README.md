# BreakThrough Frontend

Modern React-based frontend for the BreakThrough speech coaching application.

## Features

- **React 18** with TypeScript for type-safe development
- **Redux Toolkit** for state management
- **React Router** for navigation
- **Socket.IO Client** for real-time WebSocket communication
- **Web Audio API** for audio recording and playback
- **ElevenLabs Voice Agent** integration for natural AI conversations
- **Dark theme** with red/pink accents
- **Responsive design** for desktop and mobile

## Project Structure

```
frontend/
├── src/
│   ├── components/          # React components
│   │   ├── RoomLobby.tsx   # Room creation and joining
│   │   ├── SpeechRoom.tsx  # Main practice room
│   │   ├── ParticipantList.tsx
│   │   ├── AudioRecorder.tsx
│   │   ├── TranscriptDisplay.tsx
│   │   ├── AnalyticsDashboard.tsx
│   │   └── VoiceAgent.tsx  # ElevenLabs integration
│   ├── services/           # API and WebSocket services
│   │   ├── api.ts         # REST API client
│   │   └── websocket.ts   # WebSocket client
│   ├── store/             # Redux store
│   │   ├── store.ts
│   │   └── slices/        # Redux slices
│   ├── App.tsx            # Main app component
│   ├── main.tsx           # Entry point
│   └── index.css          # Global styles
├── package.json
└── vite.config.ts
```

## Getting Started

### Prerequisites

- Node.js 16+ and npm/yarn
- Backend server running (see backend/README.md)

### Installation

```bash
cd frontend
npm install
```

### Configuration

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

Edit `.env` to configure:
- `VITE_API_URL`: Backend API URL (default: http://localhost:8000/api)
- `VITE_WS_URL`: WebSocket URL (default: http://localhost:8000)

### Development

```bash
npm run dev
```

The app will be available at http://localhost:5173

### Build

```bash
npm run build
```

Build output will be in the `dist/` directory.

### Preview Production Build

```bash
npm run preview
```

## Components

### RoomLobby
- Create new practice rooms
- Join existing rooms
- Select practice mode (Debate, Group Discussion, JAM, Reading)
- Enable/disable AI facilitator

### SpeechRoom
- Main practice interface
- Real-time participant list
- Audio recording controls
- Live transcription display
- Speech analysis dashboard
- ElevenLabs voice agent integration

### AudioRecorder
- Web Audio API integration
- Real-time audio streaming to backend
- Voice activity detection
- Recording controls

### VoiceAgent
- ElevenLabs Voice Agent integration
- Real-time voice conversation
- Conversation controls (start, stop, interrupt)
- Low-latency audio playback

### AnalyticsDashboard
- Real-time speech metrics
- Progressive feedback (basic → detailed)
- Quality rating
- Session report export

### TranscriptDisplay
- Live transcription
- Participant identification
- Confidence scores
- Auto-scrolling

## State Management

Redux store with three main slices:

1. **roomSlice**: Room and participant management
2. **sessionSlice**: Session lifecycle and history
3. **speechSlice**: Transcripts and speech metrics

## Real-time Communication

### WebSocket Events

**Outgoing:**
- `join-room`: Join a practice room
- `leave-room`: Leave a room
- `speech-start`: Start speaking
- `speech-end`: Stop speaking
- `speech-data`: Audio data chunks

**Incoming:**
- `participant-joined`: New participant notification
- `participant-left`: Participant left notification
- `transcript`: Speech transcription
- `speech-analysis`: Speech metrics
- `ai-response`: AI host response

## Styling

- Dark theme with CSS variables
- Red/pink accent colors (#e91e63)
- Responsive breakpoints: 1200px, 1024px, 768px, 480px
- Custom scrollbars
- Smooth transitions and animations

## API Integration

REST API endpoints:
- `POST /api/rooms` - Create room
- `GET /api/rooms` - List rooms
- `GET /api/rooms/:id` - Get room details
- `POST /api/rooms/:id/join` - Join room
- `DELETE /api/rooms/:id/leave` - Leave room
- `POST /api/sessions` - Start session
- `GET /api/sessions/:id` - Get session
- `POST /api/sessions/:id/end` - End session

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

Requires:
- WebSocket support
- Web Audio API
- MediaRecorder API
- ES2020+ features

## Development Tips

### Hot Module Replacement
Vite provides fast HMR for instant feedback during development.

### TypeScript
All components are fully typed. Run `npm run build` to check for type errors.

### Linting
```bash
npm run lint
```

### Component Development
Components follow a consistent pattern:
1. Import dependencies
2. Define props interface
3. Use Redux hooks for state
4. Implement component logic
5. Return JSX with proper styling

## Troubleshooting

### WebSocket Connection Issues
- Verify backend is running
- Check VITE_WS_URL in .env
- Check browser console for errors

### Audio Recording Issues
- Grant microphone permissions
- Check browser compatibility
- Verify HTTPS in production (required for getUserMedia)

### Build Issues
- Clear node_modules and reinstall
- Check Node.js version (16+)
- Verify all dependencies are installed

## License

Part of the BreakThrough speech coaching application.
