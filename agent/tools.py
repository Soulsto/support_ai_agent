# agent/tools.py

import collections
import numpy as np
from langchain_core.tools import tool
from .utils import load_json
from .plotter import plot_combat_heatmap,plot_pathing_map
from itertools import groupby
from operator import itemgetter
import os

# ==============================================================================
# SECTION 1: PRIVATE HELPER FUNCTIONS (NOT TOOLS)
# These functions contain our core Python logic and can be called by any tool.
# ==============================================================================

def _get_user_filepath(game_name: str, tag_line: str) -> str:
    """Helper to create a sanitized, unique filepath for a user."""
    sanitized_name = game_name.replace(" ", "_")
    return f"data/users/{sanitized_name}_{tag_line}.json"

def _ms_to_min_sec(ms: int) -> str:
    """Helper to convert milliseconds to a MM:SS string format."""
    total_seconds = int(ms / 1000)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

METRIC_NAME_MAP = {
    "visionscore": "visionScore", "vision_score": "visionScore",
    "killparticipation": "killParticipation", "kill_participation": "killParticipation",
    "wardstakedowns": "wardTakedowns", "ward_takedowns": "wardTakedowns",
    "visionscoreperminute": "visionScorePerMinute", "vision_score_per_minute": "visionScorePerMinute"
}

def _get_average_stat_logic(filepath: str, metric: str, champion_name: str = None) -> float:
    """Core logic for calculating an average stat from a given data file."""
    data = load_json(filepath)
    if not data: return 0.0

    metric_key = METRIC_NAME_MAP.get(metric.lower(), metric)

    if champion_name:
        filtered_games = [g for g in data if g.get("champion", "").lower() == champion_name.lower()]
    else:
        filtered_games = data
    
    if not filtered_games: return 0.0

    values = [game.get(metric_key, 0) for game in filtered_games]
    return np.mean(values) if values else 0.0

def _get_user_match_data(game_name: str, tag_line: str, match_id: str) -> dict | None:
    """Loads a user's data file and finds a specific match by its ID."""
    filepath = _get_user_filepath(game_name, tag_line)
    user_data = load_json(filepath)
    if not user_data:
        return None
    return next((match for match in user_data if match.get("matchId") == match_id), None)


# ==============================================================================
# SECTION 2: AGENT TOOLS
# These are the functions decorated with @tool that the AI agent can see and use.
# ==============================================================================

@tool
def get_pro_player_average_stat(metric: str, champion_name: str = None) -> float:
    """Calculates the average for a metric from the pro player database."""
    return _get_average_stat_logic("data/pro_players_merged.json", metric, champion_name)

@tool
def get_user_average_stat(game_name: str, tag_line: str, metric: str, champion_name: str = None) -> float:
    """Calculates the average for a metric for a GIVEN USER from their personal match history."""
    filepath = _get_user_filepath(game_name, tag_line)
    return _get_average_stat_logic(filepath, metric, champion_name)

@tool
def determine_playstyle(champion_name: str, game_name: str, tag_line: str) -> dict:
    """Analyzes a user's playstyle on a champion by comparing their stats to the pro average."""
    user_filepath = _get_user_filepath(game_name, tag_line)
    pro_filepath = "data/pro_players_merged.json"

    user_vision = _get_average_stat_logic(user_filepath, 'visionScore', champion_name)
    pro_vision = _get_average_stat_logic(pro_filepath, 'visionScore', champion_name)
    user_kp = _get_average_stat_logic(user_filepath, 'killParticipation', champion_name)
    pro_kp = _get_average_stat_logic(pro_filepath, 'killParticipation', champion_name)
    user_deaths = _get_average_stat_logic(user_filepath, 'deaths', champion_name)
    pro_deaths = _get_average_stat_logic(pro_filepath, 'deaths', champion_name)

    if user_vision == 0 or pro_vision == 0:
        return {"error": f"Not enough data for {champion_name} to determine a playstyle."}

    playstyle, evidence = "Balanced", []
    if user_vision > pro_vision * 1.15:
        playstyle = "Vision-Focused Controller"
        evidence.append(f"Your average Vision Score ({user_vision:.2f}) is higher than the pro average ({pro_vision:.2f}).")
    if user_kp > pro_kp * 1.1:
        playstyle = "Aggressive Playmaker"
        evidence.append(f"Your Kill Participation ({user_kp:.2%}) is higher than the pro average ({pro_kp:.2%}).")
    if user_deaths > pro_deaths * 1.2:
        evidence.append(f"You tend to have more deaths ({user_deaths:.2f}) than pros, suggesting a high-risk style.")
    elif user_deaths < pro_deaths * 0.8:
        playstyle = "Safe/Defensive Player"
        evidence.append(f"Your average deaths ({user_deaths:.2f}) are lower than the pro average ({pro_deaths:.2f}).")
    if not evidence:
        evidence.append("Your stats are very similar to pro averages.")

    return {"inferred_playstyle": playstyle, "supporting_evidence": " ".join(evidence)}

