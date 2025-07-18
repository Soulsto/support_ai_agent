"""
analysis.py - Analysis utilities for League of Legends support player data.

Processes match data & timelines to produce JSON summaries on:
- Early game performance (deaths and warding)
- Roaming patterns and distance from lane
"""

import os
import json
import math
import logging
from typing import List, Dict, Any, Tuple, Optional
from dotenv import load_dotenv

# This loads the .env file from the current directory or parent directories
load_dotenv()

# Now, you can access the variables
import os
riot_key = os.getenv("RIOT_API_KEY")
# Assumes riot_api.py is in the agent folder
from src.api_client.riot_api import RiotAPIClient

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Instantiate the client once to be reused across all functions
try:
    riot_client = RiotAPIClient()
except ValueError as e:
    logger.error(f"Failed to initialize RiotAPIClient: {e}")
    # Exit or handle the case where the API key is missing
    riot_client = None


# ========== Data Fetching and Saving ==========

def save_raw_match_details(match_ids: List[str], save_path: str = "data/raw_match_details.json") -> None:
    """
    Downloads and saves the full, raw match detail JSON for a list of match IDs.
    """
    if not riot_client:
        logger.error("Riot API Client is not initialized. Cannot save match details.")
        return

    all_matches_data = []
    for mid in match_ids:
        logger.info(f"Fetching match detail for {mid}")
        match_data = riot_client.get_match_detail(mid)
        if match_data:
            all_matches_data.append(match_data)
        else:
            logger.warning(f"Failed to fetch details for match {mid}. Skipping.")

    with open(save_path, "w", encoding='utf-8') as f:
        json.dump(all_matches_data, f, indent=4)
    logger.info(f"Saved raw details for {len(all_matches_data)} matches to {save_path}")


# ========== Participant and Position Utilities ==========

