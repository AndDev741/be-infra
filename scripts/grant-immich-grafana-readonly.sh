#!/usr/bin/env bash
# Lets grafana_readonly (apps/immich/postgres.yaml) SELECT the Immich tables
# the bePresent dashboard reads, and nothing else: no users, sessions, API
# keys, shared links. CloudNativePG creates the role; the grants are SQL.
# Safe to rerun, and rerun it after an Immich upgrade if a dashboard panel
# says "permission denied" (a migration can recreate a table).
set -euo pipefail
tables=(asset asset_exif asset_job_status asset_file asset_video asset_face
        person album album_asset tag tag_asset smart_search stack)
sql="GRANT USAGE ON SCHEMA public TO grafana_readonly;"
for t in "${tables[@]}"; do sql+=" GRANT SELECT ON public.\"$t\" TO grafana_readonly;"; done
kubectl -n immich exec immich-pg-1 -c postgres -- psql -U postgres -d immich -v ON_ERROR_STOP=1 -c "$sql"
