

# Amazon Bedrock AgentCore Gateway features
<a name="gateway-features"></a>

Amazon Bedrock AgentCore Gateway provides features that you can optionally enable for your gateway. The following table provides a brief description of these features and links to documentation to learn more about the feature:


| Feature | Description | How to use | Learn more | 
| --- | --- | --- | --- | 
| Debugging messages | Allow the return of detailed debugging messages when invoking a gateway. | Enable when creating or updating a gateway. You can disable this setting before deploying a gateway to production. |  [Turn on debugging messages](gateway-debug-messages.md)  | 
| Custom encryption | Instead of using an Amazon-managed key, encrypt your gateway with a custom Amazon KMS key that you control and manage. | Specify the key when creating or updating a gateway. |  [Encrypt your AgentCore gateway with a customer-managed KMS key](gateway-encryption.md)  | 
| Semantic search of tools | Search for tools in your gateway with a natural language query to find ones applicable to a use case. | Enable when creating a gateway and then call the `x_amz_bedrock_agentcore_search` tool when you invoke the gateway. |  [Search for tools in your AgentCore gateway with a natural language query](gateway-using-mcp-semantic-search.md)  | 
| Tagging | Add tags to a gateway to categorize resources for tracking and organizational purposes. | Add tags when creating or updating a gateway. |  [Tagging AgentCore resources](tagging.md)  | 
| MCP sessions | Enable stateful interactions between clients and your gateway. Sessions store MCP server target session IDs for faster responses and enable advanced features like elicitation and sampling. | Specify `sessionConfiguration` in `protocolConfiguration.mcp` when creating or updating a gateway. |  [Use MCP sessions with your gateway](gateway-sessions.md)  | 
| Response streaming | Receive real-time Server-Sent Events (SSE) from your gateway during tool execution, including progress notifications, log messages, elicitation requests, and sampling requests. | Set `streamingConfiguration.enableResponseStreaming` to `true` in `protocolConfiguration.mcp` when creating or updating a gateway. |  [Receive progress notifications](gateway-mcp-progress.md)  | 
| Elicitation | Allow MCP server targets to request additional information from clients during tool calls, such as user confirmations or authentication. | Enable sessions and response streaming, then use MCP server targets that send elicitations. |  [Use elicitation with your gateway](gateway-mcp-elicitation.md)  | 
| Sampling | Allow MCP server targets to request LLM completions from clients during tool calls. | Enable sessions and response streaming. Client must declare sampling capability during initialization. |  [Use sampling with your gateway](gateway-mcp-sampling.md)  | 