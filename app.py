"""Cloud-Based Weather Monitoring Dashboard - Flask + SQLite backend.
Live data comes from the free Open-Meteo API (no API key needed).
Run:  python -m pip install -r requirements.txt  then  python app.py
A background thread records every saved city's weather every POLL_MINUTES, building a history."""
import os, sqlite3, threading, time
from datetime import datetime, timedelta, timezone
import requests
from flask import Flask, request, jsonify, g

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE, "weather.db"))
POLL_MINUTES = int(os.environ.get("POLL_MINUTES", "15"))
CACHE_SECONDS = 600
MAX_CITIES = 12
GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

app = Flask(__name__, static_folder="static", static_url_path="")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cities(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, country TEXT,
  lat REAL NOT NULL, lon REAL NOT NULL, UNIQUE(lat, lon));
CREATE TABLE IF NOT EXISTS readings(
  id INTEGER PRIMARY KEY AUTOINCREMENT, city_id INTEGER NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
  ts TEXT NOT NULL, temp REAL, feels REAL, humidity REAL, wind REAL, precip REAL, pressure REAL, code INTEGER);
CREATE INDEX IF NOT EXISTS idx_readings ON readings(city_id, ts);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value REAL NOT NULL);
"""
DEFAULTS = {"max_temp": 38, "min_temp": 5, "max_wind": 50, "max_rain_day": 50}

CODES = {0: ("Clear sky", "☀️"), 1: ("Mainly clear", "🌤️"), 2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"),
         45: ("Fog", "🌫️"), 48: ("Freezing fog", "🌫️"), 51: ("Light drizzle", "🌦️"), 53: ("Drizzle", "🌦️"),
         55: ("Heavy drizzle", "🌦️"), 56: ("Freezing drizzle", "🌧️"), 57: ("Freezing drizzle", "🌧️"),
         61: ("Light rain", "🌧️"), 63: ("Rain", "🌧️"), 65: ("Heavy rain", "🌧️"), 66: ("Freezing rain", "🌧️"),
         67: ("Freezing rain", "🌧️"), 71: ("Light snow", "🌨️"), 73: ("Snow", "🌨️"), 75: ("Heavy snow", "❄️"),
         77: ("Snow grains", "🌨️"), 80: ("Rain showers", "🌦️"), 81: ("Rain showers", "🌧️"),
         82: ("Violent showers", "⛈️"), 85: ("Snow showers", "🌨️"), 86: ("Snow showers", "🌨️"),
         95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm, hail", "⛈️"), 99: ("Thunderstorm, hail", "⛈️")}

def describe(code):
    label, icon = CODES.get(code, ("Unknown", "❔"))
    return {"label": label, "icon": icon}

def connect():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def db():
    if "db" not in g: g.db = connect()
    return g.db

@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d: d.close()

with connect() as c:
    c.executescript(SCHEMA)

# ---- Open-Meteo access
def fetch_json(url, params):
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def fetch_forecast(lat, lon):
    return fetch_json(FORECAST_URL, {
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 7,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_direction_10m,surface_pressure",
        "hourly": "temperature_2m,precipitation_probability",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max"})

def build_weather(raw):
    cur, h, d = raw["current"], raw["hourly"], raw["daily"]
    start = next((i for i, t in enumerate(h["time"]) if t[:13] >= cur["time"][:13]), 0)
    hourly = [{"time": t, "temp": v, "pop": p} for t, v, p in
              zip(h["time"][start:start + 24], h["temperature_2m"][start:start + 24], h["precipitation_probability"][start:start + 24])]
    daily = [{"date": t, "code": c, "max": hi, "min": lo, "rain": r, "pop": p, **describe(c)} for t, c, hi, lo, r, p in
             zip(d["time"], d["weather_code"], d["temperature_2m_max"], d["temperature_2m_min"],
                 d["precipitation_sum"], d["precipitation_probability_max"])]
    return {"current": {"temp": cur["temperature_2m"], "feels": cur["apparent_temperature"],
                        "humidity": cur["relative_humidity_2m"], "wind": cur["wind_speed_10m"],
                        "wind_dir": cur["wind_direction_10m"], "precip": cur["precipitation"],
                        "pressure": cur["surface_pressure"], "code": cur["weather_code"], "time": cur["time"],
                        **describe(cur["weather_code"])},
            "hourly": hourly, "daily": daily, "timezone": raw.get("timezone")}

_cache = {}  # city_id -> (fetched_at, weather)
_lock = threading.Lock()

def get_weather(city):
    with _lock:
        hit = _cache.get(city["id"])
        if hit and time.time() - hit[0] < CACHE_SECONDS: return hit[1]
    w = build_weather(fetch_forecast(city["lat"], city["lon"]))
    with _lock: _cache[city["id"]] = (time.time(), w)
    return w

def settings(conn):
    s = dict(DEFAULTS)
    s.update({r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")})
    return s

def alerts_for(w, s):
    cur, out = w["current"], []
    if cur["temp"] >= s["max_temp"]: out.append({"level": "high", "text": f"Heat: {cur['temp']}°C is above your {s['max_temp']:g}°C limit"})
    if cur["temp"] <= s["min_temp"]: out.append({"level": "high", "text": f"Cold: {cur['temp']}°C is below your {s['min_temp']:g}°C limit"})
    if cur["wind"] >= s["max_wind"]: out.append({"level": "high", "text": f"Wind: {cur['wind']} km/h is above your {s['max_wind']:g} km/h limit"})
    today = w["daily"][0]["rain"] if w["daily"] else 0
    if today and today >= s["max_rain_day"]: out.append({"level": "medium", "text": f"Rain: {today} mm expected today (limit {s['max_rain_day']:g} mm)"})
    if cur["code"] >= 95: out.append({"level": "high", "text": "Thunderstorm in the area"})
    return out

def store_reading(conn, city_id, w):
    c = w["current"]
    conn.execute("""INSERT INTO readings(city_id,ts,temp,feels,humidity,wind,precip,pressure,code) VALUES(?,?,?,?,?,?,?,?,?)""",
                 (city_id, datetime.now(timezone.utc).isoformat(timespec="seconds"), c["temp"], c["feels"],
                  c["humidity"], c["wind"], c["precip"], c["pressure"], c["code"]))
    conn.commit()

def poll_once():
    conn = connect()
    try:
        for city in conn.execute("SELECT * FROM cities").fetchall():
            try:
                w = build_weather(fetch_forecast(city["lat"], city["lon"]))
                with _lock: _cache[city["id"]] = (time.time(), w)
                store_reading(conn, city["id"], w)
            except Exception as e:
                print(f"poll failed for {city['name']}: {e}")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
        conn.execute("DELETE FROM readings WHERE ts < ?", (cutoff,)); conn.commit()
    finally:
        conn.close()

def poller():
    while True:
        poll_once()
        time.sleep(POLL_MINUTES * 60)

# ---- routes
@app.get("/api/search")
def search():
    q = request.args.get("q", "").strip()
    if len(q) < 2: return jsonify([])
    try:
        data = fetch_json(GEO_URL, {"name": q, "count": 6, "language": "en"})
    except requests.RequestException:
        return jsonify(error="Could not reach the weather service. Try again shortly."), 502
    return jsonify([{"name": r["name"], "country": r.get("country", ""), "admin": r.get("admin1", ""),
                     "lat": r["latitude"], "lon": r["longitude"]} for r in data.get("results", [])])

@app.get("/api/cities")
def cities():
    return jsonify([dict(r) for r in db().execute("SELECT * FROM cities ORDER BY name")])

@app.post("/api/cities")
def add_city():
    d = request.get_json(force=True)
    try: name, lat, lon = d["name"].strip(), round(float(d["lat"]), 4), round(float(d["lon"]), 4)
    except (KeyError, TypeError, ValueError, AttributeError): return jsonify(error="Pick a city from the search results."), 400
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or not name: return jsonify(error="Invalid location."), 400
    if db().execute("SELECT COUNT(*) FROM cities").fetchone()[0] >= MAX_CITIES:
        return jsonify(error=f"You can track up to {MAX_CITIES} cities. Remove one first."), 400
    try:
        cur = db().execute("INSERT INTO cities(name,country,lat,lon) VALUES(?,?,?,?)", (name, d.get("country", ""), lat, lon))
        db().commit()
    except sqlite3.IntegrityError:
        return jsonify(error="That city is already on your dashboard."), 409
    try:  # record a first reading right away
        city = db().execute("SELECT * FROM cities WHERE id=?", (cur.lastrowid,)).fetchone()
        store_reading(db(), city["id"], get_weather(city))
    except Exception: pass
    return jsonify(id=cur.lastrowid), 201

@app.delete("/api/cities/<int:cid>")
def delete_city(cid):
    db().execute("DELETE FROM readings WHERE city_id=?", (cid,))
    db().execute("DELETE FROM cities WHERE id=?", (cid,)); db().commit()
    _cache.pop(cid, None)
    return jsonify(ok=True)

def city_or_404(cid):
    return db().execute("SELECT * FROM cities WHERE id=?", (cid,)).fetchone()

@app.get("/api/weather/<int:cid>")
def weather(cid):
    city = city_or_404(cid)
    if not city: return jsonify(error="City not found."), 404
    try: w = get_weather(city)
    except (requests.RequestException, KeyError, ValueError):
        return jsonify(error="Could not load weather for this city right now."), 502
    return jsonify(city=dict(city), alerts=alerts_for(w, settings(db())), **w)

@app.get("/api/overview")
def overview():
    s, out = settings(db()), []
    for city in db().execute("SELECT * FROM cities ORDER BY name").fetchall():
        try:
            w = get_weather(city)
            out.append({"city": dict(city), "current": w["current"], "alerts": alerts_for(w, s)})
        except (requests.RequestException, KeyError, ValueError):
            out.append({"city": dict(city), "error": "Unavailable right now"})
    return jsonify(out)

@app.get("/api/cities/<int:cid>/history")
def history(cid):
    if not city_or_404(cid): return jsonify(error="City not found."), 404
    try: hours = max(1, min(720, int(request.args.get("hours", 24))))
    except ValueError: hours = 24
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    rows = db().execute("""SELECT ts,temp,humidity,wind,pressure FROM readings
                           WHERE city_id=? AND ts>=? ORDER BY ts""", (cid, since))
    return jsonify([dict(r) for r in rows])

@app.route("/api/settings", methods=["GET", "PUT"])
def settings_route():
    if request.method == "PUT":
        d = request.get_json(force=True)
        for k in DEFAULTS:
            if k in d:
                try: v = float(d[k])
                except (TypeError, ValueError): return jsonify(error=f"{k} must be a number."), 400
                db().execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
        db().commit()
    return jsonify(settings(db()))

@app.get("/")
def index(): return app.send_static_file("index.html")

def start_poller():
    threading.Thread(target=poller, daemon=True).start()

if __name__ == "__main__":
    start_poller()
    app.run(port=5000, debug=False)