@tool
def get_best_champions_from_pros(sort_by: str = "win_rate", top_n: int = 5) -> list[dict]:
    """Finds and ranks pro support champions from the database based on a chosen metric (win_rate or games_played)."""
    pro_data = load_json("data/pro_players_merged.json")
    if not pro_data: return []

    pro_data.sort(key=itemgetter('champion'))
    champion_stats = []
    for champion, games in groupby(pro_data, key=itemgetter('champion')):
        games_list = list(games)
        games_played = len(games_list)
        if games_played >= 5:
            wins = sum(1 for game in games_list if game.get('win'))
            win_rate = wins / games_played
            champion_stats.append({"champion": champion, "win_rate": win_rate, "games_played": games_played})

    if sort_by not in ["win_rate", "games_played"]:
        return [{"error": "Invalid sort_by value. Must be 'win_rate' or 'games_played'."}]
        
    sorted_champs = sorted(champion_stats, key=itemgetter(sort_by), reverse=True)
    return sorted_champs[:top_n]

@tool
def get_pro_build_for_champion(champion_name: str) -> dict:
    """
    (Upgraded) Finds the most common item build for a champion from the pro database.
    Returns a dictionary containing item names, image URLs, and popularity.
    """
    pro_data = load_json("data/pro_players_merged.json")
    items_list = load_json("data/items.json")
    if not pro_data or not items_list: return {"error": "Could not load data."}

    item_lookup = {str(item['id']): item for item in items_list}
    champion_games = [g for g in pro_data if g.get("champion", "").lower() == champion_name.lower()]
    if not champion_games: return {"error": f"No games found for champion {champion_name}."}

    all_items = [str(game.get(f"item{i}", 0)) for game in champion_games for i in range(6) if game.get(f"item{i}", 0) != 0]
    item_counts = collections.Counter(all_items)
    
    build = {
        "champion": champion_name.title(),
        "games_analyzed": len(champion_games),
        "boots": None, # Will be a dict
        "core_items": [] # Will be a list of dicts
    }
    
    core_items = []
    for item_id, count in item_counts.most_common():
        item_info = item_lookup.get(item_id)
        if not item_info: continue
        
        item_name = item_info.get("name")
        item_details = {
            "name": item_name,
            "image_url": item_info.get("image_url"),
            "cost": item_info.get("cost"),
            "popularity": f"{(count / len(champion_games) * 100):.0f}%"
        }

        if "Boots" in item_name and not build["boots"]:
            build["boots"] = item_details
        elif "Boots" not in item_name and "Potion" not in item_name and "Ward" not in item_name and len(core_items) < 5:
            core_items.append(item_details)

    build["core_items"] = core_items
    return build

