# SE3350 Group Project — Team 07

A complete full-stack web application built over the course of three months for SE3350.

This project includes a FastAPI backend and a React + TypeScript frontend. The application was developed as a working web app, not just a scaffold, with both client-side and server-side functionality implemented and connected through API calls.

The repository is organized as a monorepo, with the backend and frontend kept in separate folders so that each part of the system can be developed, tested, and run independently.

---

## Project Overview

This application was created as a team project for SE3350. Over a three-month development period, the team designed, implemented, and integrated a working full-stack system.

The project includes:

- A backend API built with FastAPI
- A frontend built with React, TypeScript, and Vite
- Environment configuration for both backend and frontend
- API communication between the frontend and backend
- A working local development setup
- Organized backend and frontend project structure
- Functional web app features developed throughout the term

The application was designed to demonstrate practical software engineering skills, including requirements analysis, frontend development, backend development, API design, team collaboration, iterative implementation, and documentation.

---

## Tech Stack

### Backend

- Python 3.9+
- FastAPI
- Uvicorn
- REST-style API endpoints
- Python virtual environment
- Environment variable configuration

### Frontend

- React
- TypeScript
- Vite
- Node.js 18+
- npm
- Component-based UI development
- Environment variable configuration through Vite

---

## Main Features

The web application includes a complete frontend and backend that work together to provide a functional user experience.

### Full-Stack Architecture

The project separates the backend and frontend into two main application layers.

The backend is responsible for exposing API endpoints and handling server-side logic. The frontend is responsible for displaying the user interface, sending requests to the backend, and presenting data to the user.

This separation makes the project easier to maintain, test, and expand.

### React + TypeScript Frontend

The frontend was built using React and TypeScript. This allowed the team to build the interface using reusable components while also benefiting from type safety during development.

The frontend is powered by Vite, which provides a fast development server and a modern build process.

### FastAPI Backend

The backend was built with FastAPI, a Python web framework designed for building APIs quickly and clearly.

The backend exposes endpoints that the frontend can call through HTTP requests. FastAPI also provides interactive API documentation, making it easier to test and understand the available backend routes during development.

### API Integration

The frontend communicates with the backend using a configurable API base URL.

This allows the project to run locally during development while still supporting different backend URLs through environment variables.

### Environment-Based Configuration

Both the backend and frontend include example environment files.

The frontend supports a configurable backend URL through:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

This makes it easier to switch between local development, testing, and future deployment environments.

### Local Development Workflow

The project can be run locally by starting the backend and frontend in separate terminals.

This mirrors a real full-stack development workflow where the API server and client application run independently but communicate with each other.

### Team-Based Development

The project was built collaboratively over three months. The structure of the repository supports team development by clearly separating frontend and backend responsibilities.

This made it possible for team members to work on different areas of the application while still integrating everything into one final working system.

---

## Prerequisites

Before running the project, make sure the following tools are installed:

- Python 3.9+
- Node.js 18+
- npm

The backend Python version should match the project configuration in:

```txt
backend/pyproject.toml
backend/requirements.txt
```

Node.js 18+ is required for the Vite frontend.

---

## Backend Setup

The backend is located in the `backend` folder.

From the root of the repository, run:

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment.

On macOS or Linux:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

On Windows Command Prompt:

```cmd
.venv\Scripts\activate
```

Install the backend dependencies:

```bash
pip install -r requirements.txt
```

Move into the server folder:

```bash
cd server
```

Start the FastAPI development server:

```bash
uvicorn app.main:app --reload
```

The backend will run at:

```txt
http://127.0.0.1:8000
```

FastAPI documentation is available at:

```txt
http://127.0.0.1:8000/docs
```

---

## Frontend Setup

The frontend is located in the `frontend` folder.

From the root of the repository, run:

```bash
cd frontend
npm install
npm run dev
```

The frontend will run at:

```txt
http://127.0.0.1:5173
```

---

## Running the Full Application

To run the complete application locally, use two terminal windows.

### Terminal 1 — Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd server
uvicorn app.main:app --reload
```

On Windows, replace the virtual environment activation command with the appropriate Windows command shown in the backend setup section.

Backend URL:

```txt
http://127.0.0.1:8000
```

### Terminal 2 — Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

```txt
http://127.0.0.1:5173
```

Once both servers are running, open the frontend URL in a browser.

---

## Environment Variables

The project includes sample environment files for both the backend and frontend.

Backend sample:

```txt
backend/.env.example
```

Frontend sample:

```txt
frontend/.env.example
```

To customize the backend API URL used by the frontend, create or update the frontend `.env` file and set:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Because this project uses Vite, frontend environment variables must begin with:

```txt
VITE_
```

---

## Backend Notes

The backend uses FastAPI and is launched with Uvicorn.

The main backend entry point is:

```txt
backend/server/app/main.py
```

The backend is responsible for serving the API used by the frontend.

During development, the backend can be tested directly through the browser or through the FastAPI documentation page at:

```txt
http://127.0.0.1:8000/docs
```

---

## Frontend Notes

The frontend uses React with TypeScript and Vite.

The frontend development server runs at:

```txt
http://127.0.0.1:5173
```

The frontend is responsible for:

- Rendering the user interface
- Handling user interactions
- Communicating with the backend API
- Displaying backend data to the user
- Managing client-side application behavior

---

## Development Process

This project was completed over approximately three months.

The team worked through the major stages of full-stack application development, including:

- Planning the project structure
- Setting up the backend and frontend environments
- Building backend API functionality
- Building frontend UI features
- Connecting the frontend to the backend
- Testing the application locally
- Refining the app based on project requirements
- Preparing the repository for final submission

The final result is a working full-stack web application rather than a starter scaffold.

---

## Current Status

The application is complete for the SE3350 project submission.

The project includes a working backend and frontend and can be run locally by following the setup instructions in this README.

---

## Possible Future Improvements

Although the project is complete for the course, future improvements could include:

- Adding stronger authentication and authorization
- Improving error handling across the frontend and backend
- Adding automated tests
- Improving deployment configuration
- Adding CI/CD workflows
- Expanding the database layer
- Improving UI polish and accessibility
- Adding more detailed API documentation
- Improving form validation
- Adding more robust logging

---

## Team

SE3350 Group Project — Team 07

This project was developed collaboratively as a team over a three-month period.

---

## License

This project was created for academic purposes as part of SE3350.
