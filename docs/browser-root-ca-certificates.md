

# Configure Root Certificate Authority for Amazon Bedrock AgentCore Browser
<a name="browser-root-ca-certificates"></a>

By default, Amazon Bedrock AgentCore Browser sessions trust only publicly recognized certificate authorities. If your agents need to access internal services, corporate websites, or resources behind a TLS-intercepting proxy that use certificates signed by a private CA, you must provide your custom root CA certificates when starting a session.

Amazon Bedrock AgentCore retrieves the PEM-encoded certificate content from Amazon Secrets Manager using your caller credentials, validates the X.509 format and expiry, and installs the certificates into the session’s OS trust store. This enables the browser to establish trusted HTTPS connections to your internal resources.

## How it works
<a name="browser-root-ca-how-it-works"></a>

Root Certificate Authority for Amazon Bedrock AgentCore Browser works as follows:

1. You provide a list of certificate locations, each pointing to a secret in Amazon Secrets Manager that contains a PEM-encoded root CA certificate.

1. Amazon Bedrock AgentCore uses your caller credentials to retrieve each certificate from Amazon Secrets Manager.

1. Each certificate is validated for correct X.509 PEM format and checked to ensure it has not expired and is not used before its validity start date.

1. Valid certificates are deployed to the session’s OS trust store, making them available to the browser and any network clients within the sandbox.

Certificates configured at the tool level (through `CreateBrowser` ) are combined with any certificates provided at session start time. This allows you to set organization-wide certificates on the tool and add session-specific certificates as needed.

**Note**  
Certificate configuration is a one-time operation per session. Once certificates are installed, they cannot be modified for the duration of that session.

## Prerequisites
<a name="browser-root-ca-prerequisites"></a>