@tool
def analyze_build_path(match_id: str, game_name: str, tag_line: str) -> list[dict]:
    """
    (Upgraded) Shows the chronological order of items purchased for a user in a specific match.
    It now groups items purchased at the same time into a single "shopping trip".
    Returns a list of dictionaries, where each dictionary is a shopping trip.
    """
    match_data = _get_user_match_data(game_name, tag_line, match_id)
    if not match_data:
        return [{"error": f"Match {match_id} not found."}]
    
    items_list = load_json("data/items.json")
    item_lookup = {str(item['id']): item for item in items_list}
    
    item_events = match_data.get("item_events", [])
    if not item_events:
        return [{"error": "No item purchase events found."}]

    # 1. Filter for only ITEM_PURCHASED events and get details
    purchases = []
    for event in item_events:
        if event.get("type") == "ITEM_PURCHASED":
            item_id = str(event.get("itemId"))
            item_info = item_lookup.get(item_id)
            if item_info:
                purchases.append({
                    "timestamp": event.get("timestamp", 0),
                    "name": item_info.get("name"),
                    "image_url": item_info.get("image_url")
                })

    if not purchases:
        return [{"error": "No valid item purchases found."}]

    # 2. Group consecutive purchases by timestamp
    build_path = []
    for timestamp, group in groupby(purchases, key=lambda x: x['timestamp']):
        items_in_trip = list(group)
        build_path.append({
            "timestamp_str": _ms_to_min_sec(timestamp),
            "items": items_in_trip
        })

    return build_path
@tool
def analyze_item_gold_spend(match_id: str, game_name: str, tag_line: str) -> dict:
    """Analyzes item purchases for a user in a specific match to calculate gold spent."""
    match_data = _get_user_match_data(game_name, tag_line, match_id)
    if not match_data: return {"error": f"Match {match_id} not found."}

    items_list = load_json("data/items.json")
    item_lookup = {str(item['id']): item for item in items_list}
    
    total_gold_spent = sum(item_lookup.get(str(e.get("itemId")), {}).get("cost", 0) for e in match_data.get("item_events", []) if e.get("type") == "ITEM_PURCHASED")
    final_build_cost = sum(item_lookup.get(str(match_data.get(f"item{i}")), {}).get("cost", 0) for i in range(7))
    final_build_items = [item_lookup.get(str(match_data.get(f"item{i}")), {}).get("name") for i in range(7) if match_data.get(f"item{i}")]

    return {"total_gold_spent_on_purchases": total_gold_spent, "final_build_cost": final_build_cost, "final_build_items": final_build_items}

@tool
def analyze_vision_control(match_id: str, game_name: str, tag_line: str) -> dict:
    """Provides a detailed report on vision control for a user in a specific match."""
    match_data = _get_user_match_data(game_name, tag_line, match_id)
    if not match_data: return {"error": f"Match {match_id} not found."}

    vision_events = match_data.get("vision_events", [])
    return {
        "vision_score": match_data.get("visionScore", 0),
        "wards_placed": match_data.get("wardsPlaced", 0),
        "wards_killed": match_data.get("wardsKilled", 0),
        "control_wards_bought": match_data.get("visionWardsBoughtInGame", 0),
        "control_wards_placed": sum(1 for e in vision_events if e.get('type') == 'PLACED' and e.get('ward_type') == 'CONTROL_WARD'),
        "stealth_wards_placed": sum(1 for e in vision_events if e.get('type') == 'PLACED' and e.get('ward_type') == 'SIGHT_WARD')
    }

@tool
def analyze_teamfight_positioning(match_id: str, game_name: str, tag_line: str) -> str:
    """Generates a map visualizing where a user got kills/assists versus where they died in a specific match."""
    match_data = _get_user_match_data(game_name, tag_line, match_id)
    if not match_data: return f"Match {match_id} not found."

    output_path = plot_combat_heatmap(match_data)
    return f"Positioning map generated: {output_path}" if output_path else "Could not generate map."

@tool
def find_critical_moments_in_game(game_name: str, tag_line: str, match_id: str) -> list[str]:
    """Analyzes a single game for a user by their match_id to find critical moments."""
    match_data = _get_user_match_data(game_name, tag_line, match_id)
    if not match_data: return [f"Match {match_id} not found."]

    death_events = match_data.get("death_positions", [])
    objective_events = match_data.get("enemy_objective_takes", [])
    if not death_events: return ["No deaths found in this game. Great job!"]
    
    critical_moments = []
    for death in death_events:
        death_time = death.get("timestamp", 0)
        for objective in objective_events:
            obj_time = objective.get("timestamp", 0)
            if 0 < (obj_time - death_time) <= 60000:
                obj_type = objective.get("type", "Objective").replace("_", " ").title()
                moment = (f"At {_ms_to_min_sec(death_time)}, a death was followed by the enemy taking a {obj_type} "
                          f"within a minute. This suggests the death created a critical opening.")
                critical_moments.append(moment)

    return critical_moments if critical_moments else ["No critical moments found."]

