#!/usr/bin/env bash
# One-off: builds the data-namespace Secrets for the roles that moved from
# befree's own Postgres into the shared one, reusing the passwords the apps
# already have (so only their connection URLs change):
#   befree              <- apps/befree/secrets/befree-db.sops.yaml
#   beconscient         <- apps/beconscient/secrets/beconscient-db.sops.yaml
#   beconscient_backup  <- apps/beconscient/secrets/beconscient-backup.sops.yaml
# Nothing is printed.
set -euo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

secret() {  # <name> <role> <source file> <password key>
  sops -d --output-type json "$3" | NAME="$1" ROLE="$2" KEY="$4" python3 -I -c '
import base64, json, os, sys
d = json.load(sys.stdin)
data = d.get("stringData") or {k: base64.b64decode(v).decode() for k, v in d["data"].items()}
pw = data[os.environ["KEY"]]
assert pw, "empty password"
print(json.dumps({"apiVersion": "v1", "kind": "Secret", "type": "kubernetes.io/basic-auth",
                  "metadata": {"name": os.environ["NAME"], "namespace": "data"},
                  "stringData": {"username": os.environ["ROLE"], "password": pw}}))
' | sops --encrypt --input-type json --output-type yaml --filename-override "data/secrets/$1.sops.yaml" /dev/stdin > "data/secrets/$1.sops.yaml.new"
  mv "data/secrets/$1.sops.yaml.new" "data/secrets/$1.sops.yaml"
}

secret befree-db-owner befree apps/befree/secrets/befree-db.sops.yaml password
secret beconscient-db-owner beconscient apps/beconscient/secrets/beconscient-db.sops.yaml QUARKUS_DATASOURCE_PASSWORD
secret beconscient-db-backup beconscient_backup apps/beconscient/secrets/beconscient-backup.sops.yaml PGPASSWORD
echo "wrote the befree and beconscient role Secrets"
