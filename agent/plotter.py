import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import numpy as np
import os
from matplotlib.animation import FuncAnimation
from .utils import load_json

# Define paths
ASSETS_DIR = "assets"
OUTPUT_DIR = "data/plots"
MAP_IMAGE_PATH = os.path.join(ASSETS_DIR, "summoners_rift_map.webp")

# Ensure the output directory for plots exists
os.makedirs(OUTPUT_DIR, exist_ok=True)


def plot_metric(user_data: list[dict], pro_data: list[dict], metric: str, user_label: str = "Your Stats"):
    """
    Creates a bar chart and returns the Matplotlib figure object.
    """
    if not user_data:
        print(f"Error: No user data provided for metric '{metric}'.")
        return None

    # Calculate averages
    user_values = [game.get(metric, 0) for game in user_data]
    user_avg = np.mean(user_values) if user_values else 0

    pro_values = [game.get(metric, 0) for game in pro_data]
    pro_avg = np.mean(pro_values) if pro_values else 0

    # Create the figure and axes objects
    plt.style.use('dark_background')
    fig, ax = plt.subplots()
    
    # Plot the data on the axes
    bars = ax.bar([user_label, "Pro Average"], [user_avg, pro_avg], color=['#00aaff', '#ffaa00'])
    ax.bar_label(bars, fmt='{:,.2f}')

    ax.set_ylabel(metric.replace("_", " ").title())
    ax.set_title(f"Comparison of {metric.replace('_', ' ').title()}")
    
    # Return the figure object for Streamlit to display
    return fig

def plot_death_locations(all_matches_data: list[dict]):
    """
    Creates a death locations plot and returns the Matplotlib figure object.
    """
    all_deaths = []
    for match in all_matches_data:
        death_positions = match.get("death_positions", [])
        if death_positions:
            all_deaths.extend(death_positions)

    if not all_deaths:
        print("No death location data found to plot.")
        return None

    try:
        img = mpimg.imread(MAP_IMAGE_PATH)
    except FileNotFoundError:
        print(f"Error: Map image not found at {MAP_IMAGE_PATH}")
        return None

    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.imshow(img, extent=[0, 15000, 0, 15000])

    x_coords = [death['position']['x'] for death in all_deaths if 'position' in death and 'x' in death['position']]
    y_coords = [death['position']['y'] for death in all_deaths if 'position' in death and 'y' in death['position']]

    ax.scatter(x_coords, y_coords, color='red', s=100, alpha=0.5, edgecolors='white', linewidth=0.5)
    ax.set_title("Player Death Locations")
    ax.set_xlim(0, 15000)
    ax.set_ylim(0, 15000)
    plt.xticks([])
    plt.yticks([])

    return fig # <-- Return the figure object


def create_game_animation(match_data: dict, output_filename: str = "path_animation.gif"):
    """
    (Upgraded) Creates a slower, smoother GIF animation of a single game.
    """
    pathing_data = match_data.get("full_game_pathing")
    death_positions = match_data.get("death_positions", [])

    if not pathing_data:
        print(f"Error: No 'full_game_pathing' data for animation.")
        return None

    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 10))
    # ... (the rest of the setup code is the same) ...
    plt.xticks([])
    plt.yticks([])
    try:
        img = mpimg.imread(MAP_IMAGE_PATH)
        ax.imshow(img, extent=[0, 15000, 0, 15000])
    except FileNotFoundError:
        print(f"Warning: Map image not found at {MAP_IMAGE_PATH}")
    ax.set_title(f"Game Animation: {match_data.get('champion', 'N/A')} ({match_data.get('matchId')})")
    path_line, = ax.plot([], [], '-', color='cyan', linewidth=2)
    player_dot, = ax.plot([], [], 'o', color='white', markersize=10)
    death_plot, = ax.plot([], [], 'X', color='red', markersize=15, linestyle='None', markeredgecolor='white')
    x_path = [p['position']['x'] for p in pathing_data]
    y_path = [p['position']['y'] for p in pathing_data]

    def update(frame):
        path_line.set_data(x_path[:frame+1], y_path[:frame+1])
        player_dot.set_data([x_path[frame]], [y_path[frame]])
        current_timestamp = pathing_data[frame]['timestamp']
        past_deaths = [d['position'] for d in death_positions if d.get('timestamp', 0) <= current_timestamp]
        if past_deaths:
            death_x = [pos['x'] for pos in past_deaths]
            death_y = [pos['y'] for pos in past_deaths]
            death_plot.set_data(death_x, death_y)
        return path_line, player_dot, death_plot

    num_frames = len(pathing_data)
    
    # --- NEW: Slower animation settings ---
    # We now step by 2 frames (smoother) and have a longer delay (slower).
    ani = FuncAnimation(fig, update, frames=range(0, num_frames, 2), blit=False, interval=150, repeat=False)

    output_path = os.path.join(OUTPUT_DIR, output_filename)
    print(f"Saving animation to {output_path}. This may take a while...")
    try:
        ani.save(output_path, writer='pillow', dpi=100)
        print(f"Successfully saved {output_filename}")
        plt.close(fig)
        return output_path
    except Exception as e:
        print(f"\nError saving animation: {e}")
        plt.close(fig)
        return None
    
