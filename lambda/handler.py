import boto3
import os
import json
import requests
from datetime import datetime
from decimal import Decimal

# DynamoDB setup
dynamodb = boto3.resource("dynamodb")
table_name = os.environ.get("DYNAMODB_TABLE", "strava_activities")
table = dynamodb.Table(table_name)

# S3 setup
s3 = boto3.client("s3")
bucket_name = os.environ.get("STREAMS_BUCKET")

def save_activity_to_dynamodb(activity_data):
    """Salveaza activitatea intr-un item DynamoDB"""
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
        "strava_id": str(activity_data.get("id")),
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

    item = {k: convert_to_dynamodb_compatible(v) for k, v in item.items() if v is not None}
    table.put_item(Item=item)
    print("Activitate salvata in DynamoDB.")

def save_stream_to_s3(activity_id, access_token):
    """Obține streamuri de la Strava si le salveaza in S3"""
    stream_keys = "heartrate,time,watts,cadence"
    stream_url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
    params = {"keys": stream_keys, "key_by_type": "true"}
    headers = {"Authorization": f"Bearer {access_token}"}

    res = requests.get(stream_url, headers=headers, params=params)
    if res.status_code == 200:
        stream_data = res.json()
        s3.put_object(
            Bucket=bucket_name,
            Key=f"streams/{activity_id}.json",
            Body=json.dumps(stream_data),
            ContentType="application/json"
        )
        print(f"Stream salvat in S3: s3://{bucket_name}/streams/{activity_id}.json")
    else:
        print(f"Eroare la fetch streamuri: {res.status_code} {res.text}")

