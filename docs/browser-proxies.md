

# Using browser proxies
<a name="browser-proxies"></a>

Amazon Bedrock AgentCore Browser supports routing browser traffic through your own external proxy servers. This enables organizations to:
+  **Achieve IP stability** by routing traffic through proxies with known egress IPs, eliminating re-authentication cycles caused by rotating Amazon IP addresses
+  **Support IP allowlisting** by providing stable, controllable egress addresses for services that require IP-based access controls
+  **Integrate with corporate infrastructure** by routing through your existing proxy servers for access to internal webpages and resources

## Overview
<a name="browser-proxies-overview"></a>

When you create a browser session with proxy configuration, AgentCore Browser configures the browser to route HTTP and HTTPS traffic through your specified proxy servers.

![Browser proxies request flow showing traffic routing from the browser session through a customer-managed proxy server to destination websites.](https://docs.amazonaws.cn/en_us/bedrock-agentcore/latest/devguide/images/browser-proxies-flow.png)


Request flow:

1. You call `StartBrowserSession` with a `proxyConfiguration` specifying your proxy server.

1. If using authentication, AgentCore retrieves proxy credentials from Amazon Secrets Manager.

1. The browser session starts with your proxy configuration applied.

1. Browser traffic routes through your proxy server based on your domain routing rules.

1. Your proxy server forwards requests to destination websites.

The proxy server is infrastructure you own and manage. AgentCore Browser connects to it as a client.

Proxy configuration applies the Chromium `--proxy-server` flag to the browser instance at startup, directing traffic through the specified proxy at the browser level. For scenarios that require network-layer enforcement—for example, when browser-level settings could be modified during runtime—deploy browser sessions within your own VPC. See [Configure Amazon Bedrock AgentCore Runtime and tools for VPC](agentcore-vpc.md).

## Prerequisites
<a name="browser-proxies-prerequisites"></a>

Before configuring browser proxies, ensure you have:
+  **General browser prerequisites** – Complete the standard browser tool setup. See [Get started with AgentCore Browser](browser-quickstart.md).
+  **Proxy server** – An HTTP/HTTPS proxy server that is accessible from the public internet (or reachable within your VPC if using VPC configuration) and supports the HTTP CONNECT method for HTTPS traffic tunneling.
+  ** Amazon Secrets Manager secret** (if using authentication) – A secret containing proxy credentials in JSON format with `username` and `password` keys.
+  **IAM permissions** (if using authentication) – The IAM identity calling `StartBrowserSession` must have `secretsmanager:GetSecretValue` permission for the credential secret.

## Getting started
<a name="browser-proxies-getting-started"></a>

This section shows the simplest configuration to route browser traffic through a proxy.

### Step 1: Create a credentials secret (if using authentication)
<a name="browser-proxies-step1"></a>

If your proxy requires authentication, create a secret in Amazon Secrets Manager:

```
aws secretsmanager create-secret \
  --name "my-proxy-credentials" \
  --secret-string '{"username":"<your-username>","password":"<your-password>"}'
```

Credential format requirements:


| Field | Allowed characters | 
| --- | --- | 
|  `username`  | Alphanumeric plus `@ . _ + = -`  | 
|  `password`  | Alphanumeric plus @ . \_ \+ = - \! \# $ % \* | 

Characters not allowed: colon ( `:` ), newlines, spaces, quotes.

### Step 2: Add IAM permissions
<a name="browser-proxies-step2"></a>

Add this policy to the IAM identity that will create browser sessions:

```
{
"Version": "2012-10-17",		 	 	 
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "secretsmanager:GetSecretValue",
            "Resource": "arn:aws:secretsmanager:AWS Region:AWS account:secret:secret-name*"
        }
    ]
}
```

### Step 3: Create a browser session with proxy
<a name="browser-proxies-step3"></a>

You can create a browser session with proxy configuration using the Amazon CLI, SDK, or API.

**Example**  

1. To start a browser session with a proxy using the Amazon CLI:

   ```
   aws bedrock-agentcore start-browser-session \
     --browser-identifier "aws.browser.v1" \
     --name "my-proxy-session" \
     --proxy-configuration '{
       "proxies": [{
         "externalProxy": {
           "server": "your-proxy-hostname",
           "port": 8080,
           "credentials": {
             "basicAuth": {
               "secretArn": "arn:aws:secretsmanager:region:account-id:secret:secret-name"
             }
           }
         }
       }]
     }'
   ```

   For proxies using IP allowlisting instead of credentials, omit the `credentials` field:

   ```
   aws bedrock-agentcore start-browser-session \
     --browser-identifier "aws.browser.v1" \
     --name "my-proxy-session" \
     --proxy-configuration '{
       "proxies": [{
         "externalProxy": {
           "server": "your-proxy-hostname",
           "port": 8080
         }
       }]
     }'
   ```

1. To start a browser session with a proxy using the Amazon SDK for Python (Boto3):

   ```
   import boto3
   
   client = boto3.client('bedrock-agentcore', region_name='region')
   
   response = client.start_browser_session(
       browserIdentifier="aws.browser.v1",
       name="my-proxy-session",
       proxyConfiguration={
           "proxies": [{
               "externalProxy": {
                   "server": "your-proxy-hostname",
                   "port": 8080,
                   "credentials": {
                       "basicAuth": {
                           "secretArn": "arn:aws:secretsmanager:region:account-id:secret:secret-name"
                       }
                   }
               }
           }]
       }
   )
   print(f"Session ID: {response['sessionId']}")
   ```

   For proxies using IP allowlisting instead of credentials, omit the `credentials` field:

   ```
   proxyConfiguration={
       "proxies": [{
           "externalProxy": {
               "server": "your-proxy-hostname",
               "port": 8080
           }
       }]
   }
   ```

1. To start a browser session with a proxy using the API:

   ```
   PUT /browsers/aws.browser.v1/sessions/start HTTP/1.1
   Host: bedrock-agentcore.region.amazonaws.com
   Content-Type: application/json
   Authorization: AWS4-HMAC-SHA256 ...
   
   {
     "name": "my-proxy-session",
     "proxyConfiguration": {
       "proxies": [{
         "externalProxy": {
           "server": "your-proxy-hostname",
           "port": 8080,
           "credentials": {
             "basicAuth": {
               "secretArn": "arn:aws:secretsmanager:region:account-id:secret:secret-name"
             }
           }
         }
       }]
     }
   }
   ```

## Configuration options
<a name="browser-proxies-configuration"></a>

### Domain-based routing
<a name="browser-proxies-domain-routing"></a>

Use `domainPatterns` to route specific domains through designated proxies:

**Example**  

1. 

   ```
   aws bedrock-agentcore start-browser-session \
     --browser-identifier "aws.browser.v1" \
     --name "domain-routing-session" \
     --proxy-configuration '{
       "proxies": [
         {
           "externalProxy": {
             "server": "corp-proxy.example.com",
             "port": 8080,
             "domainPatterns": [".company.com", ".internal.corp"]
           }
         },
         {
           "externalProxy": {
             "server": "general-proxy.example.com",
             "port": 8080
           }
         }
       ]
     }'
   ```

1. 

   ```
   proxyConfiguration={
       "proxies": [
           {
               "externalProxy": {
                   "server": "corp-proxy.example.com",
                   "port": 8080,
                   "domainPatterns": [".company.com", ".internal.corp"]
               }
           },
           {
               "externalProxy": {
                   "server": "general-proxy.example.com",
                   "port": 8080
               }
           }
       ]
   }
   ```

1. 

   ```
   {
     "proxyConfiguration": {
       "proxies": [
         {
           "externalProxy": {
             "server": "corp-proxy.example.com",
             "port": 8080,
             "domainPatterns": [".company.com", ".internal.corp"]
           }
         },
         {
           "externalProxy": {
             "server": "general-proxy.example.com",
             "port": 8080
           }
         }
       ]
     }
   }
   ```

With this configuration:
+ Requests to \*.company.com and \*.internal.corp route through `corp-proxy.example.com` 
+ All other requests route through `general-proxy.example.com` (default)

Domain pattern format:


| Pattern | Matches | Does not match | 
| --- | --- | --- | 
|  `.example.com`  |  `example.com` , `www.example.com` , `api.example.com`  |  `notexample.com`  | 
|  `example.com`  |  `example.com` (exact match only) |  `www.example.com`  | 

Use `.example.com` (leading dot) for subdomains. Do not use \*.example.com.

### Bypass domains
<a name="browser-proxies-bypass"></a>

Use `bypass.domainPatterns` for domains that should connect directly without any proxy:

**Example**  

1. 

   ```
   aws bedrock-agentcore start-browser-session \
     --browser-identifier "aws.browser.v1" \
     --name "bypass-session" \
     --proxy-configuration '{
       "proxies": [{
         "externalProxy": {
           "server": "proxy.example.com",
           "port": 8080
         }
       }],
       "bypass": {
         "domainPatterns": [".amazonaws.com"]
       }
     }'
   ```

1. 

   ```
   proxyConfiguration={
       "proxies": [{
           "externalProxy": {
               "server": "proxy.example.com",
               "port": 8080
           }
       }],
       "bypass": {
           "domainPatterns": [".amazonaws.com"]
       }
   }
   ```

1. 

   ```
   {
     "proxyConfiguration": {
       "proxies": [{
         "externalProxy": {
           "server": "proxy.example.com",
           "port": 8080
         }
       }],
       "bypass": {
         "domainPatterns": [".amazonaws.com"]
       }
     }
   }
   ```

**Note**  
Proxy configuration is a browser-level routing setting and does not provide network-level traffic control. For network-layer enforcement, deploy browser sessions in your VPC. See [Configure Amazon Bedrock AgentCore Runtime and tools for VPC](agentcore-vpc.md).

### Routing precedence
<a name="browser-proxies-routing-precedence"></a>

Traffic routes according to this precedence (highest to lowest):

1.  **Bypass domains** – Domains matching `bypass.domainPatterns` connect directly.

1.  **Proxy domain patterns** – Domains matching a proxy’s `domainPatterns` route through that proxy (first match wins based on array order).

1.  **Default proxy** – Unmatched domains route through the proxy without `domainPatterns`.

## Complete examples
<a name="browser-proxies-complete-examples"></a>

The following examples show a full proxy configuration with domain patterns, bypass domains, and authentication credentials.

**Example**  

1. 

   ```
   aws bedrock-agentcore start-browser-session \
     --browser-identifier "aws.browser.v1" \
     --name "proxy-session" \
     --proxy-configuration '{
       "proxies": [{
         "externalProxy": {
           "server": "proxy-hostname",
           "port": 8080,
           "domainPatterns": [".company.com"],
           "credentials": {
             "basicAuth": {
               "secretArn": "arn:aws:secretsmanager:region:account-id:secret:secret-name"
             }
           }
         }
       }],
       "bypass": {
         "domainPatterns": [".amazonaws.com"]
       }
     }'
   ```

1. 

   ```
   import boto3
   
   client = boto3.client('bedrock-agentcore', region_name='region')
   
   response = client.start_browser_session(
       browserIdentifier="aws.browser.v1",
       name="proxy-session",
       proxyConfiguration={
           "proxies": [{
               "externalProxy": {
                   "server": "proxy-hostname",
                   "port": 8080,
                   "domainPatterns": [".company.com"],
                   "credentials": {
                       "basicAuth": {
                           "secretArn": "arn:aws:secretsmanager:region:account-id:secret:secret-name"
                       }
                   }
               }
           }],
           "bypass": {
               "domainPatterns": [".amazonaws.com"]
           }
       }
   )
   print(f"Session ID: {response['sessionId']}")
   ```

1. 

   ```
   PUT /browsers/aws.browser.v1/sessions/start HTTP/1.1
   Host: bedrock-agentcore.region.amazonaws.com
   Content-Type: application/json
   Authorization: AWS4-HMAC-SHA256 ...
   
   {
     "name": "proxy-session",
     "proxyConfiguration": {
       "proxies": [{
         "externalProxy": {
           "server": "proxy-hostname",
           "port": 8080,
           "domainPatterns": [".company.com"],
           "credentials": {
             "basicAuth": {
               "secretArn": "arn:aws:secretsmanager:region:account-id:secret:secret-name"
             }
           }
         }
       }],
       "bypass": {
         "domainPatterns": [".amazonaws.com"]
       }
     }
   }
   ```

## Use cases
<a name="browser-proxies-use-cases"></a>

### IP stability for session-based portals
<a name="browser-proxies-use-case-ip-stability"></a>

Healthcare and financial portals often validate sessions based on source IP address. Rotating Amazon IP addresses cause frequent re-authentication. Route traffic through a proxy with stable egress IPs to maintain session continuity.

### Corporate infrastructure integration
<a name="browser-proxies-use-case-corporate"></a>

Organizations that route traffic through corporate proxies can extend this practice to AgentCore Browser sessions, enabling access to internal webpages and resources that require proxy-based connectivity.

### Geographic content access
<a name="browser-proxies-use-case-geographic"></a>

Access region-specific content or test regional website variations by routing traffic through proxies in specific geographic locations.

### Partner network access
<a name="browser-proxies-use-case-partner"></a>

Route partner-specific traffic through dedicated proxy infrastructure while using general proxies for other traffic.

## Session behavior
<a name="browser-proxies-session-behavior"></a>

### Configuration lifecycle
<a name="browser-proxies-config-lifecycle"></a>
+  **Set at creation** – Proxy configuration is set once at session creation. Configuration changes at runtime are not supported. Create a new session to use different settings.
+  **Session-scoped** – Each browser session has independent proxy configuration.
+  **Timeout** – Standard session timeouts apply. Proxy configuration is discarded when the session ends.

### Connectivity behavior
<a name="browser-proxies-connectivity-behavior"></a>
+  **Fail-open** – Proxy connectivity is not validated at session creation. Sessions configured with unavailable proxies will show errors when loading pages.
+  **Runtime errors** – Connection failures appear as browser error pages, visible in Live View for troubleshooting.
+  **No automatic retry** – Failed requests are not automatically retried.

## Cross-account secret access
<a name="browser-proxies-cross-account"></a>

If the credentials secret is in a different Amazon account, configure the following:

 **Secret resource policy** (in the account owning the secret):

```
{
"Version": "2012-10-17",		 	 	 
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"AWS": "arn:aws:iam::caller-account-id:root"},
        "Action": "secretsmanager:GetSecretValue",
        "Resource": "*"
    }]
}
```

 **KMS key policy** (if using a customer-managed KMS key):

```
{
    "Effect": "Allow",
    "Principal": {"AWS": "arn:aws:iam::caller-account-id:root"},
    "Action": "kms:Decrypt",
    "Resource": "*"
}
```

## Security considerations
<a name="browser-proxies-security"></a>

### Credential protection
<a name="browser-proxies-credential-protection"></a>
+ Credentials are stored in Amazon Secrets Manager and fetched using your IAM credentials.
+ Credentials are never returned in API responses. `GetBrowserSession` returns only `secretArn`.
+ Credentials are not written to logs.

### Access control
<a name="browser-proxies-access-control"></a>
+ IAM permissions control which identities can use which credential secrets.
+ Cross-account access requires explicit resource policies.

## Performance considerations
<a name="browser-proxies-performance"></a>
+  **Capacity** – Ensure your proxy can handle expected request volume.
+  **Bypass** – Add Amazon endpoints to `bypass.domainPatterns` for latency-sensitive calls.
+  **Proximity** – Use proxies geographically close to your Amazon Region.

## Constraints
<a name="browser-proxies-constraints"></a>


| Constraint | Limit | Adjustable | 
| --- | --- | --- | 
| Maximum proxies per session | 5 | Yes | 
| Maximum domain patterns per proxy | 100 | Yes | 
| Maximum bypass domain patterns | 100 | Yes | 
| Server hostname length | 253 characters | No | 
| Domain pattern length | 253 characters | No | 
| Port range | 1–65535 | No | 

To request an increase for adjustable constraints, contact Amazon support.

## Limitations
<a name="browser-proxies-limitations"></a>

Before configuring browser proxies, review these limitations to ensure the feature meets your requirements:


| Limitation | Details | 
| --- | --- | 
| Traffic routing | Proxy configuration is a browser-level setting applied at session startup. It is not a network-level control and does not guarantee that all traffic will transit the proxy. For network-layer enforcement, use [Configure Amazon Bedrock AgentCore Runtime and tools for VPC](agentcore-vpc.md). | 
| Supported protocols | HTTP and HTTPS proxies only. SOCKS4 and SOCKS5 proxies are not supported. | 
| Authentication | HTTP Basic authentication or no authentication (IP allowlisting). NTLM, Kerberos, and certificate-based authentication are not supported. | 
| Proxy changes | Proxy configuration is set once at session creation. Configuration changes at runtime are not supported. Create a new session to change proxy settings. | 
| Proxy rotation | Automatic proxy rotation for IP cycling or load distribution is not supported. Create new sessions to rotate proxies. | 
| Connection validation | Proxy connectivity is not validated at session creation. Connection errors appear at runtime. | 