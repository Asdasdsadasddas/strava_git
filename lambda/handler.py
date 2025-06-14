import os
import requests
import json

print("ID:", os.getenv('CLIENT_ID'))
print("SECRET:", os.getenv('CLIENT_SECRET'))
print("REFRESH:", os.getenv('REFRESH_TOKEN'))

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
        # === PARSEAZĂ EVENTUL STRAVA ===
        body = json.loads(event["body"])
        activity_id = body.get("object_id")
        print(f"Primit de la Strava, activitate nouă: {activity_id}")

        # === OBTINE ACCESS TOKEN CU REFRESH TOKEN ===
        auth_url = "https://www.strava.com/oauth/token"
        payload = {
            'client_id': os.getenv('CLIENT_ID'),
            'client_secret': os.getenv('CLIENT_SECRET'),
            'refresh_token': os.getenv('REFRESH_TOKEN'),
            'grant_type': 'refresh_token'
        }
        res = requests.post(auth_url, data=payload)
        print("STRAVA TOKEN RESPONSE:", res.text)
        access_token = res.json()['access_token']
        header = {'Authorization': 'Bearer ' + access_token}

        # === CERE DETALII DESPRE ACTIVITATE ===
        activity_detail_url = f"https://www.strava.com/api/v3/activities/{activity_id}"
        activity_res = requests.get(activity_detail_url, headers=header)
        activity_data = activity_res.json()
        print(f"Detalii activitate: {json.dumps(activity_data)}")

        return {"statusCode": 200, "body": "OK"}

    return {"statusCode": 405, "body": "Method Not Allowed"}
