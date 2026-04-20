import json
import logging
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
import base64
from twilio.rest import Client
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from opportunity_scraper import get_daily_opportunities

LOOKBACK_HOURS = 25
SNIPPET_LENGTH = 300

log = logging.getLogger(__name__)

def build_gmail_service(token_json_str: str):
    token_data = json.loads(token_json_str)
    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes", ["https://www.googleapis.com/auth/gmail.readonly"]),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build("gmail", "v1", credentials=creds)

def build_query(senders: list[str], keywords: list[str], hours_back: int) -> str:
    since_dt = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    since_epoch = int(since_dt.timestamp())
    
    parts = []
    if senders:
        from_parts = " OR ".join(f"from:{s}" for s in senders)
        parts.append(f"({from_parts})")
    
    if keywords:
        # e.g. subject:(internship OR placement OR ...)
        kw_body = " OR ".join(keywords)
        parts.append(f"(subject:({kw_body}))")
        
    if not parts:
        return f"after:{since_epoch}"
        
    full_q = " OR ".join(parts)
    return f"({full_q}) after:{since_epoch}"

def get_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""

def extract_body_snippet(payload: dict, max_len: int = SNIPPET_LENGTH) -> str:
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")
    if mime_type == "text/plain" and body_data:
        raw = base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace")
        return raw.strip()[:max_len]
    for part in payload.get("parts", []):
        result = extract_body_snippet(part, max_len)
        if result:
            return result
    return ""

def fetch_emails(service, senders: list[str], keywords: list[str], hours_back: int) -> list[dict]:
    query = build_query(senders, keywords, hours_back)
    results = service.users().messages().list(userId="me", q=query, maxResults=30).execute()
    messages = results.get("messages", [])
    
    emails = []
    for msg_stub in messages:
        msg = service.users().messages().get(
            userId="me", id=msg_stub["id"], format="full"
        ).execute()

        headers = msg.get("payload", {}).get("headers", [])
        from_raw = get_header(headers, "From")
        subject = get_header(headers, "Subject") or "(no subject)"

        if "<" in from_raw:
            sender_name, _, sender_email = from_raw.partition("<")
            sender_name = sender_name.strip().strip('"')
            sender_email = sender_email.rstrip(">").strip()
        else:
            sender_email = from_raw.strip()
            sender_name = sender_email

        # Determine match type
        match_type = "KEYWORD"
        for s in senders:
            if s.lower() in sender_email.lower():
                match_type = "SENDER"
                break

        body_snippet = extract_body_snippet(msg.get("payload", {}))
        if not body_snippet:
            body_snippet = msg.get("snippet", "")
        body_snippet = body_snippet[:SNIPPET_LENGTH]

        emails.append({
            "match_type": match_type,
            "sender_name": sender_name,
            "sender_email": sender_email,
            "subject": subject,
            "snippet": body_snippet,
        })
    return emails

def format_email_digest(emails: list[dict]) -> str:
    today = datetime.now().strftime("%d %b %Y")
    lines = [f"📬 *Email Digest — {today}*", "─────────────"]
    for i, email in enumerate(emails, start=1):
        lines.append(f"[{email['match_type']}] {email['sender_email']}")
        lines.append(f"*Sub:* {email['subject']}")
        if email["snippet"]:
            snippet = email["snippet"].replace("\n", " ").strip()
            lines.append(f"   {snippet[:150]}…")
        lines.append("")
    return "\n".join(lines).strip()

def format_opportunities(opps: dict) -> str:
    lines = ["*Opportunities*", "─────────────"]
    
    devpost = opps.get("devpost", [])
    for d in devpost[:5]:
        lines.append(f"[DEVPOST] {d['name']}")
        lines.append(f"Deadline: {d['deadline']} | Prize: {d['prize']}")
        lines.append(f"{d['url']}\n")
        
    unstop = opps.get("unstop", [])
    for u in unstop[:5]:
        lines.append(f"[UNSTOP] {u['name']}")
        lines.append(f"Deadline: {u['deadline']} | Org: {u['organizer']}")
        lines.append(f"{u['url']}\n")
        
    if not devpost and not unstop:
        return ""
        
    return "\n".join(lines).strip()

def send_whatsapp(message: str, sid: str, token: str, from_phone: str, to_phone: str) -> bool:
    if not sid or not token or not from_phone or not to_phone:
        log.error("Twilio credentials or phone numbers missing")
        return False
    try:
        client = Client(sid, token)
        msg = client.messages.create(
            from_=f'whatsapp:{from_phone}',
            to=f'whatsapp:{to_phone}',
            body=message
        )
        log.info(f"Twilio message sent. SID: {msg.sid}")
        return True
    except Exception as e:
        log.error(f"Twilio error: {e}")
        return False

def run_bot(user_config: dict):
    """
    Unified entry point. 
    user_config expected to have all fields from models.User properties.
    """
    watch_senders = user_config.get("watch_senders", [])
    watch_keywords = user_config.get("watch_keywords", [])
    token_json = user_config.get("gmail_token_json")
    
    if not token_json:
        log.error("Missing Gmail token")
        return False
        
    try:
        service = build_gmail_service(token_json)
        emails = fetch_emails(service, watch_senders, watch_keywords, LOOKBACK_HOURS)
        
        email_text = format_email_digest(emails) if emails else ""
        
        opps = get_daily_opportunities(
            enable_devpost=user_config.get("enable_devpost", False),
            enable_unstop=user_config.get("enable_unstop", False)
        )
        opp_text = format_opportunities(opps)
        
        full_message = f"{email_text}\n\n{opp_text}".strip()
        if not full_message:
            full_message = "📭 *Daily Check* - No new emails or opportunities found today."

        success = send_whatsapp(
            full_message, 
            user_config.get("twilio_sid"), 
            user_config.get("twilio_token"), 
            user_config.get("twilio_from"), 
            user_config.get("whatsapp_phone")
        )
        return success
    except Exception as e:
        log.error(f"Bot run error: {e}")
        return False
