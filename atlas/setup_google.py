"""One-time Google sign-in. Run on a machine with a browser:

    python -m atlas.setup_google

It opens Google's consent screen (read-only Calendar + Gmail) and writes secrets/token.json.
Copy that file to the server; Atlas refreshes it automatically after that."""
from google_auth_oauthlib.flow import InstalledAppFlow

from atlas.config import settings
from atlas.sources.google import SCOPES


def main() -> None:
    if not settings.google_client_secret.exists():
        raise SystemExit(f"Download your OAuth client JSON to {settings.google_client_secret} first (see README).")
    flow = InstalledAppFlow.from_client_secrets_file(str(settings.google_client_secret), SCOPES)
    creds = flow.run_local_server(port=0)
    settings.google_token.parent.mkdir(parents=True, exist_ok=True)
    settings.google_token.write_text(creds.to_json())
    print(f"Saved {settings.google_token}")


if __name__ == "__main__":
    main()
