

# Amazon Bedrock AgentCore in Amazon Web Services China
<a name="bedrock-agentcore"></a>

Amazon Bedrock AgentCore is the platform to build and connect agents. It helps engineers ship agents fast with any framework and any model, and connect them to enterprise systems and tools, with security enforced at the infrastructure layer that agents can’t bypass.

## Region availability
<a name="feature-regions"></a>

Amazon Bedrock AgentCore is available in the following regions in China:
+  China (Beijing) Region
+  China (Ningxia) Region

## How Amazon Bedrock AgentCore differs
<a name="feature-diff"></a>

In the China (Beijing) and China (Ningxia) Regions, Amazon Bedrock AgentCore offers the following components: Runtime, Code Interpreter, Browser, Identity, Gateway, and Observability. The differences below apply to these components.

### Capabilities not available in the China Regions
<a name="_capabilities_not_available_in_the_china_regions"></a>

The following AgentCore capabilities are not available in the China (Beijing) and China (Ningxia) Regions:
+ Memory
+ Policy
+ Harness
+ Payments
+ Knowledge Bases
+ Evaluations
+ Optimizations
+ Registry

### Identity
<a name="_identity"></a>
+ Private identity providers (IdP) — Private IdP configurations are not available in the China (Beijing) and China (Ningxia) Regions.
+ OAuth 2.0 providers — The following built-in OAuth providers are not available in the China (Beijing) and China (Ningxia) Regions: GitHub, Google, Facebook, X, Reddit, Twitch, Dropbox, CyberArk.

### Runtime
<a name="_runtime"></a>
+ Managed EC2 instance capacity provider — The Managed EC2 instance capacity provider is not available in the China (Beijing) and China (Ningxia) Regions. Only the MicroVM capacity provider is supported.
+ Bring-your-own file system (Amazon S3 Files) — The Amazon S3 Files option for bring-your-own file system is not available in the China (Beijing) and China (Ningxia) Regions.
+ Amazon Cognito inbound authorization — Cognito user pool option is not supported

### Tools
<a name="_tools"></a>
+ Bring-your-own file system (Amazon S3 Files) — The Amazon S3 Files option for bring-your-own file system is not available in the China (Beijing) and China (Ningxia) Regions.
+ Web Bot Auth (Signer) — Web Bot Auth (Signer) is not available in the China (Beijing) and China (Ningxia) Regions.

### Gateway
<a name="_gateway"></a>
+ Semantic search — Semantic search for tool discovery is not available in the China (Beijing) and China (Ningxia) Regions. Tool listing and tool invocation are unaffected.
+ Amazon Cognito authorizer — A CUSTOM\_JWT authorizer cannot use an Amazon Cognito user pool in the China (Beijing) and China (Ningxia) Regions. Use another OpenID Connect (OIDC)-compliant identity provider. The console Amazon Cognito quick-setup path is not offered.
+ Inbound authorization options — The "No authorization" inbound authorization option is not available in the China (Beijing) and China (Ningxia) Regions. All gateways must use CUSTOM\_JWT or AWS\_IAM inbound authorization.
+ Inference targets — Inference targets are not available in the China (Beijing) and China (Ningxia) Regions.
+ Connectors — The console connector catalog (for example, Slack, Jira, Salesforce, and Microsoft) is not available in the China (Beijing) and China (Ningxia) Regions. Most connectors call third-party SaaS endpoints located outside of China.
+ Amazon Web Services WAF integration — Amazon WAF integration for the AgentCore Gateway resource type is not available in the China (Beijing) and China (Ningxia) Regions.
+ Gateway rules — Gateway rules are not available in the China (Beijing) and China (Ningxia) Regions.
+ ConfigBundle A/B testing — A/B testing for ConfigBundle is not available in the China (Beijing) and China (Ningxia) Regions.

### Documentation site navigation
<a name="_documentation_site_navigation"></a>
+ Console, GitHub, and boto3 quick-access tiles — On the AgentCore documentation landing page, the Console, GitHub, and boto3 quick-access tiles are not available in the China (Beijing) and China (Ningxia) Regions. These tiles link to resources that are not applicable in the China Regions.

## Documentation
<a name="feature-guides"></a>
+  [Amazon Bedrock AgentCore Developer Guide](https://docs.amazonaws.cn/bedrock-agentcore/latest/devguide/) 