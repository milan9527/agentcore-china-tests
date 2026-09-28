import io
import json
import zipfile
import requests
import time
from botocore.config import Config
from botocore.auth import SigV4QueryAuth
from botocore.awsrequest import AWSRequest
from backend import HTML
from suite import ROOT


def run(s):
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("backend.py", (ROOT / "backend.py").read_bytes())
    s.client("lambda").update_function_code(FunctionName=s.name, ZipFile=z.getvalue())
    s.client("lambda").get_waiter("function_updated_v2").wait(FunctionName=s.name)
    api = s.client("apigateway")
    for r in api.get_resources(restApiId=s.state["api_id"])["items"]:
        for method in r.get("resourceMethods", {}):
            api.update_method(restApiId=s.state["api_id"], resourceId=r["id"], httpMethod=method,
                              patchOperations=[{"op": "replace", "path": "/authorizationType", "value": "AWS_IAM"}])
            api.put_method_response(restApiId=s.state["api_id"], resourceId=r["id"], httpMethod=method,
                                    statusCode="200", responseModels={"application/json": "Empty"})
    api.create_deployment(restApiId=s.state["api_id"], stageName="test")
    s3 = s.session.client("s3", config=Config(signature_version="s3v4"))
    s3.put_object(Bucket=s.state["bucket"], Key="page.html", Body=HTML, ContentType="text/html")
    req = AWSRequest(method="GET", url=s.state["api_url"] + "/page")
    SigV4QueryAuth(s.session.get_credentials().get_frozen_credentials(), "execute-api", s.region, expires=14400).add_auth(req)
    s.state["page_url"] = req.url
    # Signed URLs stay in local state only; published results omit them.
    s.save()
    s.control.update_gateway(gatewayIdentifier=s.state["gateway"]["gatewayId"], name=s.name,
        roleArn=s.state["agentcore_role"], protocolType="MCP", authorizerType="AWS_IAM", exceptionLevel="DEBUG")
    s.wait(lambda: s.control.get_gateway(gatewayIdentifier=s.state["gateway"]["gatewayId"]))
    url = s.state["api_url"] + "/echo"
    for attempt in range(12):
        r = requests.get(url, headers=s.signed_headers(url, service="execute-api"), timeout=30)
        if r.status_code == 200:
            break
        time.sleep(5)
    assert r.status_code == 200, {"status": r.status_code, "body": r.text}
    page = requests.get(s.state["page_url"], timeout=30)
    assert page.status_code == 200, {"pageStatus": page.status_code, "body": page.text[:500]}
    return {"iamBackend": r.json(), "browserPage": "IAM protected API, presigned access"}
