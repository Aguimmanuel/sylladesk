#!/bin/sh
# The restore path the drill (DoD #6) exercises. From backups ALONE into an empty stack.
# Usage: DATABASE_URL=... RESTIC_REPOSITORY=... RESTIC_PASSWORD=... scripts/restore.sh <snapshot-id|latest>
set -eu
SNAP="${1:?snapshot id or 'latest'}"
WORKDIR="${RESTORE_WORKDIR:-/tmp/lms-restore}"
mkdir -p "$WORKDIR"
echo "[restore] fetching snapshot $SNAP ..."
restic restore "$SNAP" --target "$WORKDIR"
SQLFILE="$(ls -t "$WORKDIR"/tmp/lms-backup/db-*.sql 2>/dev/null | head -1 || ls -t "$WORKDIR"/db-*.sql | head -1)"
echo "[restore] loading $SQLFILE into $DATABASE_URL ..."
psql "$DATABASE_URL" -f "$SQLFILE"
echo "[restore] done. Verify with /healthz and a real login."
