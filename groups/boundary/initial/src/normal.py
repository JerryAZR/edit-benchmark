"""Configuration and utilities for the boundary test module."""

import os

DEBUG = os.environ.get("DEBUG", "0") == "1"

host = "localhost"
port = 8080


def greet(name: str) -> str:
    return f"Hello, {name}!"


def farewell(name: str) -> str:
    return f"Goodbye, {name}!"


if __name__ == "__main__":
    print(greet("World"))
