from flask import Flask
import requests
import time
import threading
import os
import re
import hashlib
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import random

app = Flask(__name__)

# ==================== USE PUBLIC WAHA INSTANCE ====================
WAHA_URL = "https://waha-1-v384.onrender.com"  # Working public WAHA
DESTINATION_CHANNEL = "120363422574401710@newsletter"

SOURCE_CHANNELS = [
    "120363177070916101@newsletter",  # TechFactsDeals
    "120363179368338362@newsletter",  # Loots4u
    "120363180244702234@newsletter",  # Shopping Loot Offers
    "120363290169377613@newsletter",  # Loot Deals Official
    "120363161802971651@newsletter",  # Loot Bazaar
]

AMAZON_AFFILIATE_TAG = "lootfastdeals-21"

print("🚀 Deal Forwarder Starting with Public WAHA...")
print(f"📡 WAHA URL: {WAHA_URL}")
print("💡 Scan QR at: https://waha-1-v384.onrender.com/web")
print("=" * 60)

# ==================== YOUR EXISTING FORWARDER CODE ====================
# [PASTE ALL YOUR enhanced_forwarder.py CODE HERE EXCEPT:
# - Remove the main_loop() function
# - Remove the __main__ block at the end
# - Keep all other functions and variables]

# ==================== ENHANCED HASHTAG SYSTEM ====================
ALL_HASHTAGS = [
    "#AmazonDeals", "#AmazonIndia", "#FlipkartDeals", "#MyntraDeals", "#AjioOffers",
    "#Deals", "#Offers", "#Discount", "#Sale", "#Loot", "#Savings",
    "#Electronics", "#Fashion", "#HomeDecor", "#TechDeals", "#FashionSale",
    "#LimitedTime", "#FlashSale", "#Under500", "#Under1000", "#BudgetFriendly",
    "#MorningDeals", "#EveningDeals", "#LateNightDeals", "#NightOwlDeals"
]

def get_smart_hashtags(product_text, platform):
    """Get context-aware hashtags"""
    base_hashtags = []
    
    platform_lower = platform.lower()
    if "amazon" in platform_lower:
        base_hashtags.extend(["#AmazonDeals", "#AmazonIndia"])
    elif "flipkart" in platform_lower:
        base_hashtags.extend(["#FlipkartDeals", "#FlipkartSale"])
    elif "myntra" in platform_lower:
        base_hashtags.extend(["#MyntraDeals", "#FashionSale"])
    elif "ajio" in platform_lower:
        base_hashtags.extend(["#AjioOffers", "#AjioLoot"])
    
    current_hour = datetime.now().hour
    if 6 <= current_hour < 12:
        base_hashtags.append("#MorningDeals")
    elif 12 <= current_hour < 17:
        base_hashtags.append("#AfternoonDeals")
    elif 17 <= current_hour < 22:
        base_hashtags.append("#EveningDeals")
    else:
        base_hashtags.extend(["#LateNightDeals", "#NightOwlDeals"])
    
    price_match = re.search(r'₹(\d+,?\d+)', product_text)
    if price_match:
        price = int(price_match.group(1).replace(',', ''))
        if price < 500:
            base_hashtags.append("#Under500")
        elif price < 1000:
            base_hashtags.append("#Under1000")
    
    return ' '.join(base_hashtags[:3])

# ==================== OPTIMIZED DAILY LIMITS ====================
CHECK_INTERVAL = 30
MIN_TIME_BETWEEN_SENDS = 8
MAX_DAILY_MESSAGES = 400
MAX_HOURLY_MESSAGES = 35
MESSAGE_LIMIT = 6

# Safety tracking
last_send_time = 0
daily_message_count = 0
hourly_message_count = 0
daily_reset_time = time.time()
hourly_reset_time = time.time()

# ==================== DEDUPLICATION ====================
seen_hashes = set()
seen_asins = set()
seen_product_ids = set()
last_processed_timestamps = {}

class Stats:
    def __init__(self):
        self.total_forwarded = 0
        self.session_start = datetime.now()
        self.check_count = 0
        self.missed_deals = 0
    
    def increment_forwarded(self): self.total_forwarded += 1
    def increment_check(self): self.check_count += 1
    def increment_missed(self): self.missed_deals += 1
    def get_duration(self): return datetime.now() - self.session_start

