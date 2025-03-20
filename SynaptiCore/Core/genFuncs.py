import sys
import os
from dotenv import load_dotenv

# Add the parent directory to the path
def add_dir_to_path(dirs):
    parent_dir = os.path.normpath(os.path.join(dirs.split("SynaptiCore")[0], "SynaptiCore"))
    sys.path.append(parent_dir)

# Load env file using dotenv find and load with override true
def load_env_file():
    load_dotenv(override=True)