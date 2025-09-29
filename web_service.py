import os
import requests
import time
import re
import hashlib
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import random
from flask import Flask

app = Flask(__name__)

# ==================== CONFIGURATION FROM ENVIRONMENT ====================
WAHA_URL = os.getenv("WAHA_URL", "http://localhost:3000")
DESTINATION_CHANNEL = os.getenv("DESTINATION_CHANNEL", "120363422574401710@newsletter")
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS", "120363177070916101@newsletter,120363179368338362@newsletter,120363180244702234@newsletter,120363290169377613@newsletter,120363161802971651@newsletter").split(",")
AMAZON_AFFILIATE_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "lootfastdeals-21")

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

# ==================== SAFETY FUNCTIONS ====================
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

def get_safe_send_delay():
    base_delay = MIN_TIME_BETWEEN_SENDS
    if hourly_message_count > 30:
        base_delay += 2
    random_variation = random.uniform(1, 3)
    return base_delay + random_variation

def simulate_human_behavior():
    pause_chance = 0.2 if hourly_message_count > 20 else 0.3
    if random.random() < pause_chance:
        time.sleep(random.uniform(0.5, 1.5))

# ==================== SESSION MANAGEMENT ====================
SESSION_FILE = "forwarder_session.json"
SAFETY_FILE = "safety_tracker.json"

def save_safety_data():
    try:
        import json
        safety_data = {
            'daily_message_count': daily_message_count,
            'hourly_message_count': hourly_message_count,
            'daily_reset_time': daily_reset_time,
            'hourly_reset_time': hourly_reset_time,
            'last_save': datetime.now().isoformat()
        }
        with open(SAFETY_FILE, 'w') as f:
            json.dump(safety_data, f)
    except:
        pass

def load_safety_data():
    global daily_message_count, hourly_message_count, daily_reset_time, hourly_reset_time
    try:
        import json
        if os.path.exists(SAFETY_FILE):
            with open(SAFETY_FILE, 'r') as f:
                safety_data = json.load(f)
            
            daily_message_count = safety_data.get('daily_message_count', 0)
            hourly_message_count = safety_data.get('hourly_message_count', 0)
            daily_reset_time = safety_data.get('daily_reset_time', time.time())
            hourly_reset_time = safety_data.get('hourly_reset_time', time.time())
            
            current_time = time.time()
            if current_time - daily_reset_time > 86400:
                daily_message_count = 0
                daily_reset_time = current_time
            
            if current_time - hourly_reset_time > 3600:
                hourly_message_count = 0
                hourly_reset_time = current_time
                
    except:
        pass

def save_session():
    try:
        import json
        session_data = {
            'last_processed_timestamps': last_processed_timestamps,
            'seen_hashes': list(seen_hashes),
            'seen_asins': list(seen_asins),
            'seen_product_ids': list(seen_product_ids),
            'save_time': datetime.now().isoformat()
        }
        with open(SESSION_FILE, 'w') as f:
            json.dump(session_data, f)
    except:
        pass

def load_session():
    global last_processed_timestamps, seen_hashes, seen_asins, seen_product_ids
    try:
        import json
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, 'r') as f:
                session_data = json.load(f)
            
            last_processed_timestamps = session_data.get('last_processed_timestamps', {})
            seen_hashes = set(session_data.get('seen_hashes', []))
            seen_asins = set(session_data.get('seen_asins', []))
            seen_product_ids = set(session_data.get('seen_product_ids', []))
            
            for channel_id in last_processed_timestamps:
                last_processed_timestamps[channel_id] = float(last_processed_timestamps[channel_id])
            
            print("✅ Loaded previous session")
            return True
    except:
        pass
    
    return False

def initialize_fresh_start():
    global last_processed_timestamps
    print("🆕 Starting FRESH - will only process NEW messages")
    current_time = time.time()
    for channel_id in SOURCE_CHANNELS:
        last_processed_timestamps[channel_id] = current_time

# ==================== WAHA FUNCTIONS ====================
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
    
    simulate_human_behavior()
    
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

# ==================== TEXT PROCESSING FUNCTIONS ====================
def extract_amazon_asin(url):
    patterns = [
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})',
        r'amzn\.to/[a-zA-Z0-9]+',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match: 
            return match.group(1).upper() if pattern != r'amzn\.to/[a-zA-Z0-9]+' else "AMAZON_SHORT"
    return None

