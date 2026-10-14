#!/usr/bin/env bash
# One-off: creates an Immich API key that can only read and pause/resume job
# queues, and writes it to apps/immich/secrets/immich-ml-scheduler.sops.yaml.
# Asks for an admin API key (used once, not stored). Nothing is printed.
set -euo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
out=apps/immich/secrets/immich-ml-scheduler.sops.yaml
url="${IMMICH_URL:-https://immich.tail2f18c7.ts.net}"
read -rsp "Immich admin API key: " admin_key
echo
mkdir -p "$(dirname "$out")"
ADMIN_KEY="$admin_key" URL="$url" python3 -I -c '
import json, os, urllib.request
req = urllib.request.Request(os.environ["URL"] + "/api/api-keys", method="POST",
    data=json.dumps({"name": "ml-scheduler (be-infra)", "permissions": ["queue.read", "queue.update"]}).encode(),
    headers={"x-api-key": os.environ["ADMIN_KEY"], "content-type": "application/json"})
secret = json.load(urllib.request.urlopen(req, timeout=30))["secret"]
print(json.dumps({"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
                  "metadata": {"name": "immich-ml-scheduler", "namespace": "immich"},
                  "stringData": {"api-key": secret}}))
' | sops --encrypt --input-type json --output-type yaml --filename-override "$out" /dev/stdin > "$out.new"
mv "$out.new" "$out"
echo "wrote $out"
