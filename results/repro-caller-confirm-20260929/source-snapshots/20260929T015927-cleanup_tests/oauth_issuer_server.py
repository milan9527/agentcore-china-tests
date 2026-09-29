"""Synthetic HTTPS-tunneled IdP with secret-free token issuance/usage evidence."""
import argparse
import datetime as dt
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives import serialization
import jwt
import retest_backend as backend

JWT_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("region")
    parser.add_argument("port", type=int)
    args = parser.parse_args()
    folder = Path(os.environ["RETEST_RESULTS_DIR"])
    sec = json.loads((folder / f"{args.region}-secrets.json").read_text())
    key = serialization.load_pem_private_key(
        (folder / f"{args.region}-private-key.pem").read_bytes(), None)
    nums = key.private_numbers()
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="retest", alg="RS256", use="sig")
    os.environ.update(CLIENT_SECRET=sec["clientSecret"], PATH_KEY=sec["pathKey"],
        JWK=json.dumps(jwk), RSA_KEY=json.dumps({"n": nums.public_numbers.n, "d": nums.d}))
    lock = threading.Lock()

    def audit(row):
        with lock, (folder / f"{args.region}-issuer-events.jsonl").open("a") as stream:
            stream.write(json.dumps({"time": dt.datetime.now(dt.timezone.utc).isoformat(),
                "region": args.region, **row}) + "\n")

    class Adapter(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            self.process()

        def do_POST(self):
            self.process()

        def process(self):
            parts = urlsplit(self.path)
            prefix = "/test/" + sec["pathKey"]
            if not parts.path.startswith(prefix + "/"):
                self.send_error(404)
                return
            leaf = parts.path[len(prefix):]
            issuer = "https://" + self.headers["Host"] + prefix
            body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
            form = {k: v[0] for k, v in parse_qs(body).items()}
            token_meta = {}
            try:
                if leaf == "/secure":
                    bearer = self.headers.get("Authorization", "").removeprefix("Bearer ")
                    jwt.decode(bearer, key.public_key(), algorithms=["RS256"],
                               audience="cn-retest", issuer=issuer)
                if leaf == "/token":
                    token_meta = {
                        "grant": form.get("grant_type"), "scope": form.get("scope"),
                        "clientAuthentication": "CLIENT_SECRET_BASIC"
                        if self.headers.get("Authorization", "").startswith("Basic ") else "CLIENT_SECRET_POST",
                        "subjectTokenPresent": bool(form.get("subject_token")),
                        "subjectTokenType": form.get("subject_token_type"),
                        "actorTokenPresent": bool(form.get("actor_token")),
                        "actorTokenType": form.get("actor_token_type"),
                        "assertionPresent": bool(form.get("assertion")),
                        "codeVerifierPresent": bool(form.get("code_verifier")),
                    }
                    subject = form.get("subject_token") or form.get("assertion")
                    if subject:
                        claims = jwt.decode(subject, key.public_key(), algorithms=["RS256"],
                                            audience="cn-retest", issuer=issuer)
                        token_meta.update(subject=claims["sub"],
                            subjectTokenSha256=hashlib.sha256(subject.encode()).hexdigest())
                event = {"path": parts.path.removeprefix("/test"), "httpMethod": self.command,
                    "headers": dict(self.headers), "requestContext": {"stage": "test"},
                    "queryStringParameters": {k: v[0] for k, v in parse_qs(parts.query).items()},
                    "body": body}
                result = backend.handler(event, None)
                if leaf == "/.well-known/openid-configuration":
                    discovery = json.loads(result["body"])
                    discovery["grant_types_supported"].append(JWT_GRANT)
                    result = backend.response(discovery)
                if leaf == "/token" and form.get("grant_type") == JWT_GRANT:
                    # Reuse the fixture's client authentication before issuing a JWT-grant token.
                    if result["statusCode"] == 400 and json.loads(result["body"]).get("error") == "unsupported_grant_type":
                        claims = {"iss": issuer, "aud": "cn-retest", "client_id": "cn-retest",
                            "sub": token_meta["subject"], "scope": form.get("scope", "test"),
                            "iat": int(time.time()), "exp": int(time.time()) + 900, "grant": JWT_GRANT}
                        result = backend.response({"access_token": backend.token(claims),
                            "token_type": "Bearer", "expires_in": 900, "scope": claims["scope"]})
            except Exception as error:
                result = backend.response({"error": "invalid_token" if leaf == "/secure" else "invalid_grant",
                    "exceptionType": type(error).__name__}, 401 if leaf == "/secure" else 400)
            entry = {"event": "issuer_http", "endpoint": leaf, "method": self.command,
                     "status": result["statusCode"], **token_meta}
            if leaf == "/token" and result["statusCode"] == 200:
                value = json.loads(result["body"])["access_token"]
                claims = jwt.decode(value, key.public_key(), algorithms=["RS256"],
                                    audience="cn-retest", issuer=issuer)
                entry.update(tokenSha256=hashlib.sha256(value.encode()).hexdigest(),
                             issuedSubject=claims["sub"], issuedGrant=claims["grant"])
            if leaf == "/secure" and result["statusCode"] == 200:
                entry.update(json.loads(result["body"]))
            audit(entry)
            payload = result["body"].encode()
            self.send_response(result["statusCode"])
            for k, v in result["headers"].items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    ThreadingHTTPServer(("127.0.0.1", args.port), Adapter).serve_forever()


if __name__ == "__main__":
    main()
