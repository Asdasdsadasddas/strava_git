import requests
import openai
import urllib3
import os
from dotenv import load_dotenv
import sqlite3  

urllib3.disable_warnings()

# === STRAVA PART ===
activities_url = "https://www.strava.com/api/v3/athlete/activities"
auth_url = "https://www.strava.com/oauth/token"

# Conectare la baza de date
conn = sqlite3.connect("strava_metrics.db")
cursor = conn.cursor()

# Creare tabel dacă nu există
cursor.execute("""
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strava_id TEXT UNIQUE,
    name TEXT,
    type TEXT,
    start_date TEXT,
    distance REAL,
    elapsed_time INTEGER,
    moving_time INTEGER,
    average_speed REAL,
    pace TEXT,
    total_elevation_gain REAL,
    average_heartrate REAL,
    max_heartrate REAL,
    average_watts REAL,
    calories REAL,
    trainer BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# Incarcă variabilele din .env
load_dotenv()

# === Autentificare Strava ===
payload = {
    'client_id': os.getenv('CLIENT_ID'),
    'client_secret': os.getenv('CLIENT_SECRET'),
    'refresh_token': os.getenv('REFRESH_TOKEN'),
    'grant_type': 'refresh_token',
    'f': 'json'
}


res = requests.post(auth_url, data=payload, verify=False)
access_token = res.json()['access_token']
header = {'Authorization': 'Bearer ' + access_token}
param = {'per_page': 1, 'page': 1}
activities = requests.get(activities_url, headers=header, params=param).json()

# === Activitate detaliată ===
activity_id = activities[0]['id']
detail_url = f"https://www.strava.com/api/v3/activities/{activity_id}"
last_activity = requests.get(detail_url, headers=header).json()

# === Calcul pace sau viteza ===
average_speed = last_activity.get('average_speed', 0)
sport_type = last_activity.get('sport_type', '').lower()

if average_speed == 0:
    pace_str = "N/A"
    speed_or_pace = "Date viteza/pace indisponibile"
elif sport_type in ['run', 'trailrun', 'walk', 'hike']:
    pace = 16.6667 / average_speed
    minutes = int(pace)
    seconds = round((pace - minutes) * 60)
    pace_str = f"{minutes}:{seconds:02d}"
    speed_or_pace = f"Pace mediu: {pace_str} min/km"
elif sport_type in ['ride', 'virtualride', 'ebikeride']:
    speed_kmh = average_speed * 3.6
    pace_str = f"{speed_kmh:.1f} km/h"
    speed_or_pace = f"Viteza medie: {pace_str}"
elif sport_type == 'swim':
    pace_100m = (100 / average_speed) / 60
    minutes = int(pace_100m)
    seconds = round((pace_100m - minutes) * 60)
    pace_str = f"{minutes}:{seconds:02d}"
    speed_or_pace = f"Pace mediu: {pace_str} min/100m"
else:
    speed_kmh = average_speed * 3.6
    pace_str = f"{speed_kmh:.1f} km/h"
    speed_or_pace = f"Viteza estimata: {pace_str} (tip necunoscut)"

# === Afisare info ===
activity_info = f"""
Nume activitate: {last_activity['name']}
Tip: {last_activity['type']}
Distanta: {last_activity['distance']/1000:.2f} km
Timp activitate: {last_activity['moving_time'] / 60:.1f} minute
{speed_or_pace}
Puls mediu: {last_activity.get('average_heartrate', 'n/a')}
Puls maxim: {last_activity.get('max_heartrate', 'n/a')}
Putere medie: {last_activity.get('average_watts', 'n/a')} W
Calorii consumate: {last_activity.get('calories', 'n/a')} Kcal
"""

print(activity_info)

#  Salvare în baza de date
cursor.execute("""
INSERT OR IGNORE INTO activities (
    strava_id, name, type, start_date,
    distance, elapsed_time, moving_time,
    average_speed, pace, total_elevation_gain,
    average_heartrate, max_heartrate,
    average_watts, calories, trainer
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    str(activity_id),
    last_activity['name'],
    last_activity['type'],
    last_activity['start_date_local'],
    last_activity['distance'],
    last_activity['elapsed_time'],
    last_activity['moving_time'],
    last_activity['average_speed'],
    pace_str,
    last_activity.get('total_elevation_gain', 0),
    last_activity.get('average_heartrate'),
    last_activity.get('max_heartrate'),
    last_activity.get('average_watts'),
    last_activity.get('calories'),
    last_activity.get('trainer', False)
))
conn.commit()

print(activity_info)

# === CHATGPT PART ===
openai.api_key = "my_api_key"

prompt = f"""Am facut urmatorul antrenament:\n{activity_info}
Ce parere ai despre el? Ce imi recomanzi pentru urmatorul antrenament?"""

response = openai.ChatCompletion.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "Esti un antrenor sportiv digital. Raspunde concis, dar cu explicatii utile."},
        {"role": "user", "content": prompt}
    ]
)

print(response['choices'][0]['message']['content'])

#  Închidere conexiune DB
conn.close()
