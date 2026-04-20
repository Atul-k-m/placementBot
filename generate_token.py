"""
generate_token.py — Run this ONCE locally to generate your Gmail OAuth token.

Usage:
  1. Place your credentials.json (from Google Cloud Console) in this directory.
  2. Run:  python generate_token.py
  3. A browser window will open — sign in and grant Gmail read access.
  4. Copy the printed JSON and paste it as the GMAIL_TOKEN_JSON GitHub secret.

You only need to do this once. The token auto-refreshes via the refresh_token.
"""

import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main():
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }

    print("\n" + "=" * 60)
    print("SUCCESS! Copy the JSON below and add it as the")
    print("GMAIL_TOKEN_JSON GitHub Actions secret:")
    print("=" * 60)
    print(json.dumps(token_data, indent=2))
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
