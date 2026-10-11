#!/usr/bin/env bash
# Rotates the password of the `befree` Postgres role (the superuser of the
# instance in the befree namespace, which also holds the beconscient database).
#
# The new password never reaches the terminal or a command line: it lives in a
# shell variable, goes into the sops file through stdin and into Postgres
# through psql's stdin over the pod's local socket.
#
# Order matters: the role is changed first, then the Secret, then the backend
# restarts. Pooled connections stay open across the change, so the only window
# is the backend restart itself.
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

file=apps/befree/secrets/befree-db.sops.yaml
git diff --quiet && git diff --cached --quiet || { echo "working tree not clean" >&2; exit 1; }

new_pw="$(openssl rand -hex 24)"

# 1. New value into the encrypted file
sops -d "$file" | NEW_PW="$new_pw" python3 -c '
import base64, os, re, sys
text = sys.stdin.read()
value = base64.b64encode(os.environ["NEW_PW"].encode()).decode()
text, n = re.subn(r"(?m)^(    password: ).*$", lambda m: m.group(1) + value, text)
assert n == 1, "password key not found"
sys.stdout.write(text)
' | sops --encrypt --input-type yaml --output-type yaml --filename-override "$file" /dev/stdin > "$file.new"
mv "$file.new" "$file"

# 2. Change the role in Postgres
printf "ALTER ROLE befree PASSWORD '%s';\n" "$new_pw" \
  | kubectl -n befree exec -i postgres-0 -- psql -q -U befree -d postgres -v ON_ERROR_STOP=1 -f -
unset new_pw
echo "role password changed"

# 3. Publish the Secret through Flux and restart the backend to read it
git add "$file"
git commit -q -m "Rotate the befree Postgres superuser password"
git push -q
flux reconcile kustomization befree --with-source
kubectl -n befree rollout restart deploy/befree-backend
# The readiness probe is /q/health/ready, which includes the datasource check,
# so a finished rollout means the new pod connected with the new password.
kubectl -n befree rollout status deploy/befree-backend --timeout=180s
echo "befree backend ready with the new password"
