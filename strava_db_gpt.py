#strava_db_gpt

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
    pace_formatted TEXT,
    speed_kmh REAL,               -- AICI ADAUGI speed_kmh
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

# === Functie verificare duplicat ===
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

# === PAS: Preluare 20 activitati ===
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

# == Functie pentru media pe saptamana ==
def get_weekly_summary(cursor):
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()

    cursor.execute("""
        SELECT * FROM activities
        WHERE start_date >= ?
        AND trainer = 0
    """, (seven_days_ago,))

    activities = cursor.fetchall()

    if not activities:
        return "Nu exista activitati în ultimele 7 zile."

    total_distance = 0
    total_time = 0
    total_heartrate = 0
    heartrate_count = 0
    activity_types = {}

    for act in activities:
        total_distance += act[5] or 0
        total_time += act[7] or 0

        if act[11]:  # average_heartrate
            total_heartrate += act[12]
            heartrate_count += 1

        activity_type = act[3]
        if activity_type not in activity_types:
            activity_types[activity_type] = 0
        activity_types[activity_type] += 1

    avg_heartrate = round(total_heartrate / heartrate_count, 1) if heartrate_count else "-"
    total_distance = round(total_distance, 2)
    total_time = round(total_time, 1)

    summary = f"""
Sumar ultimele 7 zile:
- Total distanta: {total_distance} km
- Timp total antrenament: {total_time} minute
- Puls mediu general: {avg_heartrate}
- Activitati: {', '.join([f"{v}x {k}" for k, v in activity_types.items()])}
"""
    return summary

# === Partea de ChatGPT ===
openai.api_key = os.getenv('OPENAI_API_KEY')

# Obiectivul utilizatorului
user_goal = "Imbunatatirea bazei aerobe, fara deadline."

# Generam sumarul saptamanal
weekly_summary = get_weekly_summary(cursor)
print(weekly_summary)

# Cream promptul
prompt = f"""
Obiectivul meu: {user_goal}

Activitatea recenta:
{activity_info}

Rezumat saptamanal:
{weekly_summary}


Te rog sa analizezi aceste date astfel:

1. Compara distanta, durata, viteza (sau pace-ul), pulsul mediu si puterea medie (daca exista) ale activitatii recente cu media activitatilor din ultimele 7 zile.
2. Spune-mi daca acest antrenament a fost:
   - mai usor, mai intens sau similar cu media,
   - din punct de vedere al pulsului relativ la distanta si viteza.
3. Analizeaza daca exista un progres in dezvoltarea bazei aerobe:
   - Puls mediu mai mic la o viteza/durata similara,
   - Viteza mai buna la acelasi puls,
   - Timp mai lung petrecut in zone de puls aerobic (daca poti estima).
4. Daca identifici zone de imbunatatit, sugereaza corectii practice pentru antrenamentele urmatoare:
   - Volum,
   - Intensitate,
   - Durata antrenamentelor.
5. Sugestie cu privire la continuare sau modificare antrenament raportat la obiectiv.Explica scurt unde exista progres, unde e stagnare si ce ar trebui ajustat.

Vreau un raspuns structurat, clar si bazat pe datele furnizate, nu pe generalitati.

"""

# === Trimitere catre ChatGPT si afisare raspuns ===
response = openai.ChatCompletion.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "Esti un antrenor sportiv digital care vrea sa ma ajute sa imbunatatesc zona aeroba. Raspunde concis, dar cu explicatii utile."},
        {"role": "user", "content": prompt}
    ]
)

# Afisam raspunsul de la GPT
print("\n--- Raspuns GPT ---\n")
print(response['choices'][0]['message']['content'])

# === Inchidere conexiune DB ===
conn.close()




