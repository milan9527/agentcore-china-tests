

# Rate limit API examples
<a name="gateway-rate-limits-examples"></a>

The following examples show how to manage rate limits using the Amazon CLI and Amazon Python SDK (Boto3).

## Create a per-target requests-per-second limit
<a name="gateway-rate-limits-examples-per-target-rps"></a>

The following example creates a rate limit that controls requests per second on a per-target basis. A specific target gets 100 RPS, and all other targets each get their own 10 RPS bucket.

**Example**  

1. Run the following command:

   ```
   aws bedrock-agentcore-control create-gateway-rate-limit \
       --gateway-identifier my-gateway-abc1234567 \
       --dimension-keys '["targetName"]' \
       --description "Per-target RPS limit" \
       --entries '[
           {
               "dimensions": {"targetName": "my-high-traffic-target"},
               "requests": [
                   {
                       "rate": 100,
                       "period": "second"
                   }
               ]
           },
           {
               "dimensions": {"targetName": "*"},
               "requests": [
                   {
                       "rate": 10,
                       "period": "second"
                   }
               ]
           }
       ]'
   ```

1. 

   ```
   import boto3
   
   client = boto3.client("bedrock-agentcore-control", region_name="us-west-2")
   
   response = client.create_gateway_rate_limit(
       gatewayIdentifier="my-gateway-abc1234567",
       dimensionKeys=["targetName"],
       description="Per-target RPS limit",
       entries=[
           {
               "dimensions": {"targetName": "my-high-traffic-target"},
               "requests": [
                   {
                       "rate": 100,
                       "period": "second",
                   }
               ],
           },
           {
               "dimensions": {"targetName": "*"},
               "requests": [
                   {
                       "rate": 10,
                       "period": "second",
                   }
               ],
           },
       ],
   )
   
   print(f"Rate Limit ID: {response['rateLimitId']}")
   ```

## Create a per-caller requests-per-minute limit
<a name="gateway-rate-limits-examples-per-caller-rpm"></a>

The following example creates a rate limit based on the caller’s JWT `sub` claim. Premium users get 300 RPM, and all other users get 60 RPM.

**Example**  

1. Run the following command:

   ```
   aws bedrock-agentcore-control create-gateway-rate-limit \
       --gateway-identifier my-gateway-abc1234567 \
       --dimension-keys '["$.context.jwt.sub"]' \
       --description "Per-caller RPM by subscription tier" \
       --entries '[
           {
               "dimensions": {"$.context.jwt.sub": "premium-user-001"},
               "requests": [
                   {
                       "rate": 300,
                       "period": "minute"
                   }
               ]
           },
           {
               "dimensions": {"$.context.jwt.sub": "premium-user-002"},
               "requests": [
                   {
                       "rate": 300,
                       "period": "minute"
                   }
               ]
           },
           {
               "dimensions": {"$.context.jwt.sub": "*"},
               "requests": [
                   {
                       "rate": 60,
                       "period": "minute"
                   }
               ]
           }
       ]'
   ```

1. 

   ```
   import boto3
   
   client = boto3.client("bedrock-agentcore-control", region_name="us-west-2")
   
   response = client.create_gateway_rate_limit(
       gatewayIdentifier="my-gateway-abc1234567",
       dimensionKeys=["$.context.jwt.sub"],
       description="Per-caller RPM by subscription tier",
       entries=[
           {
               "dimensions": {"$.context.jwt.sub": "premium-user-001"},
               "requests": [
                   {
                       "rate": 300,
                       "period": "minute",
                   }
               ],
           },
           {
               "dimensions": {"$.context.jwt.sub": "premium-user-002"},
               "requests": [
                   {
                       "rate": 300,
                       "period": "minute",
                   }
               ],
           },
           {
               "dimensions": {"$.context.jwt.sub": "*"},
               "requests": [
                   {
                       "rate": 60,
                       "period": "minute",
                   }
               ],
           },
       ],
   )
   
   print(f"Rate Limit ID: {response['rateLimitId']}")
   ```

## Create a multi-dimension limit with tokens
<a name="gateway-rate-limits-examples-multi-dim-tokens"></a>

