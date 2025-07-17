import requests
import json
from bs4 import BeautifulSoup
import logging
import re

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def clean_html(html_string):
    """
    Uses BeautifulSoup to strip HTML tags from a string.
    """
    soup = BeautifulSoup(html_string, 'html.parser')
    # Replace <br> tags with spaces for better readability
    for br in soup.find_all("br"):
        br.replace_with(" ")
    # Remove all other HTML tags
    text = soup.get_text(separator=' ')
    # Clean up extra spaces and newlines
    return re.sub(r'\s+', ' ', text).strip()

def scrape_lol_items():
    """
    Fetches League of Legends item data from the official Riot Data Dragon API
    and saves it to a JSON file.
    """
    try:
        # --- Step 1: Get the latest patch version ---
        versions_url = "https://ddragon.leagueoflegends.com/api/versions.json"
        logging.info(f"Fetching latest patch version from {versions_url}...")
        versions_response = requests.get(versions_url)
        versions_response.raise_for_status()
        # The first version in the list is the latest one
        latest_version = versions_response.json()[0]
        logging.info(f"Latest patch version is: {latest_version}")

        # --- Step 2: Fetch the item data for the latest patch ---
        items_url = f"http://ddragon.leagueoflegends.com/cdn/{latest_version}/data/en_US/item.json"
        logging.info(f"Fetching item data from {items_url}...")
        items_response = requests.get(items_url)
        items_response.raise_for_status()
        items_raw = items_response.json()['data']

        # --- Step 3: Process the raw item data into a clean format ---
        processed_items = []
        logging.info(f"Found {len(items_raw)} items. Processing each one...")

        for item_id, item_details in items_raw.items():
            # Construct the full image URL
            image_url = f"http://ddragon.leagueoflegends.com/cdn/{latest_version}/img/item/{item_details['image']['full']}"
            
            # Skip trinkets and tutorial items which often lack a cost
            if not item_details['gold']['purchasable']:
                continue

            item_data = {
                "id": int(item_id),
                "name": item_details.get('name'),
                # The 'description' contains HTML, so we clean it for a plain text version
                "description": clean_html(item_details.get('description', '')),
                "plaintext": item_details.get('plaintext', ''), # Data Dragon provides a plaintext version too
                "cost": item_details.get('gold', {}).get('total'),
                "image_url": image_url
            }
            processed_items.append(item_data)

        # --- Step 4: Save the processed data to a JSON file ---
        output_filename = 'items.json'
        # Sort items by name for consistent output
        processed_items.sort(key=lambda x: x['name'])
        
        with open(output_filename, 'w', encoding='utf-8') as f:
            # Use indent=4 for pretty-printing the JSON
            json.dump(processed_items, f, ensure_ascii=False, indent=4)
        
        logging.info(f"Successfully saved {len(processed_items)} items to {output_filename}")

    except requests.exceptions.RequestException as e:
        logging.error(f"An error occurred during the request: {e}")
    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode JSON: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    scrape_lol_items()
