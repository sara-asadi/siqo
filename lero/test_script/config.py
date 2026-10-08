import os
import subprocess

# Postgresql conf (JOB / Docker postgres-lero)
PORT = 5433
HOST = "localhost"
USER = "postgres"
PASSWORD = "postgres"
DB = "imdb"
CONNECTION_STR = (
    "dbname=" + DB
    + " user=" + USER
    + " password=" + PASSWORD
    + " host=" + HOST
    + " port=" + str(PORT)
)
TIMEOUT = 30000000

# Absolute path on the host to the card-file bind mount.
# Postgres opens these via relative paths under the data directory
# (see CARD_PG_RELDIR), so host writes and container reads share the same files.
_LERO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PG_DB_PATH = os.path.join(_LERO_ROOT, "lero_cards")
# Path prefix Postgres uses with fopen (cwd = data directory)
CARD_PG_RELDIR = "lero_cards"

# Host used by scripts to talk to the Lero ranker (runs on the host)
LERO_SERVER_PORT = 14567
LERO_SERVER_HOST = "localhost"
# Host Postgres-in-Docker must use to reach the Lero ranker on the host.
# The Lero PG extension connects with inet_pton(), which requires a literal
# IPv4 address (it does not resolve hostnames). "host.docker.internal" only
# resolves inside the container's network namespace, not on the Mac host,
# so ask the running container what it resolves to.
def _resolve_lero_server_host_from_pg():
    fallback = "192.168.65.254"  # typical Docker Desktop gateway IP
    try:
        out = subprocess.run(
            ["docker", "exec", "postgres-lero", "getent", "ahostsv4", "host.docker.internal"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        return out.splitlines()[0].split()[0] if out else fallback
    except Exception:
        return fallback


LERO_SERVER_HOST_FROM_PG = _resolve_lero_server_host_from_pg()
LERO_SERVER_PATH = "../"
LERO_DUMP_CARD_FILE = "dump_card_with_score.txt"

# Test conf
LOG_PATH = "./log/query_latency"
SEP = "#####"
