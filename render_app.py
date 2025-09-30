import os
import requests
import time
import re
import hashlib
import random
import json
from datetime import datetime
from flask import Flask
import threading
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

# ==================== CONFIGURATION ====================
WAHA_URL = os.getenv("WAHA_URL", "https://waha-production-32e7.up.railway.app")
DESTINATION_CHANNEL = os.getenv("DESTINATION_CHANNEL", "120363422574401710@newsletter")
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS", "120363177070916101@newsletter,120363179368338362@newsletter,120363180244702234@newsletter,120363290169377613@newsletter,120363161802971651@newsletter").split(",")
AMAZON_AFFILIATE_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "lootfastdeals-21")

# ==================== SAFETY LIMITS ====================
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))
MIN_TIME_BETWEEN_SENDS = int(os.getenv("MIN_TIME_BETWEEN_SENDS", "8"))
MAX_DAILY_MESSAGES = int(os.getenv("MAX_DAILY_MESSAGES", "400"))
MAX_HOURLY_MESSAGES = int(os.getenv("MAX_HOURLY_MESSAGES", "35"))
MESSAGE_LIMIT = int(os.getenv("MESSAGE_LIMIT", "6"))

# ==================== ENHANCED HASHTAG SYSTEM ====================
ALL_HASHTAGS = [
    "#AmazonDeals", "#AmazonIndia", "#AmazonSale", "#FlipkartDeals", 
    "#FlipkartSale", "#MyntraDeals", "#AjioOffers", "#AjioLoot",
    "#Deals", "#Offers", "#Discount", "#Sale", "#Loot", "#Savings",
    "#SaveMoney", "#BudgetShopping", "#Affordable", "#CheapDeals",
    "#Electronics", "#Fashion", "#HomeDecor", "#Kitchen", "#Beauty",
    "#MobileDeals", "#LaptopDeals", "#FashionSale", "#TechDeals",
    "#GadgetDeals", "#HomeAppliances", "#KitchenEssentials",
    "#LimitedTime", "#FlashSale", "#TodayOnly", "#Hurry", "#QuickDeal",
    "#HotDeal", "#SpecialOffer", "#ExclusiveDeal", "#LimitedStock",
    "#Under500", "#Under1000", "#BudgetFriendly", "#ValueDeal",
    "#PremiumDeals", "#LuxuryDeals",
    "#MorningDeals", "#AfternoonDeals", "#EveningDeals", "#LateNightDeals",
    "#NightOwlDeals", "#EarlyAccess", "#MidnightDeals",
    "#DailyDeals", "#WeekendSale", "#TodayDeals", "#NewArrivals"
]

def get_smart_hashtags(product_text, platform):
    """Get context-aware hashtags (2-3 max)"""
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
    elif 22 <= current_hour <= 23:
        base_hashtags.extend(["#LateNightDeals", "#NightOwlDeals"])
    else:
        base_hashtags.extend(["#MidnightDeals", "#EarlyAccess", "#NightOwlDeals"])
    
    price_match = re.search(r'₹(\d+,?\d+)', product_text)
    if price_match:
        price = int(price_match.group(1).replace(',', ''))
        if price < 500:
            base_hashtags.append("#Under500")
        elif price < 1000:
            base_hashtags.append("#Under1000")
        elif price < 2000:
            base_hashtags.append("#BudgetFriendly")
    
    text_lower = product_text.lower()
    if any(word in text_lower for word in ['laptop', 'mobile', 'headphone', 'earphone', 'tablet', 'camera']):
        base_hashtags.extend(["#TechDeals", "#Electronics"])
    elif any(word in text_lower for word in ['shirt', 'dress', 'jeans', 'shoe', 'sandal', 'top', 'kurta']):
        base_hashtags.extend(["#FashionDeals", "#ClothingSale"])
    elif any(word in text_lower for word in ['kitchen', 'cooker', 'home', 'furniture', 'decor', 'appliance']):
        base_hashtags.extend(["#HomeDecor", "#KitchenDeals"])
    
    return ' '.join(base_hashtags[:3])