stats = Stats()

# ==================== CORE FORWARDER FUNCTIONS ====================
def check_daily_limits():
    global daily_message_count, hourly_message_count, daily_reset_time, hourly_reset_time
    
    if time.time() - daily_reset_time > 86400:
        daily_message_count = 0
        daily_reset_time = time.time()
    
    if time.time() - hourly_reset_time > 3600:
        hourly_message_count = 0
        hourly_reset_time = time.time()
    
    if daily_message_count >= MAX_DAILY_MESSAGES:
        return False
    
    if hourly_message_count >= MAX_HOURLY_MESSAGES:
        time.sleep(900)
        hourly_message_count = 0
        return True
    
    return True

def get_waha_health():
    try:
        response = requests.get(f"{WAHA_URL}/api/sessions", timeout=10)
        return response.status_code == 200
    except:
        return False

def send_whatsapp_message_optimized(text):
    global last_send_time, daily_message_count, hourly_message_count
    
    if not text or not text.strip(): 
        return False
    
    if not check_daily_limits():
        return False
    
    current_time = time.time()
    time_since_last_send = current_time - last_send_time
    
    if time_since_last_send < MIN_TIME_BETWEEN_SENDS:
        wait_time = MIN_TIME_BETWEEN_SENDS - time_since_last_send
        time.sleep(wait_time)
    
    payload = {"chatId": DESTINATION_CHANNEL, "text": text, "session": "default"}
    try: 
        response = requests.post(f"{WAHA_URL}/api/sendText", json=payload, timeout=15)
        
        if response.status_code == 200:
            last_send_time = time.time()
            daily_message_count += 1
            hourly_message_count += 1
            print(f"    📊 Sent: {daily_message_count}/{MAX_DAILY_MESSAGES}")
            return True
        else:
            print(f"    ❌ Send failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"    ❌ Send error: {e}")
        return False

def get_channel_messages(channel_id, limit=MESSAGE_LIMIT):
    try:
        response = requests.get(
            f"{WAHA_URL}/api/default/chats/{channel_id}/messages", 
            params={"limit": limit}, 
            timeout=10
        )
        return response.json() if response.status_code == 200 else []
    except: 
        return []

def process_message_ultra_fast(text):
    if not text: return None
    
    text = re.sub(r'From\s*\*\s*[^:]*:', '', text)
    
    urls = re.findall(r'https?://[^\s]+', text)
    if not urls: return None
    
    main_url = urls[0]
    
    # Simple platform detection
    if 'amazon' in main_url or 'amzn.to' in main_url:
        platform = "🛍️ Amazon"
        final_url = f"{main_url}{'&' if '?' in main_url else '?'}tag={AMAZON_AFFILIATE_TAG}"
    else:
        platform = "📦 Other"
        final_url = main_url
    
    clean_text = re.sub(r'https?://[^\s]+', '', text)
    lines = [line.strip() for line in clean_text.split('\n') if line.strip() and len(line) > 8]
    product_name = lines[0] if lines else "Hot Deal! 🔥"
    
    # Extract price
    price_match = re.search(r'@\s*(\d+,?\d*)|₹\s*(\d+,?\d*)', text)
    price_info = f"💰 ₹{price_match.group(1)}" if price_match else ""
    
    # Extract discount
    discount_match = re.search(r'(\d+%)', text)
    discount_info = f"🎯 {discount_match.group(1)}" if discount_match else ""
    
    message_parts = [platform, f"\n{product_name}"]
    if price_info:
        message_parts.append(f"\n{price_info}")
    if discount_info:
        message_parts.append(f"\n{discount_info}")
    
    message_parts.append(f"\n\n{final_url}")
    
    smart_hashtags = get_smart_hashtags(text, platform)
    message_parts.append(f"\n\n{smart_hashtags}")
    
    return ''.join(message_parts)

def generate_message_hash(text): 
    return hashlib.md5(text.encode()).hexdigest()

def is_duplicate(message):
    if not message: return True
    message_hash = generate_message_hash(message)
    if message_hash in seen_hashes: return True
    return False

def add_to_dedup(message):
    if not message: return
    message_hash = generate_message_hash(message)
    seen_hashes.add(message_hash)

def process_channel_real_time(channel_name, channel_id):
    deals_found = 0
    try:
        messages = get_channel_messages(channel_id)
        if not messages: 
            return 0
        
        last_timestamp = last_processed_timestamps.get(channel_id, 0)
        new_last_timestamp = last_timestamp
        
        for message in reversed(messages):
            if message.get('fromMe') or not message.get('body'): continue
            
            message_timestamp = message.get('timestamp', 0)
            if message_timestamp <= last_timestamp: continue
                
            if message_timestamp > new_last_timestamp:
                new_last_timestamp = message_timestamp
            
            if time.time() - message_timestamp > 300:
                stats.increment_missed()
                continue
            
            processed_message = process_message_ultra_fast(message.get('body', ''))
            if not processed_message or is_duplicate(processed_message):
                continue
            
            if send_whatsapp_message_optimized(processed_message):
                deals_found += 1
                stats.increment_forwarded()
                add_to_dedup(processed_message)
                print(f"    🚀 {channel_name}: DEAL SENT!")
            
        last_processed_timestamps[channel_id] = new_last_timestamp
            
    except Exception as e:
        print(f"    ❌ {channel_name} error: {str(e)}")
    
    return deals_found

def deal_forwarder_main():
    """MAIN DEAL FORWARDER LOOP"""
    channel_names = ["TechFactsDeals", "Loots4u", "Shopping Loot Offers", "Loot Deals Official", "Loot Bazaar"]
    
    print("🚀 ENHANCED WhatsApp Forwarder - 24/7 Cloud Operation!")
    print("=" * 60)
    
    # Initialize fresh start
    current_time = time.time()
    for channel_id in SOURCE_CHANNELS:
        last_processed_timestamps[channel_id] = current_time
    
    print(f"🛡️  Daily limit: {MAX_DAILY_MESSAGES} messages")
    print(f"⚡ Check interval: {CHECK_INTERVAL} seconds")
    print("=" * 60)
    
    # Wait for WAHA to be ready
    print("⏳ Waiting for WAHA connection...")
    for i in range(20):
        if get_waha_health():
            print("✅ WAHA connected successfully!")
            break
        print(f"   Waiting... ({i+1}/20)")
        time.sleep(10)
    else:
        print("⚠️ WAHA connection failed - but will continue trying")
    
    # MAIN LOOP
    while True:
        try:
            stats.increment_check()
            current_time = datetime.now().strftime("%H:%M:%S")
            
            print(f"\n🔄 CHECK #{stats.check_count} at {current_time}")
            print("-" * 40)
            
            if not get_waha_health():
                print("⚠️ WAHA not responding, retrying...")
                time.sleep(10)
                continue
            
            if not check_daily_limits():
                print("💤 Daily limit reached. Sleeping...")
                time.sleep(3600)
                continue
            
            total_forwarded = 0
            
            for name, channel_id in zip(channel_names, SOURCE_CHANNELS):
                deals = process_channel_real_time(name, channel_id)
                total_forwarded += deals
                time.sleep(0.5)
            
            if total_forwarded > 0:
                print(f"🎉 {total_forwarded} deals forwarded!")
            else:
                print(f"👀 No new deals")
            
            print(f"📈 Total: {stats.total_forwarded}")
            print(f"⏳ Next check in {CHECK_INTERVAL} seconds...\n")
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"💥 Error: {str(e)}")
            time.sleep(30)

# ==================== FLASK ROUTES ====================
@app.route('/')
def home():
    return """
    <h1>✅ Deal Forwarder Running 24/7!</h1>
    <p><strong>Status:</strong> Monitoring 5 channels for deals</p>
    <p><strong>WAHA Dashboard:</strong> <a href="https://waha-1-v384.onrender.com/web" target="_blank">Click here for QR Code</a></p>
    <p><strong>Health:</strong> <a href="/health">/health</a></p>
    <hr>
    <p><em>Using public WAHA instance - No laptop needed! 📱</em></p>
    """

@app.route('/health')
def health():
    waha_status = "✅ Connected" if get_waha_health() else "❌ Disconnected"
    return {
        "status": "running", 
        "service": "deal-forwarder",
        "waha": waha_status,
        "forwarded": stats.total_forwarded,
        "checks": stats.check_count
    }

# Start the forwarder
threading.Thread(target=deal_forwarder_main, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)