def plot_combat_heatmap(match_data: dict) -> str | None:
    """
    Generates a map showing Kills/Assists (blue) vs. Deaths (red) for a single game.
    """
    combat_events = match_data.get("combat_events", [])
    death_events = match_data.get("death_positions", [])
    match_id = match_data.get("matchId", "unknown_match")
    
    if not combat_events and not death_events:
        print(f"No combat or death data to plot for match {match_id}.")
        return None

    try:
        img = mpimg.imread(MAP_IMAGE_PATH)
    except FileNotFoundError:
        print(f"Error: Map image not found at {MAP_IMAGE_PATH}")
        return None

    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.imshow(img, extent=[0, 15000, 0, 15000])

    # Plot Kills and Assists in Blue
    kx = [e['position']['x'] for e in combat_events if 'position' in e]
    ky = [e['position']['y'] for e in combat_events if 'position' in e]
    ax.scatter(kx, ky, color='cyan', s=80, alpha=0.8, marker='+', label='Kills/Assists')

    # Plot Deaths in Red
    dx = [e['position']['x'] for e in death_events if 'position' in e]
    dy = [e['position']['y'] for e in death_events if 'position' in e]
    ax.scatter(dx, dy, color='red', s=100, alpha=0.8, marker='x', label='Deaths')

    ax.set_title(f"Combat Positioning Map - {match_id}")
    ax.set_xlim(0, 15000)
    ax.set_ylim(0, 15000)
    ax.legend()
    plt.xticks([])
    plt.yticks([])

    output_filename = f"{match_id}_combat_map.png"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    plt.savefig(output_path, bbox_inches='tight', dpi=200)
    plt.close(fig)
    print(f"Combat map saved to {output_path}")
    
    return output_path

def plot_pathing_map(match_data: dict) -> str | None:
    """
    (Upgraded) Creates and saves a map showing the player's full path,
    color-coded by game phase. Returns the path to the saved file.
    """
    pathing_data = match_data.get("full_game_pathing")
    match_id = match_data.get("matchId", "unknown_match")
    if not pathing_data or len(pathing_data) < 2:
        print("Not enough pathing data to create a map.")
        return None

    # ... (The logic for segmenting the path and setting up the plot is the same)
    EARLY_GAME_END = 14 * 60 * 1000
    MID_GAME_END = 25 * 60 * 1000
    early_path = [p['position'] for p in pathing_data if p['timestamp'] <= EARLY_GAME_END]
    mid_path = [p['position'] for p in pathing_data if EARLY_GAME_END < p['timestamp'] <= MID_GAME_END]
    late_path = [p['position'] for p in pathing_data if p['timestamp'] > MID_GAME_END]
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.set_title(f"Full Game Pathing Map - Champion: {match_data.get('champion', 'N/A')}")
    plt.xticks([]); plt.yticks([])
    try:
        img = mpimg.imread(MAP_IMAGE_PATH)
        ax.imshow(img, extent=[0, 15000, 0, 15000])
    except FileNotFoundError:
        print(f"Warning: Map image not found at {MAP_IMAGE_PATH}")
    if len(early_path) > 1:
        x, y = zip(*[(p['x'], p['y']) for p in early_path]); ax.plot(x, y, color='#e6e600', linewidth=2, label='Early Game (0-14m)', alpha=0.8)
    if len(mid_path) > 1:
        x, y = zip(*[(p['x'], p['y']) for p in mid_path]); ax.plot(x, y, color='#00e6e6', linewidth=2.5, label='Mid Game (14-25m)', alpha=0.9)
    if len(late_path) > 1:
        x, y = zip(*[(p['x'], p['y']) for p in late_path]); ax.plot(x, y, color='#ff3333', linewidth=3, label='Late Game (25m+)', alpha=1.0)
    ax.legend(loc="upper right", facecolor="black", framealpha=0.7)
    ax.set_xlim(0, 15000); ax.set_ylim(0, 15000)

    # --- NEW: Save the file and return the path ---
    output_filename = f"{match_id}_pathing_map.png"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    plt.savefig(output_path, bbox_inches='tight', dpi=200)
    plt.close(fig)
    print(f"Pathing map saved to {output_path}")
    return output_path