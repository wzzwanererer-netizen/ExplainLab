#!/usr/bin/env bash
set -euo pipefail
umask 077
run=$(realpath -e -- "$1")
[[ $(dirname "$run") == "$(realpath -e -- "$HOME")" && ${run##*/} == explainlab-b1.* ]]
[[ $(findmnt -n -T "$run/project" -o FSTYPE) == ext4 ]]
grep -Eq '^END .* exit=0$' "$run/environment.log"
out=$(mktemp -d "$run/acceptance.XXXXXXXX")
win=/mnt/d/ExplainLab/docs/acceptance/V2-A1-04-Batch-B-B1-environment-recovery/evidence
dest="$win/${out##*/}"
mkdir -- "$dest"
cp -- "$run/environment.log" "$dest/"
cd "$run/project"
sha256sum --check --strict SHA256SUMS > "$dest/input-recheck.log"
py="$run/project/.venv/bin/python"
mkdir -- "$out/pytest-posix" "$out/pytest-pg"
unset DATABASE_URL EXPLAINLAB_PG_TEST_URL
unset PGHOST PGHOSTADDR PGPORT PGUSER PGPASSWORD PGPASSFILE PGSERVICE PGSERVICEFILE PGDATABASE PGOPTIONS

run_suite() {
    local label=$1
    shift
    local rc
    (
        date -u +%FT%TZ
        printf 'Command:'
        printf ' %q' "$@"
        printf '\n'
        "$@"
    ) 2>&1 | tee "$dest/$label.log"
}

set +e
(
    date -u +%FT%TZ
    findmnt -T "$out/pytest-posix" -o SOURCE,FSTYPE,TARGET
    run_suite posix-pytest "$py" -m pytest -o addopts=--import-mode=importlib -ra \
        --basetemp="$out/pytest-posix" --junitxml="$dest/posix.xml" \
        backend/tests/test_attachment_storage.py backend/tests/test_attachment_gc.py \
        backend/tests/test_batch_a_file_write.py backend/tests/test_batch_a_process_and_identity.py
) 2>&1 | tee "$dest/posix-environment.log"
posix_rc=$?
printf 'POSIX exit=%s\n' "$posix_rc" | tee "$dest/posix-exit.txt"

(
    set -euo pipefail
    date -u +%FT%TZ
    mkdir -- "$out/packages" "$out/pg-root" "$out/pg-socket"
    printf '%s\n' 'apt-get --simulate install --no-install-recommends postgresql-18 postgresql-client-18'
    plan=$(apt-get --simulate install --no-install-recommends postgresql-18 postgresql-client-18)
    printf '%s\n' "$plan"
    mapfile -t packages < <(printf '%s\n' "$plan" | awk '/^Inst /{print $2}' | sort -u)
    (
        cd "$out/packages"
        set -x
        apt-get download postgresql-18 postgresql-client-18 "${packages[@]}"
        for f in ./*.deb; do dpkg-deb -x "$f" "$out/pg-root"; done
    )
    pg="$out/pg-root/usr/lib/postgresql/18/bin"
    libdir="$out/pg-root/usr/lib/$(uname -m)-linux-gnu"
    export LD_LIBRARY_PATH="$libdir:$out/pg-root/lib/$(uname -m)-linux-gnu"
    "$pg/postgres" --version
    "$pg/psql" --version
    ldd "$pg/postgres"
    port=$("$py" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')
    data="$out/pg-data"
    user=$(id -un)
    started=0
    cleanup() {
        local code=$?
        trap - EXIT
        if [[ $started == 1 || -f "$data/postmaster.pid" ]]; then
            "$pg/pg_ctl" -D "$data" -m fast -w -t 20 stop || {
                echo 'PostgreSQL stop failed' >&2
                if [[ $code == 0 ]]; then code=1; fi
            }
        fi
        if [[ -f "$out/server.log" ]]; then cp -- "$out/server.log" "$dest/postgresql-server.log"; fi
        exit "$code"
    }
    trap cleanup EXIT
    printf '%s\n' 'initdb: UTF8, C locale, peer on private UNIX socket, SCRAM on TCP'
    "$pg/initdb" -D "$data" -U "$user" --auth-local=peer --auth-host=scram-sha-256 --locale=C -E UTF8
    printf 'PostgreSQL data directory: %s; TCP bind: 127.0.0.1:%s\n' "$data" "$port"
    "$pg/pg_ctl" -D "$data" -l "$out/server.log" -w -t 20 \
        -o "-h 127.0.0.1 -p $port -k $out/pg-socket -c log_min_error_statement=panic" start
    started=1
    export PGPASSFILE="$out/pgpass"
    printf '%s\n' 'Validate dedicated cluster, create restricted owner and test database, verify two TCP sessions'
    "$py" - "$out/pg-socket" "$port" "$data" "$user" <<'PY'
import os
from pathlib import Path
import secrets
import sys

import psycopg
from psycopg import sql

sock, port, data_dir, admin = sys.argv[1:]
role, db = "explainlab_b1_runner", "explainlab_b1_acceptance"
password = secrets.token_urlsafe(32)
with psycopg.connect(host=sock, port=port, user=admin, dbname="postgres",
                     autocommit=True, connect_timeout=5) as conn:
    assert conn.execute("SHOW data_directory").fetchone()[0] == data_dir
    assert conn.execute("SHOW listen_addresses").fetchone()[0] == "127.0.0.1"
    assert conn.execute("SHOW port").fetchone()[0] == port
    assert conn.execute("SHOW password_encryption").fetchone()[0] == "scram-sha-256"
    print("Cluster:", conn.execute("SELECT current_database(), current_user, version()").fetchone())
    print("Data directory:", data_dir)
    conn.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}").format(
        sql.Identifier(role), sql.Literal(password)))
    conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(db), sql.Identifier(role)))
    hba = conn.execute("SELECT address, auth_method FROM pg_hba_file_rules WHERE type = 'host'").fetchall()
    assert hba and all(method == "scram-sha-256" for _, method in hba)
    print("TCP HBA:", hba)
passfile = Path(os.environ["PGPASSFILE"])
with passfile.open("x") as stream:
    stream.write(f"127.0.0.1:{port}:{db}:{role}:{password}\n")
kwargs = dict(host="127.0.0.1", port=port, dbname=db, user=role, connect_timeout=5)
with psycopg.connect(**kwargs) as a, psycopg.connect(**kwargs) as b:
    query = "SELECT pg_backend_pid(), current_database(), current_user, inet_server_port()"
    first, second = a.execute(query).fetchone(), b.execute(query).fetchone()
    assert first[0] != second[0] and first[1:] == second[1:] == (db, role, int(port))
    print("Dedicated TCP connections:", first, second)
PY
    export EXPLAINLAB_PG_TEST_URL="postgresql+psycopg://explainlab_b1_runner@127.0.0.1:$port/explainlab_b1_acceptance"
    run_suite postgresql-pytest "$py" -m pytest -o addopts=--import-mode=importlib -ra \
        --basetemp="$out/pytest-pg" --junitxml="$dest/postgresql.xml" \
        backend/tests/test_storage_lock_pg.py backend/tests/test_attachment_pg.py
) 2>&1 | tee "$dest/postgresql-environment.log"
pg_rc=$?
printf 'PostgreSQL exit=%s\n' "$pg_rc" | tee "$dest/postgresql-exit.txt"
printf 'Evidence: %s\n' "$dest"
(( posix_rc == 0 && pg_rc == 0 ))
