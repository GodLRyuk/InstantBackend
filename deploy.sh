#!/bin/bash
# Deploy script. Runs ON THE SERVER.
# Called automatically by GitHub Actions, or by hand:  /opt/instant/deploy.sh
#
# What it does:
#   1. pulls the latest backend code   (/opt/instant)
#   2. pulls the latest admin code     (/opt/instant-admin)
#   3. rebuilds and restarts containers (migrations + collectstatic run on start)
#   4. recreates Caddy only if the Caddyfile changed
#   5. checks that both sites answer, otherwise exits with an error
set -euo pipefail

main() {
  local BACKEND_DIR=/opt/instant
  local ADMIN_DIR=/opt/instant-admin

  # Only one deploy at a time. A second one waits here.
  exec 200>/var/lock/instant-deploy.lock
  flock 200

  echo "==> $(date '+%Y-%m-%d %H:%M:%S') Deploy started"

  cd "$BACKEND_DIR"
  local caddy_before
  caddy_before=$(md5sum Caddyfile | cut -d' ' -f1)

  echo "==> Pulling backend"
  git pull --ff-only

  echo "==> Pulling admin"
  git -C "$ADMIN_DIR" pull --ff-only

  echo "==> Building and restarting containers"
  docker compose up -d --build --remove-orphans

  # A bind-mounted file replaced by git is not seen by the running container,
  # so recreate Caddy when the Caddyfile changed.
  local caddy_after
  caddy_after=$(md5sum Caddyfile | cut -d' ' -f1)
  if [ "$caddy_before" != "$caddy_after" ]; then
    echo "==> Caddyfile changed, recreating Caddy"
    docker compose up -d --force-recreate caddy
  fi

  echo "==> Cleaning old images"
  docker image prune -f >/dev/null

  echo "==> Health checks"
  curl -fsS -o /dev/null --max-time 10 --retry 15 --retry-delay 4 --retry-all-errors \
    https://api.instantdelivery.cloud/admin/login/
  echo "    api   OK"
  curl -fsS -o /dev/null --max-time 10 --retry 15 --retry-delay 4 --retry-all-errors \
    https://admin.instantdelivery.cloud/
  echo "    admin OK"

  echo "==> Deploy finished"
  docker compose ps
}

main "$@"
exit $?
