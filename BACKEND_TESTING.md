# Backend testing
     
The new FastAPI service can be tested before the Next.js frontend is complete.
Run these commands from the directory containing docker-compose.yml on Unraid.
     
## Start and health check
     
    docker compose up -d --build ap-tracker-api
    curl http://127.0.0.1:8000/health
    docker exec ap-tracker-api python -m unittest discover -s /app/tests -v
     
The health response should be {"status":"ok"}. The test command checks the
Archipelago PrintJSON category rendering and hint name resolution without
requiring an active game server.
     
## Exercise the REST API
     
Use a cookie jar so the session remains logged in:
     
    curl -c cookies.txt -H "Content-Type: application/json" -d '{"username":"tester","password":"test1234"}' http://127.0.0.1:8000/api/v1/auth/register
     
    curl -b cookies.txt http://127.0.0.1:8000/api/v1/rooms
     
    curl -b cookies.txt -c cookies.txt -H "Content-Type: application/json" -d '{"label":"Test room","host":"archipelago.gg","port":44487}' http://127.0.0.1:8000/api/v1/rooms
     
Use the returned room_key to request /api/v1/rooms/{room_key}/state.
Create a slot with /api/v1/rooms/{room_key}/slots; the tracker will then
attempt to connect to the configured Archipelago server automatically.
     
## Test live updates
     
The WebSocket endpoint is:
     
    ws://<host>:8000/ws/rooms/<room_key>
     
It requires the same logged-in session cookie and room membership as the REST
API. Open it in a WebSocket client, then add a slot or change a death counter
through the REST API. The client should receive room.updated immediately.
Incoming Archipelago log messages produce room.event.
     
The current WebSocket payload is an invalidation event containing room_id;
the frontend should fetch the latest room state after receiving it. This keeps
the first live API small while allowing the response shape to evolve safely.

