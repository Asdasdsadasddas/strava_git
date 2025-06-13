# Strava_gpt_project
App that takes strava metrics and analize with chatgpt

Summary Description
This project aims to automate the analysis of training sessions by integrating Garmin devices, the Strava platform, and the ChatGPT language model. The goal is to provide personalized, intelligent feedback after each workout, without any manual input from the user.
The process is straightforward: once a physical activity (e.g., a run or a bike ride) is completed, the data is recorded by the Garmin watch and automatically synced to Strava. A local system running on a virtual machine constantly monitors the user's Strava account and fetches the latest activities. The system extracts key performance data, formats it into a structured prompt, and sends it to ChatGPT via its API.
ChatGPT analyzes the data and generates a personalized summary of the workout, including performance insights and actionable recommendations. This feedback is stored and can be accessed by the user at any time.
This solution transforms raw workout data into clear, intelligent analysis – immediately available after every training session.

Project Tasks – Checklist

 Phase 1: Local Infrastructure Setup
 Set up Ubuntu on a virtual machine (VM)
 Install PostgreSQL and configure database and user
 Install Python environment (pipenv, poetry, or virtualenv)
 Set up the base FastAPI (or Flask) server project

 Phase 2: Strava API Integration
 Create a Strava App on Strava API Dashboard
 Save client_id, client_secret, and set up redirect_uri
 Implement OAuth2 flow (authentication + token exchange)
 Store access and refresh tokens in the database
 Create an endpoint to fetch activities (GET /activities)
 Save raw activity data to PostgreSQL

 Phase 3: Activity Fetch Trigger
 Implement Strava webhook listener (POST /webhook)
 (Alternative) Create a polling script (cron job)
 On new activity trigger → fetch full activity details from Strava
 
 Phase 4: ChatGPT Analysis Integration
 Create a function to build structured prompt from activity data
 Connect to OpenAI's API (e.g. GPT-4 Turbo)
 Send activity prompt → receive and process the response
 Store the analysis result in the database
 
 Phase 5: Output & Access
 Create endpoint GET /activities/:id/report for viewing analysis
 (Optional) Implement email or Telegram notification system
 (Optional) Build a simple dashboard for viewing history and insights
 
 Phase 6: Post-MVP Enhancements
 Visual dashboard for activity trends
 Auto-categorization of workouts (intervals, recovery, tempo)
 Garmin direct integration (optional, long term)
