from fastapi import FastAPI, HTTPException
import sys
import os

# --- PATH SETUP ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from agent.tools import get_pro_build_for_champion, get_comprehensive_game_analysis


# Create the FastAPI app instance
app = FastAPI()

# --- API ENDPOINTS ---

@app.get("/")
def read_root():
    """ A simple endpoint to confirm the API is running. """
    return {"message": "Welcome to the LoL Support Agent API"}

@app.get("/pro-build/{champion_name}")
def get_pro_build(champion_name: str):
    """
    This endpoint finds the most common item build for a specific champion
    by calling our existing tool function.
    """
    # We use .func() to call the raw Python function directly
    build_data = get_pro_build_for_champion.func(champion_name=champion_name)
    return build_data

# --- NEW: Comprehensive Game Analysis Endpoint ---
@app.get("/analyze-game/{game_name}/{tag_line}/{match_id}")
def analyze_single_game(game_name: str, tag_line: str, match_id: str):
    """
    This endpoint performs a full analysis of a single game for a given user.
    """
    # We call the helper function directly
    analysis_data = get_comprehensive_game_analysis(
        match_id=match_id,
        game_name=game_name,
        tag_line=tag_line
    )
    if "error" in analysis_data:
        raise HTTPException(status_code=404, detail=analysis_data["error"])
    return analysis_data