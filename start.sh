#!/bin/bash

echo "=========================================="
echo " Starting MedBot Application"
echo "=========================================="

# Check if port 5000 is occupied, if so use 5001
PORT=5000
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
    echo "⚠️  Port 5000 is in use (likely AirPlay Receiver)."
    PORT=5001
    echo "🔄 Falling back to port 5001..."
fi

# Ensure virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating python virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Check variables
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. You may need to configure OPENROUTER_API_KEY."
fi

echo "🚀 Starting server on http://localhost:$PORT"
echo "Press Ctrl+C to stop the server."
echo "=========================================="

python -c "from app import app, initialize; initialize(); app.run(host='0.0.0.0', port=$PORT, debug=False)"
