from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, WeatherQuery, WeatherData
import datetime
from datetime import datetime


# Create DB engine
engine = create_engine("sqlite:///weather.db")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


import os
import requests
from flask import Flask, render_template, request, url_for, redirect
from dotenv import load_dotenv
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

# Load environment variables from .env
load_dotenv()
OWM_API_KEY = os.getenv("OWM_API_KEY")

app = Flask(__name__)

def geocode_location(query):
    """
    Try geocoding with Nominatim first.
    If fails, fallback to OpenWeatherMap geocoding.
    """
    # --- Try Nominatim ---
    try:
        geolocator = Nominatim(user_agent="weather_app")
        location = geolocator.geocode(query, addressdetails=True, timeout=10)
        if location:
            # Build a friendly name
            address = location.raw.get("address", {})
            name_parts = [address.get("city") or address.get("town") or address.get("village") or address.get("state")]
            if address.get("country"):
                name_parts.append(address["country"])
            return {
                "name": ", ".join([p for p in name_parts if p]),
                "lat": location.latitude,
                "lon": location.longitude,
            }
    except GeocoderTimedOut:
        pass  # Try fallback

    # --- Fallback to OpenWeatherMap ---
    url = "https://api.openweathermap.org/geo/1.0/direct"
    params = {"q": query, "limit": 1, "appid": OWM_API_KEY}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    item = data[0]
    name_parts = [item.get("name")]
    if item.get("state"):
        name_parts.append(item["state"])
    if item.get("country"):
        name_parts.append(item["country"])
    return {
        "name": ", ".join([p for p in name_parts if p]),
        "lat": item["lat"],
        "lon": item["lon"],
    }

# Function to get current weather by lat/lon
def fetch_current_weather(lat, lon):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"lat": lat, "lon": lon, "appid": OWM_API_KEY, "units": "metric"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

# Function to get 5-day forecast
def fetch_forecast(lat, lon):
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": OWM_API_KEY, "units": "metric"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()

    # Pick one forecast per day at 12:00:00
    forecast_list = []
    for item in data["list"]:
        if "12:00:00" in item["dt_txt"]:
            forecast_list.append({
                "date": item["dt_txt"].split(" ")[0],
                "temp": round(item["main"]["temp"]),
                "description": item["weather"][0]["description"].title(),
                "icon": item["weather"][0]["icon"]
            })
    return forecast_list

@app.route("/", methods=["GET"])
def index():
    forecast = None
    query = request.args.get("location", "").strip()
    error = None
    weather = None
    place = None
    geo = None

    if query:
        try:
            geo = geocode_location(query)
            if not geo:
                error = f"Could not find a location for '{query}'. Try a city, town, or zip/postal code."
            else:
                place = geo["name"]
                w = fetch_current_weather(geo["lat"], geo["lon"])
                weather = {
                    "temp": round(w["main"]["temp"]),
                    "feels_like": round(w["main"]["feels_like"]),
                    "humidity": w["main"]["humidity"],
                    "wind_speed": w["wind"]["speed"],
                    "description": w["weather"][0]["description"].title(),
                    "icon": w["weather"][0]["icon"],
                }
                forecast = fetch_forecast(geo["lat"], geo["lon"])

        except requests.HTTPError as e:
            error = f"API error: {e}"
        except Exception as e:
            error = f"Something went wrong: {e}"

    saved_queries = Session().query(WeatherQuery).all()
    return render_template("index.html", query=query, place=place, weather=weather, forecast=forecast, error=error, geo_lat=geo["lat"] if geo else None,
    geo_lon=geo["lon"] if geo else None)

@app.route("/save", methods=["POST"])
def save_weather():
    session = Session()

    # Get form data
    location_name = request.form["location_name"]
    lat = float(request.form["lat"])
    lon = float(request.form["lon"])
    start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
    end_date = datetime.strptime(request.form["end_date"], "%Y-%m-%d").date()

    # Create new WeatherQuery
    query_entry = WeatherQuery(
        location_name=location_name,
        lat=lat,
        lon=lon,
        start_date=start_date,
        end_date=end_date
    )
    session.add(query_entry)
    session.commit()

    session.close()
    return redirect(url_for("view_saved"))

@app.route("/saved")
def view_saved():
    session = Session()
    queries = session.query(WeatherQuery).all()
    session.close()
    return render_template("saved.html", queries=queries)

@app.route("/delete/<int:query_id>", methods=["POST"])
def delete_weather(query_id):
    session = Session()
    query = session.query(WeatherQuery).get(query_id)
    if query:
        session.delete(query)
        session.commit()
    session.close()
    return redirect(url_for("view_saved"))

@app.route("/edit/<int:query_id>", methods=["GET"])
def edit_weather(query_id):
    session = Session()
    query_entry = session.query(WeatherQuery).get(query_id)
    session.close()

    if not query_entry:
        return "Weather query not found!", 404

    return render_template("edit.html", query=query_entry)

@app.route("/update/<int:query_id>", methods=["GET", "POST"])
def update_weather(query_id):
    session = Session()
    query = session.query(WeatherQuery).get(query_id)

    if request.method == "POST":
        # Update with form data
        query.location_name = request.form["location_name"]
        query.lat = float(request.form["lat"])
        query.lon = float(request.form["lon"])
        query.start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
        query.end_date = datetime.strptime(request.form["end_date"], "%Y-%m-%d").date()

        session.commit()
        session.close()
        return redirect(url_for("view_saved"))

    # If GET, show the edit form
    session.close()
    return render_template("edit.html", query=query)


if __name__ == "__main__":
    app.run(debug=True)
