# Production deployment and data recovery

## SQLite backup boundary

`/data/devicepilot.db` is the primary SQLite database.  It is not a backup
location.  Mount a separately persisted host filesystem at
`/var/backups/devicepilot` (and, when the command runs in the backend
container, mount that same filesystem at `/backups`).  A directory below the
primary `/data` mount is deliberately rejected by the backup command.

The backend runs as the fixed non-root identity `10001:10001`.  The host backup
directory is root-owned, group `10001`, searchable and writable by that group;
the setgid bit keeps newly created entries in the backup operator group.  Each
published database and checksum file is owned by `10001:10001` and mode `0600`:

```sh
install -d -o root -g 10001 -m 2770 /var/backups/devicepilot
# Run from the deployed backend image with /var/backups/devicepilot mounted at /backups.
python -m scripts.backup_sqlite \
  --source /data/devicepilot.db \
  --destination /backups
```

The command uses Python's SQLite online-backup API; it never copies a live
database file.  It produces a timestamped `.db` snapshot and adjacent `.sha256`
file only after `PRAGMA integrity_check` succeeds.  Successful output contains
only the two final paths and the SHA-256 digest.  A zero exit confirms the
backup run; a nonzero exit means the run is **unconfirmed**, not that no final
artifact was published.  The utility explicitly sets each final
artifact to `0600`; confirm the owner after changing the container identity or
the host mount.  Do not store backup artifacts in Git.

Publication is an atomic same-filesystem hard-link operation: the temporary
file and timestamped final file are both created in `/backups`.  The backup
mount must therefore support hard links within one filesystem (test this on the
actual mounted filesystem before relying on scheduled backups).  A filesystem
that rejects hard links fails the backup closed rather than falling back to a
non-atomic copy.

The checksum is published before its database so a database final is never
visible without its matching checksum.  A nonzero command can therefore leave
either an orphan timestamped `.sha256` file (for example, database-final
publication failed) or a complete but unconfirmed `.db`/`.sha256` pair (for
example, a temporary-unlink or destination-directory-fsync failure after both
links).  Before retrying, first confirm that no backup process or scheduler is
still active for that destination and timestamp, then inspect the artifacts:

1. An orphan `.sha256` without a same-timestamp `.db` is not a usable backup.
   Record the failed operation and remove only that orphan after confirming no
   active run can still publish its database.
2. For a matching `.db`/`.sha256` pair, compare the checksum to a freshly
   computed SHA-256 and run `PRAGMA integrity_check` against the snapshot in a
   SQLite maintenance environment.  If both are `ok`, record the reconciliation
   and treat it as a recovery point; otherwise record the failure and remove
   the pair only after confirming no active run owns those names.

For example, the same validation used by restore applies to an unconfirmed
pair:

```sh
expected=$(tr -d '\r\n' < /var/backups/devicepilot/devicepilot-<timestamp>.sha256)
actual=$(sha256sum /var/backups/devicepilot/devicepilot-<timestamp>.db | awk '{print $1}')
test "$expected" = "$actual"
sqlite3 /var/backups/devicepilot/devicepilot-<timestamp>.db 'PRAGMA integrity_check;'
```

The final SQLite command must print `ok`.  The utility deliberately does not
delete published final names during recovery because another process could have
replaced the pathname.

On supported POSIX filesystems, the command fsyncs the backup directory after
both final artifacts are published and before reporting success.  Windows has
no portable Python directory-fsync interface; there the command fsyncs each
artifact and uses same-volume atomic hard-link publication, so the operator
must rehearse the backup and restore path on the actual NTFS-backed mount.

After each backup, retain the `10001:10001`-owned, `0600` permissions and copy it to an
encrypted off-host destination.  Retention is 7 daily, 4 weekly, and 3 monthly
recovery points.  Prune only after the off-host copy and checksum verification
have succeeded.  The off-host copy is mandatory: the local backup mount alone
does not protect against host or site loss.

## Restore procedure

Application rollback and database restore are separate operations.  Do not
restore SQLite for an ordinary application rollback.  Restore only for confirmed
data corruption or an incompatible data/schema event.

Use an approved timestamped snapshot and perform this sequence during a
maintenance window:

