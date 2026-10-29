"""Safe, deterministic diagnostics for Aiven connection failures.

Never return DB-API exception strings to unauthenticated visitors: they may
contain database hostnames, usernames, and other deployment information.
Only curated codes and static troubleshooting advice are returned.
"""


_DIAGNOSES = {
    "DB_AUTH": (
        "PostgreSQL rejected the database username or password.",
        "Copy the current Service URI from Aiven. If you manually constructed "
        "the URL, URL-encode special characters in the password."
    ),
    "DB_MISSING": (
        "The requested PostgreSQL database was not found on this service.",
        "Open the Aiven PostgreSQL service and create a database named "
        "'myplatoon' before running setup."
    ),
    "DB_DNS": (
        "The configured Aiven hostname could not be resolved.",
        "Copy the hostname from Aiven's current Connection information. "
        "Check whether the service is configured for public access."
    ),
    "DB_TIMEOUT": (
        "The PostgreSQL connection timed out.",
        "Confirm the service is RUNNING and publicly reachable from Vercel. "
        "Check Aiven's inbound IP allowlist and networking rules. "
        "Vercel function outbound IPs can vary without static egress."
    ),
    "DB_REFUSED": (
        "The PostgreSQL host refused the connection.",
        "Confirm the Aiven service is RUNNING and the host and service-specific "
        "port match the Connection information in Aiven."
    ),
    "DB_TLS": (
        "PostgreSQL could not establish the required TLS connection.",
        "Use the current Aiven Service URI with sslmode=require. "
        "If using verify-ca or verify-full, configure the Aiven CA certificate."
    ),
    "DB_ACCESS": (
        "The database rejected access under its network or authentication policy.",
        "Check Aiven's IP allowlist, TLS requirements, service and database "
        "permissions. Ensure Vercel can reach this service."
    ),
    "DB_PERMISSIONS": (
        "The PostgreSQL account cannot inspect the database schema.",
        "The account used for initial setup needs permission to inspect "
        "existing tables and apply reviewed Alembic migrations."
    ),
    "DB_LIMIT": (
        "PostgreSQL has reached its connection limit or is temporarily unavailable.",
        "Check active connections and service health in Aiven, then retry "
        "after reducing connection usage."
    ),
    "DB_OTHER": (
        "The database check failed for an unclassified reason.",
        "Open Vercel Runtime Logs for the matching DB_OTHER code. "
        "Review the Aiven service status and connection configuration."
    ),
}


def diagnose_database_error(exc):
    """Return (safe_code, safe_summary, safe_help); never include exception text."""
    original = getattr(exc, "orig", None) or exc
    code = getattr(original, "pgcode", None) or getattr(
        getattr(original, "diag", None), "sqlstate", None)
    if code == "28P01":
        category = "DB_AUTH"
    elif code == "3D000":
        category = "DB_MISSING"
    elif code == "42501":
        category = "DB_PERMISSIONS"
    elif code in ("53300", "57P03"):
        category = "DB_LIMIT"
    elif code == "28000":
        category = "DB_ACCESS"
    else:
        # Match only known diagnostic phrases. Never surface raw text or host.
        message = str(original).lower()
        if "password authentication failed" in message or "authentication failed for user" in message:
            category = "DB_AUTH"
        elif "database" in message and "does not exist" in message:
            category = "DB_MISSING"
        elif ("could not translate host name" in message
              or "name or service not known" in message
              or "nodename nor servname provided" in message
              or "temporary failure in name resolution" in message):
            category = "DB_DNS"
        elif ("certificate verify failed" in message
              or "ssl error" in message or "tlsv1 alert" in message
              or "server does not support ssl" in message):
            category = "DB_TLS"
        elif ("no pg_hba.conf entry" in message
              or "ip address is not allowed" in message
              or "not allowed to connect" in message):
            category = "DB_ACCESS"
        elif "permission denied" in message or "insufficient privilege" in message:
            category = "DB_PERMISSIONS"
        elif ("too many connections" in message
              or "remaining connection slots" in message
              or "the database system is starting up" in message):
            category = "DB_LIMIT"
        elif ("connection refused" in message or "actively refused" in message):
            category = "DB_REFUSED"
        elif ("timeout" in message or "timed out" in message
              or "no route to host" in message
              or "network is unreachable" in message):
            category = "DB_TIMEOUT"
        else:
            category = "DB_OTHER"
    return (category, *_DIAGNOSES[category])
