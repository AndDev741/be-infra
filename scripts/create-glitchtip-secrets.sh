#!/usr/bin/env bash
# One-off: builds the GlitchTip Secrets from Beyou-dev-env/.env (the compose
# stack it moved from) and a new random database password:
#   data/secrets/glitchtip-db-owner.sops.yaml   role glitchtip in the shared Postgres
#   apps/glitchtip/secrets/glitchtip.sops.yaml  DATABASE_URL, SECRET_KEY, mail settings
# Nothing is printed: the values go straight into sops.
set -euo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
env_file="${1:-$HOME/beyou/Beyou-dev-env/.env}"

enc() { sops --encrypt --input-type json --output-type yaml --filename-override "$1" /dev/stdin > "$1.new" && mv "$1.new" "$1"; }

DB_PASSWORD="$(openssl rand -hex 24)"
export DB_PASSWORD ENV_FILE="$env_file"

python3 -I -c '
import json, os
print(json.dumps({"apiVersion": "v1", "kind": "Secret", "type": "kubernetes.io/basic-auth",
                  "metadata": {"name": "glitchtip-db-owner", "namespace": "data"},
                  "stringData": {"username": "glitchtip", "password": os.environ["DB_PASSWORD"]}}))
' | enc data/secrets/glitchtip-db-owner.sops.yaml

python3 -I -c '
import json, os
env = {}
for line in open(os.environ["ENV_FILE"]):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line: continue
    k, v = line.split("=", 1)
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'\''": v = v[1:-1]
    env[k] = v
data = {
    "DATABASE_URL": "postgres://glitchtip:%s@pg-rw.data.svc:5432/glitchtip" % os.environ["DB_PASSWORD"],
    "SECRET_KEY": env["GLITCHTIP_SECRET_KEY"],
    "EMAIL_URL": env["GLITCHTIP_EMAIL_URL"],
    "DEFAULT_FROM_EMAIL": env["GLITCHTIP_FROM_EMAIL"],
}
assert all(data.values()), "a value is empty"
print(json.dumps({"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
                  "metadata": {"name": "glitchtip", "namespace": "glitchtip"}, "stringData": data}))
' | enc apps/glitchtip/secrets/glitchtip.sops.yaml
echo "wrote the glitchtip Secrets"
