import sys
from datetime import datetime, timezone

# Sunday, November 8, 2026 5:00 AM US Eastern (EST, UTC-5)
CUTOFF = datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc)

MESSAGE = (
    "Blazing Automation can no longer be used.\n"
    "Automated play is not allowed: from Sunday, November 8, 2026 5:00 AM (US Eastern) the game checks for it,\n"
    "so running macros is disabled."
)

def expired():
    return datetime.now(timezone.utc) >= CUTOFF

def block():
    if not expired():
        return False
    print(MESSAGE, flush=True)
    return True

def exit_if_expired():
    if block():
        sys.exit(1)
