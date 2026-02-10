"""
DEV.to API Integration Module
https://developers.forem.com/api
"""

import os
import requests
import json
from typing import Optional, Dict, List, Any
from dotenv import load_dotenv

# Ensure .env is loaded
load_dotenv()

BASE_URL = "https://dev.to/api"

def _get_headers() -> Dict[str, str]:
    """Get headers with API key."""
    api_key = os.getenv("DEVTO_API_KEY")
    if not api_key:
        return {}
    return {
        "api-key": api_key,
        "Content-Type": "application/json"
    }

def post_article(
    title: str,
    body_markdown: str,
    published: bool = False,
    tags: Optional[List[str]] = None,
    series: Optional[str] = None,
    canonical_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a new article on DEV.to
    
    Args:
        title: Article title
        body_markdown: Article content in markdown
        published: True to publish immediately, False for draft
        tags: List of tags (max 4)
        series: Series name for multi-part posts
        canonical_url: Original URL if cross-posting
    """
    headers = _get_headers()
    if not headers:
        return {"error": "DEVTO_API_KEY not found in environment. Please add it to .env."}

    url = f"{BASE_URL}/articles"
    
    article_data = {
        "article": {
            "title": title,
            "body_markdown": body_markdown,
            "published": published
        }
    }
    
    if tags:
        # Ensure max 4 tags
        article_data["article"]["tags"] = tags[:4]
    if series:
        article_data["article"]["series"] = series
    if canonical_url:
        article_data["article"]["canonical_url"] = canonical_url
    
    try:
        response = requests.post(url, json=article_data, headers=headers, timeout=30)
        
        if response.status_code == 401:
            return {"error": "Unauthorized. Check your DEVTO_API_KEY."}
            
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
             try:
                 error_msg += f" Response: {e.response.text}"
             except:
                 pass
        return {"error": error_msg}


def update_article(
    article_id: int,
    title: Optional[str] = None,
    body_markdown: Optional[str] = None,
    published: Optional[bool] = None,
    tags: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Update an existing article
    """
    headers = _get_headers()
    if not headers:
        return {"error": "DEVTO_API_KEY not found in environment"}

    url = f"{BASE_URL}/articles/{article_id}"
    
    article_data: Dict[str, Any] = {"article": {}}
    
    if title:
        article_data["article"]["title"] = title
    if body_markdown:
        article_data["article"]["body_markdown"] = body_markdown
    if published is not None:
        article_data["article"]["published"] = published
    if tags:
        article_data["article"]["tags"] = tags[:4]
    
    if not article_data["article"]:
        return {"error": "No fields to update provided."}

    try:
        response = requests.put(url, json=article_data, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}


def get_my_articles(page: int = 1, per_page: int = 30) -> List[Dict[str, Any]]:
    """Get all my published articles"""
    headers = _get_headers()
    if not headers:
        return [{"error": "DEVTO_API_KEY not found in environment"}]

    url = f"{BASE_URL}/articles/me/published"
    params = {"page": page, "per_page": per_page}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return [{"error": str(e)}]

def check_api_key() -> str:
    """Verify API key is valid."""
    headers = _get_headers()
    if not headers:
        return "DEVTO_API_KEY missing from .env"
        
    url = f"{BASE_URL}/articles/me" # Get my articles (published or not) to check auth
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return "✅ API Key is valid."
        elif response.status_code == 401:
            return "❌ API Key is Invalid (Unauthorized 401)."
        else:
            return f"⚠️ API check returned status {response.status_code}"
    except Exception as e:
        return f"Error checking key: {e}"