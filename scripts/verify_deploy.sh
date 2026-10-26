#!/usr/bin/env bash
# Smoke-test a deployment end to end: UI shell, every API endpoint, validation, docs,
# caching, and (if the local backend venv exists) that production numbers match local.
#
# Usage: scripts/verify_deploy.sh https://your-app.vercel.app     (or: make verify URL=...)
set -uo pipefail

BASE="${1:?usage: scripts/verify_deploy.sh <base-url>}"
BASE="${BASE%/}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_PY="$ROOT/backend/.venv/bin/python"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAILS=0

ok() { printf "  \033[32mPASS\033[0m %s\n" "$1"; }
bad() { printf "  \033[31mFAIL\033[0m %s\n" "$1"; FAILS=$((FAILS + 1)); }

# fetch NAME PATH -> writes $TMP/NAME.body and $TMP/NAME.headers, echoes "status seconds"
fetch() {
  curl -sS -o "$TMP/$1.body" -D "$TMP/$1.headers" -w '%{http_code} %{time_total}' "$BASE$2" 2>"$TMP/$1.err" || echo "000 0"
}
header() { grep -i "^$2:" "$TMP/$1.headers" | tail -1 | cut -d' ' -f2- | tr -d '\r'; }
# jq-free JSON assertions: py NAME 'python expression over b' -> prints result
py() { python3 -I -c "import json,sys; b=json.load(open('$TMP/$1.body')); print($2)"; }

check() { # check NAME PATH EXPECTED_STATUS DESCRIPTION
  read -r status secs < <(fetch "$1" "$2")
  if [ "$status" = "$3" ]; then ok "$4  [$status, ${secs}s]"; else bad "$4  [got $status, want $3] $(head -c 200 "$TMP/$1.body")"; fi
}

echo "Verifying $BASE"
echo "UI"
check index "/" 200 "GET / serves the app shell"
grep -q '<div id="root">' "$TMP/index.body" && ok "index.html has the React root" || bad "index.html missing #root"
ASSET="$(grep -oE '/assets/[^"]+\.js' "$TMP/index.body" | head -1)"
[ -n "$ASSET" ] && check asset "$ASSET" 200 "JS bundle $ASSET" || bad "no JS asset referenced"
check deeplink "/?start=2026-01-10&end=2026-01-16&mode=horizon&horizon_h=6" 200 "shareable URL with filters"

echo "API"
check health "/api/health" 200 "GET /api/health"
[ "$(py health "b['status']")" = ok ] && ok "health status ok" || bad "health status not ok"
if [ -f "$ROOT/data/manifest.json" ]; then
  want="$(python3 -I -c "import json; print(json.load(open('$ROOT/data/manifest.json'))['snapshot_id'])")"
  got="$(py health "b['snapshot_id']")"
  [ "$got" = "$want" ] && ok "deployed snapshot_id $got matches repo data/" || bad "snapshot_id $got != repo $want"
fi
[ "$(header health cache-control)" = "no-store" ] && ok "health is not cached" || bad "health cache-control: $(header health cache-control)"

check meta "/api/meta" 200 "GET /api/meta"
[ "$(py meta "b['date_range']['first_delivery_day'] + '..' + b['date_range']['last_delivery_day']")" = "2026-01-02..2026-02-01" ] \
  && ok "date range 2026-01-02..2026-02-01" || bad "unexpected date range"

check series "/api/series" 200 "GET /api/series (day-ahead default)"
[ "$(py series "len(b['points'])")" = 744 ] && ok "744 hourly points" || bad "series points: $(py series "len(b['points'])")"
check series_h "/api/series?mode=horizon&horizon_h=6" 200 "GET /api/series?mode=horizon&horizon_h=6"

check metrics "/api/metrics" 200 "GET /api/metrics"
echo "       $(py metrics "f\"MAE {b['overall']['mae_mw']:.0f} MW, bias {b['overall']['bias_mw']:+.0f} MW, \" + b['buffer']['levels'][0]['message']")"
cc="$(header metrics cache-control)"
[[ "$cc" == *"s-maxage="* ]] && ok "metrics CDN-cacheable ($cc)" || bad "metrics cache-control: $cc"

check byhour "/api/metrics/by-hour" 200 "GET /api/metrics/by-hour"
[ "$(py byhour "len(b['hours'])")" = 24 ] && ok "24 hours of day" || bad "by-hour count"
check byhorizon "/api/metrics/by-horizon" 200 "GET /api/metrics/by-horizon"
[ "$(py byhorizon "len(b['points'])")" = 48 ] && ok "48 horizons" || bad "by-horizon count"

echo "Validation"
check bad1 "/api/series?mode=horizon" 422 "missing horizon_h -> 422"
[ "$(py bad1 "b['detail'][0]['loc'][-1]")" = horizon_h ] && ok "422 names the horizon_h parameter" || bad "422 loc wrong"
check bad2 "/api/metrics?start=2025-12-01" 422 "date outside snapshot -> 422"
check bad3 "/api/series?horizon=6" 422 "unknown parameter -> 422"
[ "$(header bad1 cache-control)" = "no-store" ] && ok "errors are not cached" || bad "422 cache-control: $(header bad1 cache-control)"

echo "Docs"
check docs "/api/docs" 200 "Swagger UI at /api/docs"
check openapi "/api/openapi.json" 200 "OpenAPI schema"

echo "Caching (repeat request)"
read -r _ secs < <(fetch metrics2 "/api/metrics")
vc="$(header metrics2 x-vercel-cache)"
echo "       repeat /api/metrics: ${secs}s, x-vercel-cache=${vc:-n/a} (HIT/STALE = served from the CDN)"

if [ -x "$LOCAL_PY" ]; then
  echo "Production vs local"
  if (cd "$ROOT/backend" && LOG_LEVEL=WARNING "$LOCAL_PY" - "$TMP/metrics.body" <<'EOF'
import json, sys, warnings
warnings.filterwarnings("ignore")
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
local = TestClient(create_app(Settings(log_level="WARNING"))).get("/api/metrics").json()
prod = json.load(open(sys.argv[1]))
keys = ("coverage", "overall", "distribution", "buffer")
diff = [k for k in keys if local[k] != prod[k]]
print("       identical: " + ", ".join(k for k in keys if k not in diff))
sys.exit(1 if diff else 0)
EOF
  ) >"$TMP/cmp.out" 2>&1; then cat "$TMP/cmp.out"; ok "production /api/metrics equals local computation"
  else cat "$TMP/cmp.out"; bad "production /api/metrics differs from local"; fi
fi

echo
if [ "$FAILS" -eq 0 ]; then echo "All checks passed."; else echo "$FAILS check(s) failed."; fi
exit "$FAILS"