The following example creates a rate limit with three dimension keys that limits both requests and tokens per minute. Each caller gets their own budget scoped to a specific target and model.

**Example**  

1. Run the following command:

   ```
   aws bedrock-agentcore-control create-gateway-rate-limit \
       --gateway-identifier my-gateway-abc1234567 \
       --dimension-keys '["targetName", "qualifiedModelId", "$.context.jwt.sub"]' \
       --description "Per-caller token and request budget per target and model" \
       --entries '[
           {
               "dimensions": {"targetName": "my-inference-target", "qualifiedModelId": "anthropic.claude-3-sonnet-20240229-v1:0", "$.context.jwt.sub": "*"},
               "requests": [
                   {
                       "rate": 100,
                       "period": "minute"
                   }
               ],
               "tokens": [
                   {
                       "rate": 50000,
                       "period": "minute"
                   }
               ]
           },
           {
               "dimensions": {"targetName": "*", "qualifiedModelId": "*", "$.context.jwt.sub": "*"},
               "requests": [
                   {
                       "rate": 30,
                       "period": "minute"
                   }
               ],
               "tokens": [
                   {
                       "rate": 10000,
                       "period": "minute"
                   }
               ]
           }
       ]'
   ```

1. 

   ```
   import boto3
   
   client = boto3.client("bedrock-agentcore-control", region_name="us-west-2")
   
   response = client.create_gateway_rate_limit(
       gatewayIdentifier="my-gateway-abc1234567",
       dimensionKeys=["targetName", "qualifiedModelId", "$.context.jwt.sub"],
       description="Per-caller token and request budget per target and model",
       entries=[
           {
               "dimensions": {"targetName": "my-inference-target", "qualifiedModelId": "anthropic.claude-3-sonnet-20240229-v1:0", "$.context.jwt.sub": "*"},
               "requests": [
                   {
                       "rate": 100,
                       "period": "minute",
                   }
               ],
               "tokens": [
                   {
                       "rate": 50000,
                       "period": "minute",
                   }
               ],
           },
           {
               "dimensions": {"targetName": "*", "qualifiedModelId": "*", "$.context.jwt.sub": "*"},
               "requests": [
                   {
                       "rate": 30,
                       "period": "minute",
                   }
               ],
               "tokens": [
                   {
                       "rate": 10000,
                       "period": "minute",
                   }
               ],
           },
       ],
   )
   
   print(f"Rate Limit ID: {response['rateLimitId']}")
   ```

## Create a connection rate limit
<a name="gateway-rate-limits-examples-connection"></a>

The following example creates a connection rate limit per model. This limits the number of concurrent in-flight requests to each model, which is useful for protecting targets that have limited concurrency capacity.

**Example**  

1. Run the following command:

   ```
   aws bedrock-agentcore-control create-gateway-rate-limit \
       --gateway-identifier my-gateway-abc1234567 \
       --dimension-keys '["qualifiedModelId"]' \
       --description "Connection rate limit per model" \
       --entries '[
           {
               "dimensions": {"qualifiedModelId": "anthropic.claude-3-sonnet-20240229-v1:0"},
               "connections": [
                   {
                       "rate": 50,
                       "period": "second"
                   }
               ]
           },
           {
               "dimensions": {"qualifiedModelId": "*"},
               "connections": [
                   {
                       "rate": 20,
                       "period": "second"
                   }
               ]
           }
       ]'
   ```

1. 

   ```
   import boto3
   
   client = boto3.client("bedrock-agentcore-control", region_name="us-west-2")
   
   response = client.create_gateway_rate_limit(
       gatewayIdentifier="my-gateway-abc1234567",
       dimensionKeys=["qualifiedModelId"],
       description="Connection rate limit per model",
       entries=[
           {
               "dimensions": {"qualifiedModelId": "anthropic.claude-3-sonnet-20240229-v1:0"},
               "connections": [
                   {
                       "rate": 50,
                       "period": "second",
                   }
               ],
           },
           {
               "dimensions": {"qualifiedModelId": "*"},
               "connections": [
                   {
                       "rate": 20,
                       "period": "second",
                   }
               ],
           },
       ],
   )
   
   print(f"Rate Limit ID: {response['rateLimitId']}")
   ```

