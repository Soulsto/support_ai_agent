import os
import requests
from dotenv import load_dotenv
from urllib.parse import quote

# --- CONFIGURATION ---
# Use the exact, verified information.
GAME_NAME = "MPAINW XWRIS"
TAG_LINE = "AKAP"
REGION = "europe"

# --- SCRIPT ---
print("--- Starting Minimal API Test ---")

# 1. Load the .env file from the current directory
load_dotenv()

# 2. Get the API key
api_key = os.getenv("RIOT_API_KEY")

# 3. Print the key to confirm it's being loaded correctly
#    (It will print 'None' if it's not found)
print(f"Loaded API Key: {api_key}")

if not api_key:
    print("\nERROR: RIOT_API_KEY not found in .env file. Please check the file.")
else:
    # 4. Prepare the request
    encoded_game_name = quote(GAME_NAME)
    encoded_tag_line = quote(TAG_LINE)
    
    url = f"https://{REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{encoded_game_name}/{encoded_tag_line}"
    headers = {"X-Riot-Token": api_key}
    
    print(f"\nAttempting to call URL: {url}")
    
    try:
        # 5. Make the API call
        response = requests.get(url, headers=headers)
        
        # 6. Print the results
        print(f"\n--- RESULTS ---")
        print(f"Status Code: {response.status_code}")
        print("Response Body (Text):")
        print(response.text)

    except Exception as e:
        print(f"\nAn exception occurred: {e}")