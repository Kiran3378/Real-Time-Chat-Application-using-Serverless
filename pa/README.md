# Relay — Serverless real-time chat

Relay is a small browser chat app backed by AWS Lambda, API Gateway REST and WebSocket APIs, and DynamoDB. Messages are saved per room, recent history is available over HTTP, and connected room members receive new messages over WebSockets.

## Architecture

- `web/` — static browser client; no build step or frontend dependencies.
- `backend/app.py` — Python Lambda handlers for message history and WebSocket connect, join, send, and disconnect actions.
- `template.yaml` — AWS SAM/CloudFormation stack for the APIs, Lambdas, and DynamoDB tables.

## Deploy the backend

Requirements: AWS CLI configured with deployment permissions, AWS SAM CLI, and an AWS account.

From the project root:

```sh
sam build
sam deploy --guided
```

The stack creates a public chat API without user authentication. Anyone who knows a room name and the deployed endpoints can join it. Do not use it for confidential conversations.

After deployment, copy the `HttpApiUrl` and `WebSocketUrl` stack outputs. Open `web/index.html` in a browser (or serve the `web/` folder with any static file server), expand **Connection settings**, paste the URLs, and save. Then enter a display name and room name to chat. Endpoint values are stored in that browser's local storage.

Room names are case-sensitive and may contain 1-64 letters, numbers, underscores, or hyphens. Message history returns the latest 50 messages. Connections expire after 24 hours.

## Run tests

The backend validation tests use only the Python standard library:

```sh
python -m unittest discover -s backend/tests
```