@tool
def get_laning_phase_stats(match_id: str, game_name: str, tag_line: str) -> dict:
    """Provides key statistics about the laning phase (first 14 minutes) for a user in a given match."""
    match_data = _get_user_match_data(game_name, tag_line, match_id)
    if not match_data: return {"error": f"Match {match_id} not found."}

    deaths_in_lane = sum(1 for d in match_data.get("death_positions", []) if d.get("timestamp", 0) <= 840000)
    return {"deaths_before_14_mins": deaths_in_lane, "ward_takedowns_before_20_mins": match_data.get("wardTakedownsBefore20M", 0)}

@tool
def get_common_skill_order_for_champion(champion_name: str) -> str:
    """
    Finds the most common skill leveling order for a specific champion by analyzing all
    games played by pros in the database. Returns the first 11 levels.
    """
    pro_data = load_json("data/pro_players_merged.json")
    if not pro_data:
        return f"Could not load pro player data to analyze {champion_name}."

    # 1. Filter for all games where the champion was played
    champion_games = [
        game for game in pro_data 
        if game.get("champion", "").lower() == champion_name.lower()
    ]
    if not champion_games:
        return f"No games found for {champion_name} in the database."

    # 2. Collect all skill order lists
    all_skill_orders = [game.get("skill_level_order", []) for game in champion_games]
    # Filter out any empty lists
    all_skill_orders = [order for order in all_skill_orders if order]

    if not all_skill_orders:
        return f"Skill level data is missing for {champion_name} games."

    # 3. Find the most common skill at each level (up to level 11)
    common_order = []
    skill_map = {1: 'Q', 2: 'W', 3: 'E', 4: 'R'}
    
    for level in range(16): # Analyze the first 11 levels
        skills_at_this_level = []
        for order in all_skill_orders:
            if len(order) > level:
                skills_at_this_level.append(order[level])
        
        if not skills_at_this_level:
            break
            
        # Find the most common skill for this level
        most_common_skill_slot = collections.Counter(skills_at_this_level).most_common(1)[0][0]
        common_order.append(skill_map.get(most_common_skill_slot, '?'))

    return " -> ".join(common_order)


@tool
def analyze_objective_proximity(match_id: str, game_name: str, tag_line: str) -> list[str]:
    """
    Analyzes a user's proximity to major objectives (Dragon, Baron) when they are taken by either team.
    Requires the user's game_name, tag_line, and a specific match_id.
    Returns a list of insights about the user's positioning during these key moments.
    """
    match_data = _get_user_match_data(game_name, tag_line, match_id)
    if not match_data:
        return [f"Match {match_id} not found for user {game_name}#{tag_line}."]

    # 1. Combine all objective takes into a single list with team context
    all_objectives = []
    for obj in match_data.get("ally_objective_takes", []):
        if "DRAGON" in obj.get("type", "") or "BARON_NASHOR" in obj.get("type", ""):
            all_objectives.append({**obj, "team": "Ally"})
    for obj in match_data.get("enemy_objective_takes", []):
        if "DRAGON" in obj.get("type", "") or "BARON_NASHOR" in obj.get("type", ""):
            all_objectives.append({**obj, "team": "Enemy"})

    if not all_objectives:
        return ["No Dragon or Baron takes were found in this game's timeline data."]

    pathing_data = match_data.get("full_game_pathing")
    if not pathing_data:
        return ["No pathing data available to analyze proximity."]

    # 2. Analyze each objective event
    insights = []
    for obj in sorted(all_objectives, key=itemgetter('timestamp')):
        obj_time = obj.get("timestamp", 0)
        obj_type = obj.get("type", "Objective").replace("_", " ").title()
        obj_pos = obj.get("position", {})

        # Find the player's position at the exact moment the objective was taken
        closest_path_point = min(pathing_data, key=lambda p: abs(p['timestamp'] - obj_time))
        player_pos = closest_path_point.get("position")

        if not player_pos:
            continue
            
        # 3. Calculate distance and generate an insight
        distance = np.linalg.norm(np.array([player_pos['x'], player_pos['y']]) - np.array([obj_pos['x'], obj_pos['y']]))

        position_insight = ""
        if distance < 3000: # Approx. screen width
            position_insight = "You were present at the objective."
        elif distance > 8000:
            position_insight = "You were on the opposite side of the map."
        else:
            position_insight = "You were nearby, but not directly at the objective."

        timestamp_str = _ms_to_min_sec(obj_time)
        full_insight = f"At {timestamp_str}, the {obj['team']} team took a {obj_type}. {position_insight}"
        insights.append(full_insight)

    return insights if insights else ["No relevant objective insights found."]

