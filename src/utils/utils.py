"""
utils.py - Common utility functions for the project.

This module provides helper functions for common tasks like reading data
from files, ensuring that this logic is centralized and reusable.
"""

import json
import logging
from typing import List, Dict, Any

# Set up a logger for this module
logger = logging.getLogger(__name__)

def load_json(file_path: str) -> List[Dict[str, Any]]:
    """
    Loads data from a JSON file with robust error handling.

    Args:
        file_path: The path to the JSON file.

    Returns:
        The loaded data as a Python list of dictionaries, or an empty list
        if the file is not found or contains invalid JSON.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"File not found: {file_path}. Returning empty list.")
        return []
    except json.JSONDecodeError:
        logger.error(f"Failed to decode JSON from {file_path}. Returning empty list.")
        return []
    except Exception as e:
        logger.error(f"An unexpected error occurred loading {file_path}: {e}")
        return []