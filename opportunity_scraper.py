import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import json
import logging
from database import SessionLocal
import models

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def fetch_devpost_hackathons():
    """
    Scrape Devpost for open hackathons via JSON API.
    """
    url = "https://devpost.com/api/hackathons?status[]=open"
    headers = {"User-Agent": USER_AGENT}
    
    hackathons = []
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            log.error(f"Devpost returned status {response.status_code}")
            return []
            
        data = response.json()
        items = data.get("hackathons", [])
        
        for item in items:
            try:
                name = item.get("title", "N/A")
                link = item.get("url", "N/A")
                deadline = item.get("submission_period_dates", "N/A")
                
                # Cleanup prize amount (e.g., "$<span data-currency-value>50,000</span>")
                prize = item.get("prize_amount", "N/A")
                if "<span" in prize:
                    import re
                    prize = re.sub(r'<[^>]+>', '', prize)
                
                hackathons.append({
                    "name": name,
                    "deadline": deadline,
                    "prize": prize,
                    "url": link
                })
            except Exception as e:
                log.warning(f"Error parsing Devpost item: {e}")
                continue
                
    except Exception as e:
        log.error(f"Failed to scrape Devpost: {e}")
        
    return hackathons

def fetch_unstop_opportunities():
    """
    Use Unstop's public API to fetch competitions updated/posted in last 24h.
    """
    url = "https://unstop.com/api/public/opportunity/search-result?opportunity=all&deadline=1&page=1&size=50"
    headers = {"User-Agent": USER_AGENT}
    
    opportunities = []
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            log.error(f"Unstop returned status {response.status_code}")
            return []
            
        data = response.json()
        items = data.get("data", {}).get("data", [])
        
        now = datetime.now(timezone.utc)
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
                for field in ["approved_date", "updated_at", "created_at"]:
                    ts = item.get(field)
                    if ts:
                        try:
                            if " " in ts and "T" not in ts:
                                # e.g. "2026-04-26 10:11:09+05:30"
                                ts = ts.replace(" ", "T")
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

def update_opportunities_cache():
    """
    Internal cron job function to fetch and cache opportunities to the database.
    This avoids redundant scraping when running the bot for multiple users.
    """
    log.info("[Scraper] Updating opportunities cache...")
    devpost = fetch_devpost_hackathons()
    unstop = fetch_unstop_opportunities()
    
    db = SessionLocal()
    try:
        # Update devpost
        dp_cache = db.query(models.OpportunityCache).filter(models.OpportunityCache.platform == "devpost").first()
        if not dp_cache:
            dp_cache = models.OpportunityCache(platform="devpost")
            db.add(dp_cache)
        dp_cache.data = json.dumps(devpost)
        dp_cache.updated_at = datetime.utcnow()
        
        # Update unstop
        us_cache = db.query(models.OpportunityCache).filter(models.OpportunityCache.platform == "unstop").first()
        if not us_cache:
            us_cache = models.OpportunityCache(platform="unstop")
            db.add(us_cache)
        us_cache.data = json.dumps(unstop)
        us_cache.updated_at = datetime.utcnow()
        
        db.commit()
        log.info("[Scraper] Successfully updated opportunities cache.")
    except Exception as e:
        log.error(f"[Scraper] Failed to update opportunities cache: {e}")
    finally:
        db.close()


def get_daily_opportunities(enable_devpost=True, enable_unstop=True):
    """
    Reads from the internal cached database instead of scraping on the fly.
    """
    results = {}
    db = SessionLocal()
    try:
        if enable_devpost:
            dp = db.query(models.OpportunityCache).filter(models.OpportunityCache.platform == "devpost").first()
            if dp and dp.data:
                results["devpost"] = json.loads(dp.data)
        if enable_unstop:
            us = db.query(models.OpportunityCache).filter(models.OpportunityCache.platform == "unstop").first()
            if us and us.data:
                results["unstop"] = json.loads(us.data)
    except Exception as e:
        log.error(f"Error reading cache: {e}")
    finally:
        db.close()
    return results
