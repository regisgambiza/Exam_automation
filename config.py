import os
from dotenv import load_dotenv
import logging

REQUIRED_VARS = [
    "EXAM_USERNAME",
    "EXAM_PASSWORD",
    "BASE_URL",
    "EXAM_URL",
    "TESSERACT_PATH",
    "MODULE_NAME",
    "MAX_ATTEMPTS",
    "PICS_DIR",
    "KEEP_IMAGES"
]

def load_config() -> dict:
    """Load and validate environment variables, returning a configuration dictionary."""
    load_dotenv()
    config = {}
    for var in REQUIRED_VARS:
        value = os.getenv(var)
        if value is None:
            raise ValueError(f"Missing required environment variable: {var}")
        config[var] = value
    # Ensure pics directory exists
    pics_dir = config["PICS_DIR"]
    os.makedirs(pics_dir, exist_ok=True)
    return config
    """Load and validate environment variables, returning a configuration dictionary."""