## Block a caller with rate zero
<a name="gateway-rate-limits-examples-block-caller"></a>

The following example blocks a specific caller by setting their rate to 0. This denies all requests from the blocked caller once the change propagates (up to 30 seconds).

**Example**  

1. Run the following command:

   ```
   aws bedrock-agentcore-control create-gateway-rate-limit \
       --gateway-identifier my-gateway-abc1234567 \
       --dimension-keys '["$.context.jwt.sub"]' \
       --description "Block abusive caller" \
       --entries '[
           {
               "dimensions": {"$.context.jwt.sub": "blocked-user-789"},
               "requests": [
                   {
                       "rate": 0,
                       "period": "second"
                   }
               ]
           },
           {
               "dimensions": {"$.context.jwt.sub": "*"},
               "requests": [
                   {
                       "rate": 100,
                       "period": "second"
                   }
               ]
           }
       ]'
   ```

1. 

   ```
   import boto3
   
   client = boto3.client("bedrock-agentcore-control", region_name="us-west-2")
   
   response = client.create_gateway_rate_limit(
       gatewayIdentifier="my-gateway-abc1234567",
       dimensionKeys=["$.context.jwt.sub"],
       description="Block abusive caller",
       entries=[
           {
               "dimensions": {"$.context.jwt.sub": "blocked-user-789"},
               "requests": [
                   {
                       "rate": 0,
                       "period": "second",
                   }
               ],
           },
           {
               "dimensions": {"$.context.jwt.sub": "*"},
               "requests": [
                   {
                       "rate": 100,
                       "period": "second",
                   }
               ],
           },
       ],
   )
   
   print(f"Rate Limit ID: {response['rateLimitId']}")
   ```

## Get a rate limit
<a name="gateway-rate-limits-examples-get"></a>

The following example retrieves the details of a specific rate limit.

**Example**  

1. Run the following command:

   ```
   aws bedrock-agentcore-control get-gateway-rate-limit \
       --gateway-identifier my-gateway-abc1234567 \
       --rate-limit-id rl-abc123def456
   ```

1. 

   ```
   import boto3
   
   client = boto3.client("bedrock-agentcore-control", region_name="us-west-2")
   
   response = client.get_gateway_rate_limit(
       gatewayIdentifier="my-gateway-abc1234567",
       rateLimitId="rl-abc123def456",
   )
   
   print(f"Status: {response['status']}")
   print(f"Dimension Keys: {response['dimensionKeys']}")
   print(f"Entries: {len(response['entries'])}")
   ```

## Update a rate limit
<a name="gateway-rate-limits-examples-update"></a>

The following example updates the entries of an existing rate limit to increase the rate for a specific target.

**Note**  
The `dimensionKeys` field is immutable after creation. To change dimension keys, delete the rate limit and create a new one.

**Example**  

1. Run the following command:

   ```
   aws bedrock-agentcore-control update-gateway-rate-limit \
       --gateway-identifier my-gateway-abc1234567 \
       --rate-limit-id rl-abc123def456 \
       --description "Updated per-target RPS limit" \
       --entries '[
           {
               "dimensions": {"targetName": "my-high-traffic-target"},
               "requests": [
                   {
                       "rate": 200,
                       "period": "second"
                   }
               ]
           },
           {
               "dimensions": {"targetName": "*"},
               "requests": [
                   {
                       "rate": 20,
                       "period": "second"
                   }
               ]
           }
       ]'
   ```

1. 

   ```
   import boto3
   
   client = boto3.client("bedrock-agentcore-control", region_name="us-west-2")
   
   response = client.update_gateway_rate_limit(
       gatewayIdentifier="my-gateway-abc1234567",
       rateLimitId="rl-abc123def456",
       description="Updated per-target RPS limit",
       entries=[
           {
               "dimensions": {"targetName": "my-high-traffic-target"},
               "requests": [
                   {
                       "rate": 200,
                       "period": "second",
                   }
               ],
           },
           {
               "dimensions": {"targetName": "*"},
               "requests": [
                   {
                       "rate": 20,
                       "period": "second",
                   }
               ],
           },
       ],
   )
   
   print(f"Status: {response['status']}")
   ```

