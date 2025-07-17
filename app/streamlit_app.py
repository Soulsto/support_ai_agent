import streamlit as st
import pandas as pd
import os
import sys
import json
import re

# --- PATH SETUP ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from agent.utils import load_json
from langchain_agent.main_agent import create_agent_executor
from agent.live_fetcher import fetch_and_analyze_player_data
from agent.tools import get_comprehensive_game_analysis

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
tab1, tab2, tab3 = st.tabs(["🤖 AI Coach ", "📊 Game Analysis Dashboard", "📂 Raw Game Data"])

with tab1:
    st.header("Chat with your AI Support Coach")
    support_coach_agent = get_agent()
    
    if support_coach_agent is None:
        st.error("The AI Coach could not be initialized. Please check your API keys and restart.")
    elif st.session_state.current_user:
        st.info(f"Currently analyzing for user: **{st.session_state.current_user['game_name']}#{st.session_state.current_user['tag_line']}**")
        with st.form(key="chat_form"):
            user_question = st.text_area("Ask a specific question:", placeholder="e.g., Generate my pathing in my last game")
            submit_button = st.form_submit_button(label="Get Advice")

        if submit_button and user_question:
            current_user = st.session_state.current_user
            contextual_prompt = (f"For the user with game_name='{current_user['game_name']}' and tag_line='{current_user['tag_line']}', answer the following question: {user_question}")
            with st.spinner("The coach is thinking..."):
                result = support_coach_agent.invoke({"input": contextual_prompt})
                st.markdown(result['output'])

                # --- NEW LOGIC: Find and display any images the agent created ---
                image_paths = re.findall(r"data/plots/[\w.-]+\.(?:png|gif)", result['output'])
                if image_paths:
                    for image_path in image_paths:
                        if os.path.exists(image_path):
                            st.image(image_path)
                        else:
                            st.warning(f"Agent mentioned an image, but it was not found at path: {image_path}")
    else:
        st.warning("Please fetch your game data from the sidebar to activate the AI Coach.")


with tab2:
    st.header("Single Game Deep Dive")
    if not st.session_state.user_games.empty and st.session_state.current_user:
        user_games_df = st.session_state.user_games
        match_ids = user_games_df['matchId'].tolist()
        descriptive_options = [f"{game.get('champion', 'Unknown')} - {game.get('matchId')}" for game in user_games_df.to_dict('records')]
        selected_option = st.selectbox("Select one of your games to analyze:", options=descriptive_options)
        
        if st.button("Analyze This Game"):
            if selected_option:
                selected_match_id = selected_option.split(" - ")[1]
                with st.spinner(f"Performing analysis on {selected_match_id}..."):
                    analysis_result = get_comprehensive_game_analysis(match_id=selected_match_id, game_name=st.session_state.current_user['game_name'], tag_line=st.session_state.current_user['tag_line'])
                    if "error" in analysis_result:
                        st.error(analysis_result["error"])
                    else:
                        display_game_analysis(analysis_result)
    else:
        st.info("Fetch your game data from the sidebar to begin analysis.")

with tab3:
    st.header("Your Full Game Data")
    if not st.session_state.user_games.empty:
        st.dataframe(st.session_state.user_games)
    else:
        st.info("No user data loaded.")