# ==================== SAFETY TRACKING ====================
last_send_time = 0
daily_message_count = 0
hourly_message_count = 0
daily_reset_time = time.time()
hourly_reset_time = time.time()

# ==================== DEDUPLICATION ====================
seen_hashes = set()
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

# ==================== CORE SAFETY FUNCTIONS ====================
def check_daily_limits():
    global daily_message_count, hourly_message_count, daily_reset_time, hourly_reset_time
    
    # Daily reset (24 hours)
    if time.time() - daily_reset_time > 86400:
        daily_message_count = 0
        daily_reset_time = time.time()
        print("🔄 Daily counter reset!")
    
    # Hourly reset
    if time.time() - hourly_reset_time > 3600:
        hourly_message_count = 0
        hourly_reset_time = time.time()
        print("🕐 Hourly counter reset!")
    
    if daily_message_count >= MAX_DAILY_MESSAGES:
        print(f"🛑 DAILY LIMIT REACHED! ({MAX_DAILY_MESSAGES}/day)")
        return False
    
    if hourly_message_count >= MAX_HOURLY_MESSAGES:
        print(f"⏳ HOURLY LIMIT REACHED! ({MAX_HOURLY_MESSAGES}/hour)")
        print("   Sleeping for 15 minutes...")
        time.sleep(900)
        hourly_message_count = 0
        return True
    
    return True

def get_safe_send_delay():
    base_delay = MIN_TIME_BETWEEN_SENDS
    if hourly_message_count > 30:
        base_delay += 2
    random_variation = random.uniform(1, 3)
    return base_delay + random_variation

# ==================== WAHA COMMUNICATION ====================
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
    safe_delay = get_safe_send_delay()
    
    if time_since_last_send < safe_delay:
        wait_time = safe_delay - time_since_last_send
        print(f"    ⏳ Safety delay: {wait_time:.1f}s")
        time.sleep(wait_time)
    
    payload = {"chatId": DESTINATION_CHANNEL, "text": text, "session": "default"}
    try: 
        response = requests.post(f"{WAHA_URL}/api/sendText", json=payload, timeout=15)
        
        if response.status_code == 200:
            last_send_time = time.time()
            daily_message_count += 1
            hourly_message_count += 1
            print(f"    📊 Today: {daily_message_count}/{MAX_DAILY_MESSAGES}")
            print(f"    🕐 This hour: {hourly_message_count}/{MAX_HOURLY_MESSAGES}")
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

# ==================== MESSAGE PROCESSING ====================
def process_message_ultra_fast(text):
    if not text: return None
    
    # Clean source info
    text = re.sub(r'From\s*\*\s*[^:]*:|### From.*', '', text)
    
    # Extract URLs
    urls = re.findall(r'https?://[^\s]+', text)
    if not urls: return None
    
    main_url = urls[0]
    
    # Platform detection & affiliate tagging
    if 'amazon' in main_url or 'amzn.to' in main_url:
        platform = "🛍️ Amazon"
        final_url = f"{main_url}{'&' if '?' in main_url else '?'}tag={AMAZON_AFFILIATE_TAG}"
    elif 'flipkart' in main_url:
        platform = "📦 Flipkart"
        final_url = main_url
    elif 'myntra' in main_url:
        platform = "👕 Myntra"
        final_url = main_url
    elif 'ajio' in main_url:
        platform = "🛒 Ajio"
        final_url = main_url
    else:
        platform = "🔗 Other"
        final_url = main_url
    
    # Extract product name
    clean_text = re.sub(r'https?://[^\s]+', '', text)
    lines = [line.strip() for line in clean_text.split('\n') if line.strip() and len(line) > 8]
    product_name = lines[0] if lines else "Hot Deal! 🔥"
    
    # Extract price & discount
    price_match = re.search(r'@\s*(\d+,?\d*)|₹\s*(\d+,?\d*)', text)
    price_info = f"💰 ₹{price_match.group(1)}" if price_match else ""
    
    discount_match = re.search(r'(\d+%)', text)
    discount_info = f"🎯 {discount_match.group(1)}" if discount_match else ""
    
    # Build message
    message_parts = [platform, f"\n{product_name}"]
    if price_info:
        message_parts.append(f"\n{price_info}")
    if discount_info:
        message_parts.append(f"\n{discount_info}")
    
    message_parts.append(f"\n\n{final_url}")
    
    # Add smart hashtags
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

