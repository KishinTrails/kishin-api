#!/bin/sh
# Creates the PostgreSQL database kishin-api keeps its game data in (tiles, POIs, noise cache,
# explored tiles, plans), owned by kishin-api's user. Safe to run again: it creates what is
# missing and changes nothing else.
#
# The user must exist already. On the server it is the health database's reader, which
# health-sync's db/setup.sh creates (READER_DB_USER, default kishin-trails), so kishin-api
# uses one user and one password: owner of this database, read-only on the health database.
# kishin-api creates its tables at startup.
#
#   KISHIN_DB_NAME   the database                                     (default kishin)
#   KISHIN_DB_USER   its owner, kishin-api's user                     (default kishin-trails)
#   DB_EXEC          command that runs SQL read from standard input as a superuser.
#                    Default, for a container named postgres:
#                    docker exec -i postgres psql -U postgres -X -q -v ON_ERROR_STOP=1
#   DRY_RUN          if set, print the SQL and do nothing
set -eu

KISHIN_DB_NAME="${KISHIN_DB_NAME:-kishin}"
KISHIN_DB_USER="${KISHIN_DB_USER:-kishin-trails}"

fail() {
    echo "error: $*" >&2
    exit 1
}

case "$KISHIN_DB_NAME" in ''|*[!a-z0-9_]*) fail "KISHIN_DB_NAME may only hold lower case letters, digits and underscores" ;; esac
case "$KISHIN_DB_USER" in ''|*[!A-Za-z0-9_-]*) fail "KISHIN_DB_USER may only hold letters, digits, - and _" ;; esac

buildSql() {
    cat <<SQL
DO \$do\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${KISHIN_DB_USER}') THEN
        RAISE EXCEPTION 'the user ${KISHIN_DB_USER} does not exist: run health-sync''s db/setup.sh first';
    END IF;
END
\$do\$;
SELECT 'CREATE DATABASE "${KISHIN_DB_NAME}" OWNER "${KISHIN_DB_USER}"'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${KISHIN_DB_NAME}')\\gexec
REVOKE ALL ON DATABASE "${KISHIN_DB_NAME}" FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE "${KISHIN_DB_NAME}" TO "${KISHIN_DB_USER}";
SQL
}

if [ -n "${DRY_RUN:-}" ]; then
    buildSql
    exit 0
fi

DB_EXEC="${DB_EXEC:-docker exec -i postgres psql -U postgres -X -q -v ON_ERROR_STOP=1}"
buildSql | sh -c "$DB_EXEC"
echo "database: ${KISHIN_DB_NAME}"
echo "owner:    ${KISHIN_DB_USER}"
