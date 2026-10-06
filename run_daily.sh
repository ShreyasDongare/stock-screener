#!/usr/bin/env bash
# Daily routine. Usage:
#   ./run_daily.sh          fetch new files, rebuild prices, run scans, open dashboard
#   ./run_daily.sh view     skip the update, just open the dashboard
set -e
cd "$(dirname "$0")"
source .venv/bin/activate

if [ "$1" != "view" ]; then
  python fetch_bhav.py
  python build_prices.py
  python run_scans.py
fi

echo
echo "Dashboard: http://localhost:8000/dashboard.html   (Ctrl+C to stop)"
(sleep 1 && xdg-open http://localhost:8000/dashboard.html >/dev/null 2>&1 || true) &
python -m http.server 8000 --bind 127.0.0.1
