#!/usr/bin/env bash
# One-off: builds apps/omniroute/secrets/omniroute.sops.yaml from the compose
# project's .env (~/omniroute/.env). Nothing is printed. OMNIROUTE_MEMORY_MB is
# left out: the Deployment sets it to fit its memory limit.
set -euo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
env_file="${1:-$HOME/omniroute/.env}"
out=apps/omniroute/secrets/omniroute.sops.yaml
ENV_FILE="$env_file" python3 -I -c '
import json, os
env = {}
for line in open(os.environ["ENV_FILE"]):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line: continue
    k, v = line.split("=", 1)
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'\''": v = v[1:-1]
    env[k] = v
env.pop("OMNIROUTE_MEMORY_MB", None)
assert all(env.values()), "a value is empty"
print(json.dumps({"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
                  "metadata": {"name": "omniroute", "namespace": "omniroute"}, "stringData": env}))
' | sops --encrypt --input-type json --output-type yaml --filename-override "$out" /dev/stdin > "$out.new"
mv "$out.new" "$out"
echo "wrote $out"
