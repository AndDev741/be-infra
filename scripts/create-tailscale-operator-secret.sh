#!/usr/bin/env bash
# One-off: builds platform/tailscale/secrets/operator-oauth.sops.yaml from the
# Tailscale OAuth client (admin console > Settings > Trust credentials; write
# on Devices Core, Auth Keys and Services, tagged tag:k8s-operator). Asks for
# both values without echoing them, and nothing is printed.
set -euo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
out=platform/tailscale/secrets/operator-oauth.sops.yaml
read -rp "OAuth client ID: " client_id
read -rsp "OAuth client secret: " client_secret
echo
[ -n "$client_id" ] && [ -n "$client_secret" ] || { echo "both values are needed" >&2; exit 1; }
CLIENT_ID="$client_id" CLIENT_SECRET="$client_secret" python3 -I -c '
import json, os
print(json.dumps({"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
                  "metadata": {"name": "operator-oauth", "namespace": "tailscale"},
                  "stringData": {"client_id": os.environ["CLIENT_ID"],
                                 "client_secret": os.environ["CLIENT_SECRET"]}}))
' | sops --encrypt --input-type json --output-type yaml --filename-override "$out" /dev/stdin > "$out.new"
mv "$out.new" "$out"
echo "wrote $out"
