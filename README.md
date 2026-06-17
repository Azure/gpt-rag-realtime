|page_type| languages                               |products|
|---|-----------------------------------------|---|
|sample| <table><tr><td>Python</tr></td></table> |<table><tr><td>azure</td><td>azure-communication-services</td></tr></table>|

# VoiceRAG with Live Agent Escalation using Azure OpenAI Realtime and ACS

This sample shows how to use Azure Communication Services Call Automation to place an outbound phone call, ground the conversation with Azure AI Search, and escalate the caller to a live agent when needed.

## Table of Contents

* [Features](#features)
* [Design](#design)
* [Prerequisites](#prerequisites)
* [Setup the Python environment](#setup-the-python-environment)
* [Configuring application](#configuring-application)
* [Run app locally](#run-app-locally)
  * [Expose local server using ngrok (for callbacks)](#expose-local-server-using-ngrok-for-callbacks)
  * [Optional: Run with Docker locally](#optional-run-with-docker-locally)
* [Deploy to Azure Container Apps](#deploy-to-azure-container-apps)
* [Verification Checklist](#verification-checklist)
* [Key Files](#key-files)
* [Next Steps](#next-steps)

## Features

* **Outbound AI voice call**: Start a phone call from the web UI to a customer phone number using Azure Communication Services.
* **Grounded voice RAG**: The assistant uses the search tool and Azure AI Search to answer only from your indexed knowledge base.
* **Live agent transfer**: If the caller asks for a representative or human, the app plays a transfer message, adds the live agent as a participant, and stops AI media streaming.
* **Managed identity authentication**: Azure OpenAI Realtime is accessed with bearer token auth via DefaultAzureCredential instead of a direct API key in code.
* **Centralized prompts**: Assistant behavior and the greeting are now maintained in prompts.py for easier tuning.

# Design

![Architecture](./Architecture.png)

## Prerequisites

* An Azure account with an active subscription. [Create an account for free](https://azure.microsoft.com/free/?WT.mc_id=A261C142F).
* An Azure Communication Services resource and an outbound-capable ACS phone number.
* An Azure OpenAI resource with a GPT-4o Realtime deployment.
* A signed-in identity that can access Azure OpenAI through Microsoft Entra ID. For local development, running az login is the easiest option.
* Azure AI Search with an index that already contains your knowledge base chunks.
* A public HTTPS callback URL for ACS events during local development, such as ngrok.
* Two reachable phone numbers for testing:
  * the **customer phone number** that receives the outbound call
  * the **live agent phone number** that is added when escalation is requested
* Python 3.12 or later.
* Optional: Docker and Azure CLI for local containers or Azure Container Apps deployment.

> The app uses DefaultAzureCredential for Azure OpenAI. Make sure your local user or managed identity has the appropriate Azure OpenAI RBAC permissions.

### Setup the Python environment

Create and activate a virtual environment, then install the dependencies.

PowerShell on Windows:
```
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS or Linux:
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuring application

Create a local .env file and populate it with your values.

| Variable | Description |
|----------|-------------|
| `ACS_CONNECTION_STRING` | ACS connection string. |
| `ACS_PHONE_NUMBER` | ACS source phone number in E.164 format. |
| `CALLBACK_URI_HOST` | Public base URL for ACS callbacks, without a trailing slash. |
| `COGNITIVE_SERVICES_ENDPOINT` | Azure AI Speech or Cognitive Services endpoint used by ACS media features. |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint. |
| `AZURE_OPENAI_REALTIME_DEPLOYMENT` | GPT-4o Realtime deployment name. |
| `AZURE_OPENAI_API_VERSION` | API version, for example 2024-10-01-preview. |
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search endpoint. |
| `AZURE_SEARCH_API_KEY` | Azure AI Search admin or query key. |
| `AZURE_SEARCH_INDEX` | Search index containing the knowledge base. |
| `AZURE_SEARCH_SEMANTIC_CONFIGURATION` | Optional semantic configuration name. |
| `AZURE_SEARCH_IDENTIFIER_FIELD` | Optional identifier field. Default is chunk_id. |
| `AZURE_SEARCH_CONTENT_FIELD` | Optional content field. Default is chunk. |
| `AZURE_SEARCH_TITLE_FIELD` | Optional title field. Default is title. |
| `AZURE_SEARCH_EMBEDDING_FIELD` | Optional embedding field. Default is text_vector. |
| `AZURE_SEARCH_USE_VECTOR_QUERY` | Set to true or false to enable hybrid/vector retrieval. |
| `ACS_WEBSOCKET_URL` | ACS bidirectional media streaming WebSocket URL. |
| `TARGET_PHONE_NUMBER` | Optional default customer phone number. The UI can override it. |
| `LIVE_AGENT_PHONE_NUMBER` | Optional fallback live agent number if a number is not provided in the UI. |

Important notes:

* You do **not** need to place an Azure OpenAI API key in code.
* Before starting the app locally, sign in so DefaultAzureCredential can get a token:

```
az login
```

* Ensure your Azure AI Search index is already populated. Ingestion scripts are not part of this repo.

## Run app locally

1. Sign in to Azure locally:
```
az login
```

2. Start the application:
```
python app.py
```

3. Open the local UI in your browser:

   http://localhost:8080/

4. Enter both values in the form:
   * the customer phone number to receive the call
   * the live agent phone number for escalation

5. Click **Initiate Call**.

6. During the call, test both scenarios:
   * ask a knowledge-base question to verify RAG grounding
   * ask for a human or representative to verify live agent transfer

### Expose local server using ngrok (for callbacks)

1. Install ngrok from https://ngrok.com/download
2. Authenticate once:
```
ngrok config add-authtoken <your-token>
```
3. Start the tunnel:
```
ngrok http 8080
```
4. Copy the HTTPS forwarding URL and place it in your .env file:
```
CALLBACK_URI_HOST=https://your-ngrok-host
```
5. Restart the app so ACS uses the public callback URL.

### Optional: Run with Docker locally

```
docker build -t voicerag:latest .
docker run --env-file .env -p 8080:8080 voicerag:latest
```

If you run the app in a container, make sure the container also has a valid Azure identity path for DefaultAzureCredential, such as managed identity or service principal environment variables.

## Deploy to Azure Container Apps

Prerequisites:

* Azure CLI installed and signed in
* containerapp extension installed
* an identity for the app with permission to call Azure OpenAI

Example deployment:
```
az containerapp up \
  --resource-group <resource-group-name> \
  --name <container-app-name> \
  --ingress external \
  --target-port 8080 \
  --source .
```

> After deployment, ensure the Container App identity has access to Azure OpenAI and that all ACS callback settings use the deployed public URL.

## Verification Checklist

| Step | Expectation |
|------|-------------|
| App starts | The service starts without Python exceptions. |
| Web UI loads | The browser page is available locally or from the deployed endpoint. |
| Outbound call placed | The customer phone rings after clicking Initiate Call. |
| Audio round-trip | The caller hears the AI response over the phone call. |
| RAG tool usage | Search is invoked before knowledge-based answers. |
| Live agent escalation | Asking for a representative triggers the transfer message and adds the live agent participant. |
| AI handoff behavior | Once the live agent joins, AI media streaming stops. |

## Key Files

* app.py: ACS event handling, WebSocket orchestration, and Azure OpenAI Realtime session logic.
* ragtools.py: search tool integration and live agent transfer helpers.
* prompts.py: assistant system message and greeting configuration.
* index.html: simple web UI for entering the customer and live agent phone numbers.

## Next Steps

* Add ingestion scripts to load documents into Azure AI Search.
* Integrate logging and metrics with Azure Monitor or Application Insights.
* Add authentication, rate limiting, and network restrictions for production use.
* Add CI/CD and IaC for repeatable deployments.
* Expand call analytics and live agent reporting.
