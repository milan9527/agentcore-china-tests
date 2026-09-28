

# Add rate limits to a gateway
<a name="gateway-rate-limits"></a>

With rate limits, you control how much traffic individual callers, targets, or tools can consume on your gateway. You define dimension keys that determine how traffic is grouped, then set rate entries that specify the allowed throughput for each group.

Use rate limits to accomplish the following goals:
+ Protect backend models and tools from traffic spikes
+ Enforce per-caller quotas based on JWT claims or IAM identity
+ Block specific callers by setting a rate of zero
+ Control tokens per minute (TPM) for inference targets
+ Limit concurrent connections to endpoints

**Topics**
+ [How rate limits work](#gateway-rate-limits-how-they-work)
+ [Relationship with service-managed limits](#gateway-rate-limits-service-managed)
+ [Rate limit components](#gateway-rate-limits-components)
+ [Status lifecycle](#gateway-rate-limits-status)
+ [Limits](#gateway-rate-limits-quotas)
+ [Common API errors](#gateway-rate-limits-api-errors)
+ [Rate limit dimensions](gateway-rate-limits-dimensions.md)
+ [Rate limit metrics](gateway-rate-limits-metrics.md)
+ [Rate limit enforcement](gateway-rate-limits-enforcement.md)
+ [Rate limit API examples](gateway-rate-limits-examples.md)
+ [Rate limit best practices](gateway-rate-limits-best-practices.md)

## How rate limits work
<a name="gateway-rate-limits-how-they-work"></a>

Each rate limit defines one or more *dimension keys* that determine how the gateway groups traffic into buckets. Within a rate limit, you create *entries* that match specific dimension values and specify the allowed rate for that bucket.

When the gateway receives a request, it evaluates all active rate limits. For each rate limit, the gateway resolves the dimension keys from the request context. It finds the matching entry and checks whether the request exceeds the allowed rate. All rate limits must pass for the request to proceed (AND logic).

Rate limit changes propagate to the data plane within 30 seconds.

## Relationship with service-managed limits
<a name="gateway-rate-limits-service-managed"></a>

The gateway enforces both customer-defined rate limits and service-managed limits. Customer-defined rate limits cannot exceed the service ceiling. The effective rate for any request is the minimum of the customer-defined limit and the service-managed limit. For current service-managed limits, see [Gateway service quotas](https://docs.amazonaws.cn/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html#gateway-endpoints-quotas).

## Rate limit components
<a name="gateway-rate-limits-components"></a>


| Component | Description | 
| --- | --- | 
|  `rateLimitId`  | A unique identifier for the rate limit (2–64 characters, alphanumeric with `-`, `_`, `.`). You can specify your own ID on creation, or omit it and the service generates one automatically. Appears in throttled responses and metrics. | 
|  `dimensionKeys`  | An ordered list of 1 to 10 keys that determine how traffic is grouped into buckets. Dimension keys are immutable after creation. | 
|  `entries`  | A list of 1 to 1,000 rate entries. Each entry specifies dimension values and the allowed rate for that bucket. | 
|  `description`  | An optional text description of the rate limit’s purpose. | 

## Status lifecycle
<a name="gateway-rate-limits-status"></a>


| Status | Description | 
| --- | --- | 
|  `CREATING`  | The rate limit is being provisioned. It is not yet enforced. | 
|  `ACTIVE`  | The rate limit is active and enforced on the data plane. | 
|  `UPDATING`  | The rate limit is being updated. The previous configuration remains enforced until the update completes. | 
|  `DELETING`  | The rate limit is being removed. Enforcement stops when deletion completes. | 

## Limits
<a name="gateway-rate-limits-quotas"></a>


| Resource | Limit | 
| --- | --- | 
| Rate limits per gateway | 50 | 
| Entries per rate limit | 1,000 | 
| Dimension keys per rate limit | 10 | 
| Description maximum length | 512 characters | 
| Entry dimension values | Must match the number of dimension keys | 
| Rate value range | 0 to 10,000,000 (0 blocks all matching traffic) | 
| Propagation time | ≤ 30 seconds | 

**Important**  
Rate limits use fail-open behavior by default. If the rate limit service is unavailable or a dimension cannot be resolved, the gateway allows the request to proceed. Design your security posture accordingly and do not rely solely on rate limits as a security boundary.

## Common API errors
<a name="gateway-rate-limits-api-errors"></a>

The following errors might be returned when managing rate limits through the control plane API:


| HTTP status | Error | Description | 
| --- | --- | --- | 
| 400 |  `ValidationException`  | Invalid request parameters (for example, unsupported metric/period combination, invalid dimension values). | 
| 404 |  `ResourceNotFoundException`  | The specified gateway or rate limit does not exist. | 
| 409 |  `ConflictException`  | A rate limit with the same dimension keys already exists, or the gateway is in a state that does not allow modification. | 