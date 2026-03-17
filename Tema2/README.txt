Tema 2 - aplicație full-stack cu 3 web services

Structură:
- task_service/task_api.py       -> serviciul REST din tema 1
- app_backend/app_server.py      -> backend agregator pentru frontend
- app_backend/config.json        -> configurare URL-uri și API keys
- frontend/index.html            -> interfață web
- frontend/style.css             -> stilizare
- frontend/app.js                -> logică frontend

Cum rulezi:
1. Într-un terminal:
   cd task_service
   python task_api.py

2. În alt terminal:
   cd app_backend
   python app_server.py

3. Deschide frontend/index.html în browser.

IMPORTANT:
- Completează în app_backend/config.json:
  * openweather_api_key
  * api_ninjas_api_key

Servicii folosite:
1. REST API propriu pentru task-uri
2. OpenWeather Current Weather API
3. API Ninjas Facts API