## List rate limits
<a name="gateway-rate-limits-examples-list"></a>

The following example lists all rate limits for a gateway.

**Example**  

1. Run the following command:

   ```
   aws bedrock-agentcore-control list-gateway-rate-limits \
       --gateway-identifier my-gateway-abc1234567
   ```

1. 

   ```
   import boto3
   
   client = boto3.client("bedrock-agentcore-control", region_name="us-west-2")
   
   paginator = client.get_paginator("list_gateway_rate_limits")
   
   for page in paginator.paginate(gatewayIdentifier="my-gateway-abc1234567"):
       for rate_limit in page["rateLimits"]:
           print(
               f"ID: {rate_limit['rateLimitId']}, "
               f"Status: {rate_limit['status']}, "
               f"Dimensions: {rate_limit['dimensionKeys']}"
           )
   ```

**Note**  
Results might be paginated. Use the `nextToken` value from the response to retrieve additional pages, or use the Boto3 paginator as shown above.

## Delete a rate limit
<a name="gateway-rate-limits-examples-delete"></a>

The following example deletes a rate limit from a gateway.

**Example**  

1. Run the following command:

   ```
   aws bedrock-agentcore-control delete-gateway-rate-limit \
       --gateway-identifier my-gateway-abc1234567 \
       --rate-limit-id rl-abc123def456
   ```

1. 

   ```
   import boto3
   
   client = boto3.client("bedrock-agentcore-control", region_name="us-west-2")
   
   response = client.delete_gateway_rate_limit(
       gatewayIdentifier="my-gateway-abc1234567",
       rateLimitId="rl-abc123def456",
   )
   
   print(f"Status: {response['status']}")
   ```

## Batch put rate limits
<a name="gateway-rate-limits-examples-batch-put"></a>

The following example creates or updates multiple rate limits in a single call. Batch put uses upsert semantics — if a rate limit with the same dimension keys exists, it is updated; otherwise, a new rate limit is created.

**Note**  
Batch put is idempotent. You can safely retry failed calls without creating duplicate rate limits.

**Example**  

1. Run the following command:

   ```
   aws bedrock-agentcore-control batch-put-gateway-rate-limits \
       --gateway-identifier my-gateway-abc1234567 \
       --rate-limits '[
           {
               "dimensionKeys": ["targetName"],
               "description": "Per-target RPS",
               "entries": [
                   {
                       "dimensions": {"targetName": "*"},
                       "requests": [{"rate": 50, "period": "second"}]
                   }
               ]
           },
           {
               "dimensionKeys": ["$.context.jwt.sub"],
               "description": "Per-caller RPM",
               "entries": [
                   {
                       "dimensions": {"$.context.jwt.sub": "*"},
                       "requests": [{"rate": 120, "period": "minute"}]
                   }
               ]
           }
       ]'
   ```

1. 

   ```
   import boto3
   
   client = boto3.client("bedrock-agentcore-control", region_name="us-west-2")
   
   response = client.batch_put_gateway_rate_limits(
       gatewayIdentifier="my-gateway-abc1234567",
       rateLimits=[
           {
               "dimensionKeys": ["targetName"],
               "description": "Per-target RPS",
               "entries": [
                   {
                       "dimensions": {"targetName": "*"},
                       "requests": [
                           {"rate": 50, "period": "second"}
                       ],
                   }
               ],
           },
           {
               "dimensionKeys": ["$.context.jwt.sub"],
               "description": "Per-caller RPM",
               "entries": [
                   {
                       "dimensions": {"$.context.jwt.sub": "*"},
                       "requests": [
                           {"rate": 120, "period": "minute"}
                       ],
                   }
               ],
           },
       ],
   )
   
   for result in response["rateLimits"]:
       print(f"ID: {result['rateLimitId']}, Status: {result['status']}")
   ```