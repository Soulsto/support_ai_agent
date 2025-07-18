import streamlit as st
import pandas as pd
import os
import sys
import json
import re
import requests

# --- PATH SETUP ---
# Add the project root to the Python path to allow imports from `src`.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.utils import load_json
from src.agent.main_agent import create_agent_executor
from src.api_client.live_fetcher import fetch_and_analyze_player_data
from src.analysis.plotter import plot_pathing_map, plot_death_locations, create_game_animation, plot_metric
from src.agent.tools import (
    get_pro_build_for_champion, 
    get_comprehensive_game_analysis,
    get_pro_matchup_advice,
    analyze_gold_efficiency,
    analyze_performance_trend
)
# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="LoL Support Agent", layout="wide")

# --- UI Functions ---
def display_game_analysis(analysis_data):
    """(Upgraded) Takes the analysis dictionary and displays it in a beautiful, structured UI."""
    summary = analysis_data.get("match_summary", {})
    st.header(f"Game Analysis: {summary.get('champion')}")

    if summary.get('win'):
        st.success("Result: Victory")
    else:
        st.error("Result: Defeat")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Kills", summary.get('kills'))
    col2.metric("Deaths", summary.get('deaths'))
    col3.metric("Assists", summary.get('assists'))
    col4.metric("Vision Score", summary.get('visionScore'))
    st.divider()

    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("Laning Phase (First 14 Mins)")
        laning = analysis_data.get('laning_phase', {})
        st.write(f"Kills: **{laning.get('laning_kills', 'N/A')}** | Assists: **{laning.get('laning_assists', 'N/A')}** | Deaths: **{laning.get('deaths_before_14_mins', 'N/A')}**")
        
        st.subheader("Vision Report")
        vision = analysis_data.get('vision_report', {})
        st.write(f"Total Vision Score: **{vision.get('vision_score', 'N/A')}** | Control Wards Placed: **{vision.get('control_wards_placed', 'N/A')}** | Wards Killed: **{vision.get('wards_killed', 'N/A')}**")

    with col_right:
        st.subheader("Teamfight Positioning Map")
        map_path = analysis_data.get('teamfight_map_path')
        if map_path and os.path.exists(map_path):
            st.image(map_path, caption="Blue '+' = Kills/Assists | Red '✖' = Deaths")
        else:
            st.info("No combat data to generate a map for this game.")
    st.divider()
    
    # --- UPDATED: Item Build Path Section ---
    st.subheader("Item Build Path (Shopping Trips)")
    build_trips = analysis_data.get('build_path', [])
    
    if build_trips and isinstance(build_trips, list) and len(build_trips) > 0 and "error" not in build_trips[0]:
        for trip in build_trips:
            if "items" in trip and trip["items"]:
                # Use a two-column layout for each trip for better alignment
                time_col, items_col = st.columns([1, 5]) 
                
                with time_col:
                    st.markdown(f"**{trip.get('timestamp_str')}**")
                
                with items_col:
                    # Create sub-columns for the item images within the right column
                    item_cols = st.columns(len(trip['items']))
                    for i, item in enumerate(trip.get('items', [])):
                        with item_cols[i]:
                            st.image(item.get('image_url'), width=48, caption=item.get('name'))
                st.divider() # Add a small divider between each shopping trip
    else:
        st.info("No item purchase data was found for this match.")

# --- DATA & AGENT LOADING ---
@st.cache_data
def load_pro_data():
    return pd.DataFrame(load_json("data/pro_players_merged.json"))

@st.cache_resource
def get_agent():
    return create_agent_executor()

def _ms_to_min_sec(ms: int) -> str:
    total_seconds = int(ms / 1000)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

# Get the backend URL from an environment variable, with a fallback for local development
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# --- MAIN APP ---
st.title("League of Legends Support Agent 🛡️")

if 'user_games' not in st.session_state:
    st.session_state.user_games = pd.DataFrame()
if 'current_user' not in st.session_state:
    st.session_state.current_user = None

