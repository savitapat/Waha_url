import os
import requests
import time
import re
import hashlib
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import random
from flask import Flask
import threading

app = Flask(__name__)

# ==================== CONFIGURATION ====================
DESTINATION_CHANNEL = os.getenv("DESTINATION_CHANNEL", "120363422574401710@newsletter")
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS", "120363177070916101@newsletter,120363179368338362@newsletter,120363180244702234@newsletter,120363290169377613@newsletter,120363161802971651@newsletter").split(",")
AMAZON_AFFILIATE_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "lootfastdeals-21")

# ==================== PUBLIC WAHA INSTANCES ====================
PUBLIC_WAHA_URLS = [
    "https://waha-1-v384.onrender.com",
    "https://waha-2-0.onrender.com",
    "https://waha.onrender.com",
    "https://waha-latest.onrender.com"
]

current_waha_index = 0
active_waha_url = None

def find_working_waha():
    """Find a working WAHA instance from the list"""
    global active_waha_url, current_waha_index
    
    # Try all URLs to find a working one
    for i, url in enumerate(PUBLIC_WAHA_URLS):
        if check_waha_health(url):
            active_waha_url = url
            current_waha_index = i
            print(f"✅ Connected to WAHA: {url}")
            return url
    
    # If none work, use the first one and keep trying
    active_waha_url = PUBLIC_WAHA_URLS[0]
    print(f"⚠️  No WAHA instances available, will keep trying: {active_waha_url}")
    return active_waha_url

def check_waha_health(url):
    """Check if WAHA instance is healthy"""
    try:
        response = requests.get(f"{url}/api/sessions", timeout=10)
        if response.status_code == 200:
            return True
    except:
        pass
    return False

def get_waha_url():
    """Get current WAHA URL, find new one if current is down"""
    global active_waha_url
    
    if active_waha_url and check_waha_health(active_waha_url):
        return active_waha_url
    
    # Current WAHA is down, find new one
    return find_working_waha()

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
        else:
            base_hashtags.append("#PremiumDeals")
    
    text_lower = product_text.lower()
    if any(word in text_lower for word in ['laptop', 'mobile', 'headphone', 'earphone', 'tablet', 'camera']):
        base_hashtags.extend(["#TechDeals", "#Electronics"])
    elif any(word in text_lower for word in ['shirt', 'dress', 'jeans', 'shoe', 'sandal', 'top', 'kurta']):
        base_hashtags.extend(["#FashionDeals", "#ClothingSale"])
    elif any(word in text_lower for word in ['kitchen', 'cooker', 'home', 'furniture', 'decor', 'appliance']):
        base_hashtags.extend(["#HomeDecor", "#KitchenDeals"])
    elif any(word in text_lower for word in ['beauty', 'cream', 'lotion', 'makeup', 'skincare']):
        base_hashtags.append("#BeautyDeals")
    
    generic_pool = [h for h in ALL_HASHTAGS if h not in base_hashtags]
    num_generic = max(0, 3 - len(base_hashtags))
    random_generic = random.sample(generic_pool, min(num_generic, len(generic_pool)))
    
    all_selected = base_hashtags + random_generic
    return ' '.join(all_selected[:3])

# ==================== OPTIMIZED DAILY LIMITS ====================
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))
MIN_TIME_BETWEEN_SENDS = int(os.getenv("MIN_TIME_BETWEEN_SENDS", "8"))
MAX_DAILY_MESSAGES = int(os.getenv("MAX_DAILY_MESSAGES", "400"))
MAX_HOURLY_MESSAGES = int(os.getenv("MAX_HOURLY_MESSAGES", "35"))
MESSAGE_LIMIT = int(os.getenv("MESSAGE_LIMIT", "6"))

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
        print("🔄 Daily counter reset!")
    
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
    
    waha_url = get_waha_url()
    payload = {"chatId": DESTINATION_CHANNEL, "text": text, "session": "default"}
    
    try: 
        response = requests.post(f"{waha_url}/api/sendText", json=payload, timeout=15)
        
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
    waha_url = get_waha_url()
    try:
        response = requests.get(
            f"{waha_url}/api/default/chats/{channel_id}/messages", 
            params={"limit": limit}, 
            timeout=10
        )
        return response.json() if response.status_code == 200 else []
    except: 
        return []