def extract_flipkart_product_id(url):
    patterns = [r'/p/([a-zA-Z0-9]+)', r'pid=([a-zA-Z0-9]+)', r'fkrt\.co/([a-zA-Z0-9]+)']
    for pattern in patterns:
        match = re.search(pattern, url)
        if match: 
            return match.group(1)
    return None

def clean_url_function(url):
    if not url: return url
    try:
        parsed = urlparse(url)
        if 'amazon.' in parsed.netloc.lower() or 'amzn.to' in url.lower():
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        query_params = parse_qs(parsed.query)
        tracking_params = ['utm_source', 'utm_medium', 'ref', 'tag', 'cmpid']
        for param in tracking_params:
            query_params.pop(param, None)
        
        clean_query = '&'.join([f"{k}={v[0]}" for k, v in query_params.items()])
        cleaned_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if clean_query: cleaned_url += f"?{clean_query}"
        return cleaned_url
    except: return url

def apply_amazon_affiliate(url):
    if not url or ('amazon.' not in url.lower() and 'amzn.to' not in url.lower()): 
        return url
    cleaned_url = clean_url_function(url)
    return f"{cleaned_url}{'&' if '?' in cleaned_url else '?'}tag={AMAZON_AFFILIATE_TAG}"

def is_safe_url(url):
    safe_domains = ['amazon.in', 'amzn.to', 'flipkart.com', 'fkrt.co', 'myntra.com', 'ajio.com']
    try: 
        return any(safe_domain in urlparse(url).netloc.lower() for safe_domain in safe_domains)
    except: 
        return False

def generate_message_hash(text): 
    return hashlib.md5(text.encode()).hexdigest()

def extract_platform(url):
    if 'amazon' in url or 'amzn.to' in url: return "🛍️ Amazon"
    elif 'flipkart' in url or 'fkrt.co' in url: return "📦 Flipkart"
    elif 'myntra' in url: return "👕 Myntra"
    elif 'ajio' in url: return "🛒 Ajio"
    else: return "🔗 Other"

def extract_price_fast(text):
    price_match = re.search(r'@\s*(\d+,?\d*)|₹\s*(\d+,?\d*)', text)
    if price_match:
        price = price_match.group(1) or price_match.group(2)
        return f"💰 ₹{price}"
    return None

def extract_discount_fast(text):
    discount_match = re.search(r'(\d+%)', text)
    if discount_match:
        return f"🎯 {discount_match.group(1)}"
    return None

def process_message_ultra_fast(text):
    if not text: return None
    
    text = re.sub(r'From\s*\*\s*[^:]*:|### From.*', '', text)
    
    urls = re.findall(r'https?://[^\s]+', text)
    if not urls: return None
    
    safe_urls = [url for url in urls if is_safe_url(url)]
    if not safe_urls: return None
    
    main_url = safe_urls[0]
    
    if 'amazon' in main_url or 'amzn.to' in main_url:
        final_url = apply_amazon_affiliate(main_url)
    else:
        final_url = clean_url_function(main_url)
    
    platform = extract_platform(main_url)
    
    clean_text = re.sub(r'https?://[^\s]+', '', text)
    lines = [line.strip() for line in clean_text.split('\n') if line.strip() and len(line) > 8]
    product_name = lines[0] if lines else "Hot Deal! 🔥"
    
    price_info = extract_price_fast(text)
    discount_info = extract_discount_fast(text)
    
    message_parts = [platform, f"\n{product_name}"]
    if price_info:
        message_parts.append(f"\n{price_info}")
    if discount_info:
        message_parts.append(f"\n{discount_info}")
    
    message_parts.append(f"\n\n{final_url}")
    
    smart_hashtags = get_smart_hashtags(text, platform)
    message_parts.append(f"\n\n{smart_hashtags}")
    
    return ''.join(message_parts)

def is_duplicate(message):
    if not message: return True
    message_hash = generate_message_hash(message)
    if message_hash in seen_hashes: return True
    return False

def add_to_dedup(message):
    if not message: return
    message_hash = generate_message_hash(message)
    seen_hashes.add(message_hash)

# ==================== MAIN PROCESSING ====================
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

