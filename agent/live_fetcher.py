import logging
from .riot_api import RiotAPIClient
from .analysis import extract_support_stats, analyze_match_timeline

# Set up logger
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# In agent/live_fetcher.py

def fetch_and_analyze_player_data(game_name: str, tag_line: str, region: str, num_games: int = 20) -> list[dict] | str:
    """
    Fetches and analyzes recent support games for a given player.
    Returns a list of analyzed matches, or a string code indicating the error.
    """
    try:
        riot_client = RiotAPIClient()
    except ValueError as e:
        logger.error(f"Failed to initialize Riot API Client: {e}")
        return "API_KEY_ERROR"

    # 1. Get PUUID from Riot ID
    logger.info(f"Fetching PUUID for {game_name}#{tag_line}...")
    account_data = riot_client.get_account_by_riot_id(game_name, tag_line, region)
    if not account_data or "puuid" not in account_data:
        logger.error("Could not retrieve PUUID. Check Riot ID and region.")
        return "PLAYER_NOT_FOUND" # <-- Specific status code
    puuid = account_data["puuid"]

    # 2. Get recent match IDs
    logger.info(f"Fetching recent match IDs for PUUID {puuid}...")
    match_ids = riot_client.get_match_ids_by_puuid(puuid, region, count=num_games)
    if not match_ids:
        logger.warning("No recent matches found for this player.")
        return [] # Return an empty list, not an error

    # 3. Process each match
    analyzed_games = []
    # ... (the rest of the function is the same) ...
    for mid in match_ids:
        match_detail = riot_client.get_match_detail(mid, region)
        if not match_detail:
            continue

        participant_info = next((p for p in match_detail["info"]["participants"] if p.get("puuid") == puuid), None)
        
        if participant_info and participant_info.get("teamPosition") == "UTILITY":
            logger.info(f"Found support game {mid}. Fetching timeline...")
            timeline_data = riot_client.get_match_timeline(mid, region)
            if not timeline_data:
                logger.warning(f"Could not fetch timeline for {mid}.")
                continue

            stats = extract_support_stats([match_detail], puuid)[0]
            
            p_id = participant_info.get("participantId")
            team_id = participant_info.get("teamId")
            timeline_analysis = analyze_match_timeline(timeline_data, p_id, team_id)

            combined_match_data = {**stats, **timeline_analysis}
            analyzed_games.append(combined_match_data)
    
    logger.info(f"Successfully analyzed {len(analyzed_games)} support games.")
    return analyzed_games