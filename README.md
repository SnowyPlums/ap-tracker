# Archipelago Tracker

Self-hosted Archipelago room tracking with a Next.js frontend, FastAPI
backend, PostgreSQL persistence, and live WebSocket updates.

## Deploy with Docker Compose

1. Copy this project to the Unraid server.
2. Copy .env.example to .env.
3. Set AP_TRACKER_DATABASE_URL to the PostgreSQL URL. URL-encode special
   password characters in the URL (@ becomes %40 and $ becomes %24).
4. Set AP_TRACKER_SECRET_KEY to a long random value.
5. Set AP_TRACKER_CORS_ORIGINS to the frontend origin.
6. Set AP_TRACKER_PUBLIC_API_URL to the API address visible from users'
   browsers. For direct LAN access use http://serverip:8000. If Nginx
   Proxy Manager or Cloudflare routes /api and /ws on the same hostname, leave
   this empty and use the same-origin setup.
7. Start the stack:

       docker compose up -d --build

8. Apply database migrations:

       docker exec ap-tracker-api alembic upgrade head

The frontend is exposed on port 3000 and the API on port 8000. Nginx Proxy
Manager can proxy the frontend and API separately, including WebSocket
traffic for /ws/.

The frontend reads AP_TRACKER_PUBLIC_API_URL at container startup, so changing
the value only requires recreating the frontend container:

       docker compose up -d --force-recreate ap-tracker-web

## Accounts and access

The dashboard is public, but creating or joining rooms requires an account.
The first registered account becomes the administrator and can see all rooms.
Other users only see rooms where they are members.

Each room has a random player invite code and a separate random view-only
link. Viewer responses intentionally omit the Archipelago connection address,
connection status, and all management actions.

## Testing

The new backend and frontend can be tested independently before deployment:

       docker exec ap-tracker-api python -m unittest discover -s /app/tests -v
       curl http://127.0.0.1:8000/health

See BACKEND_TESTING.md for REST and WebSocket smoke tests.
