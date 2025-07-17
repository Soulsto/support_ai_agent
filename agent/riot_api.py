# In agent/riot_api.py
import requests
import os
import logging
import time
from dotenv import load_dotenv
from urllib.parse import quote

logger = logging.getLogger(__name__)

class RiotAPIClient:
    def __init__(self):
        # --- NEW: Explicitly load the .env file from the project root ---
        # This builds a path from this file's location up one level to the project root
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        dotenv_path = os.path.join(project_root, '.env')
        load_dotenv(dotenv_path=dotenv_path)
        
        self.api_key = os.getenv("RIOT_API_KEY")
        
        # We can now remove the debug print statement
        # print(f"DEBUG: API Key loaded into script: {self.api_key}")

        if not self.api_key:
            raise ValueError("RIOT_API_KEY not found. Please ensure a .env file exists in the project root.")
        
        self.headers = {"X-Riot-Token": self.api_key}
        self.session = requests.Session()
        self.rate_limit_delay = 1.5
        self.max_retries = 3

    # The _request method and all other get_... methods remain exactly the same.
    def _request(self, url: str, params: dict = None) -> dict | None:
        retries = 0
        while retries < self.max_retries:
            try:
                logger.debug(f"Making request to URL: {url}")
                logger.debug(f"With headers: {self.headers}")
                if params:
                    logger.debug(f"With params: {params}")
                response = self.session.get(url, headers=self.headers, params=params, timeout=15)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    logger.warning(f"Rate limit exceeded. Waiting {self.rate_limit_delay} seconds...")
                    time.sleep(self.rate_limit_delay)
                    retries += 1
                    logger.info(f"Retrying... (Attempt {retries}/{self.max_retries})")
                else:
                    logger.error(f"HTTP Error for URL {url}: {e}")
                    logger.error(f"Response body: {e.response.text}")
                    return None
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed for URL {url}: {e}")
                return None
        logger.error(f"Failed to fetch data from {url} after {self.max_retries} retries.")
        return None

    def get_account_by_riot_id(self, game_name: str, tag_line: str, region: str):
        encoded_game_name = quote(game_name)
        encoded_tag_line = quote(tag_line)
        account_url = f"https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{encoded_game_name}/{encoded_tag_line}"
        return self._request(account_url)

    def get_match_ids_by_puuid(self, puuid: str, region: str, count: int = 20):
        match_history_url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
        params = {'start': 0, 'count': count}
        return self._request(match_history_url, params=params)

    def get_match_detail(self, match_id: str, region: str):
        match_url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        return self._request(match_url)

    def get_match_timeline(self, match_id: str, region: str):
        timeline_url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
        return self._request(timeline_url)