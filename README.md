# FinSec Platform

Next-Generation Financial Security Ecosystem built with a React frontend and FastAPI backend, fully containerized with Docker.

## Project Structure

- `/backend`: FastAPI Python application
- `/frontend`: React + Vite frontend application
- `docker-compose.yml`: Orchestrates both services

## Quickstart (Docker)

Ensure you have Docker and Docker Compose installed.

1. **Start the platform:**
   ```bash
   docker compose up --build
   ```

2. **Access the services:**
   - **Frontend UI:** [http://localhost:3000](http://localhost:3000)
   - **Backend API:** [http://localhost:8000](http://localhost:8000)
   - **API Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)

## Development

If you prefer to run the services manually without Docker:

### Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```
