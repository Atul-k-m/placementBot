import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json
import logging

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def fetch_devpost_hackathons():
    """
    Scrape Devpost for open hackathons and filter by deadline (30 days).
    """
    url = "https://devpost.com/hackathons?order_by=deadline&status=open"
    headers = {"User-Agent": USER_AGENT}
    
    hackathons = []
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            log.error(f"Devpost returned status {response.status_code}")
            return []
            
        soup = BeautifulSoup(response.text, "html.parser")
        # Devpost hackathons are usually in div.hackathon-tile
        tiles = soup.select(".hackathon-tile")
        
        now = datetime.now()
        thirty_days_later = now + timedelta(days=30)
        
        for tile in tiles:
            try:
                name_tag = tile.select_one("h3")
                if not name_tag: continue
                name = name_tag.get_text(strip=True)
                
                url_tag = tile.select_one("a[href*='devpost.com']")
                link = url_tag['href'] if url_tag else ""
                
                prize_tag = tile.select_one(".prize-amount")
                prize = prize_tag.get_text(strip=True) if prize_tag else "N/A"
                
                # Deadline logic: devpost uses data-deadline or similar, 
                # but sometimes it's just text in a .submission-period or similar
                # Let's look for time tags or specific deadline text
                deadline_tag = tile.select_one("time")
                deadline_str = "N/A"
                if deadline_tag and deadline_tag.has_attr('datetime'):
                    dt_str = deadline_tag['datetime'] # e.g. 2024-05-15T...
                    try:
                        # Sometimes it's iso format
                        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                        if dt > thirty_days_later or dt < now:
                            continue
                        deadline_str = dt.strftime("%b %d")
                    except:
                        pass
                else:
                    # Fallback or skip if we can't determine deadline accurately? 
                    # For now just take the text if available
                    deadline_str = tile.select_one(".submission-period").get_text(strip=True) if tile.select_one(".submission-period") else "N/A"

                hackathons.append({
                    "name": name,
                    "deadline": deadline_str,
                    "prize": prize,
                    "url": link
                })
            except Exception as e:
                log.warning(f"Error parsing Devpost tile: {e}")
                continue
                
    except Exception as e:
        log.error(f"Failed to scrape Devpost: {e}")
        
    return hackathons

def fetch_unstop_opportunities():
    """
    Use Unstop's public API to fetch competitions updated/posted in last 24h.
    """
    url = "https://unstop.com/api/public/opportunity/search-result?opportunity=competitions&deadline=1&page=1&size=20"
    headers = {"User-Agent": USER_AGENT}
    
    opportunities = []
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            log.error(f"Unstop returned status {response.status_code}")
            return []
            
        data = response.json()
        items = data.get("data", {}).get("data", [])
        
        now = datetime.now()
        yesterday = now - timedelta(hours=24)
        
        for item in items:
            try:
                # Unstop API gives timestamps or "updated_at"
                # Check if it was updated in last 24h
                # JSON fields: title, public_url, banner_url, region, competition_type, 
                # organization_name, regn_end_date, etc.
                
                name = item.get("title", "N/A")
                organizer = item.get("organisation_name", "N/A")
                link = f"https://unstop.com/p/{item.get('public_url')}" if item.get('public_url') else "N/A"
                prize = item.get("prize", "N/A")
                
                end_date_str = item.get("regn_end_date") # e.g. "2024-04-25T23:59:59.000000Z"
                deadline = "N/A"
                if end_date_str:
                    try:
                        dt_end = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                        deadline = dt_end.strftime("%b %d")
                    except:
                        pass
                
                # posted logic: look for created_at or updated_at
                is_fresh = False
                for field in ["updated_at", "created_at"]:
                    ts = item.get(field)
                    if ts:
                        try:
                            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if dt > yesterday:
                                is_fresh = True
                                break
                        except:
                            pass
                
                if not is_fresh:
                    continue

                opportunities.append({
                    "name": name,
                    "organizer": organizer,
                    "deadline": deadline,
                    "prize": prize,
                    "url": link
                })
            except Exception as e:
                log.warning(f"Error parsing Unstop item: {e}")
                continue
                
    except Exception as e:
        log.error(f"Failed to fetch Unstop opportunities: {e}")
        
    return opportunities

def get_daily_opportunities(enable_devpost=True, enable_unstop=True):
    results = {}
    if enable_devpost:
        results["devpost"] = fetch_devpost_hackathons()
    if enable_unstop:
        results["unstop"] = fetch_unstop_opportunities()
    return results
