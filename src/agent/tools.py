# agent/tools.py

import collections
import numpy as np
from langchain_core.tools import tool
from src.utils.utils import load_json
from src.analysis.plotter import plot_combat_heatmap, plot_pathing_map
from itertools import groupby
from operator import itemgetter
import os

# ==============================================================================
# SECTION 0: CONSTANTS
# ==============================================================================
PRO_DATA_FILE = "data/pro_players_merged.json"
ITEMS_DATA_FILE = "data/items.json"
USER_DATA_DIR = "data/users/"

# ==============================================================================
# SECTION 1: PRIVATE HELPER FUNCTIONS
# ==============================================================================

def _get_user_filepath(game_name: str, tag_line: str) -> str:
    sanitized_name = game_name.replace(" ", "_")
    return os.path.join(USER_DATA_DIR, f"{sanitized_name}_{tag_line}.json")

def _ms_to_min_sec(ms: int) -> str:
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
    filepath = _get_user_filepath(game_name, tag_line)
    user_data = load_json(filepath)
    if not user_data:
        return None
    return next((match for match in user_data if match.get("matchId") == match_id), None)

# ==============================================================================
# SECTION 2: AGENT TOOLS
# ==============================================================================

@tool
def get_pro_player_average_stat(metric: str, champion_name: str = None) -> float:
    """Calculates the average for a metric from the pro player database."""
    return _get_average_stat_logic(PRO_DATA_FILE, metric, champion_name)

@tool
def get_user_average_stat(game_name: str, tag_line: str, metric: str, champion_name: str = None) -> float:
    """Calculates the average for a metric for a GIVEN USER from their personal match history."""
    filepath = _get_user_filepath(game_name, tag_line)
    return _get_average_stat_logic(filepath, metric, champion_name, is_pro=False)

@tool
def determine_playstyle(champion_name: str, game_name: str, tag_line: str) -> dict:
    """Analyzes a user's playstyle on a champion by comparing their stats to the pro average."""
    user_filepath = _get_user_filepath(game_name, tag_line)
    user_vision = get_user_average_stat.func(game_name, tag_line, 'visionScore', champion_name)
    pro_vision = get_pro_player_average_stat.func('visionScore', champion_name)
    user_kp = get_user_average_stat.func(game_name, tag_line, 'killParticipation', champion_name)
    pro_kp = get_pro_player_average_stat.func('killParticipation', champion_name)
    user_deaths = get_user_average_stat.func(game_name, tag_line, 'deaths', champion_name)
    pro_deaths = get_pro_player_average_stat.func('deaths', champion_name)

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
    pro_data = load_json(PRO_DATA_FILE)
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
    """Finds the most common item build for a champion from the pro database."""
    pro_data = load_json(PRO_DATA_FILE)
    items_list = load_json(ITEMS_DATA_FILE)
    if not pro_data or not items_list: return {"error": "Could not load data."}
    item_lookup = {str(item['id']): item for item in items_list}
    champion_games = [g for g in pro_data if g.get("champion", "").lower() == champion_name.lower()]
    if not champion_games: return {"error": f"No games found for champion {champion_name}."}
    all_items = [str(game.get(f"item{i}", 0)) for game in champion_games for i in range(6) if game.get(f"item{i}", 0) != 0]
    item_counts = collections.Counter(all_items)
    build = {"champion": champion_name.title(), "games_analyzed": len(champion_games), "boots": None, "core_items": []}
    core_items = []
    for item_id, count in item_counts.most_common():
        item_info = item_lookup.get(item_id)
        if not item_info: continue
        item_name = item_info.get("name")
        item_details = {"name": item_name, "image_url": item_info.get("image_url"), "cost": item_info.get("cost"), "popularity": f"{(count / len(champion_games) * 100):.0f}%"}
        if "Boots" in item_name and not build["boots"]:
            build["boots"] = item_details
        elif "Boots" not in item_name and "Potion" not in item_name and "Ward" not in item_name and len(core_items) < 5:
            core_items.append(item_details)
    build["core_items"] = core_items
    return build

