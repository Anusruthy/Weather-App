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
from flask import Flask, render_template, request, url_for, redirect, jsonify, Response
from dotenv import load_dotenv
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import csv
import io
import json
import dicttoxml

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
    lat = request.args.get("lat")
    lon = request.args.get("lon")

    query = session.query(WeatherQuery)

    if lat and lon:
        try:
            query = query.filter(
                (WeatherQuery.lat == float(lat)) &
                (WeatherQuery.lon == float(lon))
            )
        except ValueError:
            pass  # if not valid numbers, ignore

    queries = query.all()
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

@app.route("/api/weather", methods=["GET"])
def api_weather():
    session = Session()

    # Get filter parameters from query string
    location_filter = request.args.get("location", "").strip().lower()
    start_date_filter = request.args.get("start_date", "").strip()
    end_date_filter = request.args.get("end_date", "").strip()

    query = session.query(WeatherQuery)

    # Filter by location name if provided
    if location_filter:
        query = query.filter(WeatherQuery.location_name.ilike(f"%{location_filter}%"))

    # Filter by start and end dates if provided
    if start_date_filter:
        try:
            start_dt = datetime.strptime(start_date_filter, "%Y-%m-%d").date()
            query = query.filter(WeatherQuery.start_date >= start_dt)
        except ValueError:
            pass  # Ignore invalid date format

    if end_date_filter:
        try:
            end_dt = datetime.strptime(end_date_filter, "%Y-%m-%d").date()
            query = query.filter(WeatherQuery.end_date <= end_dt)
        except ValueError:
            pass

    queries = query.all()

    # Convert to JSON-serializable format
    data = [
        {
            "id": q.id,
            "location_name": q.location_name,
            "lat": q.lat,
            "lon": q.lon,
            "start_date": q.start_date.strftime("%Y-%m-%d"),
            "end_date": q.end_date.strftime("%Y-%m-%d")
        }
        for q in queries
    ]
    
    session.close()
    return jsonify(data)

@app.route("/export_weather")
def export_weather():
    export_format = request.args.get("format", "csv").lower()
    location_filter = request.args.get("location", "").strip().lower()
    start_date_filter = request.args.get("start_date", "").strip()
    end_date_filter = request.args.get("end_date", "").strip()
    lat_filter = request.args.get("lat")
    lon_filter = request.args.get("lon")

    session = Session()
    query = session.query(WeatherQuery)

    # Apply filters
    if location_filter:
        query = query.filter(WeatherQuery.location_name.ilike(f"%{location_filter}%"))
    if start_date_filter:
        try:
            start_dt = datetime.strptime(start_date_filter, "%Y-%m-%d").date()
            query = query.filter(WeatherQuery.start_date >= start_dt)
        except ValueError:
            pass
    if end_date_filter:
        try:
            end_dt = datetime.strptime(end_date_filter, "%Y-%m-%d").date()
            query = query.filter(WeatherQuery.end_date <= end_dt)
        except ValueError:
            pass

    # 👉 Add this block for lat/lon filtering
    if lat_filter and lon_filter:
        try:
            query = query.filter(
                (WeatherQuery.lat == float(lat_filter)) &
                (WeatherQuery.lon == float(lon_filter))
            )
        except ValueError:
            pass

    queries = query.all()
    session.close()

    # Convert to list of dicts
    data = [
        {
            "id": q.id,
            "location_name": q.location_name,
            "lat": q.lat,
            "lon": q.lon,
            "start_date": q.start_date.strftime("%Y-%m-%d"),
            "end_date": q.end_date.strftime("%Y-%m-%d"),
        }
        for q in queries
    ]

    if not data:
        return Response("No data found for given filters.", mimetype="text/plain")

    # Export logic
    if export_format == "json":
        return Response(json.dumps(data, indent=4), mimetype="application/json")
    elif export_format == "xml":
        xml_data = dicttoxml.dicttoxml(data, custom_root='weather_queries', attr_type=False)
        return Response(xml_data, mimetype="application/xml")
    else:  # default CSV
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        return Response(output.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment;filename=weather_queries.csv"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