Before configuring root CA certificates, ensure you have the following:
+ Completed the general [Prerequisites](browser-quickstart.md#browser-prerequisites).
+ Your root CA certificates stored as secrets in Amazon Secrets Manager. Each secret must contain valid PEM-encoded X.509 certificate
+ IAM permissions to read the certificate secrets from Amazon Secrets Manager. Add the following permissions to your IAM policy:

  ```
  {
  "Version": "2012-10-17",		 	 	 
      "Statement": [
          {
              "Sid": "SecretsManagerCertificateAccess",
              "Effect": "Allow",
              "Action": [
                  "secretsmanager:GetSecretValue"
              ],
              "Resource": "arn:aws:secretsmanager:<Region>:<account-id>:secret:<secret-name>"
          }
      ]
  }
  ```

## Store your certificate in Amazon Secrets Manager
<a name="browser-root-ca-store-certificate"></a>

Before you can use a root CA certificate with Amazon Bedrock AgentCore Browser, you must store it as a secret in Amazon Secrets Manager. The secret value must be the PEM-encoded certificate content.

**Example**  

1. 

   ```
   aws secretsmanager create-secret \
     --name "my-corporate-root-ca" \
     --description "Corporate root CA certificate for AgentCore sessions" \
     --secret-string file://my-root-ca.pem \
     --region <region>
   ```

1. 

   ```
   import boto3
   
   client = boto3.client('secretsmanager', region_name='<region>')
   
   # Read the PEM certificate file
   with open('my-root-ca.pem', 'r') as f:
       cert_content = f.read()
   
   response = client.create_secret(
       Name='my-corporate-root-ca',
       Description='Corporate root CA certificate for AgentCore sessions',
       SecretString=cert_content
   )
   
   print(f"Secret ARN: {response['ARN']}")
   ```

Note the secret ARN from the output. You will use this ARN when starting sessions with certificate configuration.

**Important**  
The secret must contain a valid PEM-encoded X.509 certificate. The certificate must not be expired and must be within its validity period. Amazon Bedrock AgentCore validates the certificate format and expiry before installing it.

## Start a browser session with custom certificates
<a name="browser-root-ca-session"></a>

To start a browser session that trusts your custom root CA certificates, include the `certificates` parameter in your `StartBrowserSession` request.

**Example**  

1. 

   ```
   aws bedrock-agentcore start-browser-session \
     --browser-identifier "aws.browser.v1" \
     --name "session-with-custom-ca" \
     --certificates '[
       {
         "location": {
           "secretsManager": {
             "secretArn": "arn:aws:secretsmanager:<region>:<account-id>:secret:<secret-name>"
           }
         }
       }
     ]'
   ```

1. 

   ```
   import boto3
   
   client = boto3.client('bedrock-agentcore', region_name='<region>')
   
   response = client.start_browser_session(
       browserIdentifier="aws.browser.v1",
       name="session-with-custom-ca",
       certificates=[
           {
               "location": {
                   "secretsManager": {
                       "secretArn": "arn:aws:secretsmanager:<region>:<account-id>:secret:<secret-name>"
                   }
               }
           }
       ]
   )
   
   print(f"Session ID: {response['sessionId']}")
   print(f"Status: {response['status']}")
   ```

1. 

   ```
   {
     "name": "session-with-custom-ca",
     "certificates": [
       {
         "location": {
           "secretsManager": {
             "secretArn": "arn:aws:secretsmanager:<region>:<account-id>:secret:<secret-name>"
           }
         }
       }
     ]
   }
   ```

## Using multiple certificates
<a name="browser-root-ca-multiple-certificates"></a>

You can provide multiple root CA certificates in a single browser session. This is useful when your environment requires trust for multiple internal certificate authorities, such as separate CAs for different internal services or environments.

**Example**  

1. 

   ```
   aws bedrock-agentcore start-browser-session \
     --browser-identifier "aws.browser.v1" \
     --name "session-with-multiple-cas" \
     --certificates '[
       {
         "location": {
           "secretsManager": {
             "secretArn": "arn:aws:secretsmanager:<region>:<account-id>:secret:corporate-root-ca"
           }
         }
       },
       {
         "location": {
           "secretsManager": {
             "secretArn": "arn:aws:secretsmanager:<region>:<account-id>:secret:proxy-ca"
           }
         }
       }
     ]'
   ```

1. 

   ```
   response = client.start_browser_session(
       browserIdentifier="aws.browser.v1",
       name="session-with-multiple-cas",
       certificates=[
           {
               "location": {
                   "secretsManager": {
                       "secretArn": "arn:aws:secretsmanager:<region>:<account-id>:secret:corporate-root-ca"
                   }
               }
           },
           {
               "location": {
                   "secretsManager": {
                       "secretArn": "arn:aws:secretsmanager:<region>:<account-id>:secret:proxy-ca"
                   }
               }
           }
       ]
   )
   ```

## Configure certificates at the tool level
<a name="browser-root-ca-tool-level"></a>

You can configure certificates at the tool level when creating a custom browser. Certificates configured at the tool level are automatically applied to every session started with that tool, in addition to any certificates provided at session start time.

This is useful for organization-wide certificates that should be trusted by all browser sessions.

**Example**  

1. 

   ```
   response = client.create_browser(
       name="corporate-browser",
       description="Browser with corporate CA trust",
       certificates=[
           {
               "location": {
                   "secretsManager": {
                       "secretArn": "arn:aws:secretsmanager:<region>:<account-id>:secret:corporate-root-ca"
                   }
               }
           }
       ]
   )
   
   browser_id = response['browserIdentifier']
   print(f"Browser ID: {browser_id}")
   ```

When you start a session with a browser that has certificates configured, the tool-level certificates are combined with any session-level certificates. Tool-level certificates are applied first, followed by session-level certificates.

## Certificate requirements and limits
<a name="browser-root-ca-certificate-requirements"></a>

Certificates must meet the following requirements:


| Requirement | Details | 
| --- | --- | 
| Format | PEM-encoded X.509 certificate | 
| Storage |  Amazon Secrets Manager secret (as a string value, not binary) | 
| Validity | Certificate must not be expired and must be within its validity period (between `notBefore` and `notAfter` dates) | 
| Maximum certificates per session | 10 per session and 10 per tool. A session can have up to 20 certificates in total. | 
| Secret ARN format |  `arn:aws:secretsmanager:region:account-id:secret:secret-name`  | 
| Location type | Only Amazon Secrets Manager is supported as a certificate location | 