# ==================== CHANNEL PROCESSING ====================
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
            
            # Only process messages from last 5 minutes
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

# ==================== MAIN FORWARDER LOOP ====================
def deal_forwarder_main():
    """MAIN DEAL FORWARDER LOOP - 24/7 OPERATION"""
    channel_names = ["TechFactsDeals", "Loots4u", "Shopping Loot Offers", "Loot Deals Official", "Loot Bazaar"]
    
    print("🚀 SMART WhatsApp Forwarder - 24/7 Cloud Operation!")
    print("=" * 60)
    print(f"📡 WAHA URL: {WAHA_URL}")
    print(f"🎯 Destination: {DESTINATION_CHANNEL}")
    print(f"🛡️  Daily limit: {MAX_DAILY_MESSAGES} messages")
    print(f"⚡ Check interval: {CHECK_INTERVAL} seconds")
    print("=" * 60)
    
    # Initialize fresh start
    current_time = time.time()
    for channel_id in SOURCE_CHANNELS:
        last_processed_timestamps[channel_id] = current_time
    
    # Wait for WAHA connection
    print("⏳ Waiting for WAHA connection...")
    for i in range(15):
        if get_waha_health():
            print("✅ WAHA connected successfully!")
            break
        print(f"   Waiting... ({i+1}/15)")
        time.sleep(5)
    else:
        print("⚠️  WAHA connection failed - will keep trying")
    
    # MAIN 24/7 LOOP
    while True:
        try:
            stats.increment_check()
            current_time_str = datetime.now().strftime("%H:%M:%S")
            current_hour = datetime.now().hour
            
            print(f"\n🔄 CHECK #{stats.check_count} at {current_time_str}")
            print("-" * 40)
            
            # Check WAHA health every 5 checks
            if stats.check_count % 5 == 0:
                if not get_waha_health():
                    print("⚠️  WAHA not responding, retrying...")
                    time.sleep(10)
                    continue
            
            # Night mode (reduced activity 1AM-6AM)
            if current_hour >= 1 and current_hour < 6:
                print("💤 Late night hours (1AM-6AM) - Reduced activity")
            
            # Check safety limits
            if not check_daily_limits():
                print("💤 Daily limit reached. Sleeping for 1 hour...")
                time.sleep(3600)
                continue
            
            # Process all channels
            total_forwarded = 0
            for name, channel_id in zip(channel_names, SOURCE_CHANNELS):
                deals = process_channel_real_time(name, channel_id)
                total_forwarded += deals
                time.sleep(0.5)  # Small delay between channels
            
            # Status update
            if total_forwarded > 0:
                print(f"🎉 {total_forwarded} deals forwarded!")
            else:
                print(f"👀 No new deals")
            
            print(f"📈 Total forwarded: {stats.total_forwarded}")
            print(f"⏳ Next check in {CHECK_INTERVAL} seconds...\n")
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"💥 Error in main loop: {str(e)}")
            time.sleep(30)  # Wait before retrying

