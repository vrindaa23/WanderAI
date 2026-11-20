"""
WanderPulse - AI Smart Travel Recommendation System
====================================================
Uses google.generativeai SDK with Gemini API.
Includes:
  - Candidate city pre-filtering from worldcities.csv (Domestic vs International strict filtering).
  - Parallel live API enrichment with ThreadPoolExecutor (OpenWeatherMap + Google Places).
  - Strict geographic system prompts to guarantee Domestic vs International compliance.
"""

import io
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import google.generativeai as genai
import pandas as pd
import requests
from flask import Flask, jsonify, render_template, request

# ── Windows UTF-8 fix: prevents emoji print() crash on cp1252 consoles ────────
if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# =============================================================================
#  CONFIGURATION
# =============================================================================
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY",  "AIzaSyBh796aqtgIn4AURrefs35c2MmO6CUz8NY")
WEATHER_API_KEY = os.environ.get("OWM_API_KEY",     "38d9e1b4b6915a1211ffe40920ddc075")
PLACES_API_KEY  = os.environ.get("PLACES_API_KEY",  "")   # optional for live photos/ratings

genai.configure(api_key=GEMINI_API_KEY)

# Gemini model fallback chain (prefer gemini-1.5-flash for sub-second latency if available)
GEMINI_MODELS = [
    "gemini-1.5-flash",      # optimized for speed
    "gemini-3.6-flash",      # confirmed active on this key
    "gemini-flash-latest",   # alias fallback
    "gemini-2.5-flash",      # fallback
]

# External API URLs
OWM_BASE       = "https://api.openweathermap.org/data/2.5/weather"
PLACES_NEARBY   = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
PLACES_DETAILS  = "https://maps.googleapis.com/maps/api/place/details/json"
PLACES_PHOTO    = "https://maps.googleapis.com/maps/api/place/photo"

# =============================================================================
#  FLASK APP
# =============================================================================
app = Flask(__name__)

# =============================================================================
#  GEMINI API HELPER
# =============================================================================
def call_gemini_json(system_prompt: str, user_prompt: str) -> str:
    """
    Call Gemini with JSON-mode enabled:
        generation_config={"response_mime_type": "application/json"}
    Tries each model in GEMINI_MODELS; raises RuntimeError if all fail.
    """
    full_prompt = f"{system_prompt}\n\n{user_prompt}".strip() if system_prompt else user_prompt.strip()
    last_error: Optional[Exception] = None

    for model_name in GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config={"response_mime_type": "application/json"},
            )
            response = model.generate_content(full_prompt)
            print(f"[Gemini] OK — model: {model_name}")
            return response.text
        except Exception as exc:
            print(f"[Gemini] Model '{model_name}' failed: {exc}")
            last_error = exc
            continue

    raise RuntimeError(
        f"All Gemini models failed. Last error: {last_error}. "
        "Check your API key, quota, or network connection."
    )


