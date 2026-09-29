"""Provision isolated private origin/proxy hosts and a VPC Browser."""
import base64
import datetime as dt
import hashlib
import ipaddress
import json
import secrets
import time
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from suite import ROOT


def run(s):
    ec2 = s.client("ec2")
    subnets = sorted((x for x in ec2.describe_subnets()["Subnets"] if x["DefaultForAz"]),
                     key=lambda x: x["AvailabilityZone"])
    subnet = subnets[0]
    tags = [{"Key": "Purpose", "Value": s.name}]
    s.state.update(subnet=subnet["SubnetId"], vpc=subnet["VpcId"])
    sg = ec2.create_security_group(GroupName=s.name, Description="Temporary proxy verification",
                                  VpcId=subnet["VpcId"], TagSpecifications=[
                                      {"ResourceType": "security-group", "Tags": tags}])["GroupId"]
    s.state["sg"] = sg
    s.resource("sg", sg)
    ec2.authorize_security_group_ingress(GroupId=sg, IpPermissions=[
        {"IpProtocol": "tcp", "FromPort": p, "ToPort": p,
         "UserIdGroupPairs": [{"GroupId": sg}]} for p in [80, 443, 8000, 8080, 8081, 8443, 3128, 3129]])
    enis = {}
    for role in ("origin", "proxy"):
        eni = ec2.create_network_interface(SubnetId=subnet["SubnetId"], Groups=[sg],
            Description=s.name + "-" + role, TagSpecifications=[{"ResourceType": "network-interface", "Tags": tags}])["NetworkInterface"]
        enis[role] = eni
        s.resource("eni", eni["NetworkInterfaceId"])
    origin_ip = enis["origin"]["PrivateIpAddress"]
    proxy_ip = enis["proxy"]["PrivateIpAddress"]
    assert origin_ip != proxy_ip
    dns = enis["origin"].get("PrivateDnsName") or "ip-" + origin_ip.replace(".", "-") + "." + s.region + ".compute.internal"
    hostnames = [dns, "proxy-only.agentcore.test"]
    s.state.update(private_ip=origin_ip, proxy_ip=proxy_ip, target_dns=dns, target_hosts=[origin_ip, *hostnames])
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, s.name + " test CA")])
    now = dt.datetime.now(dt.timezone.utc)
    ca = x509.CertificateBuilder().subject_name(root_name).issuer_name(root_name).public_key(ca_key.public_key()).serial_number(
        x509.random_serial_number()).not_valid_before(now-dt.timedelta(hours=1)).not_valid_after(now+dt.timedelta(days=1)).add_extension(
        x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(ca_key, hashes.SHA256())
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, origin_ip)])).issuer_name(
        root_name).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(
        now-dt.timedelta(hours=1)).not_valid_after(now+dt.timedelta(days=1)).add_extension(
        x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(origin_ip)), *[x509.DNSName(h) for h in hostnames]]),
        critical=False).sign(ca_key, hashes.SHA256())
    password = secrets.token_hex(24)
    sm = s.client("secretsmanager")
    for label, value in [
        ("ca_secret", ca.public_bytes(serialization.Encoding.PEM).decode()),
        ("proxy_secret", json.dumps({"username": "cntest", "password": password})),
        ("bad_proxy_secret", json.dumps({"username": "cntest", "password": secrets.token_hex(24)})),
    ]:
        created = sm.create_secret(Name=s.name + "-" + label, SecretString=value, Tags=tags)
        s.state[label] = created["ARN"]
        s.resource("secret", created["ARN"])
    iam = s.client("iam")
    role = iam.create_role(RoleName=s.name+"-agentcore", AssumeRolePolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [{"Effect": "Allow",
            "Principal": {"Service": "bedrock-agentcore.amazonaws.com"}, "Action": "sts:AssumeRole"}]}), Tags=tags)
    s.state["agentcore_role"] = role["Role"]["Arn"]
    s.resource("role", s.name+"-agentcore")
    iam.put_role_policy(RoleName=s.name+"-agentcore", PolicyName="proxy-validation", PolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Action": ["secretsmanager:GetSecretValue"],
             "Resource": [s.state[x] for x in ("ca_secret", "proxy_secret", "bad_proxy_secret")]},
            {"Effect": "Allow", "Action": ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces",
                "ec2:DeleteNetworkInterface", "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups"], "Resource": "*"}]}))
    ami = s.client("ssm").get_parameter(Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64")["Parameter"]["Value"]
    for host_role in ("origin", "proxy"):
        files = {
            "server.py": (ROOT/"proxy_validation_fixture.py").read_bytes(),
            "config.json": json.dumps({"role": host_role, "targetIp": origin_ip,
                "targetHosts": [origin_ip, *hostnames], "password": password}).encode(),
        }
        if host_role == "origin":
            files["server.pem"] = leaf.public_bytes(serialization.Encoding.PEM)
            files["server.key"] = leaf_key.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        userdata = "#!/bin/bash\nset -eu\numask 077\nmkdir -p /opt/proxy-validation\n"
        for name, value in files.items():
            userdata += "base64 -d > /opt/proxy-validation/" + name + " <<'FIXTURE'\n" + base64.b64encode(value).decode() + "\nFIXTURE\n"
        userdata += "nohup python3 -u /opt/proxy-validation/server.py >/var/log/proxy-validation.log 2>&1 &\n"
        response = ec2.run_instances(ImageId=ami, InstanceType="t3.micro", MinCount=1, MaxCount=1,
            NetworkInterfaces=[{"NetworkInterfaceId": enis[host_role]["NetworkInterfaceId"], "DeviceIndex": 0}],
            UserData=userdata, MetadataOptions={"HttpTokens": "required"},
            TagSpecifications=[{"ResourceType": resource_type, "Tags": tags} for resource_type in ("instance", "volume")],
            BlockDeviceMappings=[{"DeviceName": "/dev/xvda",
                "Ebs": {"VolumeSize": 8, "VolumeType": "gp3", "Encrypted": True, "DeleteOnTermination": True}}])
        iid = response["Instances"][0]["InstanceId"]
        s.state[host_role+"_instance"] = iid
        s.resource("instance", iid)
    instance_ids = [s.state[r+"_instance"] for r in ("origin", "proxy")]
    ec2.get_waiter("instance_running").wait(InstanceIds=instance_ids, WaiterConfig={"Delay": 5, "MaxAttempts": 60})
    instances = [i for reservation in ec2.describe_instances(InstanceIds=instance_ids)["Reservations"] for i in reservation["Instances"]]
    assert all(not i.get("PublicIpAddress") for i in instances)
    s.record("proxy.validation.environment", "PASS", {
        "profile": "china", "account": s.account, "instances": [{
            "id": i["InstanceId"], "ip": i["PrivateIpAddress"], "dns": i["PrivateDnsName"]} for i in instances],
        "originIp": origin_ip, "proxyIp": proxy_ip, "targetDns": dns, "publicAccess": False,
        "securityGroup": sg, "fixtureSha256": hashlib.sha256(files["server.py"]).hexdigest(),
        "controlEndpoint": s.control.meta.endpoint_url})
    created = s.control.create_browser(name=s.name.replace("-", "_")+"_proxy",
        executionRoleArn=s.state["agentcore_role"], networkConfiguration={"networkMode": "VPC",
            "vpcConfig": {"subnets": [subnet["SubnetId"]], "securityGroups": [sg], "requireServiceS3Endpoint": False}},
        tags={"Purpose": s.name})
    s.state["vpc_browser"] = created["browserId"]
    s.resource("browser", created["browserId"])
    s.wait(lambda: s.control.get_browser(browserId=created["browserId"]), timeout=600)
