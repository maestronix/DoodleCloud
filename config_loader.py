import os

def load_config():
    config = {}

    # First, try to load from config.env file
    if os.path.exists("config.env"):
        with open("config.env", "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    config[key] = value

    # Override with environment variables if they exist (for Docker)
    env_keys = ["INSTA_USER", "INSTA_PASS", "DB_HOST", "DB_NAME", "DB_USER", "DB_PASS", "DB_PORT"]
    for key in env_keys:
        if key in os.environ:
            config[key] = os.environ[key]

    return config

# Load once when imported
CONF = load_config()