1. Confirm that the stable named volume exists, then stop the backend so no
   SQLite connection remains open:

   ```sh
   docker volume inspect devicepilot_data
   docker compose -f compose.production.yml stop backend
   ```

2. Preserve the current database in the `devicepilot_data` named volume with a
   dated `devicepilot.db.pre-restore-<UTC timestamp>` name.  Do not delete it;
   it is required for investigation and a possible reversal.
3. Verify the snapshot before installing it.  The checksum file contains one
   digest line, so compare it to a fresh digest (rather than using a filename
   dependent check):

   ```sh
   expected=$(tr -d '\r\n' < /var/backups/devicepilot/devicepilot-<timestamp>.sha256)
   actual=$(sha256sum /var/backups/devicepilot/devicepilot-<timestamp>.db | awk '{print $1}')
   test "$expected" = "$actual"
   ```

4. While the backend remains stopped, use this maintenance command to preserve
   the existing database, copy the verified snapshot into the stable
   `devicepilot_data` volume, and set the fixed backend owner and private mode.
   Substitute the already verified UTC timestamp in both snapshot paths:

   ```sh
   docker run --rm \
     -v devicepilot_data:/data \
     -v /var/backups/devicepilot:/backups:ro \
     alpine:3.21 sh -eu -c '
       cp -p /data/devicepilot.db /data/devicepilot.db.pre-restore-<UTC timestamp>
       expected=$(tr -d "\r\n" < /backups/devicepilot-<UTC timestamp>.sha256)
       actual=$(sha256sum /backups/devicepilot-<UTC timestamp>.db | awk "{print \$1}")
       test "$expected" = "$actual"
       cp /backups/devicepilot-<UTC timestamp>.db /data/devicepilot.db
       chown 10001:10001 /data/devicepilot.db
       chmod 0600 /data/devicepilot.db
     '
   ```
5. Start the backend and wait for readiness:

   ```sh
   docker compose -f compose.production.yml up -d backend
   docker compose -f compose.production.yml exec -T backend python -c \
     "from urllib.request import urlopen; assert urlopen('http://127.0.0.1:8000/health/ready').status == 200"
   ```

6. Inspect representative Device and Fault records through the authenticated UI
   or API, including expected counts and recent fault entries.  Record the
   restore timestamp, source snapshot, checksum, operator, and verification
   result in the operations log.

Chroma is rebuildable and is not restored as part of the SQLite procedure. Only when retrieval data is actually missing or damaged, rebuild it inside the Backend container so production paths are used:

```sh
docker compose -f compose.production.yml exec -T backend \
  python -m scripts.index_knowledge --rebuild
```

The Hugging Face model cache is likewise re-downloadable inside the Backend container. Do not run the production rebuild from the host against an unrelated host-side Chroma path.

## Repeatable local restore rehearsal

Run this rehearsal before production changes and after changes to the backup utility. It uses only a fresh temporary directory; it neither reads nor copies the live DevicePilot database. Every Python command is checked immediately. A failure throws, retains the rehearsal directory as evidence, and skips cleanup.

```powershell
$rehearsal = New-Item -ItemType Directory -Path (Join-Path $env:TEMP ("devicepilot-backup-rehearsal-" + [guid]::NewGuid()))
$succeeded = $false
try {
    $primary = New-Item -ItemType Directory -Path (Join-Path $rehearsal 'primary')
    $source = Join-Path $primary 'primary.db'
    $backups = Join-Path $rehearsal 'backups'
    $restore = Join-Path $rehearsal 'restored.db'
    @"
import sqlite3
from pathlib import Path

source = Path(r"__SOURCE__")
with sqlite3.connect(source) as connection:
    connection.execute("CREATE TABLE rehearsal (id INTEGER PRIMARY KEY, note TEXT NOT NULL)")
    connection.executemany("INSERT INTO rehearsal (note) VALUES (?)", [("pump",), ("motor",)])
"@.Replace('__SOURCE__', $source) | .\.venv\Scripts\python.exe
    if ($LASTEXITCODE -ne 0) { throw "fixture creation failed with exit code $LASTEXITCODE" }

    .\.venv\Scripts\python.exe -m scripts.backup_sqlite --source $source --destination $backups
    if ($LASTEXITCODE -ne 0) { throw "backup failed with exit code $LASTEXITCODE" }

    $snapshot = Get-ChildItem $backups -Filter '*.db' | Select-Object -First 1
    if ($null -eq $snapshot) { throw 'backup produced no database snapshot' }
    Copy-Item -LiteralPath $snapshot.FullName -Destination $restore -ErrorAction Stop

    @"
import sqlite3
from pathlib import Path

restore = Path(r"__RESTORE__")
with sqlite3.connect(restore) as connection:
    assert connection.execute("SELECT COUNT(*) FROM rehearsal").fetchone() == (2,)
    assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
print("restore rehearsal: rows=2 integrity=ok")
"@.Replace('__RESTORE__', $restore) | .\.venv\Scripts\python.exe
    if ($LASTEXITCODE -ne 0) { throw "restore validation failed with exit code $LASTEXITCODE" }

    $succeeded = $true
}
finally {
    if ($succeeded) {
        Remove-Item -LiteralPath $rehearsal -Recurse -Force
    } else {
        Write-Warning "Restore rehearsal failed; evidence retained at $rehearsal"
    }
}
```

