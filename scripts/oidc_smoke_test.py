"""End-to-end OIDC check against the running stack: signs in through Keycloak's real login page with
Authorization Code + PKCE (as the browser does), then calls protected API endpoints with the access token.

    python scripts/oidc_smoke_test.py
"""

import base64
import hashlib
import re
import secrets
import sys
from html import unescape
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

ISSUER = "http://localhost:8081/realms/grp-demo"
API = "http://localhost:8000"
CLIENT_ID = "grp-web"
REDIRECT = "http://localhost:5173/"


def sign_in(username: str, password: str) -> str:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    with httpx.Client(follow_redirects=False, timeout=20) as c:
        auth = c.get(f"{ISSUER}/protocol/openid-connect/auth?" + urlencode({
            "client_id": CLIENT_ID, "redirect_uri": REDIRECT, "response_type": "code", "scope": "openid profile",
            "state": secrets.token_urlsafe(8), "code_challenge": challenge, "code_challenge_method": "S256",
        }))
        action = unescape(re.search(r'action="([^"]+)"', auth.text).group(1))
        # Keycloak's session cookies are marked Secure. Browsers still send them to http://localhost (a secure
        # context); httpx doesn't, so forward them explicitly.
        cookies = "; ".join(f"{k}={v}" for k, v in c.cookies.items())
        login = c.post(action, data={"username": username, "password": password}, headers={"Cookie": cookies})
        code = parse_qs(urlparse(login.headers["location"]).query)["code"][0]
        token = c.post(f"{ISSUER}/protocol/openid-connect/token", data={
            "grant_type": "authorization_code", "client_id": CLIENT_ID, "code": code,
            "redirect_uri": REDIRECT, "code_verifier": verifier,
        })
        token.raise_for_status()
        return token.json()["access_token"]


def main() -> int:
    checks = []

    def check(name: str, got: int, want: int) -> None:
        checks.append(got == want)
        print(f"{'PASS' if got == want else 'FAIL'}  {name}: HTTP {got} (expected {want})")

    check("download without a token", httpx.get(f"{API}/api/scenarios/rp50/download").status_code, 401)
    check("download with a forged token",
          httpx.get(f"{API}/api/scenarios/rp50/download", headers={"Authorization": "Bearer abc.def.ghi"}).status_code, 401)
    viewer = sign_in("viewer", "viewer")
    analyst = sign_in("analyst", "analyst")
    check("explain as viewer", httpx.post(f"{API}/api/explain", headers={"Authorization": f"Bearer {viewer}"},
          json={"scenario_id": "rp100", "question": "How many people are exposed?"}, timeout=120).status_code, 200)
    check("download as viewer (no analyst role)",
          httpx.get(f"{API}/api/scenarios/rp50/download", headers={"Authorization": f"Bearer {viewer}"}).status_code, 403)
    check("download as analyst",
          httpx.get(f"{API}/api/scenarios/rp50/download", headers={"Authorization": f"Bearer {analyst}"}).status_code, 200)
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
