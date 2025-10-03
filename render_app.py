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

# ==================== OPTIMIZED CONFIGURATION ====================
WAHA_URL = os.getenv("WAHA_URL", "https://waha-production-32e7.up.railway.app")
DESTINATION_CHANNEL = os.getenv("DESTINATION_CHANNEL", "120363422574401710@newsletter")
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS", "120363177070916101@newsletter,120363179368338362@newsletter,120363180244702234@newsletter,120363290169377613@newsletter,120363161802971651@newsletter").split(",")
AMAZON_AFFILIATE_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "lootfastdeals-21")

# ==================== OPTIMIZED PERFORMANCE SETTINGS ====================
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "15"))  # ⚡ Faster checking
MIN_TIME_BETWEEN_SENDS = int(os.getenv("MIN_TIME_BETWEEN_SENDS", "3"))  # ⚡ Reduced delay
MAX_DAILY_MESSAGES = int(os.getenv("MAX_DAILY_MESSAGES", "500"))  # Increased
MAX_HOURLY_MESSAGES = int(os.getenv("MAX_HOURLY_MESSAGES", "60"))  # Increased
MESSAGE_LIMIT = int(os.getenv("MESSAGE_LIMIT", "25"))  # ⚡ Check more messages!

# ==================== SIMPLIFIED HASHTAGS ====================
HASHTAGS = [
    "#AmazonDeals", "#FlipkartSale", "#MyntraDeals", "#AjioOffers",
    "#Under500", "#Under1000", "#BudgetFriendly", "#ElectronicsDeals",
    "#FashionSale", "#HomeDecor", "#TechDeals", "#DailyDeals"
]

def get_simple_hashtags(message_count):
    """Fast hashtag selection without complex processing"""
    idx1 = message_count % len(HASHTAGS)
    idx2 = (message_count * 3) % len(HASHTAGS)
    return f"{HASHTAGS[idx1]} {HASHTAGS[idx2]}"

# ==================== OPTIMIZED DEDUPLICATION ====================
seen_hashes = set()
seen_urls = set()
last_processed_timestamps = {}

# ==================== OPTIMIZED SAFETY TRACKING ====================
last_send_time = 0
daily_message_count = 0
hourly_message_count = 0
daily_reset_time = time.time()
hourly_reset_time = time.time()

class Stats:
    def __init__(self):
        self.total_forwarded = 0
        self.session_start = datetime.now()
        self.check_count = 0
        self.missed_deals = 0
        self.duplicates_blocked = 0
        self.spam_filtered = 0
    
    def increment_forwarded(self): self.total_forwarded += 1
    def increment_check(self): self.check_count += 1
    def increment_missed(self): self.missed_deals += 1
    def increment_duplicates(self): self.duplicates_blocked += 1
    def increment_spam(self): self.spam_filtered += 1
    def get_duration(self): return datetime.now() - self.session_start

stats = Stats()

# ==================== OPTIMIZED MESSAGE FILTERING ====================
def is_spam_message(text):
    """LESS AGGRESSIVE spam filtering"""
    if not text or not text.strip():
        return True
    
    text_lower = text.lower()
    
    # Only filter obvious spam
    spam_patterns = [
        r'f+a+s+t+',  # FAAAST, FASSST, etc.
        r'^\s*[0-9,]+\s*$',  # Just numbers
    ]
    
    for pattern in spam_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    
    # Must contain URL
    urls = re.findall(r'https?://[^\s]+', text)
    if not urls:
        return True
    
    return False

