# Agent-to-Agent Interoperability through MCP: AWS and Databricks

A document-processing solution in which an orchestrator agent on AWS discovers agents through a registry and delegates work to them over the Model Context Protocol (MCP), across two cloud environments.

- **Word documents (.docx)** are processed by an agent on **AWS** (Bedrock AgentCore Runtime).
- **PDF documents (.pdf)** are processed by an agent on **Databricks** (Databricks Apps), with results stored in **Unity Catalog**.

Both synchronous and asynchronous processing are supported.

## Architecture

<img width="2720" height="2480" alt="image" src="https://github.com/user-attachments/assets/a2cac4f6-4536-41db-af93-03f9980e1d83" />



**Flow**

1. The user uploads a document in the React chatbot (hosted on AWS Amplify). The file goes directly to Amazon S3 through a short-lived presigned upload link.
2. An S3 event triggers an AWS Lambda function (asynchronous mode), or the chatbot calls the API and waits (synchronous mode).
3. The **orchestrator agent** (Strands, running on Bedrock AgentCore Runtime, using Claude on Amazon Bedrock) reads the **agent registry** to discover available agents and chooses one based on each agent's card.
4. The orchestrator connects to the chosen agent's **MCP server**, discovers its tools and calls the processing tool:
   - **AWS DOCX agent**: MCP server on AgentCore Runtime, authenticated with AWS IAM (SigV4). Extracts paragraphs and tables, enriches and summarizes with Claude on Bedrock, stores results in S3.
   - **Databricks PDF agent**: MCP server on Databricks Apps, authenticated with OAuth (service principal). Extracts text (with OCR fallback for scanned pages), enriches and summarizes with a Databricks-hosted model, stores results in a Unity Catalog table and the original file in a Unity Catalog volume.
5. Every step is recorded as an event on the job, and the chatbot shows a live two-lane timeline (AWS and Databricks) with the final summary, key points and entities.
6. Results in Unity Catalog can be queried in plain English with Databricks Genie.

## Components

| Component | Technology | Location |
|---|---|---|
| Chatbot | React + Vite, AWS Amplify | `frontend/` |
| API and upload trigger | AWS Lambda (Function URL + S3 event) | `aws/api_lambda/` |
| Orchestrator agent | Strands Agents on Bedrock AgentCore Runtime | `aws/orchestrator/` |
| DOCX agent (MCP server) | FastMCP on Bedrock AgentCore Runtime | `aws/docx_mcp_server/` |
| PDF agent (MCP server) | FastMCP on Databricks Apps | `databricks/mcp-pdf-agent/` |
| PDF agent development notebook | Databricks notebook | `databricks/notebooks/` |
| Agent registry and job store | Amazon DynamoDB | `aws/common/seed_registry.py` |
| Shared helpers and tests | Databricks OAuth, AWS SigV4 signing, MCP test clients | `aws/common/` |
| Sample documents (fictional) | .docx and .pdf | `samples/` |

## Agent registry

Each agent is described by a card: its cloud, the file types it accepts, its MCP endpoint, its authentication method and the tool to call. The orchestrator reads these cards at runtime instead of having destinations in its code, so adding a new agent (including one on another cloud) only requires adding a card.

## Security

- No credentials in code: the Databricks service principal's OAuth credentials are stored in AWS Secrets Manager and read at runtime.
- Cloud-native authentication on each side: AWS IAM (SigV4) for the AgentCore MCP server, OAuth client credentials for the Databricks App.
- Least-privilege IAM roles: each component can access only the specific tables, secret, bucket paths and runtimes it needs.
- Input validation in MCP tools: the Databricks tool only accepts HTTPS Amazon S3 links; the AWS tool only accepts approved buckets. File type, size and page count are checked.
- The Databricks agent receives a presigned download link that expires in minutes and never gets standing access to the S3 bucket.

## Deployment summary

- **AWS**: S3 bucket, two DynamoDB tables (`a2a-jobs`, `a2a-agent-registry`), a Secrets Manager secret, two AgentCore runtimes (deployed with the AgentCore starter toolkit using direct code deploy), a Lambda function with a Function URL and an S3 event trigger, and an Amplify app.
- **Databricks**: a Unity Catalog table and volume, a Databricks App with a SQL warehouse and serving endpoint as resources, a service principal with "Can use" permission on the app, and a Genie space on the results table.

## Known limitations and next steps

- CORS on the S3 bucket and the Lambda Function URL currently allows all origins; in production it would be restricted to the chatbot's domain.
- The Function URL is public for the demo; production would add user authentication (for example, Amazon Cognito).
- The summary is displayed progressively in the chatbot; true token-by-token streaming from the agents is a next step.
- PDFs are limited to 5 pages and files to 10 MB for the demo.
- The AgentCore starter toolkit used for deployment has been superseded by the new AgentCore CLI; new projects should use the new CLI.
