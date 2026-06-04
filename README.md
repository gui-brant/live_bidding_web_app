# Live Bidding Web App

A full-stack live auction and bidding platform built for SE3350 by Team 07.

This repository contains a working web application with a FastAPI backend and a React + TypeScript frontend. The app supports role-based user flows, live auction rooms, real-time bidding updates, Kogbucks balance tracking, item management, wishlists, and administrative auction controls.

The project was developed over approximately three months as a complete course project, not as a scaffold. It demonstrates a practical full-stack architecture where the frontend, backend API, MongoDB persistence layer, and WebSocket event system work together to support a live bidding experience.

---

## Purpose

The purpose of the application is to provide an internal auction system where users can participate in live auctions using a virtual currency called Kogbucks.

Regular users can view their dashboard, track their Kogbucks balance, browse available auctions, join invited bidding rooms, place bids, use chat, maintain a wishlist, and review items they have won.

Administrators can manage the auction system by creating and editing auctions, assigning items to auctions, inviting users, managing users, viewing past auctions, managing Kogbucks, and running administrative bidding-room views.

---

## Main Features

### Authentication and Protected Routes

The app includes an authentication flow and separates access between regular users and administrators.

Protected routes prevent unauthenticated users from accessing the main application. Additional route guards separate regular user pages from admin-only pages.

User-facing routes include:

- Dashboard
- Settings
- Wishlist
- Auctions
- Bidding room

Admin-facing routes include:

- Admin overview
- Auction management
- Past auctions
- Item management
- User management
- Kogbucks management
- Admin bidding room
- Admin wishlist view

---

### User Dashboard

The dashboard gives users a summary of their account and auction activity.

It displays:

- User profile information
- User role
- Email and display name
- Available Kogbucks balance
- Held Kogbucks balance
- Account balance status
- Items won by the user
- Winning bid amounts
- Auction names and item statuses

This gives each user a clear overview of their current standing in the auction system.

---

### Kogbucks Balance System

The application uses Kogbucks as the virtual auction currency.

Users have balances that can be:

- Available for bidding
- Temporarily held during active bidding
- Updated after auction results are finalized

The backend includes support for default development Kogbucks values and stores user balances in the database.

---

### Auction Browsing

Users can view available auctions through the Auctions page.

The auction system supports multiple auction states, including upcoming, live, and ended auctions. Users can browse auctions, inspect auction details, and access bidding rooms when they are allowed to participate.

---

### Live Bidding Rooms

The bidding room is one of the core parts of the application.

Inside a bidding room, users can:

- View auction details
- See auction items
- Search/filter items in the room
- See the active or selected item
- Join an auction they were invited to
- Place bids
- View bid history
- See the latest bidder
- Track item statuses such as live, temporarily owned, pre-sold, and sold
- Receive live room state updates
- See winner ticker messages
- Use the in-room chat system

The frontend connects to the backend's real-time auction room system so auction state, bids, chat messages, and event notifications can update during the auction experience.

---

### Real-Time Updates with WebSockets

The backend includes WebSocket support for auction-room events.

The application uses this real-time layer to broadcast auction updates, including state changes, bid updates, auction-ending events, and chat-related activity.

The backend also includes an outbox dispatcher pattern for WebSocket events, helping coordinate database-backed events with live client updates.

---

### Auction Auto-End and Inactivity Handling

The backend includes background tasks for auction lifecycle management.

These tasks can:

- Detect expired running auctions
- Automatically close auctions when their end time is reached
- Distribute results after an auction ends
- Broadcast auction-ended and auction-state-updated events
- Process inactivity notifications for auctions

This helps keep auction state consistent without requiring manual intervention for every auction lifecycle event.

---

### Wishlist

Users can maintain a wishlist of auction items they are interested in.

The wishlist feature gives users a way to track desirable items separately from the live bidding flow.

Administrators also have access to an admin wishlist view, which can help with understanding user interest and demand.

---

### Admin Auction Management

Administrators can manage auctions from the admin interface.

Admin auction features include:

- Listing auctions
- Filtering auctions by status
- Searching auctions by title or category
- Creating new auctions
- Editing existing auctions
- Setting auction start and end times
- Assigning items to auctions
- Viewing active and upcoming auctions
- Viewing past auctions
- Inviting eligible users to participate in auctions

