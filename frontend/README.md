# SE3350 Frontend

React + TypeScript + Vite frontend for the SE3350 project.

## Setup

```bash
cd frontend
npm install
npm run dev
```

## Environment

Copy the example env file and adjust if needed:

```bash
cp .env.example .env
```

`VITE_API_BASE_URL` defaults to `http://localhost:8000` if not set.

## Notes

- The app uses mock data when the backend is unavailable (network error or 5xx).
- 401 responses redirect to `/login`.
- TODOs are left in the API layer for real endpoint wiring.