def get_participant_info(timeline_data: Dict[str, Any], puuid: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Returns the (participantId, teamId) for a given puuid from timeline data.
    Returns (None, None) if the participant is not found.
    """
    for p in timeline_data.get("info", {}).get("participants", []):
        if p.get("puuid") == puuid:
            return p.get("participantId"), p.get("teamId")
    return None, None

def calculate_distance(x1: int, y1: int, x2: int, y2: int) -> float:
    """
    Calculates the Euclidean distance between two points.
    """
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)


# ========== Core Analysis Functions ==========

def extract_support_stats(match_data_list: list[dict[str, any]], puuid: str) -> list[dict[str, any]]:
    """
    Extracts a comprehensive list of support player stats from raw match data,
    including core stats, pings, vision, combat, and specific challenges.
    """
    stats_list = []
    for match in match_data_list:
        participant_info = next((p for p in match["info"]["participants"] if p.get("puuid") == puuid), None)
        if not participant_info:
            continue

        challenges = participant_info.get("challenges", {})

        # --- NEW: Create a simplified summary for all 10 players ---
        all_participants_summary = []
        for p in match["info"]["participants"]:
            all_participants_summary.append({
                "championName": p.get("championName"),
                "teamPosition": p.get("teamPosition"),
                "teamId": p.get("teamId"),
                "win": p.get("win", False),
                "kills": p.get("kills", 0),
                "deaths": p.get("deaths", 0),
                "assists": p.get("assists", 0),
                "goldEarned": p.get("goldEarned", 0),
                "puuid": p.get("puuid")
            })

        # --- Consolidate stats with multiple possible names ---
        cc_time = (
            participant_info.get("totalTimeCCingOthers") or
            participant_info.get("timeCCingOthers") or
            challenges.get("totalTimeCCDealt") or
            0
        )
        # --- The definitive shield stat, using the new field you found ---
        shielding = (
            participant_info.get("totalDamageShieldedOnTeammates") or
            participant_info.get("totalDamageShielded") or
            challenges.get("effectiveHealAndShielding") or # Fallback
            0
        )
        healing = (
            participant_info.get("totalHealsOnTeammates") or
            challenges.get("effectiveHealAndShielding") or # Fallback
            0
        )

        stats = {
            "matchId": match["metadata"]["matchId"],
            "proPlayerName": participant_info.get("riotIdGameName") or participant_info.get("summonerName"),
            "champion": participant_info.get("championName"),
            "win": participant_info.get("win", False),
            "gameDuration": match["info"].get("gameDuration", 0),
            "allParticipants": all_participants_summary,
            
            # Core KDA
            "kills": participant_info.get("kills", 0),
            "deaths": participant_info.get("deaths", 0),
            "assists": participant_info.get("assists", 0),
            "killParticipation": challenges.get("killParticipation", 0.0),

            # Items
            "item0": participant_info.get("item0", 0),
            "item1": participant_info.get("item1", 0),
            "item2": participant_info.get("item2", 0),
            "item3": participant_info.get("item3", 0),
            "item4": participant_info.get("item4", 0),
            "item5": participant_info.get("item5", 0),
            "item6": participant_info.get("item6", 0), # Trinket

            # Vision Stats
            "visionScore": participant_info.get("visionScore", 0),
            "wardsPlaced": participant_info.get("wardsPlaced", 0),
            "wardsKilled": participant_info.get("wardsKilled", 0),
            "detectorWardsPlaced": participant_info.get("detectorWardsPlaced", 0),
            "visionWardsBoughtInGame": participant_info.get("visionWardsBoughtInGame", 0),
            "visionScoreAdvantageLaneOpponent": challenges.get("visionScoreAdvantageLaneOpponent", 0.0),
            "visionScorePerMinute": challenges.get("visionScorePerMinute", 0.0),
            
            # Combat and Utility Stats
            "totalTimeCCingOthers": cc_time,
            "totalHealsOnTeammates": healing,
            "totalDamageShieldedOnTeammates": shielding,
            "enemyChampionImmobilizations": challenges.get("enemyChampionImmobilizations", 0),
            "saveAllyFromDeath": challenges.get("saveAllyFromDeath", 0),
            "skillshotsHit": challenges.get("skillshotsHit", 0),
            "damageTakenOnTeamPercentage": challenges.get("damageTakenOnTeamPercentage", 0.0),

            # Pings
            "assistMePings": participant_info.get("assistMePings", 0),
            "enemyMissingPings": participant_info.get("enemyMissingPings", 0),
            "enemyVisionPings": participant_info.get("enemyVisionPings", 0),
            "onMyWayPings": participant_info.get("onMyWayPings", 0),
            "visionClearedPings": participant_info.get("visionClearedPings", 0),
            
            # More Challenge Stats
            "controlWardTimeCoverageInRiverOrEnemyHalf": challenges.get("controlWardTimeCoverageInRiverOrEnemyHalf", 0.0),
            "highestCrowdControlScore": challenges.get("highestCrowdControlScore", 0),
            "controlWardsPlaced": challenges.get("controlWardsPlaced", 0),
            "effectiveHealAndShielding": challenges.get("effectiveHealAndShielding", 0.0),
            "immobilizeAndKillWithAlly": challenges.get("immobilizeAndKillWithAlly", 0),
            "knockEnemyIntoTeamAndKill": challenges.get("knockEnemyIntoTeamAndKill", 0),
            "stealthWardsPlaced": challenges.get("stealthWardsPlaced", 0),
            "wardsGuarded": challenges.get("wardsGuarded", 0),
            "wardTakedowns": challenges.get("wardTakedowns", 0),
            "wardTakedownsBefore20M": challenges.get("wardTakedownsBefore20M", 0),
        }
        stats_list.append(stats)
    return stats_list


def analyze_match_timeline(timeline_data: dict[str, any], participant_id: int, team_id: int) -> dict[str, any]:
    """
    Analyzes timeline data to extract pathing, deaths, objectives (ally & enemy),
    skill leveling, vision events, combat events, and item purchases.
    """
    # --- Initialize all data lists ---
    early_game_pathing, full_game_pathing, death_positions, enemy_objective_takes = [], [], [], []
    skill_level_order = []
    vision_events = []
    item_events = []
    combat_events = []
    ally_objective_takes = []

    # --- THIS IS THE CORRECTED LINE ---
    # These are the correct coordinates for the player's OWN bot lane outer turret.
    # Blue side (team 100) is bottom-left, Red side (team 200) is top-right.
    bot_tower_pos = (10565, 1045) if team_id == 100 else (4325, 13865)
    
    twenty_minutes_ms = 20 * 60 * 1000
    enemy_team_id = 200 if team_id == 100 else 100

    if not timeline_data or "frames" not in timeline_data.get("info", {}):
        return {
            "early_game_pathing": [], "full_game_pathing": [], "death_positions": [],
            "enemy_objective_takes": [], "skill_level_order": [], "vision_events": [],
            "item_events": [], "combat_events": [], "ally_objective_takes": []
        }

    # --- Frame and Event Processing Loop ---
    for frame in timeline_data["info"]["frames"]:
        timestamp = frame.get("timestamp", 0)
        
        # Pathing Analysis
        participant_frame = frame.get("participantFrames", {}).get(str(participant_id))
        if participant_frame and "position" in participant_frame:
            pos = participant_frame["position"]
            distance = calculate_distance(pos["x"], pos["y"], bot_tower_pos[0], bot_tower_pos[1])
            pathing_point = {"timestamp": timestamp, "position": pos, "distance_from_tower": round(distance)}
            full_game_pathing.append(pathing_point)
            if timestamp <= twenty_minutes_ms:
                early_game_pathing.append(pathing_point)

        # Event Analysis
        for event in frame.get("events", []):
            event_type = event.get("type")
            
            # --- Capture events related to our player ---
            if event.get("participantId") == participant_id:
                if event_type == "SKILL_LEVEL_UP":
                    skill_level_order.append(event.get("skillSlot"))
                elif event_type in ["ITEM_PURCHASED", "ITEM_SOLD", "ITEM_UNDO"]:
                    item_events.append({"timestamp": timestamp, "type": event_type, "itemId": event.get("itemId")})

            # --- Capture Vision and Combat Events by player ---
            if event_type == "WARD_PLACED" and event.get("creatorId") == participant_id:
                vision_events.append({"timestamp": timestamp, "type": "PLACED", "ward_type": event.get("wardType"), "position": event.get("position", {})})
            elif event_type == "WARD_KILLED" and event.get("killerId") == participant_id:
                vision_events.append({"timestamp": timestamp, "type": "KILLED", "ward_type": event.get("wardType"), "position": event.get("position", {})})
            
            if event_type == "CHAMPION_KILL":
                if event.get("victimId") == participant_id:
                    death_positions.append(event)
                elif event.get("killerId") == participant_id:
                    combat_events.append({"timestamp": timestamp, "type": "KILL", "position": event.get("position", {})})
                elif participant_id in event.get("assistingParticipantIds", []):
                    combat_events.append({"timestamp": timestamp, "type": "ASSIST", "position": event.get("position", {})})

            # --- Capture Objective Takes by either team ---
            killer_team = event.get("killerTeamId", event.get("teamId"))
            if event_type in ["ELITE_MONSTER_KILL", "BUILDING_KILL"]:
                obj_data = {"timestamp": timestamp, "type": event.get("monsterType") or event.get("buildingType"), "lane": event.get("laneType"), "position": event.get("position", {})}
                if killer_team == enemy_team_id:
                    enemy_objective_takes.append(obj_data)
                elif killer_team == team_id:
                    ally_objective_takes.append(obj_data)

    return {
        "early_game_pathing": early_game_pathing,
        "full_game_pathing": full_game_pathing,
        "death_positions": death_positions,
        "enemy_objective_takes": enemy_objective_takes,
        "skill_level_order": skill_level_order,
        "vision_events": vision_events,
        "item_events": item_events,
        "combat_events": combat_events,
        "ally_objective_takes": ally_objective_takes
    }