This gives administrators control over the auction schedule and participant access.

---

### Admin Item Management

Administrators can create and update auction items.

Item management includes:

- Item name
- Category
- Description
- Image URL
- Item status
- Sold and pre-sold handling
- Gift card and physical item categories

The frontend also normalizes image URLs to make item image entry easier during administration.

---

### Admin User and Kogbucks Management

The admin area includes tools for managing users and Kogbucks.

This supports the administrative side of the auction economy, including reviewing users and managing the virtual currency used for bidding.

---

### MongoDB Persistence

The backend is designed to use MongoDB for persistent storage.

Configured collections include:

- Users
- Items
- Auctions
- Bids
- Auction messages
- Auction chat messages
- Wishlist entries
- WebSocket outbox events

MongoDB configuration is controlled through environment variables.

---

## Tech Stack

### Backend

- Python 3.9+
- FastAPI
- Uvicorn
- Motor async MongoDB driver
- PyMongo
- Pydantic
- PyJWT
- WebSockets
- python-dotenv
- pytest
- httpx

### Frontend

- React 18
- TypeScript
- Vite
- React Router
- npm

### Database and Runtime

- MongoDB
- Environment-variable based configuration
- Local development support
- WebSocket-based live updates

---

## Prerequisites

Before running the project, make sure you have the following installed:

- Python 3.9+
- Node.js 18+
- npm
- MongoDB access, either local or hosted

---

## Backend Setup

From the repository root:

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

Install dependencies:

```bash
pip install -r requirements.txt
```

Move into the backend server folder:

```bash
cd server
```

Run the FastAPI development server:

```bash
uvicorn app.main:app --reload
```

Backend default URL:

```txt
http://127.0.0.1:8000
```

FastAPI documentation:

```txt
http://127.0.0.1:8000/docs
```

---

## Frontend Setup

From the repository root:

```bash
cd frontend
npm install
npm run dev
```

Frontend default URL:

```txt
http://127.0.0.1:5173
```

---

## Running the Full Application Locally

Run the backend and frontend in separate terminal windows.

### Terminal 1 — Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd server
uvicorn app.main:app --reload
```

On Windows, use the appropriate virtual environment activation command shown above.

### Terminal 2 — Frontend

```bash
cd frontend
npm install
npm run dev
```

Then open the frontend in your browser:

```txt
http://127.0.0.1:5173
```

---

## Environment Variables

The project uses environment variables for backend and frontend configuration.

### Frontend

To customize the backend API URL used by the frontend, set:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Because this project uses Vite, frontend environment variables must begin with `VITE_`.

### Backend

Important backend environment variables include:

```env
MONGODB_URI=your_mongodb_connection_string
MONGODB_DB_NAME=auction_system
CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
DEV_ADMIN_EMAILS=admin@example.com
DEV_DEFAULT_KOGBUCKS=1000
```

The backend also supports configurable collection names for users, items, auctions, bids, auction messages, chat messages, wishlist entries, and WebSocket outbox events.

---

## Development Notes

- The frontend and backend are intentionally separated into their own folders.
- The frontend uses React Router for page navigation and route protection.
- The backend exposes API routers for authentication, users, auctions, bids, items, and wishlist functionality.
- MongoDB is required for the full backend feature set.
- WebSockets are used for real-time auction-room behavior.
- Background backend tasks manage auction expiration and inactivity-related processing.
- The app includes both regular-user and administrator workflows.

---

## Current Status

The application is complete for the SE3350 Team 07 project submission.

It is a working full-stack live bidding web app with implemented frontend pages, backend APIs, database-backed auction state, real-time bidding-room functionality, and administrative tools.

---

## Possible Future Improvements

Potential future improvements include:

- Production deployment configuration
- Stronger authentication and authorization hardening
- More detailed automated test coverage
- More robust error handling and logging
- Improved accessibility testing
- CI/CD pipeline setup
- Expanded reporting for auction results
- More advanced admin analytics
- Email delivery integration for production OTP flows
- More granular audit logs for bidding and admin actions

---

## Team

SE3350 Group Project — Team 07

This project was developed collaboratively over approximately three months.

---

## License

This project was created for academic purposes as part of SE3350.
