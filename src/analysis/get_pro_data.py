import os
import json
import logging
from typing import List, Dict, Any
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.api_client.riot_api import RiotAPIClient
from src.analysis.analysis import extract_support_stats, analyze_match_timeline
from src.utils.utils import load_json

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    riot_client = RiotAPIClient()
except ValueError as e:
    logger.error(f"Failed to initialize RiotAPIClient: {e}")
    riot_client = None

# --- File Paths ---
PRO_PLAYER_CONFIG_PATH = "data/pro_players.json"
PRO_DATA_DIR = "data/pro_players/"
MERGED_PRO_DATA_PATH = "data/pro_players_merged.json"
MATCH_COUNT_TO_FETCH = 15


def enrich_pro_player_config_with_puuids() -> List[Dict[str, Any]]:
    """
    Loads the pro player config, finds missing PUUIDs using the Riot API,
    and saves the updated config back to the file. This should only need
    to fetch the PUUID for each player once.
    """
    if not riot_client:
        logger.error("Riot API Client not initialized. Cannot enrich config.")
        return []

    players = load_json(PRO_PLAYER_CONFIG_PATH)
    if not isinstance(players, list):
        logger.error("Pro player config is not a valid list.")
        return []

    config_was_updated = False
    for player in players:
        if "puuid" not in player or not player["puuid"]:
            logger.info(f"PUUID not found for {player['gameName']}. Fetching from API...")
            account_data = riot_client.get_account_by_riot_id(
                game_name=player['gameName'],
                tag_line=player['tagLine'],
                region=player['region']
            )
            if account_data and "puuid" in account_data:
                player["puuid"] = account_data["puuid"]
                logger.info(f"Found PUUID for {player['gameName']}: {player['puuid']}")
                config_was_updated = True
            else:
                logger.error(f"Could not fetch PUUID for {player['gameName']}. Please check their Riot ID and region.")

    if config_was_updated:
        with open(PRO_PLAYER_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(players, f, indent=2)
        logger.info(f"Updated {PRO_PLAYER_CONFIG_PATH} with new PUUIDs.")
    
    return players


def update_pro_player_data(player_info: dict[str, any]):
    """
    Fetches and processes both stats and timeline data for new support games.
    """
    player_name = player_info['gameName']
    player_puuid = player_info['puuid']
    player_region = player_info['region']
    player_file_path = os.path.join(PRO_DATA_DIR, f"{player_name}.json")

    logger.info(f"--- Starting update for {player_name} ---")

    player_data = load_json(player_file_path) if os.path.exists(player_file_path) else []
    existing_match_ids = {match['matchId'] for match in player_data}
    os.makedirs(PRO_DATA_DIR, exist_ok=True)

    recent_match_ids = riot_client.get_match_ids_by_puuid(player_puuid, player_region, count=35)
    if not recent_match_ids:
        logger.warning(f"No recent matches found for {player_name}.")
        return

    new_match_ids = [mid for mid in recent_match_ids if mid not in existing_match_ids]
    if not new_match_ids:
        logger.info(f"No new matches to check for {player_name}.")
        return

    logger.info(f"Checking {len(new_match_ids)} new matches for support role...")
    
    new_matches_to_add = []
    for mid in new_match_ids:
        match_detail = riot_client.get_match_detail(mid, region=player_region)
        if not match_detail:
            continue
        
        participant_info = next((p for p in match_detail["info"]["participants"] if p.get("puuid") == player_puuid), None)
        
        if participant_info and participant_info.get("teamPosition") == "UTILITY":
            logger.info(f"Found support game {mid}. Fetching timeline...")
            timeline_data = riot_client.get_match_timeline(mid, region=player_region)
            if not timeline_data:
                logger.warning(f"Could not fetch timeline for {mid}. Skipping timeline analysis.")
                continue

            # Get stats and timeline analysis for this single match
            stats = extract_support_stats([match_detail], player_puuid)[0] # Pass as a list to reuse function
            
            p_id = participant_info.get("participantId")
            team_id = participant_info.get("teamId")
            timeline_analysis = analyze_match_timeline(timeline_data, p_id, team_id)

            # Merge all data together for this one match
            combined_match_data = {**stats, **timeline_analysis}
            new_matches_to_add.append(combined_match_data)

    if new_matches_to_add:
        player_data.extend(new_matches_to_add)
        with open(player_file_path, 'w', encoding='utf-8') as f:
            json.dump(player_data, f, indent=4)
        logger.info(f"Successfully saved {len(new_matches_to_add)} new support matches with timeline data to {player_file_path}.")
    else:
        logger.info(f"No new support games found for {player_name} in the latest batch.")


def update_all_pro_players(pro_players: List[Dict[str, Any]]):
    """Loops through all players and updates their data."""
    for player_info in pro_players:
        if "puuid" in player_info and player_info["puuid"]:
            update_pro_player_data(player_info)
        else:
            logger.warning(f"Skipping {player_info['gameName']} because PUUID is missing.")


def merge_pro_data():
    """Merges all individual pro player JSON files into a single file."""
    all_pro_stats = []
    if not os.path.exists(PRO_DATA_DIR):
        logger.warning(f"Pro player data directory not found: {PRO_DATA_DIR}")
        return

    for filename in os.listdir(PRO_DATA_DIR):
        if filename.endswith(".json"):
            player_name = filename.replace(".json", "")
            logger.info(f"Merging data for {player_name}")
            file_path = os.path.join(PRO_DATA_DIR, filename)
            player_data = load_json(file_path)
            for match in player_data:
                match['proPlayerName'] = player_name
            all_pro_stats.extend(player_data)

    with open(MERGED_PRO_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_pro_stats, f, indent=4)
    logger.info(f"Successfully merged data for {len(all_pro_stats)} matches into {MERGED_PRO_DATA_PATH}.")


if __name__ == '__main__':
    print("Pro Player Data Manager")
    
    # Step 1: Enrich the config file with PUUIDs.
    print("Step 1: Checking for and fetching missing PUUIDs...")
    enriched_players = enrich_pro_player_config_with_puuids()
    print("Step 1: Complete.\n")

    # Step 2: Run the main update/merge process
    print("Step 2: Choose an action")
    print("  1: Update all pro player data from Riot API (and merge)")
    print("  2: Merge only existing local data")
    choice = input("Enter your choice (1 or 2): ")

    if choice == '1':
        print("\nUpdating all pro players...")
        update_all_pro_players(enriched_players)
        print("\nMerging data...")
        merge_pro_data()
    elif choice == '2':
        print("\nMerging data...")
        merge_pro_data()
    else:
        print("Invalid choice.")
    
    print("\nProcess finished.")