def default_serializer(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

def lambda_handler(event, context):
    print("DEBUG EVENT:", json.dumps(event))  # <- debug
    method = event.get("requestContext", {}).get("http", {}).get("method", "") or event.get("httpMethod", "")

    if method == "GET":
        query = event.get("queryStringParameters", {})
        if query and query.get("hub.mode") == "subscribe":
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"hub.challenge": query.get("hub.challenge")})
            }
        elif event.get("requestContext", {}).get("http", {}).get("path", "").endswith("/activities"):
            query_params = event.get("queryStringParameters", {}) or {}
            print("Query parameters:", query_params)

            athlete_id = "9746797"  # ← momentan hardcodat

            scan_kwargs = {
                "FilterExpression": "athlete_id = :athlete_id",
                "ExpressionAttributeValues": {":athlete_id": athlete_id}
            }

            try:
                response = table.scan(**scan_kwargs)
                activities = response.get("Items", [])

                # Filtrare dupa tip si data (manual)
                filtered = []
                for act in activities:
                    if "type" in query_params and act.get("type") != query_params["type"]:
                        continue
                    if "since" in query_params:
                        since_date = query_params["since"]
                        if act.get("start_date", "") < since_date:
                            continue
                    filtered.append(act)

                filtered.sort(key=lambda x: x.get("start_date", ""), reverse=True)
                if "limit" in query_params:
                    try:
                        filtered = filtered[:int(query_params["limit"])]
                    except:
                        pass

                results = []
                for a in filtered:
                    distance_km = float(a.get("distance", 0)) / 1000
                    moving_time_min = float(a.get("moving_time", 1)) / 60
                    type_ = a.get("type", "Unknown")

                    if type_.lower() in ["run", "walk"]:
                        pace = moving_time_min / distance_km if distance_km else 0
                        pace_or_speed = f"{pace:.2f} min/km"
                    elif type_.lower() == "swim":
                        pace = (moving_time_min / (float(a.get("distance", 1)) / 100)) if a.get("distance") else 0
                        pace_or_speed = f"{pace:.2f} min/100m"
                    else:
                        speed = distance_km / (moving_time_min / 60) if moving_time_min else 0
                        pace_or_speed = f"{speed:.2f} km/h"

                    results.append({
                        "strava_id": a.get("strava_id"),
                        "start_date": a.get("start_date"),
                        "name": a.get("name"),
                        "type": type_,
                        "distance_km": round(distance_km, 2),
                        "moving_time_min": round(moving_time_min, 1),
                        "average_heartrate": a.get("average_heartrate"),
                        "max_heartrate": a.get("max_heartrate"),
                        "calories": a.get("calories"),
                        "pace_or_speed": pace_or_speed
                    })

                return {
                    "statusCode": 200,
                    "headers": {
                        "Content-Type": "application/json",
                        "Access-Control-Allow-Origin": "*"
                    },
                    "body": json.dumps(results, default=default_serializer)
                }

            except Exception as e:
                print("Eroare la scan:", e)
                return {
                    "statusCode": 500,
                    "headers": {
                        "Content-Type": "application/json",
                        "Access-Control-Allow-Origin": "*"
                    },
                    "body": json.dumps({"error": f"Eroare interna: {str(e)}"})
                }

        elif "pathParameters" in event and event["pathParameters"].get("id"):
            activity_id = event["pathParameters"]["id"]
            print(f"Request pentru activitate: {activity_id}")

            try:
                # DynamoDB
                response = table.get_item(Key={"strava_id": activity_id})
                activity = response.get("Item")
                if not activity:
                    return {
                        "statusCode": 404,
                        "headers": {
                            "Content-Type": "application/json",
                            "Access-Control-Allow-Origin": "*"
                        },
                        "body": json.dumps({"error": f"Activitate nu a fost gasita in DynamoDB: {str(e)}"})
                    }

                # S3
                try:
                    stream_key = f"streams/{activity_id}.json"
                    s3_response = s3.get_object(Bucket=bucket_name, Key=stream_key)
                    stream_data = json.loads(s3_response["Body"].read())
                except s3.exceptions.NoSuchKey:
                    stream_data = None

                return {
                    "statusCode": 200,
                    "headers": {
                        "Content-Type": "application/json",
                        "Access-Control-Allow-Origin": "*"
                    },
                    "body": json.dumps({
                        "activity": activity,
                        "stream": stream_data
                    }, default=str)
                }
            
            except Exception as e:
                print("Eroare la interogare:", e)
                return {"statusCode": 500, "body": f"Eroare interna: {str(e)}"}
        return {
            "statusCode": 400,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"error": f"Cerere GET invalida: {str(e)}"})
        }

    elif method == "POST":
        body = json.loads(event["body"])
        activity_id = body.get("object_id")
        print(f"Primit de la Strava, activitate noua: {activity_id}")

        res = requests.post("https://www.strava.com/oauth/token", data={
            'client_id': os.getenv('CLIENT_ID'),
            'client_secret': os.getenv('CLIENT_SECRET'),
            'refresh_token': os.getenv('REFRESH_TOKEN'),
            'grant_type': 'refresh_token'
        })

        if res.status_code != 200:
            return {
                "statusCode": 500,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps({"error": f"Auth error: {res.text}"})
            }

        access_token = res.json().get('access_token')
        headers = {'Authorization': f'Bearer {access_token}'}

        activity_url = f"https://www.strava.com/api/v3/activities/{activity_id}"
        activity_res = requests.get(activity_url, headers=headers)

        if activity_res.status_code != 200:
            return {"statusCode": 500, "body": f"Activity error: {activity_res.text}"}

        activity_data = activity_res.json()
        print("Detalii activitate:", json.dumps(activity_data))

        activity_type = activity_data.get("type", "").lower()
        distance = float(activity_data.get("distance", 0))

        if activity_type == "ride" and distance == 0.0:
            print("Activitate ignorata: tip 'Ride' cu distanța 0 — probabil duplicat de la ceas.")
            return {"statusCode": 200, "body": "Activitate duplicat ignorata"}

        try:
            save_activity_to_dynamodb(activity_data)
            save_stream_to_s3(activity_id, access_token)
        except Exception as e:
            print("Eroare la salvare:", e)
            return {"statusCode": 500, "body": f"Eroare: {str(e)}"}

        return {"statusCode": 200, "body": "OK"}
    return {
        "statusCode": 405,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps({"error": "Method Not Allowed"})
    }