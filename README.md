# Cloud-Based Weather Monitoring Dashboard

Live weather from the free Open-Meteo API (no API key, internet connection required).

## Run locally (Windows / Mac / Linux)
    python -m venv venv
    venv\Scripts\activate          # Mac/Linux: source venv/bin/activate
    python -m pip install -r requirements.txt
    python app.py                  # open http://localhost:5000

## Features
- Search any city and add it to the dashboard (up to 12)
- Current conditions: temperature, feels-like, humidity, wind, pressure, precipitation
- Next-24-hours chart and 7-day forecast
- A background thread records every city's weather every 15 minutes (POLL_MINUTES), giving a stored history chart
- Alerts when your limits are crossed (heat, cold, wind, heavy rain today) or a thunderstorm is reported
- Adjustable alert limits; auto-refresh every 5 minutes; light and dark mode

## Deploy to the cloud
- Run with ONE worker so only one background poller runs:
  Linux: pip install gunicorn, then `gunicorn -w 1 --threads 4 -b 0.0.0.0:8000 "app:app"`
  Windows: pip install waitress, then `waitress-serve app:app`
- When started through gunicorn/waitress, call `start_poller()` once (for example in a small wsgi.py) because the poller
  starts automatically only with `python app.py`
- Use PostgreSQL and HTTPS for production. There is no login: anyone with the URL can add cities, so put it behind
  authentication (or add the login code from the earlier projects) before making it public.
- Hosting options: AWS Elastic Beanstalk, EC2, Render, Railway. Use a persistent disk for DB_PATH.

## Config (environment variables)
DB_PATH, POLL_MINUTES (default 15)
