import boto3
import os
import json
import requests
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource("dynamodb")
table_name = os.environ.get("DYNAMODB_TABLE", "strava_activities")
table = dynamodb.Table(table_name)

def save_activity_to_dynamodb(activity_data):
    """Salveaza activitatea într-un item DynamoDB"""
    from decimal import Decimal

    def convert_to_dynamodb_compatible(value):
        if isinstance(value, float):
            return Decimal(str(value))
        elif isinstance(value, dict):
            return {k: convert_to_dynamodb_compatible(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [convert_to_dynamodb_compatible(v) for v in value]
        else:
            return value

    item = {
        "strava_id": str(activity_data.get("id")),  # partition key
        "athlete_id": str(activity_data.get("athlete", {}).get("id")),
        "name": activity_data.get("name"),
        "type": activity_data.get("type"),
        "start_date": activity_data.get("start_date"),
        "distance": activity_data.get("distance"),
        "moving_time": activity_data.get("moving_time"),
        "elapsed_time": activity_data.get("elapsed_time"),
        "total_elevation_gain": activity_data.get("total_elevation_gain"),
        "average_speed": activity_data.get("average_speed"),
        "max_speed": activity_data.get("max_speed"),
        "average_heartrate": activity_data.get("average_heartrate"),
        "max_heartrate": activity_data.get("max_heartrate"),
        "calories": activity_data.get("calories"),
        "created_at": datetime.utcnow().isoformat(),
        "raw_payload": activity_data
    }

    # Elimina None și convertește float -> Decimal
    item = {k: convert_to_dynamodb_compatible(v) for k, v in item.items() if v is not None}

    table.put_item(Item=item)
    print("Activitate salvata în DynamoDB.")

def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    if not method:
        method = event.get("httpMethod", "")

    if method == "GET":
        query = event.get("queryStringParameters", {})
        if query and query.get("hub.mode") == "subscribe":
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"hub.challenge": query.get("hub.challenge")})
            }
        return {"statusCode": 400, "body": "Invalid verification"}

    elif method == "POST":
        body = json.loads(event["body"])
        activity_id = body.get("object_id")
        print(f"Primit de la Strava, activitate noua: {activity_id}")

        # Obtine tokenul de acces
        res = requests.post("https://www.strava.com/oauth/token", data={
            'client_id': os.getenv('CLIENT_ID'),
            'client_secret': os.getenv('CLIENT_SECRET'),
            'refresh_token': os.getenv('REFRESH_TOKEN'),
            'grant_type': 'refresh_token'
        })

        if res.status_code != 200:
            return {"statusCode": 500, "body": f"Auth error: {res.text}"}

        access_token = res.json().get('access_token')
        headers = {'Authorization': f'Bearer {access_token}'}
        
        # Detalii activitate
        activity_url = f"https://www.strava.com/api/v3/activities/{activity_id}"
        activity_res = requests.get(activity_url, headers=headers)

        if activity_res.status_code != 200:
            return {"statusCode": 500, "body": f"Activity error: {activity_res.text}"}

        activity_data = activity_res.json()
        print("Detalii activitate:", json.dumps(activity_data))

        # Verificare: ignoram activitatile de tip Ride cu distanta 0
        activity_type = activity_data.get("type", "").lower()
        distance = float(activity_data.get("distance", 0))

        if activity_type == "ride" and distance == 0.0:
            print("Activitate ignorata: tip 'Ride' cu distanta 0 — probabil duplicat de la ceas.")
            return {"statusCode": 200, "body": "Activitate duplicat ignorata"}

        try:
            save_activity_to_dynamodb(activity_data)
        except Exception as e:
            print("Eroare la salvare:", e)
            return {"statusCode": 500, "body": f"Eroare DB: {str(e)}"}

        return {"statusCode": 200, "body": "OK"}

    return {"statusCode": 405, "body": "Method Not Allowed"}
