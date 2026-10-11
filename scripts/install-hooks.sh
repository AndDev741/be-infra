#!/usr/bin/env bash
# Installs a pre-commit hook that runs gitleaks on the staged changes and
# refuses an unencrypted Secret. Run once per clone.
set -euo pipefail
hook="$(git rev-parse --git-path hooks)/pre-commit"
cat > "$hook" <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
gitleaks git --staged --redact --no-banner
for f in $(git diff --cached --name-only --diff-filter=ACM); do
  [ -f "$f" ] || continue
  if grep -qE '^kind: Secret' "$f" && ! grep -q '^sops:' "$f"; then
    echo "refusing $f: a Secret must be encrypted with sops (name it *.sops.yaml)" >&2
    exit 1
  fi
done
HOOK
chmod +x "$hook"
echo "installed $hook"
