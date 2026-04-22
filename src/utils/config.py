import os
import yaml
from pathlib import Path

def load_config():
    # Determine the environment, default to 'local'
    env = os.environ.get("ENV", "local")
    
    # Path to the config directory
    config_dir = Path(__file__).resolve().parent.parent.parent / "config"
    config_file = config_dir / f"{env}.yaml"
    
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
        
    with open(config_file, "r") as f:
        config = yaml.safe_load(f)
        
    return config

config = load_config()