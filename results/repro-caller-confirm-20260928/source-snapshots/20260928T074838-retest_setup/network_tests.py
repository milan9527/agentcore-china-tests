import base64
import datetime as dt
import ipaddress
import json
import secrets
import time
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from playwright.sync_api import sync_playwright
from browser_tests import start, stop, connect
from suite import ROOT


def infra(s):
    ec2 = s.client("ec2")
    for key, suffix in [("ca_secret", "-root-ca-"), ("proxy_secret", "-proxy-")]:
        previous = next((x["id"] for x in s.state["resources"] if x["kind"] == "secret" and s.name + suffix in x["id"]), None)
        if previous:
            s.state[key] = previous
    subnet = next(x for x in ec2.describe_subnets()["Subnets"] if x["DefaultForAz"])
    s.state["subnet"] = subnet["SubnetId"]
    s.state["vpc"] = subnet["VpcId"]
    tags = [{"Key": "Purpose", "Value": s.name}, {"Key": "Name", "Value": s.name}]
    sg = s.state.get("sg")
    if not sg:
        sg = ec2.create_security_group(GroupName=s.name, Description="Temporary AgentCore private feature tests", VpcId=subnet["VpcId"])["GroupId"]
        s.resource("sg", sg)
    s.state["sg"] = sg
    ec2.create_tags(Resources=[sg], Tags=tags)
    if not ec2.describe_security_groups(GroupIds=[sg])["SecurityGroups"][0]["IpPermissions"]:
        ec2.authorize_security_group_ingress(GroupId=sg, IpPermissions=[{"IpProtocol": "tcp", "FromPort": p, "ToPort": p,
            "UserIdGroupPairs": [{"GroupId": sg}]} for p in [8000, 8443, 3128, 2049]])
    old_eni = next((x for x in s.state["resources"] if x["kind"] == "eni"), None)
    if old_eni:
        eni = ec2.describe_network_interfaces(NetworkInterfaceIds=[old_eni["id"]])["NetworkInterfaces"][0]
    else:
        eni = ec2.create_network_interface(SubnetId=subnet["SubnetId"], Groups=[sg], Description=s.name)["NetworkInterface"]
        s.resource("eni", eni["NetworkInterfaceId"])
    ip = eni["PrivateIpAddress"]
    s.state["private_ip"] = ip
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, s.name + " root CA")])
    now = dt.datetime.now(dt.timezone.utc)
    ca = x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(
        now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=7)).add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(ca_key, hashes.SHA256())
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ip)])).issuer_name(name).public_key(key.public_key()).serial_number(
        x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=7)).add_extension(
        x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(ip))]), critical=False).sign(ca_key, hashes.SHA256())
    pem = ca.public_bytes(serialization.Encoding.PEM).decode()
    if "ca_secret" in s.state:
        root_secret = s.client("secretsmanager").put_secret_value(SecretId=s.state["ca_secret"], SecretString=pem)
    else:
        root_secret = s.client("secretsmanager").create_secret(Name=s.name + "-root-ca", SecretString=pem, Tags=tags)
        s.resource("secret", root_secret["ARN"])
    s.state["ca_secret"] = root_secret["ARN"]
    password = secrets.token_hex(16)
    if "proxy_secret" in s.state:
        proxy_secret = s.client("secretsmanager").put_secret_value(SecretId=s.state["proxy_secret"], SecretString=json.dumps({"username": "cntest", "password": password}))
    else:
        proxy_secret = s.client("secretsmanager").create_secret(Name=s.name + "-proxy", SecretString=json.dumps({"username": "cntest", "password": password}), Tags=tags)
        s.resource("secret", proxy_secret["ARN"])
    s.state["proxy_secret"] = proxy_secret["ARN"]
    files = {"private_server.py": (ROOT / "private_server.py").read_bytes(),
        "config.json": json.dumps({"ip": ip, "password": password}).encode(),
        "server.pem": cert.public_bytes(serialization.Encoding.PEM),
        "server.key": key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())}
    userdata = "#!/bin/bash\nmkdir -p /opt/cn-test\n"
    for path, content in files.items():
        userdata += "base64 -d > /opt/cn-test/" + path + " <<'CNFIXTURE'\n" + base64.b64encode(content).decode() + "\nCNFIXTURE\n"
    userdata += "chmod 600 /opt/cn-test/*.key /opt/cn-test/config.json\nnohup python3 /opt/cn-test/private_server.py >/var/log/cn-test.log 2>&1 &\n"
    ami = s.client("ssm").get_parameter(Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64")["Parameter"]["Value"]
    r = ec2.run_instances(ImageId=ami, InstanceType="t3.micro", MinCount=1, MaxCount=1,
        NetworkInterfaces=[{"NetworkInterfaceId": eni["NetworkInterfaceId"], "DeviceIndex": 0}],
        UserData=userdata, MetadataOptions={"HttpTokens": "required"}, TagSpecifications=[{"ResourceType": "instance", "Tags": tags},
        {"ResourceType": "volume", "Tags": tags}], BlockDeviceMappings=[{"DeviceName": "/dev/xvda",
            "Ebs": {"VolumeSize": 8, "VolumeType": "gp3", "Encrypted": True, "DeleteOnTermination": True}}])
    iid = r["Instances"][0]["InstanceId"]
    s.resource("instance", iid)
    s.state["instance"] = iid
    s.save()
    ec2.get_waiter("instance_running").wait(InstanceIds=[iid], WaiterConfig={"Delay": 5, "MaxAttempts": 40})
    return {"instanceId": iid, "privateIp": ip, "publicAccess": False, "subnet": subnet["SubnetId"]}


def run(s):
    if "instance" not in s.state:
        if not s.test("network.fixture", lambda: infra(s)):
            return
    c = s.control
    network = {"networkMode": "VPC", "vpcConfig": {"subnets": [s.state["subnet"]], "securityGroups": [s.state["sg"]],
                                                  "requireServiceS3Endpoint": False}}
    if "vpc_browser" not in s.state:
        r = s.test("browser.vpc.create", lambda: c.create_browser(name=s.name.replace("-", "_") + "_vpc",
            executionRoleArn=s.state["agentcore_role"], networkConfiguration=network, tags={"Purpose": s.name}))
        if not r:
            return
        s.state["vpc_browser"] = r["browserId"]
        s.resource("browser", r["browserId"])
    bid = s.state["vpc_browser"]
    s.test("browser.vpc.ready", lambda: s.wait(lambda: c.get_browser(browserId=bid)))
    r = s.test("browser.vpc.start", lambda: start(s, bid))
    if not r:
        return
    ip = s.state["private_ip"]
    with sync_playwright() as pw:
        br = connect(s, pw, r)
        pg = br.contexts[0].new_page()
        def private():
            deadline = time.monotonic() + 180
            while True:
                try:
                    response = pg.goto(f"http://{ip}:8000", timeout=15000)
                    assert response.status == 200
                    assert "private-network-ok" in pg.locator("body").inner_text()
                    return {"privateHttpStatus": response.status, "title": pg.title()}
                except Exception:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(5)
        s.test("browser.vpc.private_http", private)
        def untrusted():
            try:
                pg.goto(f"https://{ip}:8443", timeout=20000)
            except Exception as e:
                assert "ERR_CERT_AUTHORITY_INVALID" in str(e), str(e)
                return "Private CA rejected without trust configuration"
            raise AssertionError("Untrusted CA accepted")
        s.test("browser.certificates.untrusted_rejected", untrusted)
        br.close()
    s.test("browser.vpc.stop", lambda: stop(s, r))
    certs = [{"location": {"secretsManager": {"secretArn": s.state["ca_secret"]}}}]
    r = s.test("browser.certificates.start_with_root_ca", lambda: start(s, bid, certificates=certs))
    if r:
        with sync_playwright() as pw:
            br = connect(s, pw, r)
            pg = br.contexts[0].new_page()
            def trusted():
                response = pg.goto(f"https://{ip}:8443", timeout=25000)
                assert response.status == 200
                assert "private-network-ok" in pg.locator("body").inner_text()
                return "Private TLS accepted with supplied CA; no ignoreHTTPSerrors"
            s.test("browser.certificates.trusted_https", trusted)
            br.close()
        s.test("browser.certificates.stop", lambda: stop(s, r))
    proxy = {"proxies": [{"externalProxy": {"server": ip, "port": 3128,
                    "credentials": {"basicAuth": {"secretArn": s.state["proxy_secret"]}}}}],
             "bypass": {"domainPatterns": [ip]}}
    r = s.test("browser.proxy.start_basic_auth_bypass", lambda: start(s, bid, proxyConfiguration=proxy))
    if r:
        with sync_playwright() as pw:
            br = connect(s, pw, r)
            pg = br.contexts[0].new_page()
            def proxied():
                response = pg.goto("http://proxy-only.agentcore.test", timeout=30000)
                assert response.status == 200
                assert "authenticated-proxy-ok" in pg.locator("body").inner_text()
                return "Request to synthetic domain routed through authenticated proxy"
            s.test("browser.proxy.authenticated_routing", proxied)
            def bypass():
                pg.goto(f"http://{ip}:8000", timeout=25000)
                assert "private-network-ok" in pg.locator("body").inner_text()
                return "Bypass reached private endpoint directly"
            s.test("browser.proxy.bypass", bypass)
            br.close()
        s.test("browser.proxy.stop", lambda: stop(s, r))
    s.test("browser.efs", lambda: efs(s))


def efs(s):
    efs = s.client("efs")
    fs = efs.create_file_system(CreationToken=s.name, Encrypted=True, PerformanceMode="generalPurpose",
                               Tags=[{"Key": "Purpose", "Value": s.name}])
    fid = fs["FileSystemId"]
    s.resource("efs", fid)
    deadline = time.monotonic() + 180
    while efs.describe_file_systems(FileSystemId=fid)["FileSystems"][0]["LifeCycleState"] != "available":
        assert time.monotonic() < deadline, "EFS creation timeout"
        time.sleep(3)
    mt = efs.create_mount_target(FileSystemId=fid, SubnetId=s.state["subnet"], SecurityGroups=[s.state["sg"]])
    s.resource("efs-mount", mt["MountTargetId"])
    ap = efs.create_access_point(FileSystemId=fid, PosixUser={"Uid": 1000, "Gid": 1000},
         RootDirectory={"Path": "/test", "CreationInfo": {"OwnerUid": 1000, "OwnerGid": 1000, "Permissions": "0777"}},
         Tags=[{"Key": "Purpose", "Value": s.name}])
    s.resource("efs-ap", ap["AccessPointId"])
    s.client("iam").put_role_policy(RoleName=s.name + "-agentcore", PolicyName="efs-test", PolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["elasticfilesystem:ClientMount", "elasticfilesystem:ClientWrite"],
            "Resource": fs["FileSystemArn"], "Condition": {"ArnEquals": {"elasticfilesystem:AccessPointArn": ap["AccessPointArn"]}}}]}))
    while efs.describe_mount_targets(MountTargetId=mt["MountTargetId"])["MountTargets"][0]["LifeCycleState"] != "available":
        assert time.monotonic() < deadline, "EFS mount target creation timeout"
        time.sleep(3)
    conf = [{"efsConfiguration": {"accessPointArn": ap["AccessPointArn"], "fileSystemArn": fs["FileSystemArn"], "mountPath": "/mnt/efs"}}]
    r = start(s, s.state["vpc_browser"], filesystemConfigurations=conf)
    s.record("browser.efs.session_start", "PASS", {"sessionId": r["sessionId"]})
    try:
        with sync_playwright() as pw:
            br = connect(s, pw, r)
            ctx = br.contexts[0]
            pg = ctx.new_page()
            pg.goto(f"http://{s.state['private_ip']}:8000")
            cdp = ctx.new_cdp_session(pg)
            cdp.send("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": "/mnt/efs"})
            pg.locator("#download").click()
            time.sleep(3)
            pg.goto("file:///mnt/efs/persist.txt")
            assert "efs-persist-ok" in pg.locator("body").inner_text()
            br.close()
    finally:
        stop(s, r)
    r2 = start(s, s.state["vpc_browser"], filesystemConfigurations=conf)
    try:
        with sync_playwright() as pw:
            br = connect(s, pw, r2)
            pg = br.contexts[0].new_page()
            pg.goto("file:///mnt/efs/persist.txt")
            assert "efs-persist-ok" in pg.locator("body").inner_text()
            br.close()
    finally:
        stop(s, r2)
    return {"fileSystemId": fid, "writtenAndRestoredAcrossSessions": True}