def process_message_ultra_fast(text):
    if not text: return None
    
    text = re.sub(r'From\s*\*\s*[^:]*:|### From.*', '', text)
    
    urls = re.findall(r'https?://[^\s]+', text)
    if not urls: return None
    
    main_url = urls[0]
    
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
    
    clean_text = re.sub(r'https?://[^\s]+', '', text)
    lines = [line.strip() for line in clean_text.split('\n') if line.strip() and len(line) > 8]
    product_name = lines[0] if lines else "Hot Deal! 🔥"
    
    price_match = re.search(r'@\s*(\d+,?\d*)|₹\s*(\d+,?\d*)', text)
    price_info = f"💰 ₹{price_match.group(1)}" if price_match else ""
    
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
    
    print("🚀 SMART WhatsApp Forwarder - 24/7 Cloud Operation!")
    print("=" * 60)
    
    # Initialize fresh start
    current_time = time.time()
    for channel_id in SOURCE_CHANNELS:
        last_processed_timestamps[channel_id] = current_time
    
    print(f"🛡️  Daily limit: {MAX_DAILY_MESSAGES} messages")
    print(f"⚡ Check interval: {CHECK_INTERVAL} seconds")
    print("💡 Using Public WAHA instances")
    print("=" * 60)
    
    # Find initial WAHA instance
    find_working_waha()
    
    # MAIN LOOP
    while True:
        try:
            stats.increment_check()
            current_time = datetime.now().strftime("%H:%M:%S")
            current_hour = datetime.now().hour
            
            print(f"\n🔄 CHECK #{stats.check_count} at {current_time}")
            print("-" * 40)
            
            # Check WAHA health periodically
            if stats.check_count % 5 == 0:
                if not check_waha_health(active_waha_url):
                    print("🔄 WAHA instance down, finding new one...")
                    find_working_waha()
            
            if current_hour >= 1 and current_hour < 6:
                print("💤 Late night hours (1AM-6AM) - Reduced activity")
            
            if not check_daily_limits():
                print("💤 Daily limit reached. Sleeping for 1 hour...")
                time.sleep(3600)
                continue
            
            total_forwarded = 0
            
            for name, channel_id in zip(channel_names, SOURCE_CHANNELS):
                deals = process_channel_real_time(name, channel_id)
                total_forwarded += deals
                time.sleep(0.3)
            
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
    waha_status = "✅ Connected" if active_waha_url and check_waha_health(active_waha_url) else "❌ Disconnected"
    return f"""
    <h1>✅ WhatsApp Deal Forwarder Running 24/7!</h1>
    <p><strong>Status:</strong> Monitoring 5 channels for deals</p>
    <p><strong>WAHA Status:</strong> {waha_status}</p>
    <p><strong>Current WAHA:</strong> {active_waha_url or 'Finding...'}</p>
    <p><strong>WAHA Dashboard:</strong> <a href="{active_waha_url}/web" target="_blank">Click here for QR Code</a></p>
    <p><strong>Forwarded Today:</strong> {daily_message_count}/{MAX_DAILY_MESSAGES}</p>
    <p><strong>Total Forwarded:</strong> {stats.total_forwarded}</p>
    <p><strong>Health:</strong> <a href="/health">/health</a></p>
    <hr>
    <p><em>Using Public WAHA instances - No installation needed! 🚀</em></p>
    """

@app.route('/health')
def health():
    waha_status = "✅ Connected" if active_waha_url and check_waha_health(active_waha_url) else "❌ Disconnected"
    return {
        "status": "running", 
        "service": "deal-forwarder",
        "waha_status": waha_status,
        "current_waha": active_waha_url,
        "forwarded_today": daily_message_count,
        "total_forwarded": stats.total_forwarded,
        "uptime": str(stats.get_duration())
    }

@app.route('/ping')
def ping():
    """Keep-alive endpoint to prevent Render sleep"""
    return {"status": "pong", "timestamp": datetime.now().isoformat()}

# Start the forwarder
print("🎯 Starting Smart WhatsApp Forwarder...")
print("💡 Using Public WAHA instances - No local installation!")
forwarder_thread = threading.Thread(target=deal_forwarder_main, daemon=True)
forwarder_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)