def clean_json_text(text: str) -> str:
    """Strip markdown codeblock wrappers."""
    s = text.strip()
    s = re.sub(r"^```json\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"^```\s*",     "", s, flags=re.MULTILINE)
    s = re.sub(r"\s*```$",     "", s, flags=re.MULTILINE)
    return s.strip()

# =============================================================================
#  WORLDCITIES CSV — Filtering & Lat/Lng source
# =============================================================================
_cities_df: Optional[pd.DataFrame] = None


def _load_cities() -> pd.DataFrame:
    global _cities_df
    if _cities_df is not None:
        return _cities_df
    csv_path = os.path.join(os.path.dirname(__file__), "worldcities.csv")
    try:
        df = pd.read_csv(csv_path, encoding="utf-8", on_bad_lines="skip")
        df.columns = [c.lower().strip() for c in df.columns]
        if "lng" not in df.columns:
            if "lon" in df.columns:
                df = df.rename(columns={"lon": "lng"})
            elif "longitude" in df.columns:
                df = df.rename(columns={"longitude": "lng", "latitude": "lat"})
        col = "city_ascii" if "city_ascii" in df.columns else "city"
        df["_search"] = df[col].astype(str).str.lower().str.strip()
        df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
        df["lng"] = pd.to_numeric(df["lng"], errors="coerce")
        df["population"] = pd.to_numeric(df["population"], errors="coerce").fillna(0)
        df = df.dropna(subset=["lat", "lng"])
        _cities_df = df
        print(f"[CSV] worldcities.csv loaded — {len(df):,} cities")
    except Exception as exc:
        print(f"[CSV] Load error: {exc}")
        _cities_df = pd.DataFrame(columns=["_search", "lat", "lng", "country", "city", "population"])
    return _cities_df


_load_cities()   # Eager load at startup


def get_city_coords(city_name: str) -> Optional[Dict[str, float]]:
    """Return {'lat', 'lng'} from CSV for a city, or None if not found."""
    df = _load_cities()
    if df.empty:
        return None
    key = city_name.strip().lower()
    match = df[df["_search"] == key]
    if match.empty:
        match = df[df["_search"].str.startswith(key[:5])]
    if match.empty:
        return None
    row = match.iloc[0]
    return {"lat": float(row["lat"]), "lng": float(row["lng"])}


def get_candidate_cities(dest_type: str, user_country: str = "India", limit: int = 15) -> List[str]:
    """
    Strictly filter candidate cities from worldcities.csv:
      - Domestic  → ONLY cities whose country matches user_country.
      - International → ONLY cities whose country does NOT match user_country.

    Uses stratified sampling (top-1000 by population then random sample) so the
    result is geographically diverse instead of always returning the same megacities.
    Returns `limit` city strings in "City (Country)" format.
    """
    df = _load_cities()
    if df.empty:
        return []

    uc = user_country.strip().lower()
    df_copy = df.copy()
    df_copy["country_clean"] = df_copy["country"].astype(str).str.strip().str.lower()

    is_domestic = dest_type.strip().lower() == "domestic"

    if is_domestic:
        # ── Include ONLY the user's home country ───────────────────────────
        filtered = df_copy[df_copy["country_clean"] == uc]
        if filtered.empty:                          # fuzzy fallback
            filtered = df_copy[df_copy["country_clean"].str.contains(uc, na=False)]
    else:
        # ── Exclude the user's home country STRICTLY ───────────────────────
        filtered = df_copy[df_copy["country_clean"] != uc]
        # Also hard-block common aliases (e.g. "india" spelled differently)
        for alias in [uc, "india", "bharat"]:
            filtered = filtered[~filtered["country_clean"].str.contains(alias, na=False)]

    if filtered.empty:
        filtered = df_copy

    # Stratified diverse sample: take top-1000 by population, then random-sample `limit`
    pool = filtered.sort_values(by="population", ascending=False).head(1000)
    sample_n = min(limit, len(pool))
    sampled = pool.sample(n=sample_n, random_state=None)   # random_state=None → different each call

    col = "city_ascii" if "city_ascii" in sampled.columns else "city"
    return [f"{row[col]} ({row['country']})" for _, row in sampled.iterrows()]

# =============================================================================
#  OPENWEATHERMAP  — real-time weather
# =============================================================================
_WEATHER_EMOJI: Dict[str, str] = {
    "Clear": "☀️", "Clouds": "☁️", "Rain": "🌧️", "Drizzle": "🌦️",
    "Thunderstorm": "⛈️", "Snow": "❄️", "Mist": "🌫️",
    "Haze": "🌫️", "Fog": "🌫️", "Smoke": "🌫️",
    "Dust": "🌪️", "Sand": "🌪️", "Tornado": "🌪️", "Squall": "🌬️",
}


def fetch_live_weather(lat: float, lng: float) -> Dict[str, Any]:
    """Fetch current weather from OpenWeatherMap."""
    try:
        r = requests.get(
            OWM_BASE,
            params={"lat": lat, "lon": lng, "appid": WEATHER_API_KEY, "units": "metric"},
            timeout=5,
        )
        r.raise_for_status()
        d    = r.json()
        main = d.get("main", {})
        wind = d.get("wind", {})
        w    = (d.get("weather") or [{}])[0]
        cond = w.get("main", "N/A")
        icon = w.get("icon", "")
        return {
            "temp":        round(main.get("temp", 0), 1),
            "feels_like":  round(main.get("feels_like", 0), 1),
            "humidity":    main.get("humidity", 0),
            "condition":   cond,
            "description": w.get("description", "").capitalize(),
            "wind_speed":  round(wind.get("speed", 0), 1),
            "emoji":       _WEATHER_EMOJI.get(cond, "🌤️"),
            "icon_url":    f"https://openweathermap.org/img/wn/{icon}@2x.png" if icon else "",
            "source":      "OpenWeatherMap Live",
        }
    except Exception as exc:
        print(f"[OWM] Error at ({lat},{lng}): {exc}")
        return {
            "temp": "N/A", "feels_like": "N/A", "humidity": "N/A",
            "condition": "Unavailable",
            "description": "Live weather temporarily unavailable",
            "wind_speed": "N/A", "emoji": "🌤️", "icon_url": "",
            "source": "Fallback",
        }

# =============================================================================
#  GOOGLE PLACES API
# =============================================================================
def _photo_url(ref: str, width: int = 400) -> str:
    return f"{PLACES_PHOTO}?maxwidth={width}&photo_reference={ref}&key={PLACES_API_KEY}"


def fetch_place_live_data(name: str, lat: float, lng: float) -> Dict[str, Any]:
    """Search Google Places Nearby for an attraction."""
    if not PLACES_API_KEY:
        return {
            "rating": None, "open_now": None,
            "address": "", "photo_url": "",
            "source": "Places key not configured",
        }
    try:
        sr = requests.get(
            PLACES_NEARBY,
            params={
                "location": f"{lat},{lng}", "radius": 1500,
                "keyword": name, "key": PLACES_API_KEY,
            },
            timeout=5,
        )
        sr.raise_for_status()
        results = sr.json().get("results", [])
        if not results:
            return {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "No result"}

        p        = results[0]
        place_id = p.get("place_id", "")
        rating   = p.get("rating")
        photos   = p.get("photos", [])
        open_now = (p.get("opening_hours") or {}).get("open_now")
        address  = p.get("vicinity", "")
        photo    = _photo_url(photos[0]["photo_reference"]) if photos else ""

        return {"rating": rating, "open_now": open_now, "address": address,
                "photo_url": photo, "source": "Google Places Live"}
    except Exception as exc:
        print(f"[Places] Error for '{name}': {exc}")
        return {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Places error"}

# =============================================================================
#  PARALLEL ENRICHMENT PIPELINE WITH ThreadPoolExecutor
# =============================================================================
def enrich_destination(dest: Dict[str, Any]) -> Dict[str, Any]:
    """
    Attach live OWM weather and Google Places data to a destination dict.
    Weather + all attraction Places calls run concurrently via ThreadPoolExecutor.
    """
    coords = dest.get("coordinates") or {}
    lat    = float(coords.get("lat", 0) or 0)
    lng    = float(coords.get("lng", 0) or 0)

    csv_coords = get_city_coords(dest.get("name", ""))
    if csv_coords:
        lat = csv_coords["lat"]
        lng = csv_coords["lng"]
        dest["coordinates"] = {"lat": lat, "lng": lng}

    with ThreadPoolExecutor(max_workers=6) as executor:
        weather_future = executor.submit(fetch_live_weather, lat, lng)
        places_futures = {}
        attractions    = dest.get("attractions", [])
        for att in attractions:
            a_lat = float((att.get("coordinates") or {}).get("lat", lat) or lat)
            a_lng = float((att.get("coordinates") or {}).get("lng", lng) or lng)
            places_futures[executor.submit(fetch_place_live_data, att.get("name", ""), a_lat, a_lng)] = att

        try:
            dest["live_weather"] = weather_future.result(timeout=6)
        except Exception as exc:
            print(f"[OWM] Timeout/error: {exc}")
            dest["live_weather"] = {
                "temp": "N/A", "feels_like": "N/A", "humidity": "N/A",
                "condition": "Unavailable", "description": "Weather unavailable",
                "wind_speed": "N/A", "emoji": "🌤️", "icon_url": "", "source": "Fallback"
            }

        for future, att in places_futures.items():
            try:
                att["live_places"] = future.result(timeout=6)
            except Exception as exc:
                print(f"[Places] Timeout/error: {exc}")
                att["live_places"] = {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Timeout"}

    return dest

# =============================================================================
#  FALLBACK SAMPLE DATA  (one set per trip type — keyed by dest_type)
# =============================================================================

# ── DOMESTIC fallback (India) ─────────────────────────────────────────────────
_FALLBACK_DOMESTIC: List[Dict] = [
    {
        "id": "fb-dom-1",
        "name": "Manali",
        "location": "Himachal Pradesh, India",
        "matchPercentage": 91,
        "pitch": "A stunning Himalayan escape where adventure meets serenity among snow-capped peaks and cedar forests.",
        "coordinates": {"lat": 32.2396, "lng": 77.1887},
        "weatherInsight": "Best October–June. Cool summers (15–25°C) and snowy winters.",
        "budgetSplit": {"transport": 25, "stay": 35, "food": 20, "activities": 20},
        "live_weather": {
            "temp": "N/A", "feels_like": "N/A", "humidity": "N/A",
            "condition": "Sample Data", "description": "Live data unavailable — AI offline mode",
            "wind_speed": "N/A", "emoji": "🏔️", "icon_url": "", "source": "Fallback",
        },
        "attractions": [
            {"name": "Rohtang Pass", "category": "Nature / Adventure",
             "coordinates": {"lat": 32.3715, "lng": 77.2454},
             "description": "High-altitude pass with snow views and adventure sports.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
            {"name": "Solang Valley", "category": "Adventure",
             "coordinates": {"lat": 32.3199, "lng": 77.1516},
             "description": "Famous for skiing, paragliding, and zorbing.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
            {"name": "Hadimba Temple", "category": "Historical / Culture",
             "coordinates": {"lat": 32.2390, "lng": 77.1807},
             "description": "Ancient 16th-century wooden temple set inside cedar forest.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
        ],
        "localDelicacies": [
            {"name": "Siddu", "type": "Local Bread", "description": "Steamed wheat bread stuffed with walnuts & poppy seeds."},
            {"name": "Trout Fish Curry", "type": "Seafood", "description": "Fresh river trout slow-cooked in local spices."},
        ],
        "itinerary": [
            {"day": 1, "title": "Arrival & Mall Road", "activities": ["Morning: Check in", "Afternoon: Mall Road", "Evening: Beas River walk"]},
            {"day": 2, "title": "Rohtang Adventure", "activities": ["Morning: Drive to Rohtang Pass", "Afternoon: Snow sports", "Evening: Bonfire dinner"]},
            {"day": 3, "title": "Culture & Valley", "activities": ["Morning: Hadimba Temple", "Afternoon: Solang Valley paragliding", "Evening: Stargazing"]},
        ],
        "packingChecklist": [
            {"item": "Thermal Inner Wear", "category": "Clothing", "packed": False},
            {"item": "Winter Jacket", "category": "Clothing", "packed": False},
            {"item": "Snow Boots", "category": "Footwear", "packed": False},
            {"item": "Sunscreen SPF 50+", "category": "Essentials", "packed": False},
        ],
    },
    {
        "id": "fb-2",
        "name": "Goa",
        "location": "Goa, India",
        "matchPercentage": 87,
        "pitch": "Sun-soaked golden beaches, Portuguese heritage lanes, and vibrant coastal night vibes.",
        "coordinates": {"lat": 15.2993, "lng": 74.1240},
        "weatherInsight": "November–February is peak season with clear skies and 28°C weather.",
        "budgetSplit": {"transport": 20, "stay": 40, "food": 25, "activities": 15},
        "live_weather": {
            "temp": "N/A", "feels_like": "N/A", "humidity": "N/A",
            "condition": "Sample Data", "description": "Live data unavailable — AI offline mode",
            "wind_speed": "N/A", "emoji": "🏖️", "icon_url": "", "source": "Fallback",
        },
        "attractions": [
            {"name": "Baga Beach", "category": "Beaches / Nightlife",
             "coordinates": {"lat": 15.5531, "lng": 73.7517},
             "description": "Iconic beach with water sports and vibrant shacks.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
            {"name": "Basilica of Bom Jesus", "category": "Historical",
             "coordinates": {"lat": 15.5009, "lng": 73.9117},
             "description": "UNESCO World Heritage 16th-century church.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
            {"name": "Dudhsagar Falls", "category": "Nature",
             "coordinates": {"lat": 15.3144, "lng": 74.3144},
             "description": "Spectacular four-tiered 310m waterfall.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
        ],
        "localDelicacies": [
            {"name": "Fish Curry Rice", "type": "Local Dish", "description": "Goa's soul food — coconut fish curry with rice."},
            {"name": "Prawn Balchao", "type": "Street Food", "description": "Fiery Goan prawn pickle with soft pao bread."},
        ],
        "itinerary": [
            {"day": 1, "title": "North Goa Beaches", "activities": ["Morning: Calangute & Baga", "Afternoon: Water sports", "Evening: Sunset at Anjuna"]},
            {"day": 2, "title": "Heritage Walk", "activities": ["Morning: Old Goa Churches", "Afternoon: Fontainhas Quarter", "Evening: Mandovi River cruise"]},
            {"day": 3, "title": "Nature & Spice", "activities": ["Morning: Dudhsagar jeep safari", "Afternoon: Spice plantation tour", "Evening: Beach dinner"]},
        ],
        "packingChecklist": [
            {"item": "Swimwear", "category": "Clothing", "packed": False},
            {"item": "Light Cotton Shirts", "category": "Clothing", "packed": False},
            {"item": "Sunscreen SPF 50+", "category": "Essentials", "packed": False},
        ],
    },
    {
        "id": "fb-3",
        "name": "Jaipur",
        "location": "Rajasthan, India",
        "matchPercentage": 84,
        "pitch": "The Pink City enchants with royal Rajput forts, lively bazaars, and legendary heritage culture.",
        "coordinates": {"lat": 26.9124, "lng": 75.7873},
        "weatherInsight": "October–March is ideal with pleasant 18–28°C days.",
        "budgetSplit": {"transport": 20, "stay": 35, "food": 20, "activities": 25},
        "live_weather": {
            "temp": "N/A", "feels_like": "N/A", "humidity": "N/A",
            "condition": "Sample Data", "description": "Live data unavailable — AI offline mode",
            "wind_speed": "N/A", "emoji": "🏰", "icon_url": "", "source": "Fallback",
        },
        "attractions": [
            {"name": "Amber Fort", "category": "Historical / Culture",
             "coordinates": {"lat": 26.9855, "lng": 75.8513},
             "description": "Hilltop fort with intricate mirror mosaics.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
            {"name": "Hawa Mahal", "category": "Historical",
             "coordinates": {"lat": 26.9239, "lng": 75.8267},
             "description": "Iconic Palace of Winds with 953 lattice windows.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
            {"name": "City Palace", "category": "Museum",
             "coordinates": {"lat": 26.9258, "lng": 75.8237},
             "description": "Royal palace complex housing galleries and courtyards.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
        ],
        "localDelicacies": [
            {"name": "Dal Baati Churma", "type": "Traditional", "description": "Baked wheat balls served with lentils and sweet churma."},
            {"name": "Ghewar", "type": "Dessert", "description": "Traditional disc sweet soaked in syrup and topped with rabri."},
        ],
        "itinerary": [
            {"day": 1, "title": "Forts & Palaces", "activities": ["Morning: Amber Fort", "Afternoon: Hawa Mahal & City Palace", "Evening: Light Show"]},
            {"day": 2, "title": "Bazaars & Culture", "activities": ["Morning: Jantar Mantar", "Afternoon: Johari Bazaar", "Evening: Chokhi Dhani dinner"]},
            {"day": 3, "title": "Sunrise & Flavors", "activities": ["Morning: Nahargarh sunrise", "Afternoon: Heritage walk", "Evening: Rooftop dinner"]},
        ],
        "packingChecklist": [
            {"item": "Cotton Kurta", "category": "Clothing", "packed": False},
            {"item": "Sunglasses", "category": "Essentials", "packed": False},
            {"item": "Walking Shoes", "category": "Footwear", "packed": False},
        ],
    },
]

# ── INTERNATIONAL fallback (Paris / Dubai / Bali) ─────────────────────────────
_FALLBACK_INTERNATIONAL: List[Dict] = [
    {
        "id": "fb-int-1",
        "name": "Paris",
        "location": "Île-de-France, France",
        "matchPercentage": 93,
        "pitch": "The City of Light dazzles with world-class museums, romantic riverbanks, and haute cuisine on every corner.",
        "coordinates": {"lat": 48.8566, "lng": 2.3522},
        "weatherInsight": "Best April–June and Sep–Oct. Mild 15–22°C with long golden evenings.",
        "budgetSplit": {"transport": 30, "stay": 40, "food": 20, "activities": 10},
        "live_weather": {
            "temp": "N/A", "feels_like": "N/A", "humidity": "N/A",
            "condition": "Sample Data", "description": "Live data unavailable — AI offline mode",
            "wind_speed": "N/A", "emoji": "🗼", "icon_url": "", "source": "Fallback",
        },
        "attractions": [
            {"name": "Eiffel Tower", "category": "Landmark",
             "coordinates": {"lat": 48.8584, "lng": 2.2945},
             "description": "Iconic iron lattice tower offering panoramic city views.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
            {"name": "Louvre Museum", "category": "Culture / Art",
             "coordinates": {"lat": 48.8606, "lng": 2.3376},
             "description": "World's largest art museum housing the Mona Lisa.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
            {"name": "Montmartre", "category": "Culture / Neighbourhood",
             "coordinates": {"lat": 48.8867, "lng": 2.3431},
             "description": "Bohemian hilltop quarter with Sacré-Cœur and artist studios.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
        ],
        "localDelicacies": [
            {"name": "Croissant", "type": "Bakery", "description": "Flaky buttery pastry best enjoyed warm from a boulangerie."},
            {"name": "Steak Frites", "type": "Main Course", "description": "Classic bistro steak with crispy golden fries."},
        ],
        "itinerary": [
            {"day": 1, "title": "Iconic Landmarks", "activities": ["Morning: Eiffel Tower", "Afternoon: Seine River cruise", "Evening: Champs-Élysées stroll"]},
            {"day": 2, "title": "Art & Culture", "activities": ["Morning: Louvre Museum", "Afternoon: Musée d'Orsay", "Evening: Dinner in Le Marais"]},
            {"day": 3, "title": "Neighbourhoods", "activities": ["Morning: Montmartre & Sacré-Cœur", "Afternoon: Saint-Germain cafés", "Evening: Jazz bar"]},
        ],
        "packingChecklist": [
            {"item": "Light Trench Coat", "category": "Clothing", "packed": False},
            {"item": "Comfortable Walking Shoes", "category": "Footwear", "packed": False},
            {"item": "Universal Power Adapter", "category": "Electronics", "packed": False},
        ],
    },
    {
        "id": "fb-int-2",
        "name": "Dubai",
        "location": "Emirate of Dubai, UAE",
        "matchPercentage": 90,
        "pitch": "A futuristic skyline rising from the desert — world records, luxury malls, and golden sand dunes all in one city.",
        "coordinates": {"lat": 25.2048, "lng": 55.2708},
        "weatherInsight": "Best November–March with warm sunny 22–28°C days and cool evenings.",
        "budgetSplit": {"transport": 20, "stay": 45, "food": 20, "activities": 15},
        "live_weather": {
            "temp": "N/A", "feels_like": "N/A", "humidity": "N/A",
            "condition": "Sample Data", "description": "Live data unavailable — AI offline mode",
            "wind_speed": "N/A", "emoji": "🏙️", "icon_url": "", "source": "Fallback",
        },
        "attractions": [
            {"name": "Burj Khalifa", "category": "Landmark",
             "coordinates": {"lat": 25.1972, "lng": 55.2744},
             "description": "World's tallest building with observation decks at 124th & 148th floors.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
            {"name": "Dubai Desert Safari", "category": "Adventure",
             "coordinates": {"lat": 24.9500, "lng": 55.4500},
             "description": "Dune bashing, camel rides, and traditional Bedouin camp dinner.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
            {"name": "Dubai Mall & Aquarium", "category": "Shopping / Entertainment",
             "coordinates": {"lat": 25.1985, "lng": 55.2796},
             "description": "World's largest mall featuring a 10-million-litre walk-through aquarium.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
        ],
        "localDelicacies": [
            {"name": "Shawarma", "type": "Street Food", "description": "Spit-roasted meat wrap served with garlic sauce — ubiquitous and delicious."},
            {"name": "Luqaimat", "type": "Dessert", "description": "Crispy fried dumplings drizzled with date syrup and sesame."},
        ],
        "itinerary": [
            {"day": 1, "title": "Sky & Skyline", "activities": ["Morning: Burj Khalifa At The Top", "Afternoon: Dubai Fountain show", "Evening: Dubai Frame"]},
            {"day": 2, "title": "Desert & Culture", "activities": ["Morning: Old Dubai & Gold Souk", "Afternoon: Dubai Museum", "Evening: Desert Safari & BBQ"]},
            {"day": 3, "title": "Beaches & Luxury", "activities": ["Morning: Jumeirah Beach", "Afternoon: Palm Jumeirah Monorail", "Evening: Marina Walk dinner"]},
        ],
        "packingChecklist": [
            {"item": "Light Linen Shirts", "category": "Clothing", "packed": False},
            {"item": "Sunscreen SPF 50+", "category": "Essentials", "packed": False},
            {"item": "Sunglasses", "category": "Essentials", "packed": False},
        ],
    },
    {
        "id": "fb-int-3",
        "name": "Bali",
        "location": "Bali Province, Indonesia",
        "matchPercentage": 88,
        "pitch": "Tropical paradise of emerald rice terraces, sacred temples, surf breaks, and affordable luxury spas.",
        "coordinates": {"lat": -8.3405, "lng": 115.0920},
        "weatherInsight": "Best April–October (dry season). Warm 27–32°C with low humidity and clear skies.",
        "budgetSplit": {"transport": 25, "stay": 35, "food": 15, "activities": 25},
        "live_weather": {
            "temp": "N/A", "feels_like": "N/A", "humidity": "N/A",
            "condition": "Sample Data", "description": "Live data unavailable — AI offline mode",
            "wind_speed": "N/A", "emoji": "🌴", "icon_url": "", "source": "Fallback",
        },
        "attractions": [
            {"name": "Tegallalang Rice Terraces", "category": "Nature",
             "coordinates": {"lat": -8.4312, "lng": 115.2779},
             "description": "Stunning UNESCO-recognised stepped rice paddies in lush jungle.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
            {"name": "Uluwatu Temple", "category": "Historical / Culture",
             "coordinates": {"lat": -8.8292, "lng": 115.0849},
             "description": "Clifftop sea temple with Kecak fire dance at sunset.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
            {"name": "Seminyak Beach", "category": "Beaches / Nightlife",
             "coordinates": {"lat": -8.6907, "lng": 115.1571},
             "description": "Chic beach strip with world-class surf, beach clubs, and sunset cocktails.",
             "live_places": {"rating": None, "open_now": None, "address": "", "photo_url": "", "source": "Fallback"}},
        ],
        "localDelicacies": [
            {"name": "Nasi Goreng", "type": "Main Course", "description": "Indonesia's famous wok-fried rice with egg, kecap manis, and prawn crackers."},
            {"name": "Babi Guling", "type": "Traditional", "description": "Slow-roasted suckling pig with crispy skin — Bali's ceremonial feast."},
        ],
        "itinerary": [
            {"day": 1, "title": "Arrival & Ubud", "activities": ["Morning: Tegallalang terraces", "Afternoon: Monkey Forest", "Evening: Traditional Kecak dance"]},
            {"day": 2, "title": "Temples & Cliffs", "activities": ["Morning: Tanah Lot Temple", "Afternoon: Uluwatu cliffs", "Evening: Jimbaran seafood dinner"]},
            {"day": 3, "title": "Beach & Surf", "activities": ["Morning: Surf lesson at Kuta", "Afternoon: Seminyak beach clubs", "Evening: Rooftop sunset bar"]},
        ],
        "packingChecklist": [
            {"item": "Sarong (for temples)", "category": "Clothing", "packed": False},
            {"item": "Reef-safe Sunscreen", "category": "Essentials", "packed": False},
            {"item": "Insect Repellent", "category": "Medical", "packed": False},
        ],
    },
]


def get_fallback(dest_type: str) -> List[Dict]:
    """Return the correct fallback dataset for the given dest_type."""
    if dest_type.strip().lower() == "domestic":
        return _FALLBACK_DOMESTIC
    return _FALLBACK_INTERNATIONAL


# Legacy alias — points to domestic for backward compatibility
FALLBACK_RECOMMENDATIONS = _FALLBACK_DOMESTIC

# =============================================================================
#  GEMINI SYSTEM PROMPT
# =============================================================================
SYSTEM_PROMPT = """
You are an expert AI Travel Planner and Concierge.
Return 3 hyper-personalized travel destination recommendations matching the user preferences.

Output ONLY a single raw JSON object with no markdown, no code fences, no preamble text.

Required JSON schema:
{
  "recommendations": [
    {
      "id": "dest-1",
      "name": "Exact City Name",
      "location": "State / Country",
      "matchPercentage": 93,
      "pitch": "Crisp 1-2 sentence pitch tailored to the user vibe.",
      "coordinates": {"lat": 12.9716, "lng": 77.5946},
      "weatherInsight": "Short climate summary (1-2 sentences).",
      "budgetSplit": {"transport": 30, "stay": 40, "food": 15, "activities": 15},
      "attractions": [
        {
          "name": "Attraction Name",
          "category": "Historical / Adventure / Nature / Culture / Nightlife / Food",
          "coordinates": {"lat": 12.975, "lng": 77.599},
          "description": "Short 1-sentence description."
        }
      ],
      "localDelicacies": [
        {"name": "Dish Name", "type": "Food / Street Food",
         "description": "Short description."}
      ],
      "itinerary": [
        {"day": 1, "title": "Day 1 Theme",
         "activities": ["Morning: Activity", "Afternoon: Activity", "Evening: Activity"]}
      ],
      "packingChecklist": [
        {"item": "Item name", "category": "Clothing / Essentials / Electronics / Medical",
         "packed": false}
      ]
    }
  ]
}

Hard rules:
1. STRICT GEOGRAPHIC RULE: Strictly respect the Domestic or International location constraint.
   - INTERNATIONAL means ZERO cities inside the user's home country. Not a single one.
   - DOMESTIC means ZERO cities outside the user's home country. Not a single one.
2. Keep overview pitch, descriptions, and weather insights concise (1-2 sentences max) to minimize response latency.
3. Coordinates MUST be geographically accurate for the chosen city.
4. Provide MINIMUM 3 attractions per destination.
5. Itinerary MUST have EXACTLY the requested number of days with concise activity bullet points.
6. Output ONLY pure valid JSON — nothing before or after it.
7. NEVER output Markdown, code fences (```), or prose explanations.
"""

# =============================================================================
#  FLASK ROUTES
# =============================================================================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/recommend", methods=["POST"])
def recommend():
    try:
        body         = request.json or {}
        dest_type    = body.get("destinationType", "Domestic")
        user_country = body.get("userCountry", "India").strip() or "India"
        budget       = body.get("budgetRange",     "Standard")
        companion    = body.get("travelCompanion", "Solo")
        vibes_raw    = body.get("vibes",           ["Relaxation"])
        vibes        = ", ".join(vibes_raw) if isinstance(vibes_raw, list) else str(vibes_raw)
        duration     = int(body.get("duration", 5))
        pace         = body.get("pace", "Relaxed")
        is_domestic  = dest_type.strip().lower() == "domestic"

        print(f"[/recommend] {companion} | {dest_type} ({user_country}) | {budget} | {vibes} | {duration}d | {pace}")

        # ── Step 1: Pre-filter candidate cities (strict geofencing) ───────────
        candidates     = get_candidate_cities(dest_type, user_country=user_country, limit=15)
        candidates_str = ", ".join(candidates) if candidates else ("Major Indian cities" if is_domestic else "Major global cities outside India")

        # ── Step 2: Build hard-constraint prompt for Gemini ───────────────────
        if is_domestic:
            geo_constraint = (
                f"CRITICAL CONSTRAINT — DOMESTIC MODE:\n"
                f"  • You MUST ONLY recommend destinations that are physically located INSIDE {user_country}.\n"
                f"  • ABSOLUTELY DO NOT suggest any city, town, or region outside {user_country}.\n"
                f"  • Violation of this rule makes the entire response unusable."
            )
        else:
            geo_constraint = (
                f"CRITICAL CONSTRAINT — INTERNATIONAL MODE:\n"
                f"  • You MUST ONLY recommend destinations that are physically located OUTSIDE {user_country}.\n"
                f"  • ABSOLUTELY DO NOT suggest ANY city inside {user_country} — this includes but is not\n"
                f"    limited to: Goa, Manali, Jaipur, Shimla, Kerala, Mumbai, Delhi, Darjeeling,\n"
                f"    Rishikesh, Munnar, Coorg, Ooty, Leh, Udaipur, Varanasi, Agra, or any other\n"
                f"    {user_country} city, state, or territory.\n"
                f"  • Choose from globally recognised international destinations such as\n"
                f"    Bali (Indonesia), Bangkok (Thailand), Tokyo (Japan), Paris (France),\n"
                f"    Dubai (UAE), Rome (Italy), Singapore, New York (USA), Maldives, etc.\n"
                f"  • Violation of this rule makes the entire response unusable."
            )

        user_prompt = f"""
{geo_constraint}

Valid candidate cities pre-filtered from database (pick ONLY from these or equivalent international cities):
{candidates_str}

User Travel Preferences:
- Home Country      : {user_country}
- Destination Scope : {dest_type}  ← ENFORCE STRICTLY
- Budget Tier       : {budget}
- Travel Companion  : {companion}
- Vibes / Interests : {vibes}
- Trip Duration     : {duration} days
- Travel Pace       : {pace}

Instructions:
1. Select EXACTLY 3 destinations. Each MUST satisfy the geographic constraint above.
2. ALL destinations must be outside {user_country} if International, inside if Domestic.
3. Keep pitches, descriptions, and activity details short and crisp (1-2 sentences max).
4. Itinerary MUST have EXACTLY {duration} day entries — no more, no less.
5. Return ONLY the JSON object — no prose, no markdown.
"""
        destinations: List[Dict]
        data_source: str

        try:
            raw_text     = call_gemini_json(SYSTEM_PROMPT, user_prompt)
            cleaned      = clean_json_text(raw_text)
            ai_result    = json.loads(cleaned)
            destinations = ai_result.get("recommendations", [])

            if not destinations:
                raise ValueError("Gemini returned an empty recommendations list.")

            # ── Post-process: sanity-check that Gemini respected the geo rule ──
            # If International but any destination has user_country in location → discard & fallback
            if not is_domestic:
                uc_lower = user_country.lower()
                violators = [
                    d for d in destinations
                    if uc_lower in (d.get("location") or "").lower()
                    or uc_lower in (d.get("name") or "").lower()
                ]
                if violators:
                    names = ", ".join(v.get("name", "?") for v in violators)
                    raise ValueError(
                        f"Gemini violated geo-constraint — returned {user_country} cities: {names}. "
                        "Switching to fallback."
                    )

            data_source = "gemini"
            print(f"[/recommend] Gemini OK — {len(destinations)} destinations")

        except Exception as gemini_err:
            print(f"[/recommend] Gemini error/geo-violation — using fallback. Reason: {gemini_err}")
            # ── FIX: Always pick the correct fallback for the selected trip type ──
            destinations = get_fallback(dest_type)
            data_source  = "fallback"

        # ── Step 3: Enrich all destinations in parallel using ThreadPoolExecutor ─
        with ThreadPoolExecutor(max_workers=max(len(destinations), 1)) as executor:
            futures = [executor.submit(enrich_destination, d) for d in destinations]
            final   = [f.result(timeout=15) for f in futures]

        return jsonify({"success": True, "data": final, "source": data_source})

    except Exception as unhandled:
        print(f"[/recommend] Unhandled error: {unhandled}")
        # ── FIX: Unhandled-error path also uses the correct type-aware fallback ──
        return jsonify({
            "success": True,
            "data":    get_fallback(dest_type),
            "source":  "fallback",
            "warning": str(unhandled),
        })


@app.route("/api/chat", methods=["POST"])
def chat():
    """AI Travel Buddy chatbot route."""
    try:
        body        = request.json or {}
        dest_name   = body.get("destinationName", "General Travel")
        context_str = body.get("context", "")[:3500]
        user_msg    = body.get("message", "").strip()

        if not user_msg:
            return jsonify({"success": False, "error": "Message cannot be empty."}), 400

        chat_prompt = f"""
You are WanderBuddy — an enthusiastic, friendly AI travel concierge.
Current destination: {dest_name}

Destination context:
{context_str}

Traveller's question: {user_msg}

Give concise, insider advice (under 150 words). Use bullet points.
"""
        try:
            raw_reply = call_gemini_json("", chat_prompt)
            try:
                parsed = json.loads(raw_reply)
                if isinstance(parsed, dict):
                    reply = (
                        parsed.get("reply")
                        or parsed.get("message")
                        or parsed.get("text")
                        or str(parsed)
                    )
                else:
                    reply = raw_reply
            except (json.JSONDecodeError, TypeError):
                reply = raw_reply

        except Exception as chat_err:
            print(f"[/chat] Gemini failed: {chat_err}")
            reply = (
                f"I'm temporarily offline! Here's a quick tip for {dest_name}: "
                "Explore local food spots and check real-time weather before head out!"
            )

        return jsonify({"success": True, "reply": str(reply).strip()})

    except Exception as exc:
        print(f"[/chat] Unhandled error: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500


# =============================================================================
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)