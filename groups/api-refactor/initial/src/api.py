"""Public API client for the weather service."""

import requests

BASE_URL = "https://api.weather.example/v1"


def get_current_weather(city):
    """Fetch current weather for a city."""
    url = f"{BASE_URL}/weather/{city}"
    response = requests.get(url)
    return response.text


def get_forecast(city, days):
    """Fetch weather forecast for a city."""
    url = f"{BASE_URL}/forecast/{city}"
    response = requests.get(url, params={"days": days})
    return response.text


def get_alerts(region):
    """Fetch active weather alerts for a region."""
    url = f"{BASE_URL}/alerts/{region}"
    response = requests.get(url)
    return response.text
