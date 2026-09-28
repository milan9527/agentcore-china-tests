"""Synthetic issuer/backend. No real identities; private key exists only for this test."""
import base64
import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qs, urlencode


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def unb64(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def token(claims):
    key = json.loads(os.environ["RSA_KEY"])
    unsigned = b64(b'{"alg":"RS256","kid":"retest","typ":"JWT"}') + "." + b64(json.dumps(claims).encode())
    digest = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(unsigned.encode()).digest()
    size = (key["n"].bit_length() + 7) // 8
    padded = b"\x00\x01" + b"\xff" * (size - len(digest) - 3) + b"\x00" + digest
    signature = pow(int.from_bytes(padded, "big"), key["d"], key["n"]).to_bytes(size, "big")
    return unsigned + "." + b64(signature)


def verify_jwt(value):
    key = json.loads(os.environ["RSA_KEY"])
    a, b, c = value.split(".")
    digest = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256((a + "." + b).encode()).digest()
    size = (key["n"].bit_length() + 7) // 8
    padded = b"\x00\x01" + b"\xff" * (size - len(digest) - 3) + b"\x00" + digest
    assert pow(int.from_bytes(unb64(c), "big"), 65537, key["n"]).to_bytes(size, "big") == padded
    claims = json.loads(unb64(b))
    assert claims["exp"] > time.time()
    return claims


def response(body, status=200, headers=None):
    return {"statusCode": status, "headers": {"Content-Type": "application/json", **(headers or {})},
            "body": body if isinstance(body, str) else json.dumps(body)}


def handler(event, context):
    prefix = "/" + os.environ["PATH_KEY"]
    path = event.get("path", "")
    if event.get("type") == "REQUEST":
        allowed = path.startswith(prefix + "/")
        return {"principalId": "synthetic-fixture", "policyDocument": {"Version": "2012-10-17",
                "Statement": [{"Action": "execute-api:Invoke", "Effect": "Allow" if allowed else "Deny",
                               "Resource": event["methodArn"]}]}}
    if "httpMethod" not in event:
        return {"sum": event.get("a", 0) + event.get("b", 0), "fixture": "retest-lambda"}
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    issuer = "https://" + headers["host"] + "/" + event["requestContext"]["stage"] + prefix
    leaf = path[len(prefix):]
    query = event.get("queryStringParameters") or {}
    if leaf == "/.well-known/openid-configuration":
        return response({"issuer": issuer, "jwks_uri": issuer + "/jwks", "authorization_endpoint": issuer + "/authorize",
            "token_endpoint": issuer + "/token", "response_types_supported": ["code"], "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"], "scopes_supported": ["test", "openid"],
            "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
            "grant_types_supported": ["client_credentials", "authorization_code", "refresh_token",
                                      "urn:ietf:params:oauth:grant-type:token-exchange"],
            "code_challenge_methods_supported": ["S256"]})
    if leaf == "/jwks":
        return response({"keys": [json.loads(os.environ["JWK"])]})
    if leaf == "/page":
        return response('<html><head><title>Retest China</title></head><body><h1>Browser retest 中国区</h1>'
            '<input id="name" autofocus style="width:400px;height:40px;font:24px sans-serif">'
            '<a id="download" download="retest.txt" href="data:text/plain,agentcore-download-ok">Download</a>'
            '<a id="httpdownload" download href="download">HTTP download</a></body></html>',
            headers={"Content-Type": "text/html"})
    if leaf == "/download":
        return response("agentcore-download-ok", headers={"Content-Type": "application/octet-stream",
                                                        "Content-Disposition": 'attachment; filename="retest.txt"'})
    if leaf == "/authorize":
        assert query["client_id"] == "cn-retest"
        payload = json.dumps({k: query.get(k) for k in ["redirect_uri", "code_challenge"]} | {"exp": time.time() + 300}).encode()
        code = b64(payload) + "." + b64(hmac.new(os.environ["CLIENT_SECRET"].encode(), payload, hashlib.sha256).digest())
        return response("", 302, {"Location": query["redirect_uri"] + ("&" if "?" in query["redirect_uri"] else "?") +
                                  urlencode({"code": code, "state": query.get("state", "")})})
    if leaf == "/token":
        raw = event.get("body") or ""
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode()
        form = {k: v[0] for k, v in parse_qs(raw).items()}
        client_id, client_secret = form.get("client_id"), form.get("client_secret")
        if headers.get("authorization", "").startswith("Basic "):
            client_id, client_secret = base64.b64decode(headers["authorization"][6:]).decode().split(":", 1)
        if client_id != "cn-retest" or not hmac.compare_digest(client_secret or "", os.environ["CLIENT_SECRET"]):
            return response({"error": "invalid_client"}, 401)
        grant = form.get("grant_type", "")
        sub = "synthetic-service"
        if grant == "authorization_code":
            code, signature = form["code"].split(".")
            payload = unb64(code)
            assert hmac.compare_digest(unb64(signature), hmac.new(os.environ["CLIENT_SECRET"].encode(), payload, hashlib.sha256).digest())
            obj = json.loads(payload)
            assert obj["exp"] > time.time() and obj["redirect_uri"] == form["redirect_uri"]
            if obj.get("code_challenge"):
                assert b64(hashlib.sha256(form["code_verifier"].encode()).digest()) == obj["code_challenge"]
            sub = "synthetic-user"
        elif grant == "urn:ietf:params:oauth:grant-type:token-exchange":
            sub = verify_jwt(form["subject_token"])["sub"]
        elif grant not in ["client_credentials", "refresh_token"]:
            return response({"error": "unsupported_grant_type"}, 400)
        claims = {"iss": issuer, "aud": "cn-retest", "client_id": "cn-retest", "sub": sub, "scope": form.get("scope", "test"),
                  "iat": int(time.time()), "exp": int(time.time()) + 900, "grant": grant}
        # Log only flow metadata; never tokens, codes, or credentials.
        print(json.dumps({"event": "token_issued", "grant": grant, "subject": sub}))
        return response({"access_token": token(claims), "token_type": "Bearer", "expires_in": 900,
                         "refresh_token": token(claims | {"refresh": True}), "scope": claims["scope"]})
    if leaf == "/secure":
        try:
            bearer = headers.get("authorization", "").removeprefix("Bearer ")
            claims = verify_jwt(bearer)
            return response({"authenticated": True, "sub": claims["sub"], "grant": claims.get("grant"),
                             "tokenSha256": hashlib.sha256(bearer.encode()).hexdigest()})
        except Exception:
            return response({"error": "invalid_token"}, 401)
    if leaf in ["/echo", "/callback"]:
        return response({"fixture": "retest", "ok": True})
    return response({"error": "not_found"}, 404)