@tool
def analyze_build_path(match_id: str, game_name: str, tag_line: str) -> list[dict]:
    """Shows the chronological order of items purchased for a user in a specific match."""
    match_data = _get_user_match_data(game_name, tag_line, match_id)
    if not match_data: return [{"error": f"Match {match_id} not found."}]
    items_list = load_json(ITEMS_DATA_FILE)
    item_lookup = {str(item['id']): item for item in items_list}
    item_events = match_data.get("item_events", [])
    if not item_events: return [{"error": "No item purchase events found."}]
    purchases = []
    for event in item_events:
        if event.get("type") == "ITEM_PURCHASED":
            item_id = str(event.get("itemId"))
            item_info = item_lookup.get(item_id)
            if item_info:
                purchases.append({"timestamp": event.get("timestamp", 0), "name": item_info.get("name"), "image_url": item_info.get("image_url")})
    if not purchases: return [{"error": "No valid item purchases found."}]
    build_path = []
    for timestamp, group in groupby(purchases, key=lambda x: x['timestamp']):
        items_in_trip = list(group)
        build_path.append({"timestamp_str": _ms_to_min_sec(timestamp), "items": items_in_trip})
    return build_path

@tool
def analyze_item_gold_spend(match_id: str, game_name: str, tag_line: str) -> dict:
    """Analyzes item purchases for a user in a specific match to calculate gold spent."""
    match_data = _get_user_match_data(game_name, tag_line, match_id)
    if not match_data: return {"error": f"Match {match_id} not found."}
    items_list = load_json(ITEMS_DATA_FILE)
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
    return {"vision_score": match_data.get("visionScore", 0), "wards_placed": match_data.get("wardsPlaced", 0), "wards_killed": match_data.get("wardsKilled", 0), "control_wards_bought": match_data.get("visionWardsBoughtInGame", 0), "control_wards_placed": sum(1 for e in vision_events if e.get('type') == 'PLACED' and e.get('ward_type') == 'CONTROL_WARD'), "stealth_wards_placed": sum(1 for e in vision_events if e.get('type') == 'PLACED' and e.get('ward_type') == 'SIGHT_WARD')}

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
                moment = (f"At {_ms_to_min_sec(death_time)}, a death was followed by the enemy taking a {obj_type} within a minute. This suggests the death created a critical opening.")
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
    """Finds the most common skill leveling order for a specific champion from pro games."""
    pro_data = load_json(PRO_DATA_FILE)
    if not pro_data: return f"Could not load pro player data to analyze {champion_name}."
    champion_games = [game for game in pro_data if game.get("champion", "").lower() == champion_name.lower()]
    if not champion_games: return f"No games found for {champion_name} in the database."
    all_skill_orders = [order for order in [game.get("skill_level_order", []) for game in champion_games] if order]
    if not all_skill_orders: return f"Skill level data is missing for {champion_name} games."
    common_order = []
    skill_map = {1: 'Q', 2: 'W', 3: 'E', 4: 'R'}
    for level in range(11):
        skills_at_this_level = [order[level] for order in all_skill_orders if len(order) > level]
        if not skills_at_this_level: break
        most_common_skill_slot = collections.Counter(skills_at_this_level).most_common(1)[0][0]
        common_order.append(skill_map.get(most_common_skill_slot, '?'))
    return " -> ".join(common_order)

@tool
def analyze_objective_proximity(match_id: str, game_name: str, tag_line: str) -> list[str]:
    """Analyzes a user's proximity to major objectives when they are taken."""
    match_data = _get_user_match_data(game_name, tag_line, match_id)
    if not match_data: return [f"Match {match_id} not found."]
    all_objectives = []
    for obj in match_data.get("ally_objective_takes", []):
        if "DRAGON" in obj.get("type", "") or "BARON_NASHOR" in obj.get("type", ""):
            all_objectives.append({**obj, "team": "Ally"})
    for obj in match_data.get("enemy_objective_takes", []):
        if "DRAGON" in obj.get("type", "") or "BARON_NASHOR" in obj.get("type", ""):
            all_objectives.append({**obj, "team": "Enemy"})
    if not all_objectives: return ["No Dragon or Baron takes were found in this game's timeline data."]
    pathing_data = match_data.get("full_game_pathing")
    if not pathing_data: return ["No pathing data available to analyze proximity."]
    insights = []
    for obj in sorted(all_objectives, key=itemgetter('timestamp')):
        obj_time = obj.get("timestamp", 0)
        obj_type = obj.get("type", "Objective").replace("_", " ").title()
        obj_pos = obj.get("position", {})
        closest_path_point = min(pathing_data, key=lambda p: abs(p['timestamp'] - obj_time))
        player_pos = closest_path_point.get("position")
        if not player_pos: continue
        distance = np.linalg.norm(np.array([player_pos['x'], player_pos['y']]) - np.array([obj_pos['x'], obj_pos['y']]))
        position_insight = "You were present at the objective." if distance < 3000 else "You were on the opposite side of the map." if distance > 8000 else "You were nearby, but not directly at the objective."
        insights.append(f"At {_ms_to_min_sec(obj_time)}, the {obj['team']} team took a {obj_type}. {position_insight}")
    return insights if insights else ["No relevant objective insights found."]

