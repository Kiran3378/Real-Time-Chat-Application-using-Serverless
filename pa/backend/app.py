import json
import os
import re
import time
import uuid
from datetime import datetime, timezone


ROOM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_USERNAME_LENGTH = 32
MAX_MESSAGE_LENGTH = 2000


def validate_room_id(value):
    if not isinstance(value, str) or not ROOM_ID_PATTERN.fullmatch(value):
        raise ValueError("Room names must be 1-64 letters, numbers, underscores, or hyphens.")
    return value


def validate_username(value):
    if not isinstance(value, str):
        raise ValueError("Enter a display name.")
    username = value.strip()
    if not username or len(username) > MAX_USERNAME_LENGTH:
        raise ValueError(f"Display names must be 1-{MAX_USERNAME_LENGTH} characters.")
    return username


def validate_message_text(value):
    if not isinstance(value, str):
        raise ValueError("Enter a message.")
    text = value.strip()
    if not text or len(text) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Messages must be 1-{MAX_MESSAGE_LENGTH} characters.")
    return text


def _tables():
    import boto3

    dynamodb = boto3.resource("dynamodb")
    return (
        dynamodb.Table(os.environ["MESSAGES_TABLE"]),
        dynamodb.Table(os.environ["CONNECTIONS_TABLE"]),
    )


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def messages_handler(event, context):
    from boto3.dynamodb.conditions import Key

    room_id = (event.get("pathParameters") or {}).get("roomId")
    try:
        validate_room_id(room_id)
    except ValueError as error:
        return _response(400, {"error": str(error)})

    messages_table, _ = _tables()
    result = messages_table.query(
        KeyConditionExpression=Key("RoomId").eq(room_id),
        ScanIndexForward=False,
        Limit=50,
    )
    messages = [
        {
            "id": item["id"],
            "username": item["username"],
            "text": item["text"],
            "sentAt": item["sentAt"],
        }
        for item in reversed(result.get("Items", []))
    ]
    return _response(200, {"roomId": room_id, "messages": messages})


def _management_client(event):
    import boto3

    request_context = event["requestContext"]
    endpoint_url = (
        f"https://{request_context['domainName']}/{request_context['stage']}"
    )
    return boto3.client("apigatewaymanagementapi", endpoint_url=endpoint_url)


def _post_to_connection(client, connection_id, data):
    from botocore.exceptions import ClientError

    try:
        client.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(data).encode("utf-8"),
        )
    except ClientError as error:
        if error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 410:
            raise
        _, connections_table = _tables()
        connections_table.delete_item(Key={"ConnectionId": connection_id})
        return False
    return True


def _send_error(client, connection_id, message):
    _post_to_connection(client, connection_id, {"type": "error", "message": message})


def websocket_handler(event, context):
    _, connections_table = _tables()
    request_context = event["requestContext"]
    connection_id = request_context["connectionId"]
    route_key = request_context["routeKey"]

    if route_key == "$connect":
        connections_table.put_item(
            Item={
                "ConnectionId": connection_id,
                "ExpiresAt": int(time.time()) + 86400,
            }
        )
        return {"statusCode": 200}

    if route_key == "$disconnect":
        connections_table.delete_item(Key={"ConnectionId": connection_id})
        return {"statusCode": 200}

    client = _management_client(event)
    try:
        payload = json.loads(event.get("body") or "{}")
        if not isinstance(payload, dict):
            raise ValueError("The message must be a JSON object.")

        if route_key == "join":
            room_id = validate_room_id(payload.get("roomId"))
            username = validate_username(payload.get("username"))
            connections_table.update_item(
                Key={"ConnectionId": connection_id},
                UpdateExpression=(
                    "SET RoomId = :room_id, Username = :username, ExpiresAt = :expires_at"
                ),
                ExpressionAttributeValues={
                    ":room_id": room_id,
                    ":username": username,
                    ":expires_at": int(time.time()) + 86400,
                },
            )
            _post_to_connection(
                client,
                connection_id,
                {"type": "joined", "roomId": room_id, "username": username},
            )
            return {"statusCode": 200}

        if route_key == "sendMessage":
            room_id = validate_room_id(payload.get("roomId"))
            text = validate_message_text(payload.get("text"))
            sender = connections_table.get_item(
                Key={"ConnectionId": connection_id},
                ConsistentRead=True,
            ).get("Item")
            if not sender or sender.get("RoomId") != room_id:
                raise ValueError("Join this room before sending a message.")

            sent_at = (
                datetime.now(timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )
            message = {
                "id": str(uuid.uuid4()),
                "username": sender["Username"],
                "text": text,
                "sentAt": sent_at,
            }
            messages_table, _ = _tables()
            messages_table.put_item(
                Item={
                    "RoomId": room_id,
                    "MessageKey": f"{sent_at}#{message['id']}",
                    **message,
                }
            )

            from boto3.dynamodb.conditions import Key

            query = {
                "IndexName": "RoomConnectionsIndex",
                "KeyConditionExpression": Key("RoomId").eq(room_id),
                "ProjectionExpression": "ConnectionId",
            }
            while True:
                recipients = connections_table.query(**query)
                for recipient in recipients.get("Items", []):
                    _post_to_connection(
                        client,
                        recipient["ConnectionId"],
                        {"type": "message", "message": message},
                    )
                last_key = recipients.get("LastEvaluatedKey")
                if not last_key:
                    break
                query["ExclusiveStartKey"] = last_key
            return {"statusCode": 200}

        _send_error(client, connection_id, "Unsupported WebSocket action.")
    except (json.JSONDecodeError, ValueError) as error:
        _send_error(client, connection_id, str(error))

    return {"statusCode": 200}
