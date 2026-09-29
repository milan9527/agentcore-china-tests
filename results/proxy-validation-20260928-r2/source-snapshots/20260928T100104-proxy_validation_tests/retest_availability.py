def run(s):
    names=[name for page in s.client("ec2").get_paginator("describe_vpc_endpoint_services").paginate()
           for name in page["ServiceNames"] if "agentcore" in name.lower()]
    for feature in ["gateway.private_link","browser.private_link"]:
        s.record(feature,"NOT_AVAILABLE" if not names else "PARTIAL",
                 {"allPagesScanned":True,"advertisedServices":names,"scope":"This account and region"})
    for resource in s.state["resources"]:
        if resource["kind"]=="oauth-provider" and resource["id"].endswith("-token-exchange"):
            provider=s.control.get_oauth2_credential_provider(name=resource["id"])
            s.record("gateway.oauth.token_exchange.provider_configuration","PASS",
                {"providerArn":provider["credentialProviderArn"],
                 "scope":"Provider configuration is accepted; Gateway target is account-gated"})
