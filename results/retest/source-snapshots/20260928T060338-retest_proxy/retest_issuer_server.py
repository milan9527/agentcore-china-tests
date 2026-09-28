"""Local adapter for the synthetic issuer, exposed temporarily through HTTPS tunnel."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from cryptography.hazmat.primitives import serialization
import jwt
from retest_backend import handler


def main():
    p=argparse.ArgumentParser();p.add_argument("region");p.add_argument("port",type=int);args=p.parse_args()
    folder=Path(__file__).parent/"results/retest"
    sec=json.loads((folder/f"{args.region}-secrets.json").read_text())
    key=serialization.load_pem_private_key((folder/f"{args.region}-private-key.pem").read_bytes(),None)
    nums=key.private_numbers();jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="retest",alg="RS256",use="sig")
    os.environ.update(CLIENT_SECRET=sec["clientSecret"],PATH_KEY=sec["pathKey"],JWK=json.dumps(jwk),
                      RSA_KEY=json.dumps({"n":nums.public_numbers.n,"d":nums.d}))
    class Adapter(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_GET(self):self.process()
        def do_POST(self):self.process()
        def process(self):
            parts=urlsplit(self.path)
            if not parts.path.startswith("/test/"+sec["pathKey"]+"/"):
                self.send_error(404);return
            try:
                result=handler({"path":parts.path.removeprefix("/test"),"httpMethod":self.command,
                    "headers":dict(self.headers),"requestContext":{"stage":"test"},
                    "queryStringParameters":{k:v[0] for k,v in parse_qs(parts.query).items()},
                    "body":self.rfile.read(int(self.headers.get("Content-Length",0))).decode()},None)
            except Exception as error:
                result={"statusCode":400,"body":json.dumps({"error":type(error).__name__}),"headers":{"Content-Type":"application/json"}}
            body=result["body"].encode()
            self.send_response(result["statusCode"])
            for k,v in result["headers"].items():self.send_header(k,v)
            self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
    ThreadingHTTPServer(("127.0.0.1",args.port),Adapter).serve_forever()


if __name__=="__main__":main()