The Python validation must report `restore rehearsal: rows=2 integrity=ok`. Only a fully successful rehearsal removes its temporary directory.

## Host preparation and secret files

Phase 9.1 does not create a VPS, real DNS record, production credential, or deployment. Before Phase 9.2, provision one Linux host with Docker Engine and the Compose plugin, allow inbound TCP `80` and `443`, point the chosen DNS name at that host, and confirm the ACME contact and firewall policy. Caddy is the only service with published ports; do not expose frontend `80`, backend `8000`, SQLite, Chroma, Docker, MCP, or a troubleshooting Skill service.

Create two external environment files and make them readable only by root:

```sh
install -d -o root -g root -m 0700 /etc/devicepilot
install -o root -g root -m 0600 /dev/null /etc/devicepilot/backend.env
install -o root -g root -m 0600 /dev/null /etc/devicepilot/caddy.env
```

Populate `/etc/devicepilot/backend.env` with the approved LLM/provider configuration and operational settings. `LLM_MODEL`, `LLM_API_BASE`, `LLM_TIMEOUT_SECONDS`, `RAG_ENABLED`, `RAG_EMBEDDING_MODEL`, `RAG_MAX_DISTANCE`, `RAG_TOP_K`, `RAG_CHUNK_SIZE`, and `RAG_CHUNK_OVERLAP` are operator-controlled only from that file; Compose keeps only fixed container paths such as `/app/knowledge` and `/data/chroma`. Populate `/etc/devicepilot/caddy.env` with `DEVICEPILOT_DOMAIN`, `ACME_EMAIL`, `BASIC_AUTH_USERNAME`, and a Caddy-supported password hash. Never copy a real value into Git, an issue, CI output, Compose-rendered output, or an operations transcript, and never diagnose production by printing the full environment.

Generate the hash in an approved private operator session:

```sh
docker run --rm caddy:2.11.4-alpine caddy hash-password
```

A bcrypt hash contains `$`. Docker Compose interpolates unquoted `$` sequences in `env_file`, so store the hash with literal single `$` separators exactly as Caddy generated it and wrap the complete value in single quotes, as shown by the tracked dummy example; do not double the dollar signs. Verify the rendered dummy environment begins with a valid Caddy-supported hash prefix before installing real credentials.

## Exact-version release procedure

Choose an approved Git commit or release and use the same immutable value for both application images. Do not use `latest`:

```sh
git checkout <approved-exact-git-ref>
export APP_VERSION=<approved-exact-git-sha-or-release-tag>
docker compose -f compose.production.yml config --quiet
docker compose -f compose.production.yml build backend frontend
docker compose -f compose.production.yml up -d
```

Keep the current and immediately previous `devicepilot-backend:<APP_VERSION>` and `devicepilot-frontend:<APP_VERSION>` images locally. Do not prune them until the replacement release and recovery checks are accepted. The normal production start is standalone; it does not merge `docker-compose.yml`.

Production sets `APP_ENV=production`, `TRUST_PROXY_HEADERS=true`, and `AUTO_SEED_DEMO=false`. FastAPI `/docs`, `/redoc`, and `/openapi.json` are therefore unavailable. Demo data is never inserted implicitly. When a deployment is intentionally a demonstration, run the existing idempotent command once:

