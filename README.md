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

<img width="1898" height="810" alt="Screenshot 2026-10-26 185619" src="https://github.com/user-attachments/assets/f2bcb391-f226-4509-9382-f6a74bd812d5" />


## Deploy to the cloud
- Run with ONE worker so only one background poller runs:
  Linux: pip install gunicorn, then `gunicorn -w 1 --threads 4 -b 0.0.0.0:8000 "app:app"`
  Windows: pip install waitress, then `waitress-serve app:app`
- When started through gunicorn/waitress, call `start_poller()` once (for example in a small wsgi.py) because the poller
  starts automatically only with `python app.py`
- Use PostgreSQL and HTTPS for production. There is no login: anyone with the URL can add cities, so put it behind
  authentication (or add the login code from the earlier projects) before making it public.
- Hosting options: AWS Elastic Beanstalk, EC2, Render, Railway. Use a persistent disk for DB_PATH.

<img width="1901" height="901" alt="Screenshot 2026-10-26 185635" src="https://github.com/user-attachments/assets/7be8cedd-437d-46a0-a33d-525ba4b52da8" />
<img width="1882" height="896" alt="Screenshot 2026-10-26 185649" src="https://github.com/user-attachments/assets/0f144270-66c0-4224-b9ee-77f3bd7ad06a" />


## Config (environment variables)
DB_PATH, POLL_MINUTES (default 15)
