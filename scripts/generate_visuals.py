# generate_visuals.py

import os
import sys
# Add project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.utils.utils import load_json
from src.analysis.plotter import plot_roaming_trend, plot_death_locations, create_game_animation

# --- CONFIGURATION ---
MERGED_DATA_PATH = "data/pro_players_merged.json"
# Set to True to generate animations.
GENERATE_ANIMATIONS = True 
# Set how many games you want to process. Use a small number for testing.
GAMES_TO_PROCESS = 3 

# In generate_visuals.py

def main():
    """
    Main function to load data and generate visuals for each game.
    """
    print("Loading merged player data...")
    all_games = load_json(MERGED_DATA_PATH)

    if not all_games:
        print(f"No data found in {MERGED_DATA_PATH}. Please run the data manager first.")
        return
        
    games_to_visualize = all_games[:GAMES_TO_PROCESS]
    print(f"Found {len(all_games)} total games. Processing the first {len(games_to_visualize)} games.")

    for i, game in enumerate(games_to_visualize):
        match_id = game.get("matchId", f"unknown_match_{i}")
        champion = game.get("champion", "Unknown")
        
        # --- NEW: Get player name and create a descriptive base filename ---
        # Replace spaces with underscores for cleaner filenames
        player_name = game.get("proPlayerName", "UnknownPlayer").replace(" ", "_")
        base_filename = f"{player_name}_{champion}_{match_id}"

        print(f"\n--- Processing visuals for {match_id} ({champion}) ---")

        # 1. Generate roaming trend plot with the new name
        plot_roaming_trend(game, output_filename=f"{base_filename}_roaming.png")

        # 2. Generate death location plot with the new name
        plot_death_locations([game], output_filename=f"{base_filename}_deaths.png")

        # 3. Generate GIF animation with the new name (if enabled)
        if GENERATE_ANIMATIONS:
            create_game_animation(game, output_filename=f"{base_filename}_animation.gif")

    print("\n--- Visual generation complete! ---")
    print(f"Check the '{os.path.join('data', 'plots')}' directory for your files.")


if __name__ == "__main__":
    main()