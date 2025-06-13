import requests
import openai
import urllib3
import os
from dotenv import load_dotenv
import sqlite3
from datetime import datetime, timedelta

urllib3.disable_warnings()

# === STRAVA API ===
activities_url = "https://www.strava.com/api/v3/athlete/activities"
activity_detail_url = "https://www.strava.com/api/v3/activities/"
auth_url = "https://www.strava.com/oauth/token"

# === DB CONNECT ===
conn = sqlite3.connect("strava_metrics.db")
cursor = conn.cursor()

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

# === .env config ===
load_dotenv()

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

# === Funcție verificare duplicat ===
def is_duplicate_activity(act):
    # Eliminam "Z" daca apare la final
    start_raw = act['start_date_local'].replace('Z', '')
    start_time = datetime.fromisoformat(start_raw)
    
    time_lower = (start_time - timedelta(seconds=10)).isoformat()
    time_upper = (start_time + timedelta(seconds=10)).isoformat()

    cursor.execute("""
        SELECT 1 FROM activities
        WHERE type = ?
        AND ABS(distance - ?) < 50
        AND ABS(elapsed_time - ?) < 10
        AND start_date BETWEEN ? AND ?
    """, (
        act['type'],
        act['distance'],
        act['elapsed_time'],
        time_lower,
        time_upper
    ))

    return cursor.fetchone() is not None

# === PAS: Preluare 20 activitați ===
param = {'per_page': 20, 'page': 1}
activity_list = requests.get(activities_url, headers=header, params=param).json()

for act in activity_list:
    if is_duplicate_activity(act):
        print(f"Duplicat ignorat: {act['name']} - {act['start_date_local']}")
        continue

    #  GET activitate detaliata
    detailed_act = requests.get(activity_detail_url + str(act['id']), headers=header).json()

    # Daca e o activitate pe trainer, o ignoram
    if detailed_act.get('trainer', False):
        print(f"Ignorat (trainer=True): {detailed_act['name']} - {detailed_act['start_date_local']}")
        continue

    # === Pace / viteza ===
    average_speed = detailed_act.get('average_speed', 0)
    sport_type = detailed_act.get('sport_type', '').lower()
    pace_str = None       # pentru run/walk
    speed_kmh = None      # pentru ride/swim

    if average_speed > 0:
        if sport_type in ['run', 'trailrun', 'walk', 'hike']:
        # calculam pace în min/km
            pace = 16.6667 / average_speed
            minutes = int(pace)
            seconds = round((pace - minutes) * 60)
            pace_str = f"{minutes}:{seconds:02d} min/km"

        elif sport_type in ['ride', 'virtualride', 'ebikeride', 'swim']:
        # conversie în km/h
            speed_kmh = round(average_speed * 3.6, 1)

    # === Inserare în DB ===
    cursor.execute("""
        INSERT OR IGNORE INTO activities (
            strava_id, name, type, start_date,
            distance, elapsed_time, moving_time,
            average_speed, pace_formatted, speed_kmh,
            total_elevation_gain, average_heartrate,
            max_heartrate, average_watts, calories, trainer
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(detailed_act['id']),
        detailed_act['name'],
        detailed_act['type'],
        detailed_act['start_date_local'],
        round(detailed_act['distance'] / 1000, 2),           # în km
        round(detailed_act['elapsed_time'] / 60, 1),         # în minute
        round(detailed_act['moving_time'] / 60, 1),
        detailed_act.get('average_speed'),
        pace_str,
        speed_kmh,
        detailed_act.get('total_elevation_gain', 0),
        detailed_act.get('average_heartrate'),
        detailed_act.get('max_heartrate'),
        detailed_act.get('average_watts'),
        detailed_act.get('calories'),
        detailed_act.get('trainer', False)
    ))
    conn.commit()
    print(f"Salvat: {detailed_act['name']} - {detailed_act['start_date_local']}")

# === Ultima activitate salvata ===
cursor.execute("SELECT * FROM activities ORDER BY start_date DESC LIMIT 1")
row = cursor.fetchone()

if row:
    activity_type = row[3].lower()

    if activity_type in ['run', 'walk', 'hike', 'trailrun']:
        pace_or_speed = row[9] if row[9] else '–'
    elif activity_type in ['ride', 'virtualride', 'ebikeride', 'swim']:
        pace_or_speed = f"{row[10]} km/h" if row[10] else '–'
    else:
        pace_or_speed = '–'

    activity_info = f"""
Nume activitate: {row[2]}
Tip: {row[3]}
Distanta: {row[5]:.2f} km
Timp activitate: {row[7]:.1f} minute
Pace/Viteza: {pace_or_speed}
Puls mediu: {row[12]}
Puls maxim: {row[13]}
Putere medie: {row[14]} W
Calorii consumate: {row[15]} Kcal
"""
print(activity_info)

# === ChatGPT ===
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

# === Închidere conexiune DB ===
conn.close()