def print_safety_status():
    daily_remaining = MAX_DAILY_MESSAGES - daily_message_count
    hourly_remaining = MAX_HOURLY_MESSAGES - hourly_message_count
    time_until_daily_reset = 86400 - (time.time() - daily_reset_time)
    time_until_hourly_reset = 3600 - (time.time() - hourly_reset_time)
    
    hours_until_daily = time_until_daily_reset / 3600
    minutes_until_hourly = time_until_hourly_reset / 60
    
    print(f"🛡️  SAFETY STATUS:")
    print(f"   📨 Today: {daily_message_count}/{MAX_DAILY_MESSAGES} ({daily_remaining} remaining)")
    print(f"   🕐 This hour: {hourly_message_count}/{MAX_HOURLY_MESSAGES} ({hourly_remaining} remaining)")
    print(f"   🔄 Daily reset: {hours_until_daily:.1f}h | Hourly reset: {minutes_until_hourly:.0f}m")

def deal_forwarder_main():
    """MAIN DEAL FORWARDER LOOP"""
    channel_names = ["TechFactsDeals", "Loots4u", "Shopping Loot Offers", "Loot Deals Official", "Loot Bazaar"]
    
    print("🚀 ENHANCED WhatsApp Forwarder - 24/7 Cloud Operation!")
    print("=" * 60)
    
    load_safety_data()
    
    if not load_session():
        initialize_fresh_start()
    
    print_safety_status()
    print(f"⚡ Check interval: {CHECK_INTERVAL} seconds")
    print(f"🎯 Daily limit: {MAX_DAILY_MESSAGES} messages")
    print(f"⏰ Extended timing: Until 1 AM (Early Access Deals)")
    print(f"🏷️ Smart hashtags: 2-3 context-aware tags per post")
    print("=" * 60)
    
    # Wait for WAHA to be ready
    print("⏳ Waiting for WAHA server to start...")
    for i in range(30):
        if get_waha_health():
            print("✅ WAHA connected successfully!")
            break
        print(f"   Waiting... ({i+1}/30)")
        time.sleep(10)
    else:
        print("❌ WAHA failed to start - but forwarder will continue trying")
    
    import atexit
    atexit.register(save_safety_data)
    atexit.register(save_session)
    
    # MAIN LOOP
    while True:
        try:
            stats.increment_check()
            current_time = datetime.now().strftime("%H:%M:%S")
            current_hour = datetime.now().hour
            
            print(f"\n🔄 CHECK #{stats.check_count} at {current_time}")
            print("-" * 40)
            
            if not get_waha_health():
                print("⚠️ WAHA not responding, retrying...")
                time.sleep(10)
                continue
            
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
            
            if stats.check_count % 10 == 0:
                save_safety_data()
                save_session()
                
            if stats.check_count % 5 == 0:
                print_safety_status()
            
            if total_forwarded > 0:
                print(f"🎉 {total_forwarded} deals forwarded with smart hashtags!")
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
    <h1>✅ WhatsApp Deal Forwarder Running 24/7!</h1>
    <p><strong>Status:</strong> Monitoring 5 channels for deals</p>
    <p><strong>Forwarded Today:</strong> {}/{} messages</p>
    <p><strong>Total Forwarded:</strong> {}</p>
    <p><strong>Health:</strong> <a href="/health">/health</a></p>
    <hr>
    <p><em>Running on Render cloud - No laptop needed! 📱</em></p>
    """.format(daily_message_count, MAX_DAILY_MESSAGES, stats.total_forwarded)

@app.route('/health')
def health():
    waha_status = "✅ Connected" if get_waha_health() else "❌ Disconnected"
    return {
        "status": "running", 
        "service": "deal-forwarder",
        "waha": waha_status,
        "forwarded_today": daily_message_count,
        "total_forwarded": stats.total_forwarded,
        "uptime": str(stats.get_duration())
    }

@app.route('/ping')
def ping():
    """Keep-alive endpoint to prevent Render sleep"""
    return {"status": "pong", "timestamp": datetime.now().isoformat()}

# Start the forwarder in background thread
import threading
forwarder_thread = threading.Thread(target=deal_forwarder_main, daemon=True)
forwarder_thread.start()

if __name__ == '__main__':
    print("🚀 Starting WhatsApp Deal Forwarder on Render...")
    app.run(host='0.0.0.0', port=5000, debug=False)