def get_comprehensive_game_analysis(match_id: str, game_name: str, tag_line: str) -> dict:
    """
    Performs a full analysis of a single game for a given user.
    Gathers stats for laning, vision, builds, and generates a teamfight map.
    """
    match_data = _get_user_match_data(game_name, tag_line, match_id)
    if not match_data:
        return {"error": f"Match {match_id} not found."}

    # --- NEW: Laning phase combat analysis ---
    laning_phase_limit = 14 * 60 * 1000
    laning_kills = sum(1 for e in match_data.get("combat_events", []) if e['type'] == 'KILL' and e['timestamp'] <= laning_phase_limit)
    laning_assists = sum(1 for e in match_data.get("combat_events", []) if e['type'] == 'ASSIST' and e['timestamp'] <= laning_phase_limit)

    laning_stats = get_laning_phase_stats.func(match_id, game_name, tag_line)
    laning_stats['laning_kills'] = laning_kills
    laning_stats['laning_assists'] = laning_assists
    
    # --- Get other analyses ---
    build_path = analyze_build_path.func(match_id, game_name, tag_line)
    vision_report = analyze_vision_control.func(match_id, game_name, tag_line)
    teamfight_map_path = plot_combat_heatmap(match_data)
    
    # Also pass through the raw vision events for the new UI
    vision_report['vision_events_log'] = match_data.get("vision_events", [])

    # --- Assemble the final report ---
    analysis_report = {
        "match_summary": {
            "champion": match_data.get("champion"), "win": match_data.get("win"),
            "kills": match_data.get("kills"), "deaths": match_data.get("deaths"),
            "assists": match_data.get("assists"), "visionScore": match_data.get("visionScore")
        },
        "laning_phase": laning_stats,
        "build_path": build_path,
        "vision_report": vision_report,
        "teamfight_map_path": teamfight_map_path
    }
    return analysis_report

@tool
def get_latest_match_id(game_name: str, tag_line: str) -> str:
    """
    Finds and returns the match_id of the most recent game from a user's match history.
    Use this when the user asks for their "last" or "latest" game.
    """
    filepath = _get_user_filepath(game_name, tag_line)
    user_data = load_json(filepath)
    if not user_data:
        return "No user data found. Please fetch games first."
    try:
        latest_game = user_data[-1]
        return latest_game.get('matchId')
    except (IndexError, TypeError, KeyError):
        return "Could not determine the latest game from the available data."
    
@tool
def generate_pathing_map_for_match(match_id: str, game_name: str, tag_line: str) -> str:
    """
    Generates a color-coded pathing map for a user's specific game and returns the file path.
    Use this when a user asks to see their pathing, roaming, or movement for a specific match.
    """
    match_data = _get_user_match_data(game_name, tag_line, match_id)
    if not match_data:
        return f"Could not find data for match {match_id}."

    # This tool calls the plotting function to do the actual work
    output_path = plot_pathing_map(match_data)
    
    if output_path and os.path.exists(output_path):
        return f"Pathing map for match {match_id} has been generated and saved to {output_path}"
    else:
        return "An error occurred while trying to generate the pathing map."