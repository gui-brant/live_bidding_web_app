# SE3350 Monorepo Scaffold

This repository contains a FastAPI backend and a React + TypeScript frontend.

## Prerequisites
- Python 3.9+ (matches `backend/pyproject.toml` / `backend/requirements.txt`)
- Node.js 18+ (for Vite)

## Backend (FastAPI)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd server
uvicorn app.main:app --reload
```

Backend default URL: `http://127.0.0.1:8000`

## Frontend (Vite React TS)

```bash
cd frontend
npm install
npm run dev
```

Frontend default URL: `http://127.0.0.1:5173`

## Environment Variables
- Backend sample: `backend/.env.example`
- Frontend sample: `frontend/.env.example`

> Tip: To customize the API URL, set `VITE_API_BASE_URL` in the frontend `.env` file.

## Notes
- The database is not implemented yet (no MySQL / SQLAlchemy / Alembic in this phase).
- All endpoints are placeholders and will be replaced with real logic later.

