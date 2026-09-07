"""
Gmail OAuth2 Setup Script for HirePulse
========================================
Run this script ONCE on your local machine to get the GMAIL_REFRESH_TOKEN.

Prerequisites:
1. Go to https://console.cloud.google.com/
2. Create a new project (or use existing)
3. Enable the Gmail API: https://console.cloud.google.com/apis/library/gmail.googleapis.com
4. Go to Credentials > Create Credentials > OAuth client ID
5. Choose "Desktop app" as application type
6. Download the JSON and note the client_id and client_secret

Usage:
    python setup_gmail_oauth.py <CLIENT_ID> <CLIENT_SECRET>
"""

import sys
import json
import urllib.request
import urllib.parse
import webbrowser

def main():
    if len(sys.argv) != 3:
        print("Usage: python setup_gmail_oauth.py <CLIENT_ID> <CLIENT_SECRET>")
        print("\nGet these from: https://console.cloud.google.com/apis/credentials")
        sys.exit(1)

    client_id = sys.argv[1]
    client_secret = sys.argv[2]

    # Step 1: Generate authorization URL
    scopes = "https://www.googleapis.com/auth/gmail.send"
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri=urn:ietf:wg:oauth:2.0:oob&"
        f"response_type=code&"
        f"scope={scopes}&"
        f"access_type=offline&"
        f"prompt=consent"
    )

    print("\n" + "=" * 60)
    print("STEP 1: Authorize Gmail Access")
    print("=" * 60)
    print("\nOpening browser... If it doesn't open, visit this URL:\n")
    print(auth_url)
    print()

    webbrowser.open(auth_url)

    # Step 2: Get authorization code from user
    auth_code = input("Paste the authorization code here: ").strip()

    # Step 3: Exchange authorization code for tokens
    print("\nExchanging code for tokens...")

    payload = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob"
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        refresh_token = data.get("refresh_token")
        access_token = data.get("access_token")

        if not refresh_token:
            print("\n❌ ERROR: No refresh_token received. Try again with prompt=consent.")
            print(f"Response: {json.dumps(data, indent=2)}")
            sys.exit(1)

        print("\n" + "=" * 60)
        print("✅ SUCCESS! Add these to your Render Environment Variables:")
        print("=" * 60)
        print(f"\nGMAIL_CLIENT_ID     = {client_id}")
        print(f"GMAIL_CLIENT_SECRET = {client_secret}")
        print(f"GMAIL_REFRESH_TOKEN = {refresh_token}")

        # Test sending
        print("\n" + "=" * 60)
        print("Testing Gmail API access...")
        print("=" * 60)

        # Get user's email
        profile_req = urllib.request.Request(
            "https://gmail.googleapis.com/gmail/v1/users/me/profile",
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET"
        )
        with urllib.request.urlopen(profile_req, timeout=10) as resp:
            profile = json.loads(resp.read().decode("utf-8"))
            print(f"\n✅ Connected to Gmail: {profile.get('emailAddress')}")

        print(f"\nDone! Copy the 3 values above to Render Dashboard > Environment.")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