def extract_amazon_asin(url):
    """Fast ASIN extraction"""
    patterns = [
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match: 
            return match.group(1).upper()
    return None

def clean_and_normalize_url(url):
    """Fast URL cleaning"""
    try:
        parsed = urlparse(url)
        # Remove common tracking parameters quickly
        clean_url = re.sub(r'[?&](utm_[^&]+|ref=[^&]+|cmpid=[^&]+)', '', url)
        return clean_url if clean_url else url
    except:
        return url

def apply_amazon_affiliate(url):
    """Fast affiliate tag application"""
    if not url or ('amazon.' not in url.lower() and 'amzn.to' not in url.lower()):
        return url
    
    # Remove any existing tag quickly
    cleaned_url = re.sub(r'[?&]tag=[^&]+', '', url)
    separator = '&' if '?' in cleaned_url else '?'
    return f"{cleaned_url}{separator}tag={AMAZON_AFFILIATE_TAG}"

def is_safe_url(url):
    """Fast URL safety check"""
    safe_domains = ['amazon.in', 'amzn.to', 'flipkart.com', 'fkrt.co', 
                   'myntra.com', 'ajio.com']
    try: 
        domain = urlparse(url).netloc.lower()
        return any(safe_domain in domain for safe_domain in safe_domains)
    except: 
        return False

# ==================== OPTIMIZED SAFETY FUNCTIONS ====================
def check_daily_limits():
    global daily_message_count, hourly_message_count, daily_reset_time, hourly_reset_time
    
    # Daily reset (24 hours)
    if time.time() - daily_reset_time > 86400:
        daily_message_count = 0
        daily_reset_time = time.time()
    
    # Hourly reset
    if time.time() - hourly_reset_time > 3600:
        hourly_message_count = 0
        hourly_reset_time = time.time()
    
    if daily_message_count >= MAX_DAILY_MESSAGES:
        print(f"🛑 DAILY LIMIT REACHED! ({MAX_DAILY_MESSAGES}/day)")
        return False
    
    if hourly_message_count >= MAX_HOURLY_MESSAGES:
        print(f"⏳ HOURLY LIMIT REACHED! ({MAX_HOURLY_MESSAGES}/hour)")
        time.sleep(300)  # Reduced from 600 to 300 seconds
        hourly_message_count = 0
        return True
    
    return True

def get_safe_send_delay():
    return MIN_TIME_BETWEEN_SENDS + random.uniform(0.5, 2)  # Faster sending

# ==================== OPTIMIZED DEDUPLICATION ====================
def generate_message_hash(text): 
    return hashlib.md5(text.encode()).hexdigest()

def is_duplicate_message(text, url):
    """Fast duplicate detection"""
    if not text or not url:
        return True
    
    # Method 1: URL-based (fastest)
    clean_url = clean_and_normalize_url(url)
    if clean_url in seen_urls:
        stats.increment_duplicates()
        return True
    
    # Method 2: Message hash
    message_hash = generate_message_hash(text)
    if message_hash in seen_hashes:
        stats.increment_duplicates()
        return True
    
    return False

def add_to_dedup(text, url):
    """Fast duplicate tracking"""
    if not text or not url:
        return
    
    clean_url = clean_and_normalize_url(url)
    seen_urls.add(clean_url)
    
    message_hash = generate_message_hash(text)
    seen_hashes.add(message_hash)

# ==================== OPTIMIZED WAHA COMMUNICATION ====================
def get_waha_health():
    try:
        response = requests.get(f"{WAHA_URL}/api/sessions", timeout=5)  # Faster timeout
        return response.status_code == 200
    except:
        return False

def send_whatsapp_message_fast(text):
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
        time.sleep(wait_time)
    
    payload = {"chatId": DESTINATION_CHANNEL, "text": text, "session": "default"}
    try: 
        response = requests.post(f"{WAHA_URL}/api/sendText", json=payload, timeout=10)  # Faster timeout
        
        if response.status_code == 200:
            last_send_time = time.time()
            daily_message_count += 1
            hourly_message_count += 1
            print(f"📊 Today: {daily_message_count}/{MAX_DAILY_MESSAGES}")
            return True
        else:
            print(f"❌ Send failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Send error: {e}")
        return False

def get_channel_messages(channel_id, limit=MESSAGE_LIMIT):
    try:
        response = requests.get(
            f"{WAHA_URL}/api/default/chats/{channel_id}/messages", 
            params={"limit": limit}, 
            timeout=8  # Faster timeout
        )
        return response.json() if response.status_code == 200 else []
    except: 
        return []

# ==================== OPTIMIZED MESSAGE PROCESSING ====================
def process_message_fast(text):
    if not text: 
        return None, None
    
    # Fast spam check
    if is_spam_message(text):
        stats.increment_spam()
        return None, None
    
    # Clean source info quickly
    text = re.sub(r'From\s*\*\s*[^:]*:|### From.*', '', text)
    
    # Extract URLs
    urls = re.findall(r'https?://[^\s]+', text)
    if not urls: 
        return None, None
    
    # Use first safe URL
    safe_urls = [url for url in urls if is_safe_url(url)]
    if not safe_urls: 
        return None, None
    
    main_url = safe_urls[0]
    
    # Fast platform detection
    if 'amazon' in main_url or 'amzn.to' in main_url:
        platform = "🛍️ Amazon"
        final_url = apply_amazon_affiliate(main_url)
    elif 'flipkart' in main_url or 'fkrt.co' in main_url:
        platform = "📦 Flipkart"
        final_url = clean_and_normalize_url(main_url)
    elif 'myntra' in main_url:
        platform = "👕 Myntra"
        final_url = clean_and_normalize_url(main_url)
    elif 'ajio' in main_url:
        platform = "🛒 Ajio"
        final_url = clean_and_normalize_url(main_url)
    else:
        platform = "🔗 Other"
        final_url = clean_and_normalize_url(main_url)
    
    # Fast product name extraction
    clean_text = re.sub(r'https?://[^\s]+', '', text)
    lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
    
    product_name = "Hot Deal! 🔥"
    for line in lines:
        if len(line) > 8 and not re.search(r'f+a+s+t+', line.lower()):
            product_name = line[:100]  # Limit length
            break
    
    # Fast price extraction
    price_match = re.search(r'[@₹]\s*(\d+,?\d*,?\d+)', text)
    price_info = f"💰 ₹{price_match.group(1)}" if price_match else "💰 Great Deal!"
    
    # Build message quickly
    hashtags = get_simple_hashtags(stats.total_forwarded)
    
    final_message = f"""{platform}
{product_name}

{price_info}

{final_url}

{hashtags}"""
    
    return final_message, main_url

# ==================== OPTIMIZED CHANNEL PROCESSING ====================
def process_channel_fast(channel_name, channel_id):
    deals_found = 0
    try:
        messages = get_channel_messages(channel_id)
        if not messages: 
            return 0
        
        last_timestamp = last_processed_timestamps.get(channel_id, 0)
        new_last_timestamp = last_timestamp
        
        for message in reversed(messages):
            if message.get('fromMe') or not message.get('body'): 
                continue
            
            message_timestamp = message.get('timestamp', 0)
            if message_timestamp <= last_timestamp: 
                continue
                
            if message_timestamp > new_last_timestamp:
                new_last_timestamp = message_timestamp
            
            # Process messages from last 10 minutes (increased from 5)
            if time.time() - message_timestamp > 600:
                stats.increment_missed()
                continue
            
            processed_message, original_url = process_message_fast(message.get('body', ''))
            if not processed_message:
                continue
            
            # Fast duplicate check
            if is_duplicate_message(processed_message, original_url):
                continue
            
            if send_whatsapp_message_fast(processed_message):
                deals_found += 1
                stats.increment_forwarded()
                add_to_dedup(processed_message, original_url)
                print(f"🚀 {channel_name}: DEAL SENT!")
            
        last_processed_timestamps[channel_id] = new_last_timestamp
            
    except Exception as e:
        print(f"❌ {channel_name} error: {str(e)}")
    
    return deals_found

# ==================== OPTIMIZED MAIN LOOP ====================
def deal_forwarder_main():
    """OPTIMIZED MAIN LOOP - FASTER PROCESSING"""
    channel_names = ["TechFactsDeals", "Loots4u", "Shopping Loot Offers", "Loot Deals Official", "Loot Bazaar"]
    
    print("🚀 OPTIMIZED WhatsApp Forwarder - HIGH SPEED OPERATION!")
    print("=" * 60)
    print(f"📡 WAHA URL: {WAHA_URL}")
    print(f"🎯 Destination: {DESTINATION_CHANNEL}")
    print(f"⚡ Check interval: {CHECK_INTERVAL} seconds")
    print(f"📨 Messages per check: {MESSAGE_LIMIT}")
    print(f"🔍 Optimized filtering: Less aggressive spam detection")
    print("=" * 60)
    
    # Initialize
    current_time = time.time()
    for channel_id in SOURCE_CHANNELS:
        last_processed_timestamps[channel_id] = current_time - 300  # Start from 5 minutes ago
    
    # Wait for WAHA connection
    print("⏳ Waiting for WAHA connection...")
    for i in range(10):  # Reduced from 15
        if get_waha_health():
            print("✅ WAHA connected successfully!")
            break
        print(f"   Waiting... ({i+1}/10)")
        time.sleep(3)  # Reduced from 5
    else:
        print("⚠️  WAHA connection failed - will keep trying")
    
    # OPTIMIZED MAIN LOOP
    while True:
        try:
            stats.increment_check()
            current_time_str = datetime.now().strftime("%H:%M:%S")
            
            print(f"\n🔄 CHECK #{stats.check_count} at {current_time_str}")
            print("-" * 40)
            
            # Check WAHA health every 10 checks (reduced frequency)
            if stats.check_count % 10 == 0:
                if not get_waha_health():
                    print("⚠️  WAHA not responding, retrying...")
                    time.sleep(5)  # Reduced from 10
                    continue
            
            # Check safety limits
            if not check_daily_limits():
                print("💤 Daily limit reached. Sleeping for 30 minutes...")
                time.sleep(1800)  # Reduced from 3600
                continue
            
            # Process all channels quickly
            total_forwarded = 0
            for name, channel_id in zip(channel_names, SOURCE_CHANNELS):
                deals = process_channel_fast(name, channel_id)
                total_forwarded += deals
                time.sleep(0.1)  # Much faster between channels
            
            # Status update
            if total_forwarded > 0:
                print(f"🎉 {total_forwarded} deals forwarded!")
            else:
                print("👀 No new deals")
            
            print(f"📈 Total forwarded: {stats.total_forwarded}")
            print(f"⏳ Next check in {CHECK_INTERVAL} seconds...\n")
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"💥 Error in main loop: {str(e)}")
            time.sleep(10)  # Reduced from 30

# ==================== FLASK ENDPOINTS (UNCHANGED) ====================
@app.route('/')
def home():
    # ... (keep existing Flask endpoints unchanged)
    pass

@app.route('/health')
def health():
    # ... (keep existing Flask endpoints unchanged)
    pass

@app.route('/ping')
def ping():
    # ... (keep existing Flask endpoints unchanged)
    pass

@app.route('/stats')
def stats_page():
    # ... (keep existing Flask endpoints unchanged)
    pass

@app.route('/test-whatsapp')
def test_whatsapp():
    # ... (keep existing Flask endpoints unchanged)
    pass

@app.route('/waha-health')
def waha_health():
    # ... (keep existing Flask endpoints unchanged)
    pass

# ==================== START SERVICES ====================
print("🎯 Starting OPTIMIZED WhatsApp Forwarder...")
print("💡 Features: Faster Processing + Less Filtering + Higher Limits")

# Start the forwarder in background thread
forwarder_thread = threading.Thread(target=deal_forwarder_main, daemon=True)
forwarder_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)