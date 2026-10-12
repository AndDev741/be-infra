#!/usr/bin/env bash
# One-off: builds apps/beyou/secrets/beyou-backup.sops.yaml from what the compose
# backup used (Beyou-dev-env/.env and the root-only restic password file), so the
# in-cluster backup writes to the same restic repository.
#
# Nothing is printed: the values go from the files straight into sops.
# Run it in your own terminal (it asks for sudo to read the restic password).
set -euo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
env_file="${1:-$HOME/beyou/Beyou-dev-env/.env}"
out=apps/beyou/secrets/beyou-backup.sops.yaml

pw_file="$(sed -nE 's/^RESTIC_PASSWORD_FILE=["'\'']?([^"'\'']*)["'\'']?$/\1/p' "$env_file")"
RESTIC_PASSWORD="$(sudo cat "$pw_file")" \
PGPASSWORD="$(sops -d --extract '["stringData"]["password"]' data/secrets/beyou-db-owner.sops.yaml)" \
ENV_FILE="$env_file" python3 -I -c '
import json, os, sys
env = {}
for line in open(os.environ["ENV_FILE"]):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line: continue
    k, v = line.split("=", 1)
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'\''": v = v[1:-1]
    env[k] = v
data = {k: env[k] for k in ("RESTIC_REPOSITORY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                             "BACKUP_HEARTBEAT_URL", "BACKUP_RESTORE_HEARTBEAT_URL")}
data["BACKUP_MAX_REPO_GB"] = env.get("BACKUP_MAX_REPO_GB", "5")
data["RESTIC_PASSWORD"] = os.environ["RESTIC_PASSWORD"]
data.update(PGHOST="pg-rw.data.svc", PGDATABASE="beyou", PGUSER="beyou", PGPASSWORD=os.environ["PGPASSWORD"])
assert all(data.values()), "a value is empty"
json.dump({"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
           "metadata": {"name": "beyou-backup", "namespace": "beyou"}, "stringData": data}, sys.stdout)
' | sops --encrypt --input-type json --output-type yaml --filename-override "$out" /dev/stdin > "$out.new"
mv "$out.new" "$out"
echo "wrote $out ($(grep -c "ENC\[" "$out") encrypted values)"