def get_comprehensive_game_analysis(match_id: str, game_name: str, tag_line: str) -> dict:
    """Performs a full analysis of a single game for a given user."""
    match_data = _get_user_match_data(game_name, tag_line, match_id)
    if not match_data: return {"error": f"Match {match_id} not found."}
    laning_phase_limit = 15 * 60 * 1000
    laning_kills = sum(1 for e in match_data.get("combat_events", []) if e['type'] == 'KILL' and e['timestamp'] <= laning_phase_limit)
    laning_assists = sum(1 for e in match_data.get("combat_events", []) if e['type'] == 'ASSIST' and e['timestamp'] <= laning_phase_limit)
    laning_stats = get_laning_phase_stats.func(match_id, game_name, tag_line)
    laning_stats['laning_kills'] = laning_kills
    laning_stats['laning_assists'] = laning_assists
    build_path = analyze_build_path.func(match_id, game_name, tag_line)
    vision_report = analyze_vision_control.func(match_id, game_name, tag_line)
    teamfight_map_path = plot_combat_heatmap(match_data)
    vision_report['vision_events_log'] = match_data.get("vision_events", [])
    analysis_report = {"match_summary": {"champion": match_data.get("champion"), "win": match_data.get("win"), "kills": match_data.get("kills"), "deaths": match_data.get("deaths"), "assists": match_data.get("assists"), "visionScore": match_data.get("visionScore")}, "laning_phase": laning_stats, "build_path": build_path, "vision_report": vision_report, "teamfight_map_path": teamfight_map_path}
    return analysis_report

@tool
def get_latest_match_id(game_name: str, tag_line: str) -> str:
    """Finds and returns the match_id of the most recent game from a user's match history."""
    filepath = _get_user_filepath(game_name, tag_line)
    user_data = load_json(filepath)
    if not user_data: return "No user data found. Please fetch games first."
    try:
        latest_game = user_data[-1]
        return latest_game.get('matchId')
    except (IndexError, TypeError, KeyError):
        return "Could not determine the latest game from the available data."

@tool
def generate_pathing_map_for_match(match_id: str, game_name: str, tag_line: str) -> str:
    """Generates a color-coded pathing map for a user's specific game."""
    match_data = _get_user_match_data(game_name, tag_line, match_id)
    if not match_data: return f"Could not find data for match {match_id}."
    output_path = plot_pathing_map(match_data)
    if output_path and os.path.exists(output_path):
        return f"Pathing map for match {match_id} has been generated and saved to {output_path}"
    else:
        return "An error occurred while trying to generate the pathing map."

