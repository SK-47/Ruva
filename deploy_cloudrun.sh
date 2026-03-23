#!/bin/bash

# Configuration
PROJECT_ID="gemini-489210"
REGION="us-central1"
BACKEND_SERVICE="speech-backend"
FRONTEND_SERVICE="speech-frontend"

# Check for gcloud
if ! command -v gcloud &> /dev/null; then
    echo "gcloud CLI not found. Please install it first."
    exit 1
fi

echo "🚀 Starting SpeechApp Deployment to Cloud Run..."

# Set project
gcloud config set project $PROJECT_ID

# --- Environment Variable Parsing ---
echo "📝 Parsing .env file for backend environment variables..."
if [ ! -f .env ]; then
    echo "❌ ERROR: No .env file found in root directory!"
    echo "Please create one and add your MongoDB Atlas URL."
    exit 1
fi

# Check for critical variables
if ! grep -q "MONGODB_URL" .env; then
    echo "❌ ERROR: MONGODB_URL not found in .env!"
    echo "Please add your MongoDB Atlas connection string to the .env file."
    exit 1
fi

if ! grep -q "REDIS_URL" .env; then
    echo "❌ ERROR: REDIS_URL not found in .env!"
    echo "Please add your Redis connection string to the .env file."
    exit 1
fi

ENV_VARS=$(grep -v '^#' .env | grep -v '^[[:space:]]*$' | grep -v '^COMPOSE_' | grep -v '^BACKEND_PORT' | grep -v '^FRONTEND_PORT' | grep -v '^MONGO_' | grep -v '^REDIS_PORT' | grep -v '^REDIS_PASSWORD' | grep -v '^NETWORK_NAME' | grep -v '^DATA_BASE_PATH' | grep -v '^UPLOADS_PATH' | grep -v '^LOGS_PATH' | paste -sd "," -)

# 1. Build and Push Backend
echo "📦 Building Backend image..."
gcloud builds submit backend/ --tag gcr.io/$PROJECT_ID/$BACKEND_SERVICE

# 2. Deploy Backend
echo "🌍 Deploying Backend to Cloud Run..."
gcloud run deploy $BACKEND_SERVICE \
    --image gcr.io/$PROJECT_ID/$BACKEND_SERVICE \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --memory 4Gi \
    --cpu 2 \
    --timeout 300 \
    --set-env-vars="$ENV_VARS,ALLOWED_ORIGINS=*"

# Get Backend URL
BACKEND_URL=$(gcloud run services describe $BACKEND_SERVICE --platform managed --region $REGION --format 'value(status.url)')
BACKEND_URL=$(echo $BACKEND_URL | sed 's/http:\/\//https:\/\//g')
echo "✅ Backend deployed at: $BACKEND_URL"

# 3. Build and Push Frontend
echo "📦 Building Frontend image..."
# Use cloudbuild.yaml to handle build arguments
gcloud builds submit frontend/ \
    --config=frontend/cloudbuild.yaml \
    --substitutions=_VITE_API_URL=$BACKEND_URL/api,_VITE_WS_URL=$BACKEND_URL,_SERVICE_NAME=$FRONTEND_SERVICE

# 4. Deploy Frontend
echo "🌍 Deploying Frontend to Cloud Run..."
gcloud run deploy $FRONTEND_SERVICE \
    --image gcr.io/$PROJECT_ID/$FRONTEND_SERVICE \
    --platform managed \
    --region $REGION \
    --port 80 \
    --allow-unauthenticated

FRONTEND_URL=$(gcloud run services describe $FRONTEND_SERVICE --platform managed --region $REGION --format 'value(status.url)')

echo "--------------------------------------------------"
echo "🎉 Deployment Complete!"
echo "--------------------------------------------------"
echo "Frontend URL: $FRONTEND_URL"
echo "Backend URL:  $BACKEND_URL"
echo "--------------------------------------------------"
