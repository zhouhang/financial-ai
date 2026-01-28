#!/bin/bash
# Finance MCP API Server Startup Script

echo "Starting Finance MCP API Server..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q fastapi uvicorn sqlalchemy pymysql python-jose[cryptography] passlib[bcrypt] python-multipart httpx pydantic-settings openpyxl pandas

# Start API server
echo "Starting API server on port 8000..."
python api_server.py