```sh
docker compose -f compose.production.yml run --rm --no-deps backend python -m scripts.seed_demo
```

Re-running it is safe, but every run is still an explicit operator action and should be recorded.

## Health, authentication, and smoke checks

The unauthenticated public probe is limited to `https://<domain>/healthz`. All UI and `/api` traffic requires Caddy Basic Auth. Do not place the password on a shared command line or in shell history; use an approved secret-aware client or a private netrc-style credential file. Confirm:

1. `http://<domain>` redirects to HTTPS and the TLS certificate matches the configured DNS name.
2. `/healthz` returns `200` without credentials.
3. `/` and `/api/...` return `401` without credentials.
4. Authenticated UI and representative Device/Fault reads succeed.
5. Backend liveness and SQLite-only readiness succeed internally:

   ```sh
   docker compose -f compose.production.yml exec -T backend python -c \
     "from urllib.request import urlopen; assert urlopen('http://127.0.0.1:8000/health/live').status == 200; assert urlopen('http://127.0.0.1:8000/health/ready').status == 200"
   ```

6. Backend outbound HTTPS succeeds without calling a paid LLM:

   ```sh
   docker compose -f compose.production.yml exec -T backend python -c \
     "from urllib.request import urlopen; assert urlopen('https://example.com', timeout=10).status == 200"
   ```

7. `docker compose -f compose.production.yml ps` shows only Caddy with host mappings `80:80` and `443:443`; frontend and backend have none.
8. Caddy belongs only to `edge`, frontend to `edge` and internal `app`, and backend to internal `app` plus the dedicated non-internal `egress` network.

Caddy replaces incoming forwarding headers, nginx forwards the Caddy-generated `X-Forwarded-For` unchanged, and Caddy removes its Basic Auth `Authorization` header before nginx. Re-run `python -m scripts.verify_proxy_boundary` with the local dummy test images after proxy changes.

Docker uses bounded `local` logs. Application and proxy logging must never include request bodies, Basic Auth or other Authorization values, API keys, full fault descriptions, LLM prompts, retrieved chunks, secret-bearing provider errors, or environment dumps.

## Application rollback

Application rollback is tag selection, not database restoration. Check out the previously approved exact Git ref, set `APP_VERSION` to the retained previous image tag, validate the standalone Compose definition, and recreate services without rebuilding:

```sh
git checkout <previous-approved-exact-git-ref>
export APP_VERSION=<previous-retained-version>
docker compose -f compose.production.yml config --quiet
docker compose -f compose.production.yml up -d --no-build
```

Run the full health/authenticated smoke checklist again. Restore SQLite only for confirmed corruption or a documented incompatible data/schema event, using the separate procedure above. If Chroma is missing or incompatible, rebuild it inside the running Backend container so the operation uses the production `/app/knowledge` and `/data/chroma` paths:

```sh
docker compose -f compose.production.yml exec -T backend \
  python -m scripts.index_knowledge --rebuild
```

If `/data/huggingface` is missing, allow the pinned embedding model to download again inside that container. Neither rebuild justifies restoring SQLite.

## Backup schedule and exclusions

Run the maintenance profile/one-shot backup against the independent host path and verify the printed checksum and artifact permissions:

```sh
export APP_VERSION=<currently-deployed-version>
docker compose --profile maintenance -f compose.production.yml run --rm backup
```

Retain 7 daily, 4 weekly, and 3 monthly verified recovery points and copy them to encrypted off-host storage before pruning. Rehearse restore on the actual filesystem and hard-link-capable backup mount before relying on the schedule.

Production Compose intentionally contains no remote MCP transport/service and no troubleshooting Skill runtime. The existing MCP server remains local stdio interoperability, and the repository Skill remains external Host guidance. Adding network exposure for either requires a separate authentication, authorization, data-egress, and threat review.

## CI boundary

`.github/workflows/ci.yml` runs on pull requests and pushes to `main` with `contents: read`. It installs/tests Backend and Frontend code, compiles Python, runs `pip check`, validates Compose and Caddy using dummy values, builds both local images, and exercises the proxy boundary. It does not call an LLM, deploy, push an image, use SSH, contain a VPS credential, or receive production secrets.