# Finance UI Backend

Backend API for Finance UI - Schema Management and Dify Integration

## Features

- User authentication (JWT)
- Schema management (CRUD operations)
- File upload and preview
- Dify AI integration with command detection
- Multi-user support

## Tech Stack

- FastAPI
- SQLAlchemy + PyMySQL
- JWT authentication
- Pydantic validation

## Setup

### 1. Install Dependencies

```bash
cd finance-ui/backend
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and update values:

```bash
cp .env.example .env
```

### 3. Initialize Database

```bash
python init_db.py
```

This will:
- Create `finance-ai` database
- Create `users` and `user_schemas` tables
- Verify table structure

### 4. Run Server

```bash
python main.py
```

Or with uvicorn:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## API Documentation

Once the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login and get token
- `GET /api/auth/me` - Get current user info

### Schemas
- `GET /api/schemas` - List user schemas
- `POST /api/schemas` - Create new schema
- `GET /api/schemas/{id}` - Get schema details
- `PUT /api/schemas/{id}` - Update schema
- `DELETE /api/schemas/{id}` - Delete schema

### Files
- `POST /api/files/upload` - Upload files
- `GET /api/files/preview` - Preview Excel file

### Dify
- `POST /api/dify/chat` - Chat with Dify AI

## Testing

### Health Check
```bash
curl http://localhost:8000/health
```

### Register User
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"test","email":"test@example.com","password":"test123"}'
```

### Login
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test123"}'
```

## Project Structure

```
backend/
├── main.py                 # FastAPI app
├── config.py              # Configuration
├── database.py            # Database connection
├── init_db.py            # Database initialization
├── models/               # SQLAlchemy models
├── schemas/              # Pydantic schemas
├── routers/              # API routes
├── services/             # Business logic
└── utils/                # Utilities
```