# ==================== FLASK WEB SERVICE ====================
@app.route('/')
def home():
    waha_status = "✅ Connected" if get_waha_health() else "❌ Disconnected"
    daily_remaining = MAX_DAILY_MESSAGES - daily_message_count
    uptime = stats.get_duration()
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>WhatsApp Deal Forwarder</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .status {{ padding: 15px; border-radius: 5px; margin: 10px 0; }}
            .connected {{ background: #d4edda; color: #155724; }}
            .disconnected {{ background: #f8d7da; color: #721c24; }}
            .stats {{ background: #e2e3e5; padding: 15px; border-radius: 5px; }}
            .progress {{ background: #e9ecef; border-radius: 5px; overflow: hidden; margin: 10px 0; }}
            .progress-bar {{ background: #007bff; height: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 WhatsApp Deal Forwarder Running 24/7!</h1>
            
            <div class="status {('connected' if waha_status == '✅ Connected' else 'disconnected')}">
                <strong>Status:</strong> Monitoring 5 channels for deals
            </div>
            
            <div class="stats">
                <p><strong>WAHA Status:</strong> {waha_status}</p>
                <p><strong>Current WAHA:</strong> {WAHA_URL}</p>
                <p><strong>WAHA Dashboard:</strong> <a href="{WAHA_URL}/web" target="_blank">Click here for QR Code</a></p>
                
                <p><strong>Forwarded Today:</strong> {daily_message_count}/{MAX_DAILY_MESSAGES} ({daily_remaining} remaining)</p>
                <div class="progress">
                    <div class="progress-bar" style="width: {(daily_message_count/MAX_DAILY_MESSAGES)*100}%"></div>
                </div>
                
                <p><strong>Total Forwarded:</strong> {stats.total_forwarded}</p>
                <p><strong>Uptime:</strong> {str(uptime).split('.')[0]}</p>
                <p><strong>Health Checks:</strong> {stats.check_count}</p>
            </div>
            
            <div style="margin-top: 20px;">
                <p><strong>Quick Links:</strong></p>
                <a href="/health">Health Check</a> | 
                <a href="/ping">Ping</a> | 
                <a href="/stats">Statistics</a>
            </div>
            
            <hr>
            <p><em>✅ WAHA on Railway + Forwarder on Render = 24/7 Operation!</em></p>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    waha_status = "✅ Connected" if get_waha_health() else "❌ Disconnected"
    return {
        "status": "running", 
        "service": "deal-forwarder",
        "timestamp": datetime.now().isoformat(),
        "waha_status": waha_status,
        "waha_url": WAHA_URL,
        "forwarded_today": daily_message_count,
        "total_forwarded": stats.total_forwarded,
        "uptime": str(stats.get_duration()),
        "health_checks": stats.check_count
    }

@app.route('/ping')
def ping():
    """Keep-alive endpoint to prevent Render sleep"""
    return {
        "status": "pong", 
        "timestamp": datetime.now().isoformat(),
        "service": "deal-forwarder",
        "message": "Service is alive and running"
    }

@app.route('/stats')
def stats_page():
    """Detailed statistics"""
    daily_remaining = MAX_DAILY_MESSAGES - daily_message_count
    hourly_remaining = MAX_HOURLY_MESSAGES - hourly_message_count
    
    return {
        "service": "deal-forwarder",
        "timestamp": datetime.now().isoformat(),
        "message_limits": {
            "daily": f"{daily_message_count}/{MAX_DAILY_MESSAGES}",
            "daily_remaining": daily_remaining,
            "hourly": f"{hourly_message_count}/{MAX_HOURLY_MESSAGES}", 
            "hourly_remaining": hourly_remaining
        },
        "performance": {
            "total_forwarded": stats.total_forwarded,
            "missed_deals": stats.missed_deals,
            "health_checks": stats.check_count,
            "uptime": str(stats.get_duration())
        },
        "configuration": {
            "check_interval": CHECK_INTERVAL,
            "min_send_delay": MIN_TIME_BETWEEN_SENDS,
            "message_limit_per_check": MESSAGE_LIMIT
        }
    }

# ==================== START SERVICES ====================
print("🎯 Starting Smart WhatsApp Forwarder...")
print("💡 WAHA on Railway + Forwarder on Render")
print("🌐 Web service starting on port 5000...")

# Start the forwarder in background thread
forwarder_thread = threading.Thread(target=deal_forwarder_main, daemon=True)
forwarder_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)