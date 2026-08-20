#!/bin/sh
set -eu

# The API imports its tracker during startup, so the schema must exist before
# Uvicorn creates the application lifespan and opens tracker tasks.
alembic upgrade head

exec "$@"