# --- SIDEBAR ---
with st.sidebar:
    st.header("Fetch Your Game Data")
    with st.form("user_input_form"):
        game_name = st.text_input("Your Riot ID")
        tag_line = st.text_input("Your Tagline")
        region = st.selectbox("Region", ["europe", "americas", "asia"])
        fetch_button = st.form_submit_button("Fetch My Games")

    if fetch_button and game_name and tag_line:
        with st.spinner(f"Fetching games for {game_name}#{tag_line}..."):
            newly_fetched_games = fetch_and_analyze_player_data(game_name, tag_line, region)
            if isinstance(newly_fetched_games, list):
                sanitized_name = game_name.replace(" ", "_")
                user_file_path = f"data/users/{sanitized_name}_{tag_line}.json"
                os.makedirs("data/users", exist_ok=True)
                if os.path.exists(user_file_path): existing_games = load_json(user_file_path)
                else: existing_games = []
                existing_match_ids = {game['matchId'] for game in existing_games}
                unique_new_games = [g for g in newly_fetched_games if g['matchId'] not in existing_match_ids]
                combined_games = existing_games + unique_new_games
                with open(user_file_path, 'w') as f: json.dump(combined_games, f, indent=4)
                st.session_state.user_games = pd.DataFrame(combined_games)
                st.session_state.current_user = {"game_name": game_name, "tag_line": tag_line}
                st.success(f"Added {len(unique_new_games)} new games for {game_name}#{tag_line}.")
            else:
                st.error("Player not found. Please check your inputs.")

# --- TABS FOR DISPLAY ---
tabs = st.tabs([
    "🤖 AI Coach", 
    "📊 Game Analysis Dashboard", 
    "🧪 New Agent Tools", 
    "📂 Your Game Data", 
    "⚡ Pro Player Build"
])

with tabs[0]: # AI Coach
    st.header("Chat with your AI Support Coach")
    support_coach_agent = get_agent()
    
    if support_coach_agent is None:
        st.error("The AI Coach could not be initialized. Please check your API keys and restart.")
    elif st.session_state.current_user:
        st.info(f"Currently analyzing for user: **{st.session_state.current_user['game_name']}#{st.session_state.current_user['tag_line']}**")
        with st.form(key="chat_form"):
            user_question = st.text_area("Ask a specific question:", placeholder="e.g., Generate my pathing in my last game, or give me advice for using Thresh.")
            submit_button = st.form_submit_button(label="Get Advice")

        if submit_button and user_question:
            current_user = st.session_state.current_user
            contextual_prompt = (f"For the user with game_name='{current_user['game_name']}' and tag_line='{current_user['tag_line']}', answer the following question: {user_question}")
            with st.spinner("The coach is thinking..."):
                result = support_coach_agent.invoke({"input": contextual_prompt})
                st.markdown(result['output'])

                # Find and display any images the agent created
                image_paths = re.findall(r"data/plots/[\w.-]+\.(?:png|gif)", result['output'])
                if image_paths:
                    for image_path in image_paths:
                        if os.path.exists(image_path):
                            st.image(image_path)
                        else:
                            st.warning(f"Agent mentioned an image, but it was not found at path: {image_path}")
    else:
        st.warning("Please fetch your game data from the sidebar to activate the AI Coach.")

with tabs[1]: # Game Analysis Dashboard
    st.header("Single Game Deep Dive")
    if not st.session_state.user_games.empty and st.session_state.current_user:
        user_games_df = st.session_state.user_games
        descriptive_options = [f"{game.get('champion', 'Unknown')} - {game.get('matchId')}" for game in user_games_df.to_dict('records')]
        selected_option = st.selectbox("Select one of your games to analyze:", options=descriptive_options)
        
        if st.button("Analyze This Game"):
            if selected_option:
                selected_match_id = selected_option.split(" - ")[1]
                current_user = st.session_state.current_user
                
                with st.spinner(f"Performing analysis via API for {selected_match_id}..."):
                    api_url = f"{BACKEND_URL}/analyze-game/{current_user['game_name']}/{current_user['tag_line']}/{selected_match_id}"
                    try:
                        response = requests.get(api_url)
                        if response.status_code == 200:
                            analysis_result = response.json()
                            display_game_analysis(analysis_result)
                        else:
                            st.error(f"Error from API: {response.json().get('detail', 'Unknown error')}")
                    except requests.exceptions.ConnectionError:
                        st.error("Connection Error: Could not connect to the API. Is the backend server running?")
                        st.code("To run the backend, use this command in a new terminal:\n\nuvicorn backend.main:app --reload")
    else:
        st.info("Fetch your game data from the sidebar to begin analysis.")

