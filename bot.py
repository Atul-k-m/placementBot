"""
bot.py — Daily Email Monitor Bot
Checks Gmail for emails from specific senders and sends WhatsApp notifications
via CallMeBot API. Designed to run once daily via GitHub Actions.
"""

import os
import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from email import message_from_bytes

import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ─────────────────────────────────────────────
# Configuration (all from environment variables)
# ─────────────────────────────────────────────

# Comma-separated list of sender emails to watch, e.g. "alice@example.com,bob@example.com"
WATCH_SENDERS: list[str] = [
    email.strip()
    for email in os.environ.get("WATCH_SENDERS", "").split(",")
    if email.strip()
]

# CallMeBot WhatsApp settings
CALLMEBOT_API_KEY: str = os.environ.get("CALLMEBOT_API_KEY", "")
WHATSAPP_PHONE: str = os.environ.get("WHATSAPP_PHONE", "")  # include country code, e.g. +919876543210

# Gmail OAuth credentials (stored as a JSON string in the secret GMAIL_TOKEN_JSON)
GMAIL_TOKEN_JSON: str = os.environ.get("GMAIL_TOKEN_JSON", "")

# How many hours back to look for emails (set slightly > 24 to avoid gaps)
LOOKBACK_HOURS: int = int(os.environ.get("LOOKBACK_HOURS", "25"))

# Maximum body snippet length (characters)
SNIPPET_LENGTH: int = 300

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Gmail helpers
# ─────────────────────────────────────────────

def build_gmail_service():
    """Build and return an authenticated Gmail API service object."""
    if not GMAIL_TOKEN_JSON:
        raise EnvironmentError(
            "GMAIL_TOKEN_JSON environment variable is not set. "
            "Run generate_token.py locally first and paste the output into your GitHub secret."
        )

    token_data = json.loads(GMAIL_TOKEN_JSON)
    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes", ["https://www.googleapis.com/auth/gmail.readonly"]),
    )

    # Refresh the access token if expired
    if creds.expired and creds.refresh_token:
        log.info("Access token expired — refreshing…")
        creds.refresh(Request())

    return build("gmail", "v1", credentials=creds)


def build_query(senders: list[str], hours_back: int) -> str:
    """Build a Gmail search query string."""
    since_dt = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    # Gmail uses Unix epoch seconds in the 'after:' operator
    since_epoch = int(since_dt.timestamp())

    from_parts = " OR ".join(f"from:{s}" for s in senders)
    query = f"({from_parts}) after:{since_epoch}"
    log.info("Gmail query: %s", query)
    return query


def get_header(headers: list[dict], name: str) -> str:
    """Extract a specific header value from a list of header dicts."""
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def extract_body_snippet(payload: dict, max_len: int = SNIPPET_LENGTH) -> str:
    """
    Recursively extract plain-text body from a Gmail message payload.
    Falls back to the Gmail API snippet if no text/plain part is found.
    """
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime_type == "text/plain" and body_data:
        raw = base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace")
        return raw.strip()[:max_len]

    # Recurse into multipart
    for part in payload.get("parts", []):
        result = extract_body_snippet(part, max_len)
        if result:
            return result

    return ""


def fetch_emails(service, senders: list[str], hours_back: int) -> list[dict]:
    """
    Search Gmail for messages from watched senders in the last `hours_back` hours.
    Returns a list of dicts: {sender_name, sender_email, subject, snippet}.
    """
    query = build_query(senders, hours_back)
    results = service.users().messages().list(userId="me", q=query, maxResults=20).execute()
    messages = results.get("messages", [])
    log.info("Found %d message(s) matching query.", len(messages))

    emails = []
    for msg_stub in messages:
        msg = service.users().messages().get(
            userId="me",
            id=msg_stub["id"],
            format="full",
        ).execute()

        headers = msg.get("payload", {}).get("headers", [])
        from_raw = get_header(headers, "From")
        subject = get_header(headers, "Subject") or "(no subject)"

        # Parse "Name <email@example.com>" format
        if "<" in from_raw:
            sender_name, _, sender_email = from_raw.partition("<")
            sender_name = sender_name.strip().strip('"')
            sender_email = sender_email.rstrip(">").strip()
        else:
            sender_email = from_raw.strip()
            sender_name = sender_email

        # Extract body snippet; fall back to the Gmail pre-built snippet
        body_snippet = extract_body_snippet(msg.get("payload", {}))
        if not body_snippet:
            body_snippet = msg.get("snippet", "")
        body_snippet = body_snippet[:SNIPPET_LENGTH]

        emails.append(
            {
                "sender_name": sender_name,
                "sender_email": sender_email,
                "subject": subject,
                "snippet": body_snippet,
            }
        )

    return emails


