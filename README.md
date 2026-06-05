# Live Bidding Web App

**Live Bidding Web App** is a full-stack auction platform built for the SE3350 Team 07 course project. It combines a FastAPI backend, MongoDB persistence, WebSocket-based auction rooms, and a React + TypeScript frontend so users can authenticate, browse auctions, join invited live rooms, place bids with a virtual currency called Kogbucks, chat during auctions, manage wishlists, and review won items while administrators manage users, items, auctions, invitations, and auction lifecycle controls. **Status:** complete academic prototype / local-development application, not a production deployment. The fastest way to inspect it is to run the backend from `backend/server` with `uvicorn app.main:app --reload`, run the frontend from `frontend` with `npm run dev`, then review the FastAPI docs at `http://127.0.0.1:8000/docs` and the React app at `http://127.0.0.1:5173`.

## Table of contents

- [Problem and purpose](#problem-and-purpose)
- [Project status](#project-status)
- [Fastest way to run or inspect](#fastest-way-to-run-or-inspect)
- [Architecture and approach](#architecture-and-approach)
- [Repository structure](#repository-structure)
- [Core user flows](#core-user-flows)
- [Representative API and WebSocket usage](#representative-api-and-websocket-usage)
- [Validation and testing](#validation-and-testing)
- [Data, persistence, and environment assumptions](#data-persistence-and-environment-assumptions)
- [Inputs and outputs](#inputs-and-outputs)
- [Performance and real-time notes](#performance-and-real-time-notes)
- [Reproducibility notes](#reproducibility-notes)
- [Design rationale](#design-rationale)
- [Limitations and failure cases](#limitations-and-failure-cases)
- [What I would improve next](#what-i-would-improve-next)
- [Collaborators and credit](#collaborators-and-credit)
- [License / academic use](#license--academic-use)

## Problem and purpose

Live auctions are stateful, concurrent, and role-sensitive: users need to see the same auction state at nearly the same time, bids must update balances and item status consistently, administrators need controls for scheduling and inventory, and the system must avoid giving every user access to every auction. This project addresses that problem with a separated frontend/backend architecture: React handles protected user/admin interfaces, FastAPI exposes auction/auth/item/user/bid/wishlist APIs, MongoDB stores auction state and related records, and WebSockets broadcast live room events such as bid placement, participant joins, chat messages, state refreshes, and auction endings.

## Project status

| Area | Current status | Evidence in repository |
| --- | --- | --- |
| Frontend app | Implemented | React + TypeScript + Vite project in `frontend/` |
| Backend API | Implemented | FastAPI application in `backend/server/app/main.py` |
| Authentication | Implemented for local/dev workflows | OTP request/verify routes, JWT/cookie support, dev OTP endpoint |
| User/admin routing | Implemented | Protected React routes split user pages from admin pages |
| Auction lifecycle | Implemented | Create/start/join/invite/state/end behavior through auction services/routes |
| Real-time updates | Implemented | WebSocket rooms under `/ws/auctions/{auction_id}` |
| Persistence | Implemented through MongoDB | MongoDB collections for users, items, auctions, bids, messages, chat, wishlist, and outbox |
| Background tasks | Implemented | Auto-end loop, inactivity loop, and WebSocket outbox dispatcher |
| Testing | Partial / underdeveloped | Backend includes `pytest` and `httpx` dependencies, but no full committed automated test suite was found during inspection |
| Deployment | Not implemented | No Docker Compose, production hosting config, CI/CD, or cloud deployment scripts included |

## Fastest way to run or inspect

### Prerequisites

- Python 3.9+
- Node.js 18+
- npm
- MongoDB, either local or hosted

### 1. Configure backend environment

Create `backend/server/.env` or export equivalent environment variables:

```env
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=auction_system
CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
AUTH_DEV_MODE=true
DEV_ADMIN_EMAILS=admin@example.com
DEV_DEFAULT_KOGBUCKS=1000
```

Optional collection overrides are supported for users, items, auctions, bids, auction messages, chat messages, wishlist entries, OTPs, and WebSocket outbox events.

### 2. Run the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd server
uvicorn app.main:app --reload
```

Backend:

```text
http://127.0.0.1:8000
```

API docs:

```text
http://127.0.0.1:8000/docs
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"ok": true}
```

### 3. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend:

```text
http://127.0.0.1:5173
```

### 4. Development login path

With `AUTH_DEV_MODE=true`, local OTP testing is easier:

1. Request an OTP from the frontend login page or `POST /auth/otp/request`.
2. Read the code from the development endpoint:

```text
GET /dev/otp/{email}
```

3. Verify the OTP through the frontend or `POST /auth/otp/verify`.
4. Use an email listed in `DEV_ADMIN_EMAILS` for admin access.

## Architecture and approach

```mermaid
flowchart TD
    U[User / Admin Browser] --> F[React + TypeScript Frontend]
    F -->|REST API| A[FastAPI Backend]
    F -->|WebSocket| W[/ws/auctions/{auction_id}/]
    A --> M[(MongoDB)]
    A --> S[AuctionService]
    S --> M
    S --> O[MongoDB WebSocket Outbox]
    O --> D[WsOutboxDispatcher]
    D --> W
    A --> BG[Background Tasks]
    BG --> S
    W --> F
```

The application is intentionally split into independent frontend and backend projects. The frontend owns navigation, route protection, user/admin pages, and interaction flows. The backend owns authentication, authorization checks, auction rules, persistence, WebSocket room management, bid/event processing, and background lifecycle tasks.

<details>
<summary>Backend modules to inspect first</summary>

- `backend/server/app/main.py` — FastAPI app creation, MongoDB setup, CORS, dependency overrides, background tasks, router registration, health check, and dev OTP endpoint.
- `backend/server/app/auth/` — OTP login, JWT/cookie handling, current-user dependencies, and auth services.
- `backend/server/app/auction/auction_router.py` — auction creation, start, state, join, invitations, dashboard, chat, and admin/user auction flows.
- `backend/server/app/auction/auction_ws.py` — WebSocket event contract, room manager, access checks, initial snapshots, ping/pong, and sync requests.
- `backend/server/app/auction/ws_outbox.py` — database-backed outbox dispatcher for queued WebSocket events.
- `backend/server/app/bids/` — bid placement and bid-related state changes.
- `backend/server/app/items/` — item creation and management.
- `backend/server/app/users/` — user and Kogbucks-facing operations.
- `backend/server/app/wishlist/` — wishlist records and related APIs.

</details>

<details>
<summary>Frontend modules to inspect first</summary>

- `frontend/src/main.tsx` — React/Vite entry point and browser router setup.
- `frontend/src/app/App.tsx` — route map for auth, user pages, and admin pages.
- `frontend/src/components/ProtectedRoute.tsx` — authentication guard.
- `frontend/src/components/AdminRoute.tsx` — admin-only route guard.
- `frontend/src/components/UserRoute.tsx` — regular user route guard.
- `frontend/src/app/pages/BiddingRoom.tsx` — user bidding-room experience.
- `frontend/src/app/pages/admin/AdminBiddingRoom.tsx` — admin room experience.
- `frontend/src/app/pages/admin/` — auction, item, user, Kogbucks, wishlist, and past-auction administration.

</details>

## Repository structure

```text
.
├── backend/
│   ├── requirements.txt
│   └── server/
│       └── app/
│           ├── main.py
│           ├── auth/
│           ├── auction/
│           ├── bids/
│           ├── items/
│           ├── users/
│           ├── wishlist/
│           └── helper/
├── frontend/
│   ├── package.json
│   └── src/
│       ├── app/
│       ├── components/
│       ├── api/
│       └── styles.css
└── README.md
```

## Core user flows

### Regular user flow

1. User requests and verifies an OTP.
2. User lands on the dashboard and sees profile/balance information.
3. User browses available auctions.
4. User joins an auction they were invited to.
5. User opens a live bidding room.
6. User receives an initial WebSocket snapshot.
7. User places bids, views bid history, receives room events, and uses chat.
8. User reviews won items and balance changes.

### Admin flow

1. Admin signs in using an email configured through `DEV_ADMIN_EMAILS` or the production-equivalent admin mechanism.
2. Admin creates auctions and sets timing.
3. Admin creates/edits items and assigns items to auctions.
4. Admin invites users to auctions.
5. Admin starts or monitors live auctions.
6. Background tasks and WebSocket events keep room state synchronized.
7. Admin reviews users, Kogbucks, wishlists, and past auction results.

## Representative API and WebSocket usage

### Request OTP

```bash
curl -X POST http://127.0.0.1:8000/auth/otp/request \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com"}'
```

The backend intentionally returns `204 No Content` even on some request failures to avoid leaking whether an account exists.

### Verify OTP

```bash
curl -X POST http://127.0.0.1:8000/auth/otp/verify \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","code":"123456"}'
```

Depending on JWT settings, the backend either returns an access token in JSON or sets an HTTP-only cookie.

### Health check

```bash
curl http://127.0.0.1:8000/health
```

### WebSocket room contract

The WebSocket endpoint is:

```text
/ws/auctions/{auction_id}
```

The backend emits stable event envelopes such as:

```json
{
  "type": "auction.state_updated",
  "auction_id": "...",
  "server_time": "...",
  "state": {}
}
```

Supported event concepts include:

- `auction.connected`
- `auction.started`
- `auction.ended`
- `auction.state_updated`
- `auction.timer_extended`
- `auction.invites_updated`
- `auction.participant_joined`
- `auction.chat_message`
- `bid.placed`
- `auction.snapshot`

The room access check is role-sensitive: admins can enter, while regular users must be invited, the auction must be running, and the user must have joined before opening the live channel.

## Validation and testing

### What is currently verifiable

Manual/local validation paths:

```bash
# Backend dependency/install check
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd server
uvicorn app.main:app --reload
```

```bash
# Backend health check
curl http://127.0.0.1:8000/health
```

```bash
# Frontend TypeScript build check
cd frontend
npm install
npm run build
```

```bash
# Frontend local run
npm run dev
```

### Automated testing status

The backend dependency list includes `pytest` and `httpx`, which are appropriate for FastAPI route testing, but a full committed automated test suite was not found during README inspection. The frontend currently exposes Vite scripts for `dev`, `build`, and `preview`, but no committed test script is listed in `package.json`.

### Recommended validation checklist for reviewers

- Confirm backend starts with MongoDB configured.
- Confirm `/health` returns `{"ok": true}`.
- Confirm `/docs` renders FastAPI OpenAPI docs.
- Confirm OTP request/verify works in development mode.
- Confirm admin route access with an email in `DEV_ADMIN_EMAILS`.
- Create at least one user, item, and auction.
- Invite a user to an auction.
- Start the auction.
- Join the auction as the invited user.
- Open two browsers and confirm WebSocket state updates after a bid.
- Confirm auction end distributes results and updates item/user state.

## Data, persistence, and environment assumptions

### MongoDB collections

The backend resolves collection names from environment variables and defaults to collections such as:

- `users`
- `items`
- `auctions`
- `bids`
- `auction_messages`
- `auction_chat_messages`
- `wishlist`
- `ws_outbox`
- `otps`

### Data assumptions

- Users have roles, typically `rep` or `admin`.
- Kogbucks are represented as virtual balances stored on user records.
- Auctions have statuses such as upcoming/running/ended depending on service state.
- Regular users cannot freely enter every live room; invitation and join state matter.
- Items can move through auction states such as live, temporarily owned, pre-sold, and sold.
- WebSocket outbox records are persisted before dispatch so room updates can be coordinated with backend state changes.

### Required environment variables

```env
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=auction_system
CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
AUTH_DEV_MODE=true
DEV_ADMIN_EMAILS=admin@example.com
DEV_DEFAULT_KOGBUCKS=1000
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Inputs and outputs

| Type | Input/output | Description |
| --- | --- | --- |
| Input | User email + OTP | Authentication flow |
| Input | Auction/item/admin forms | Create and update platform state |
| Input | Bid amount / selected item | Live auction action |
| Input | Chat messages | Room communication |
| Output | JWT/cookie + profile | Authenticated session |
| Output | Auction state | Current status, participants, items, bids, timers |
| Output | WebSocket events | Real-time updates to auction room clients |
| Output | Kogbucks state | Available/held/committed user balances |
| Output | Wishlist entries | User item-interest tracking |
| Output | Auction results | Won items, winner state, final bid amounts |

## Performance and real-time notes

- WebSocket clients are grouped by `auction_id` in memory.
- Broadcast fan-out sends one JSON-safe payload to every socket in a room.
- The outbox dispatcher polls MongoDB for pending events, claims them, broadcasts them, and marks them sent.
- Dispatcher settings such as poll interval and batch size are configurable through environment variables.
- Background tasks poll for auction auto-end and inactivity notifications.
- This architecture is appropriate for a course-scale prototype, but a multi-instance production deployment would need shared pub/sub or a distributed WebSocket/event layer because in-memory room membership does not automatically span server processes.

## Reproducibility notes

- Backend dependencies are listed in `backend/requirements.txt`.
- Frontend dependencies and scripts are listed in `frontend/package.json`.
- The app requires MongoDB to exercise the full backend feature set.
- The repo does not currently include a Docker Compose file for MongoDB + backend + frontend.
- The repo does not currently include a seed script for creating known users, auctions, and items.
- Development OTP support can make local inspection easier, but it should not be enabled in production.
- Results and UI state depend on MongoDB contents; reviewers may need to create sample records manually through the API/admin UI.

## Design rationale

### Why FastAPI?

FastAPI provides typed request/response models, automatic OpenAPI docs, dependency injection, async handlers, and native WebSocket support. Those features make it a good fit for a course-scale app that needs both REST APIs and live auction rooms.

### Why React + TypeScript + Vite?

React supports a component-based UI for separate user/admin workflows. TypeScript makes route props, API payloads, and UI state safer to refactor. Vite keeps the local development loop fast.

### Why MongoDB?

Auction rooms, bids, messages, wishlists, and user balances can be represented as document records with flexible shapes during prototyping. MongoDB also integrates cleanly with FastAPI through Motor for async access.

### Why a WebSocket outbox?

Directly broadcasting after every write can couple persistence and live delivery too tightly. The outbox pattern gives the backend a database-backed event queue, making event dispatch more inspectable and recoverable than ad hoc broadcasts alone.

### Why separate user and admin routes?

The app has two distinct products in one system: a bidder experience and an auction-management console. Separating route guards and page groups makes permission boundaries clearer and reduces accidental exposure of admin controls.

## Limitations and failure cases

| Limitation | Why it matters | What would fix it |
| --- | --- | --- |
| No committed seed data/script | A fresh reviewer may not have users, items, or auctions to inspect | Add seed script with sample admin, users, items, auctions, and bids |
| Limited automated tests | Harder to prove bid, balance, and lifecycle correctness | Add pytest route/service tests and frontend component/e2e tests |
| No Docker Compose | Setup depends on local MongoDB configuration | Add Docker Compose for MongoDB, backend, and frontend |
| Development OTP mode | Useful locally but unsafe if left on in production | Document production auth settings and enforce safe defaults |
| In-memory WebSocket rooms | Does not scale across multiple backend instances | Add Redis/pub-sub or managed event broker |
| No CI/CD | Builds/tests are not automatically enforced | Add GitHub Actions for backend tests and frontend build |
| No performance benchmark | Real-time capacity is unknown | Add load tests for concurrent sockets and bid placement |
| No formal data migration/versioning | MongoDB schema changes are implicit | Add migration scripts or schema-versioning strategy |
| No accessibility test report | UI quality is not fully documented | Add keyboard/screen-reader checks and automated accessibility scans |
| No production deployment config | Not ready for real users | Add deployment docs, HTTPS/CORS/auth hardening, logging, monitoring, and secrets management |

## What I would improve next

1. Add a `docker-compose.yml` with MongoDB, backend, and frontend.
2. Add a `seed_demo_data.py` script for deterministic reviewer setup.
3. Add backend pytest coverage for auth, auctions, bid placement, Kogbucks balance changes, wishlist, and auction closing.
4. Add frontend build/test automation and basic e2e tests for user/admin flows.
5. Add WebSocket integration tests for join, snapshot, bid, chat, and reconnect behavior.
6. Add CI that runs backend tests and frontend `npm run build`.
7. Add screenshots or GIFs of dashboard, auction room, admin auction management, item management, and wishlist.
8. Add a production configuration guide for auth, CORS, secrets, SMTP, MongoDB indexes, and logging.
9. Add performance benchmarks for concurrent users per auction room and bid-update latency.
10. Add a short threat model for bidding integrity, admin access, replay attacks, and balance manipulation.

## Collaborators and credit

**SE3350 Group Project — Team 07**

This project was developed collaboratively over approximately three months. Collaborator credit is preserved from the original README:

- [Sihong Liu](https://github.com/Sihong-Liu)
- [anshu-420](https://github.com/anshu-420)
- [Kevin041005](https://github.com/Kevin041005)
- [notarychant](https://github.com/notarychant)

README restructuring and documentation improvements were added later to make the project easier to inspect as a technical due-diligence artifact while preserving collaborator attribution.

## License / academic use

This project was created for academic purposes as part of SE3350. No production license or warranty is implied by this repository.