with tabs[2]: # New Agent Tools
    st.header("New Feature Testing")
    if not st.session_state.current_user:
        st.warning("Please fetch your game data from the sidebar to use these tools.")
    else:
        st.info(f"Testing for user: **{st.session_state.current_user['game_name']}#{st.session_state.current_user['tag_line']}**")
        
        # --- 1. Matchup Advisor ---
        st.subheader("⚔️ Pro Matchup Advisor")
        col1, col2 = st.columns(2)
        with col1:
            your_champ = st.text_input("Your Support Champion", "Nami")
        with col2:
            enemy_champ = st.text_input("Enemy Support Champion", "Blitzcrank")
        if st.button("Get Matchup Advice"):
            with st.spinner("The coach is thinking about this matchup..."):
                advice = get_pro_matchup_advice.func(your_champion=your_champ, enemy_champion=enemy_champ)
                if "error" in advice:
                    st.error(advice["error"])
                else:
                    st.header(advice.get("matchup", "Matchup Advice"))
                    st.markdown(advice.get("advice", "No advice could be generated."))
        st.divider()

        # --- 3. Gold Efficiency ---
        st.subheader("💰 Gold Efficiency Analysis")
        if not st.session_state.user_games.empty:
            # Create descriptive options for the dropdown
            user_games_df = st.session_state.user_games
            descriptive_options_gold = [f"{game.get('champion', 'Unknown')} - {game.get('matchId')}" for game in user_games_df.to_dict('records')]
            selected_option_gold = st.selectbox("Select a Game for Gold Analysis", options=descriptive_options_gold, key="gold_eff_select")
            
            if st.button("Analyze Gold Efficiency"):
                if selected_option_gold:
                    # Extract the match_id from the selected string
                    selected_match_id_gold = selected_option_gold.split(" - ")[1]
                    with st.spinner("Analyzing gold..."):
                        current_user = st.session_state.current_user
                        gold_data = analyze_gold_efficiency.func(match_id=selected_match_id_gold, game_name=current_user['game_name'], tag_line=current_user['tag_line'])
                        if "error" in gold_data:
                            st.error(gold_data["error"])
                        else:
                            st.metric(label=f"Your GPM on {gold_data['your_champion']}", value=gold_data['your_gpm'], delta=f"{float(gold_data['your_gpm']) - float(gold_data['pro_average_gpm']):.2f} vs Pro Avg")
                            st.write(f"Pro Average GPM: {gold_data['pro_average_gpm']}")
        else:
            st.info("No games loaded to analyze gold for.")
        st.divider()

        # --- 4. Performance Trend ---
        st.subheader("📈 Performance Trend")
        metric_options = ["visionScore", "killParticipation", "deaths", "assists", "wardsPlaced", "wardsKilled"]
        selected_metric = st.selectbox("Select a metric to track your trend:", options=metric_options)
        if st.button("Analyze My Trend"):
            with st.spinner("Analyzing your game history..."):
                current_user = st.session_state.current_user
                trend_data = analyze_performance_trend.func(game_name=current_user['game_name'], tag_line=current_user['tag_line'], metric=selected_metric)
                if "error" in trend_data:
                    st.error(trend_data["error"])
                else:
                    st.write(f"**Trend for {trend_data['metric']} over the last {trend_data['games_analyzed']} games:**")
                    st.metric(label="Trend Direction", value=trend_data['trend'])
                    st.write(f"Older Games Avg: {trend_data['average_of_first_half']} -> Newer Games Avg: {trend_data['average_of_second_half']}")
                    st.info(trend_data['insight'])

with tabs[3]: # Raw Game Data
    st.header("Your Full Game Data")
    if not st.session_state.user_games.empty:
        st.dataframe(st.session_state.user_games)
    else:
        st.info("No user data loaded.")

with tabs[4]: # FastAPI
    st.header("Pro Player Build Explorer")
    pro_df = load_pro_data()

    if pro_df.empty:
        st.warning("Pro player data is not available.")
    else:
        champions = sorted(pro_df['champion'].unique())
        selected_champion_build = st.selectbox("Choose a champion to see their pro build:", options=champions)

        if selected_champion_build:
            with st.spinner(f"Finding most common build for {selected_champion_build}..."):
                api_url = f"{BACKEND_URL}/pro-build/{selected_champion_build}"
                try:
                    response = requests.get(api_url)
                    if response.status_code == 200:
                        build_data = response.json()
                        st.subheader(f"Most Common Pro Build for {build_data.get('champion')}")
                        st.caption(f"Based on {build_data.get('games_analyzed')} pro games.")
                        cols = st.columns(6)
                        if build_data.get("boots") and build_data["boots"].get("image_url"):
                            with cols[0]:
                                st.image(build_data["boots"]["image_url"], width=64)
                                st.caption(f"{build_data['boots']['name']}")
                        for i, item in enumerate(build_data.get("core_items", [])):
                            if i < 5 and item.get("image_url"):
                                with cols[i+1]:
                                    st.image(item["image_url"], width=64)
                                    st.caption(f"{item['name']} ({item['popularity']})")
                    else:
                        st.error(f"Error fetching data from API: Status code {response.status_code}")
                except requests.exceptions.ConnectionError as e:
                    st.error(f"Connection Error: Could not connect to the API. Is the backend server running?")
                    st.code("To run the backend, use this command in a new terminal: uvicorn backend.main:app --reload")
