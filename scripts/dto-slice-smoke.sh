#!/bin/sh
# Newsletter slice smoke test against the PostgreSQL lane (http://pg.localhost:8088).
# usage: scripts/dto-slice-smoke.sh dal|sql
# Selects the adapter with SHOPWARE_NEWSLETTER_RECIPIENT_STORAGE (read when the container is compiled), clears the cache, runs the cycle and prints "step -> http code error-code".
set -e
case "$1" in dal|sql) ;; *) echo "usage: $0 dal|sql"; exit 1 ;; esac
podman exec -e SHOPWARE_NEWSLETTER_RECIPIENT_STORAGE="$1" instance-web-1 bin/console cache:clear -q
PSQL="podman exec instance-postgres-1 psql -U shopware -At -c"
E="smoke-$1-$(date +%s)@example.com"
call() { # label method path json
  code=$(curl -s -o /tmp/smoke-body.json -w '%{http_code}' -X "$2" "http://pg.localhost:8088/store-api$3" \
    -H "sw-access-key: SWSCAWRXZ21RCTF1OE5NYNHJTA" -H 'Content-Type: application/json' -H 'Accept: application/json' -d "$4")
  echo "$1 -> $code $(python3 -I "$(dirname "$0")/smoke-body.py")"
}
call "subscribe new" POST /newsletter/subscribe "{\"email\":\"$E\",\"option\":\"subscribe\",\"storefrontUrl\":\"http://pg.localhost:8088\",\"firstName\":\"Smoke\"}"
call "subscribe again" POST /newsletter/subscribe "{\"email\":\"$E\",\"option\":\"subscribe\",\"storefrontUrl\":\"http://pg.localhost:8088\",\"lastName\":\"Again\"}"
call "subscribe invalid email" POST /newsletter/subscribe '{"email":"nope","option":"subscribe","storefrontUrl":"http://pg.localhost:8088"}'
call "subscribe invalid option" POST /newsletter/subscribe "{\"email\":\"$E\",\"option\":\"bogus\",\"storefrontUrl\":\"http://pg.localhost:8088\"}"
call "subscribe bad storefrontUrl" POST /newsletter/subscribe "{\"email\":\"$E\",\"option\":\"subscribe\",\"storefrontUrl\":\"http://evil.example\"}"
H=$($PSQL "select hash from newsletter_recipient where email='$E'")
EM=$(printf '%s' "$E" | shasum | cut -d' ' -f1)
call "confirm wrong em" POST /newsletter/confirm "{\"hash\":\"$H\",\"em\":\"x\"}"
call "confirm unknown hash" POST /newsletter/confirm '{"hash":"unknown","em":"x"}'
call "confirm" POST /newsletter/confirm "{\"hash\":\"$H\",\"em\":\"$EM\"}"
call "confirm twice" POST /newsletter/confirm "{\"hash\":\"$H\",\"em\":\"$EM\"}"
call "unsubscribe missing email" POST /newsletter/unsubscribe '{}'
call "unsubscribe unknown" POST /newsletter/unsubscribe '{"email":"unknown-smoke@example.com"}'
call "unsubscribe" POST /newsletter/unsubscribe "{\"email\":\"$E\"}"
echo "row: $($PSQL "select status||'|'||coalesce(first_name,'')||'|'||coalesce(last_name,'')||'|'||(confirmed_at is not null) from newsletter_recipient where email='$E'")"