@tool
def analyze_performance_trend(game_name: str, tag_line: str, metric: str, num_games: int = 10) -> dict:
    """Analyzes a user's performance trend for a specific metric over their last N games."""
    filepath = _get_user_filepath(game_name, tag_line)
    data = load_json(filepath)
    if not data or len(data) < 3: return {"error": "Not enough game data found to analyze a trend. Need at least 3 games."}
    metric_key = METRIC_NAME_MAP.get(metric.lower(), metric)
    recent_games = data[-num_games:]
    if len(recent_games) < 3: return {"error": f"Not enough recent games to analyze a trend. Need at least 3, found {len(recent_games)}."}
    values = [game.get(metric_key, 0) for game in recent_games]
    first_half = values[:len(values)//2]
    second_half = values[len(values)//2:]
    avg_first_half = np.mean(first_half)
    avg_second_half = np.mean(second_half)
    trend = "Stable"
    if avg_second_half > avg_first_half * 1.05: trend = "Upward"
    elif avg_second_half < avg_first_half * 0.95: trend = "Downward"
    return {"metric": metric_key, "trend": trend, "games_analyzed": len(values), "average_of_first_half": f"{avg_first_half:.2f}", "average_of_second_half": f"{avg_second_half:.2f}", "insight": f"Your performance for '{metric_key}' is on a(n) {trend.lower()} trend over the last {len(values)} games."}

@tool
def get_pro_matchup_advice(your_champion: str, enemy_champion: str) -> dict:
    """
    Provides advice for a support matchup based on pro player data.
    Analyzes win rate, KDA, and common first items for both your champion and the enemy champion.
    """
    pro_data = load_json(PRO_DATA_FILE)
    if not pro_data:
        return {"error": "Could not load pro player data."}

    matchup_games = [
        game for game in pro_data 
        if your_champion in [p['championName'] for p in game.get('allParticipants', [])] 
        and enemy_champion in [p['championName'] for p in game.get('allParticipants', [])]
    ]

    if not matchup_games:
        return {"error": f"No pro games found for the {your_champion} vs. {enemy_champion} matchup."}

    def calculate_stats(champion_name):
        wins, kills, deaths, assists, items = 0, 0, 0, 0, []
        for game in matchup_games:
            stats = next((p for p in game['allParticipants'] if p['championName'] == champion_name), None)
            if not stats: continue
            if stats.get('win'): wins += 1
            kills += stats.get('kills', 0)
            deaths += stats.get('deaths', 0)
            assists += stats.get('assists', 0)
            if stats.get('item0'): items.append(stats.get('item0'))
        
        num_games = len(matchup_games)
        win_rate = (wins / num_games) * 100 if num_games > 0 else 0
        avg_kda = f"{kills/num_games:.1f}/{deaths/num_games:.1f}/{assists/num_games:.1f}"
        
        common_item = "N/A"
        if items:
            item_id = collections.Counter(items).most_common(1)[0][0]
            items_list = load_json(ITEMS_DATA_FILE)
            item_info = next((item for item in items_list if str(item['id']) == str(item_id)), None)
            if item_info: common_item = item_info['name']
            
        return {"win_rate": f"{win_rate:.2f}%", "average_kda": avg_kda, "most_common_first_item": common_item}

    your_stats = calculate_stats(your_champion)
    enemy_stats = calculate_stats(enemy_champion)

    return {
        "matchup": f"{your_champion} vs. {enemy_champion}",
        "games_analyzed": len(matchup_games),
        "your_champion_stats": your_stats,
        "enemy_champion_stats": enemy_stats,
        "advice": f"In this matchup, {your_champion} has a {your_stats['win_rate']} win rate against {enemy_champion}. Your average KDA is {your_stats['average_kda']} vs. their {enemy_stats['average_kda']}. A common start is {your_stats['most_common_first_item']} while they often start with {enemy_stats['most_common_first_item']}."
    }

@tool
def analyze_gold_efficiency(match_id: str, game_name: str, tag_line: str) -> dict:
    """
    Analyzes the user's gold spending and GPM compared to their lane opponent and pros.
    """
    user_match_data = _get_user_match_data(game_name, tag_line, match_id)
    if not user_match_data: return {"error": f"Match {match_id} not found for the user."}

    champion_name = user_match_data.get("champion")
    if not champion_name: return {"error": "Champion name not found in user match data."}

    # Find user and enemy support in the participant list
    user_participant = next((p for p in user_match_data.get('allParticipants', []) if p['puuid'] == user_match_data['puuid']), None)
    if not user_participant: return {"error": "Could not find user's participant data."}
    
    enemy_support = next((p for p in user_match_data.get('allParticipants', []) if p['teamPosition'] == 'UTILITY' and p['teamId'] != user_participant['teamId']), None)

    # Calculate GPM
    duration_minutes = user_match_data.get("gameDuration", 0) / 60
    user_gpm = user_match_data.get("goldEarned", 0) / duration_minutes if duration_minutes > 0 else 0
    enemy_gpm = enemy_support.get("goldEarned", 0) / duration_minutes if enemy_support and duration_minutes > 0 else 0

    # Gold difference at 14 mins
    user_gold_at_14 = next((p['gold'] for p in user_match_data.get('gold_timeline', []) if p['timestamp'] >= 840000), 0)
    enemy_gold_at_14 = next((p['gold'] for p in enemy_support.get('gold_timeline', []) if p['timestamp'] >= 840000), 0) if enemy_support else 0
    gold_diff_at_14 = user_gold_at_14 - enemy_gold_at_14

    # Pro GPM
    pro_data = load_json(PRO_DATA_FILE)
    pro_games_on_champ = [g for g in pro_data if g.get("champion") == champion_name]
    pro_gpms = [game.get("goldEarned", 0) / (game.get("gameDuration", 1) / 60) for game in pro_games_on_champ]
    avg_pro_gpm = np.mean(pro_gpms) if pro_gpms else 0

    return {
        "your_champion": champion_name,
        "enemy_champion": enemy_support.get('championName') if enemy_support else "N/A",
        "your_gpm": f"{user_gpm:.2f}",
        "enemy_gpm": f"{enemy_gpm:.2f}",
        "pro_average_gpm": f"{avg_pro_gpm:.2f}",
        "gold_difference_at_14_mins": gold_diff_at_14,
        "comparison_insight": f"Your GPM was {user_gpm:.2f} vs. your opponent's {enemy_gpm:.2f}. At 14 minutes, you had a gold difference of {gold_diff_at_14}. The pro average GPM for {champion_name} is {avg_pro_gpm:.2f}."
    }