# ─────────────────────────────────────────────
# WhatsApp / CallMeBot helpers
# ─────────────────────────────────────────────

def send_whatsapp(message: str) -> bool:
    """
    Send a WhatsApp message via the CallMeBot API.
    Returns True on success, False on failure.
    """
    if not CALLMEBOT_API_KEY or not WHATSAPP_PHONE:
        raise EnvironmentError(
            "CALLMEBOT_API_KEY and WHATSAPP_PHONE must be set as environment variables."
        )

    url = "https://api.callmebot.com/whatsapp.php"
    params = {
        "phone": WHATSAPP_PHONE,
        "text": message,
        "apikey": CALLMEBOT_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            log.info("WhatsApp message sent successfully.")
            return True
        else:
            log.error("CallMeBot returned status %d: %s", response.status_code, response.text)
            return False
    except requests.RequestException as exc:
        log.error("Failed to reach CallMeBot API: %s", exc)
        return False


# ─────────────────────────────────────────────
# Message formatting
# ─────────────────────────────────────────────

def format_email_digest(emails: list[dict]) -> str:
    """Format the list of emails into a WhatsApp message."""
    today = datetime.now().strftime("%d %b %Y")
    lines = [f"📬 *Email Digest — {today}*", f"Found *{len(emails)}* new email(s):\n"]

    for i, email in enumerate(emails, start=1):
        lines.append(f"*{i}. From:* {email['sender_name']} <{email['sender_email']}>")
        lines.append(f"   *Subject:* {email['subject']}")
        if email["snippet"]:
            # Trim and sanitise snippet for readability
            snippet = email["snippet"].replace("\n", " ").strip()
            lines.append(f"   *Preview:* {snippet[:200]}…")
        lines.append("")  # blank separator

    return "\n".join(lines).strip()


def format_no_updates() -> str:
    """Format the 'no updates' message."""
    today = datetime.now().strftime("%d %b %Y")
    watched = ", ".join(WATCH_SENDERS) if WATCH_SENDERS else "configured senders"
    return (
        f"📭 *Email Digest — {today}*\n"
        f"No new emails from: {watched}\n"
        f"All quiet today! ✅"
    )


# ─────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────

def main():
    log.info("=== Email Monitor Bot starting ===")

    # Validate configuration
    if not WATCH_SENDERS:
        raise EnvironmentError(
            "WATCH_SENDERS is not set or empty. "
            "Set it to a comma-separated list of sender email addresses."
        )

    # Build Gmail service
    log.info("Authenticating with Gmail API…")
    service = build_gmail_service()

    # Fetch emails
    log.info("Searching for emails from: %s", WATCH_SENDERS)
    try:
        emails = fetch_emails(service, WATCH_SENDERS, LOOKBACK_HOURS)
    except HttpError as exc:
        log.error("Gmail API error: %s", exc)
        raise

    # Compose and send WhatsApp notification
    if emails:
        message = format_email_digest(emails)
        log.info("Sending digest for %d email(s)…", len(emails))
    else:
        message = format_no_updates()
        log.info("Sending 'no updates' notification…")

    log.info("Message preview:\n%s", message)
    success = send_whatsapp(message)

    if not success:
        raise RuntimeError("Failed to send WhatsApp notification. Check CallMeBot credentials.")

    log.info("=== Bot finished successfully ===")


if __name__ == "__main__":
    main()
