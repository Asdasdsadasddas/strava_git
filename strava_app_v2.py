import requests
import openai
import urllib3
import os
from dotenv import load_dotenv

urllib3.disable_warnings()

# === STRAVA PART ===
activities_url = "https://www.strava.com/api/v3/athlete/activities"
auth_url = "https://www.strava.com/oauth/token"

# Incarcă variabilele din .env
load_dotenv()

# Pasul 1: Autentificare
payload = {
    'client_id': os.getenv('CLIENT_ID'),
    'client_secret': os.getenv('CLIENT_SECRET'),
    'refresh_token': os.getenv('REFRESH_TOKEN'),
    'grant_type': 'refresh_token',
    'f': 'json'
}

# Pasul 1: Obtine access_token
res = requests.post(auth_url, data=payload, verify=False)
access_token = res.json()['access_token']

# Pasul 2: Cerere catre API pentru ultima activitate (lista sumara)
header = {'Authorization': 'Bearer ' + access_token}
param = {'per_page': 1, 'page': 1}
activities = requests.get(activities_url, headers=header, params=param).json()

# Pasul 3: Ia ID-ul ultimei activitati
activity_id = activities[0]['id']

# Pasul 4: Cerere detaliata pentru acea activitate
detail_url = f"https://www.strava.com/api/v3/activities/{activity_id}"
last_activity = requests.get(detail_url, headers=header).json()

# Pasul 5: Calculeaza viteza sau pace-ul
average_speed = last_activity.get('average_speed', 0)
sport_type = last_activity.get('sport_type', '').lower()

if average_speed == 0:
    speed_or_pace = "Date viteza/pace indisponibile"
elif sport_type in ['run', 'trailrun', 'walk', 'hike']:
    pace = 16.6667 / average_speed
    minutes = int(pace)
    seconds = round((pace - minutes) * 60)
    speed_or_pace = f"Pace mediu: {minutes}:{seconds:02d} min/km"
elif sport_type in ['ride', 'virtualride', 'ebikeride']:
    speed_kmh = average_speed * 3.6
    speed_or_pace = f"Viteza medie: {speed_kmh:.1f} km/h"
elif sport_type == 'swim':
    pace_100m = (100 / average_speed) / 60
    minutes = int(pace_100m)
    seconds = round((pace_100m - minutes) * 60)
    speed_or_pace = f"Pace mediu: {minutes}:{seconds:02d} min/100m"
else:
    speed_kmh = average_speed * 3.6
    speed_or_pace = f"Viteza estimata: {speed_kmh:.1f} km/h (tip necunoscut)"

# Pasul 6: Format final pentru afișare
activity_info = f"""
Nume activitate: {last_activity['name']}
Tip: {last_activity['type']}
Distanta: {last_activity['distance']/1000:.2f} km
Timp activitate: {last_activity['moving_time'] / 60:.1f} minuteN
{speed_or_pace}
Puls mediu: {last_activity.get('average_heartrate', 'n/a')}
Puls maxim: {last_activity.get('max_heartrate', 'n/a')}
Putere medie: {last_activity.get('average_watts', 'n/a')} W
Calorii consumate: {last_activity.get('calories', 'n/a')} Kcal
"""

print(activity_info)


# === CHATGPT PART ===

# === Autentificare ===
openai.api_key = os.getenv("OPENAI_API_KEY")

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



# try:
#     response = openai.ChatCompletion.create(
#         model="gpt-4o",
#         messages=[
#             {"role": "system", "content": "Esti un antrenor sportiv digital."},
#             {"role": "user", "content": prompt}
#         ]
#     )
#     analysis = response['choices'][0]['message']['content']
#     print(analysis)

# except openai.error.RateLimitError:
#     print("Eroare: Ai depasit limita de utilizare a API-ului. Verifica contul tau pe platform.openai.com.")

# except Exception as e:
#     print("A aparut o eroare:", e)