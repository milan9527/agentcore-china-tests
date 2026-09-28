

# Examples
<a name="gateway-interceptors-examples"></a>

The following examples show Python Amazon Lambda functions for common interceptor use cases.

## Pass-through interceptor
<a name="gateway-interceptors-examples-passthrough"></a>

This example demonstrates a simple interceptor that logs the MCP method for REQUEST interceptors and passes all requests and responses through unchanged:

```
import json
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda function that handles both REQUEST and RESPONSE interceptor types.

    For REQUEST interceptors: logs the MCP method and passes request through unchanged
    For RESPONSE interceptors: passes response through unchanged
    """
    # Extract the MCP data from the event
    mcp_data = event.get('mcp', {})

    # Check if this is a REQUEST or RESPONSE interceptor based on presence of gatewayResponse
    if 'gatewayResponse' in mcp_data and mcp_data['gatewayResponse'] != None:
        # This is a RESPONSE interceptor
        logger.info("Processing RESPONSE interceptor - passing through unchanged")

        # Pass through the original request and response unchanged
        response = {
          "interceptorOutputVersion": "1.0",
          "mcp": {
              "transformedGatewayResponse": {
                  "body": mcp_data.get('gatewayResponse', {}).get('body', {}),
                  "statusCode": mcp_data.get('gatewayResponse', {}).get('statusCode', 200)
              }
          }
        }
    else:
        # This is a REQUEST interceptor
        gateway_request = mcp_data.get('gatewayRequest', {})
        request_body = gateway_request.get('body', {})
        mcp_method = request_body.get('method', 'unknown')

        # Log the MCP method
        logger.info(f"Processing REQUEST interceptor - MCP method: {mcp_method}")

        # Pass through the original request unchanged
        response = {
          "interceptorOutputVersion": "1.0",
          "mcp": {
              "transformedGatewayRequest": {
                  "body": request_body,
              }
          }
        }

    return response
```

This Lambda function can be configured as both a REQUEST and RESPONSE interceptor. When configured as a REQUEST interceptor, it will log the MCP method from the incoming request. When configured as a RESPONSE interceptor, it will simply pass the response through unchanged. Both interceptor types return the original data without modification, making this a "pass-through" interceptor.

## Customize model routing with a request interceptor
<a name="gateway-interceptors-examples-model-routing"></a>

For inference targets, the gateway selects a target from the `model` field using [model-based routing](gateway-target-inference-connector.html#gateway-target-inference-connector-routing). A REQUEST interceptor can rewrite `model` before the gateway evaluates routing, which lets you support a *virtual model ID*: a stable alias that does not map to any single configured model. The interceptor resolves the alias to a concrete target-qualified ID in the form `{targetName}/{modelId}`, so callers use one name while you control model selection centrally.

**HTTP interceptor payload**  
Inference targets use the `http` interceptor payload, in which the request body is a base64-encoded string. For more information, see [Interceptors for HTTP targets](gateway-interceptors-types.html#gateway-interceptors-types-http).

The following REQUEST interceptor resolves the virtual model ID `auto-claude` to a specific Anthropic model based on the size of the request input: `anthropic/claude-haiku-4-5` for small requests, `anthropic/claude-sonnet-4-6` for medium requests, and `anthropic/claude-opus-4-7` for large requests. Callers send `auto-claude`, and the gateway routes each request to the resolved model on the `anthropic` target. Requests that use any other model ID pass through unchanged and follow normal model-based routing.

```
import base64
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# The virtual model ID that this interceptor resolves to a concrete
# target-qualified ID in the form "{targetName}/{modelId}".
VIRTUAL_MODEL = "auto-claude"

# Approximate input-size thresholds (in characters) used to choose a model.
SONNET_THRESHOLD = 2000
OPUS_THRESHOLD = 8000


def resolve_auto_claude(payload):
    """Choose an Anthropic model based on the size of the request input."""
    input_size = len(json.dumps(payload.get("input", "")))
    if input_size >= OPUS_THRESHOLD:
        return "anthropic/claude-opus-4-7"
    if input_size >= SONNET_THRESHOLD:
        return "anthropic/claude-sonnet-4-6"
    return "anthropic/claude-haiku-4-5"


def lambda_handler(event, context):
    http = event.get("http", {})
    request = http.get("gatewayRequest", {})
    encoded_body = request.get("body")

    # Nothing to transform (for example, an empty body) - pass through.
    if not encoded_body:
        return {"interceptorOutputVersion": "1.0", "http": {}}

    try:
        payload = json.loads(base64.b64decode(encoded_body))
    except (ValueError, TypeError) as exc:
        logger.warning("Passing request through unchanged; could not parse body: %s", exc)
        return {"interceptorOutputVersion": "1.0", "http": {}}

    # Only resolve the virtual model ID; let everything else route normally.
    if not isinstance(payload, dict) or payload.get("model") != VIRTUAL_MODEL:
        return {"interceptorOutputVersion": "1.0", "http": {}}

    resolved = resolve_auto_claude(payload)
    logger.info("Resolved virtual model %s -> %s", VIRTUAL_MODEL, resolved)
    payload["model"] = resolved

    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    return {
        "interceptorOutputVersion": "1.0",
        "http": {
            "transformedGatewayRequest": {
                "body": encoded
            }
        },
    }
```

Attach the function to your gateway as a REQUEST interceptor. For instructions, see [Configuring interceptors](gateway-interceptors-configuration.html#gateway-interceptors-configuration-creation). The gateway service role must also have permission to invoke the function. For more information, see [Permissions for interceptors](gateway-interceptors-permissions.html).

To see the resolution, send a request that uses the `auto-claude` alias. The interceptor rewrites `model` to a concrete Anthropic model based on the input size, and the gateway routes the request to that model on the `anthropic` target.

```
awscurl --service bedrock-agentcore --region us-west-2 -X POST \
    "https://GATEWAY_ID.gateway.bedrock-agentcore.us-west-2.amazonaws.com/inference/v1/responses" \
    -H "Content-Type: application/json" \
    -d '{"model": "auto-claude", "input": "Hello!", "max_output_tokens": 50}'
```