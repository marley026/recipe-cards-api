from fastapi import FastAPI
from bs4 import BeautifulSoup
import datetime
import extruct
import html
import pytz
import requests
from urllib.parse import urlparse
from w3lib.html import get_base_url

app = FastAPI()
def sanitize_text(value):
    if not isinstance(value, str):
        return value
    # Unescape HTML (e.g., &amp;)
    value = html.unescape(value)
    # Replace non-breaking spaces with regular spaces
    value = value.replace('\xa0', ' ')
    # Strip leading/trailing whitespace
    return value.strip()

def sanitize_json(obj):
    if isinstance(obj, dict):
        return {k: sanitize_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_json(item) for item in obj]
    elif isinstance(obj, str):
        return sanitize_text(obj)
    else:
        return obj
    
def format_json(json, url, site):
    jsonFields = ["name", "description", "author", "image", "totalTime", "prepTime", "cookTime", "recipeYield", "recipeCategory", "recipeCuisine", "keywords", "aggregateRating", "recipeIngredient", "recipeInstructions", "publisher", "copyrightHolder"]

    final = {}
    for field in jsonFields:
        value = json.get(field)
        if value:
            final[field] = value
    
    final['url'] = url
    if not final.get('publisher'):
        final['publisher'] = {}
        final['publisher']['name'] = site

    """
    if not final.get('image'):
        try:
            image = get_recipe_content(url, 'image')
        except RuntimeError:
            image = None
        if image:
            final['image'] = image
    """

    final['dateSaved'] = datetime.datetime.now(pytz.utc).timestamp()

    return sanitize_json(final)

def get_recipe_content(url, fetch_type):
    # Add header to mimic a browser connection
    headers = {"Cache-Control":"max-age=0","Upgrade-Insecure-Requests":"1","User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7","Sec-Fetch-Site":"same-origin","Sec-Fetch-Mode":"navigate","Sec-Fetch-User":"?1","Sec-Fetch-Dest":"document","Accept-Encoding":"gzip, deflate","Accept-Language":"en-US,en;q=0.9"}
    # Get website HTML
    try:
        response = requests.get(url, headers=headers)
    except requests.exceptions.MissingSchema:
        return {"status": 400, "error": "Invalid URL format (missing http/https)"}
    except requests.exceptions.InvalidURL:
        return {"status": 400, "error": "Malformed URL"}
    except requests.exceptions.ConnectionError:
        return {"status": 502, "error": "Could not connect to host"}
    except requests.exceptions.Timeout:
        return {"status": 504, "error": "Request timed out"}
    except requests.exceptions.HTTPError as e:
        return {"status": response.status_code, "error": f"HTTP error: {str(e)}"}
    except Exception as e:
        return {"status": 500, "error": f"Unexpected error: {str(e)}"}
    
    if response.status_code == 200:
        # Replace relative urls with absolute url
        base_url = get_base_url(response.text, response.url)
        data = extruct.extract(response.text, base_url=base_url)

        if fetch_type == 'recipe':
            # Check for JSON-LD  ---  Should work with most websites schema.org
            for item in data.get('json-ld', []):
                # Get site name
                soup = BeautifulSoup(response.text, "html.parser")
                site_name = soup.find("meta", property="og:site_name")
                if site_name and site_name.get("content"):
                    site = site_name["content"]
                else:
                    parsed_url = urlparse(response.url)
                    site = parsed_url.netloc.replace('www.', '').split('.')[0].capitalize()

                item_type = item.get('@type')
                # Check if recipe  ---  Sometimes wrapped in an @graph
                if "@graph" in item:
                    for sub_item in item["@graph"]:
                        sub_item_type = sub_item.get('@type')
                        if sub_item_type == 'Recipe' or (isinstance(sub_item_type, list) and 'Recipe' in sub_item_type):
                            return format_json(sub_item, url, site)
                elif item_type == 'Recipe' or (isinstance(item_type, list) and 'Recipe' in item_type):
                    return format_json(item, url, site)
        """ else:
            for item in data.get('json-ld', []):
                image = item.get('image')
                if image:
                    return image
            raise RuntimeError("No Image") """
    else:
        return {"status": 500, "error": f"Connection unsuccessful: {response.status_code}"}
    return {"status": 500, "error": "No recipe found"}

@app.get("/")
def home():
  return {"status": 200}

@app.get("/get/{url:path}")
def get(url):
  content = get_recipe_content(url, 'recipe')
  return content