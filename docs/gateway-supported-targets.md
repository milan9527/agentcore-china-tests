

# Supported targets for Amazon Bedrock AgentCore gateways
<a name="gateway-supported-targets"></a>

Targets define the capabilities that your gateway will host. Amazon Bedrock AgentCore Gateway supports three categories of targets:
+  **MCP targets** – Operate in aggregation mode. The gateway acts as an MCP server whose capabilities combine those of all its MCP targets into a single unified virtual MCP server.
+  **HTTP targets** – The gateway sends traffic directly to HTTP targets without aggregation or protocol translation.
+  **Inference targets** – Route LLM traffic to model providers with model-based routing, providing a unified endpoint across multiple providers.

You can attach different credential providers to different targets, which lets you securely control access to targets. The following topics explain the target types in each category and how they integrate into your gateway. The final topic discusses how target names are constructed for a gateway.

**Topics**
+ [MCP targets](gateway-targets-mcp.md)
+ [HTTP targets](gateway-targets-http.md)
+ [Inference targets](gateway-targets-inference.md)