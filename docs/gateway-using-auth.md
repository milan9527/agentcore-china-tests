

# Authorize and authenticate to an AgentCore gateway and gateway target
<a name="gateway-using-auth"></a>

To invoke your gateway and gateway target, you’ll need to make sure that the following credentials that you set up while fulfilling the [prerequisites](gateway-prerequisites.md) are recognized during gateway invocation:
+  [Inbound authorization](gateway-inbound-auth.md) – Authorization and authentication to the gateway.
+  [Outbound authorization](gateway-outbound-auth.md) – Authorization and authentication to the gateway target.

To learn how to obtain and configure credentials, review the provider documentation for the methods that you choose.

The following sections provide examples of obtaining and configuring credentials for different use cases.

**Topics**
+ [Example: Authorization for the default gateway and target created by the AgentCore CLI](gateway-using-auth-ex-starter.md)
+ [Example: Authentication with an authorization code grant when invoking a gateway](gateway-using-auth-ex-3lo.md)