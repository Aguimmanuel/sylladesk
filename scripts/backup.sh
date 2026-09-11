#!/bin/sh
# Nightly backup (FR-25): pg_dump + restic snapshot to offsite (Backblaze B2 / R2).
# Run via cron / Render cron job. All config from env — no secrets in this file.
# Required env: DATABASE_URL, RESTIC_REPOSITORY, RESTIC_PASSWORD,
#               B2_ACCOUNT_ID, B2_ACCOUNT_KEY  (or any restic backend vars)
set -eu
STAMP="$(date +%Y%m%d-%H%M%S)"
WORKDIR="${BACKUP_WORKDIR:-/tmp/lms-backup}"
mkdir -p "$WORKDIR"

echo "[backup $STAMP] dumping database..."
pg_dump "$DATABASE_URL" > "$WORKDIR/db-$STAMP.sql"

echo "[backup $STAMP] snapshotting via restic..."
restic snapshots 2>/dev/null >/dev/null || restic init
restic backup "$WORKDIR" --tag lms --tag "nightly-$STAMP"
rm -rf "$WORKDIR"

echo "[backup $STAMP] pruning (30-day retention)..."
restic forget --keep-within 30d --prune
echo "[backup $STAMP] done."
