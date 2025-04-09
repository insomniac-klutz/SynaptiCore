import sys
import os
from dotenv import load_dotenv
import snowflake.connector

# Add the parent directory to the path
def add_dir_to_path(dirs):
    parent_dir = os.path.normpath(os.path.join(dirs.split("SynaptiCore")[0], "SynaptiCore"))
    sys.path.append(parent_dir)

# Load env file using dotenv find and load with override true
def load_env_file():
    load_dotenv(override=True)

def create_connection():
        
        DB_CREDS = {
            "user": os.getenv("SNOWFLAKE_DB_USER"),
            "password": os.getenv("SNOWFLAKE_DB_PASSWORD"),
            "account": os.getenv("SNOWFLAKE_DB_ACCOUNT"),
            "warehouse": os.getenv("SNOWFLAKE_DB_WAREHOUSE"),
            "database": os.getenv("SNOWFLAKE_DB_DBNAME"),
            "role": os.getenv("SNOWFLAKE_DB_ROLE"),
            "host":os.getenv("SNOWFLAKE_DB_HOST")
        }

        return snowflake.connector.connect(**DB_CREDS)
