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

# ==================== OPTIMIZED RENDER ENV VARIABLES ====================
WAHA_URL = os.getenv("WAHA_URL", "https://waha-production-32e7.up.railway.app")
DESTINATION_CHANNEL = os.getenv("DESTINATION_CHANNEL", "120363422574401710@newsletter")
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS", "120363177070916101@newsletter,120363179368338362@newsletter,120363180244702234@newsletter,120363290169377613@newsletter,120363161802971651@newsletter").split(",")
AMAZON_AFFILIATE_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "lootfastdeals-21")

# ==================== BALANCED PERFORMANCE SETTINGS ====================
MAX_DAILY_MESSAGES = int(os.getenv("MAX_DAILY_MESSAGES", "450"))        # 🛡️ Safe daily limit
MAX_HOURLY_MESSAGES = int(os.getenv("MAX_HOURLY_MESSAGES", "45"))       # ⚡ Increased from 35
MESSAGE_LIMIT = int(os.getenv("MESSAGE_LIMIT", "25"))                   # ⚡ Increased from 20
MIN_TIME_BETWEEN_SENDS = int(os.getenv("MIN_TIME_BETWEEN_SENDS", "5"))  # ⚡ Reduced from 8
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "15"))                 # ⚡ Reduced from 20

# ==================== OPTIMIZED ROTATING HASHTAGS ====================
HASHTAG_CATEGORIES = {
    'time_based': [
        "#MorningDeals", "#AfternoonDeals", "#EveningDeals", 
        "#LateNightDeals", "#TodayDeals", "#DailyDeals"
    ],
    'platform_based': {
        'amazon': ["#AmazonDeals", "#AmazonIndia", "#AmazonSale"],
        'flipkart': ["#FlipkartDeals", "#FlipkartSale", "#FlipkartShopping"],
        'myntra': ["#MyntraDeals", "#FashionSale", "#MyntraFashion"],
        'ajio': ["#AjioOffers", "#AjioLoot", "#AjioFashion"],
        'other': ["#Deals", "#Offers", "#Discount"]
    },
    'price_based': [
        "#Under500", "#Under1000", "#BudgetFriendly", 
        "#PremiumDeals", "#Affordable"
    ],
    'category_based': [
        "#Electronics", "#Fashion", "#HomeDecor", "#TechDeals",
        "#MobileDeals", "#Appliances", "#FashionDeals"
    ]
}

def get_fast_hashtags(product_text, platform, message_count):
    """Optimized hashtag selection - faster but still smart"""
    selected_hashtags = []
    
    # Fast platform detection
    platform_lower = platform.lower()
    if "amazon" in platform_lower:
        platform_tags = HASHTAG_CATEGORIES['platform_based']['amazon']
    elif "flipkart" in platform_lower:
        platform_tags = HASHTAG_CATEGORIES['platform_based']['flipkart']
    elif "myntra" in platform_lower:
        platform_tags = HASHTAG_CATEGORIES['platform_based']['myntra']
    elif "ajio" in platform_lower:
        platform_tags = HASHTAG_CATEGORIES['platform_based']['ajio']
    else:
        platform_tags = HASHTAG_CATEGORIES['platform_based']['other']
    
    # Simple rotation
    platform_idx = message_count % len(platform_tags)
    selected_hashtags.append(platform_tags[platform_idx])
    
    # Time-based (simple hour-based)
    current_hour = datetime.now().hour
    time_tags = HASHTAG_CATEGORIES['time_based']
    time_idx = current_hour % len(time_tags)
    selected_hashtags.append(time_tags[time_idx])
    
    # Fast price detection
    price_match = re.search(r'₹(\d+,?\d+)', product_text)
    if price_match:
        price = int(price_match.group(1).replace(',', ''))
        if price < 500:
            price_tag = "#Under500"
        elif price < 1000:
            price_tag = "#Under1000"
        else:
            price_tag = "#BudgetFriendly"
        selected_hashtags.append(price_tag)
    else:
        # Quick category detection
        text_lower = product_text.lower()
        if any(word in text_lower for word in ['laptop', 'mobile', 'headphone', 'tech']):
            category_tag = "#TechDeals"
        elif any(word in text_lower for word in ['shirt', 'dress', 'jeans', 'shoe', 'fashion']):
            category_tag = "#FashionDeals"
        elif any(word in text_lower for word in ['kitchen', 'home', 'decor']):
            category_tag = "#HomeDecor"
        else:
            category_tags = HASHTAG_CATEGORIES['category_based']
            category_idx = message_count % len(category_tags)
            category_tag = category_tags[category_idx]
        
        selected_hashtags.append(category_tag)
    
    return ' '.join(selected_hashtags[:3])

# ==================== OPTIMIZED DEDUPLICATION ====================
seen_hashes = set()
seen_asins = set()
seen_product_ids = set()
seen_urls = set()
last_processed_timestamps = {}

# ==================== ENHANCED SAFETY TRACKING ====================
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
        self.errors_count = 0
    
    def increment_forwarded(self): self.total_forwarded += 1
    def increment_check(self): self.check_count += 1
    def increment_missed(self): self.missed_deals += 1
    def increment_duplicates(self): self.duplicates_blocked += 1
    def increment_spam(self): self.spam_filtered += 1
    def increment_errors(self): self.errors_count += 1
    def get_duration(self): return datetime.now() - self.session_start

stats = Stats()

# ==================== OPTIMIZED MESSAGE FILTERING ====================
def is_spam_message_fast(text):
    """Fast but effective spam filtering"""
    if not text or not text.strip():
        return True
    
    text_lower = text.lower()
    
    # Essential spam patterns only
    spam_patterns = [
        r'f+a+s+t+',  # FAAAST, FASSST, etc.
        r'coupon.*none',  # Coupon with none
        r'^\s*[0-9,]+\s*$',  # Just numbers
    ]
    
    for pattern in spam_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    
    # Must contain URL
    urls = re.findall(r'https?://[^\s]+', text)
    if not urls:
        return True
    
    # Light product checking
    product_indicators = ['amazon', 'flipkart', 'myntra', 'ajio', 'http']
    if not any(indicator in text_lower for indicator in product_indicators):
        return True
    
    return False

def extract_amazon_asin_fast(url):
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

def extract_product_id_fast(url):
    """Fast product ID extraction"""
    if 'flipkart.com' in url or 'fkrt.co' in url:
        match = re.search(r'/p/([a-zA-Z0-9]+)', url)
        return f"flipkart_{match.group(1)}" if match else None
    elif 'myntra.com' in url:
        match = re.search(r'/product/([a-zA-Z0-9]+)', url)
        return f"myntra_{match.group(1)}" if match else None
    elif 'ajio.com' in url:
        match = re.search(r'/p/([a-zA-Z0-9]+)', url)
        return f"ajio_{match.group(1)}" if match else None
    return None

def clean_and_normalize_url_fast(url):
    """Fast URL cleaning"""
    try:
        # Quick parameter removal
        clean_url = re.sub(r'[?&](utm_[^&]+|ref=[^&]+|cmpid=[^&]+)', '', url)
        return clean_url if clean_url else url
    except:
        return url

def apply_amazon_affiliate_fast(url):
    """Fast affiliate tag application"""
    if not url or ('amazon.' not in url.lower() and 'amzn.to' not in url.lower()):
        return url
    
    # Remove any existing tag quickly
    cleaned_url = re.sub(r'[?&]tag=[^&]+', '', url)
    separator = '&' if '?' in cleaned_url else '?'
    return f"{cleaned_url}{separator}tag={AMAZON_AFFILIATE_TAG}"

def is_safe_url_fast(url):
    """Fast URL safety check"""
    safe_domains = ['amazon.in', 'amzn.to', 'flipkart.com', 'fkrt.co', 
                   'myntra.com', 'ajio.com']
    try: 
        domain = urlparse(url).netloc.lower()
        return any(safe_domain in domain for safe_domain in safe_domains)
    except: 
        return False

# ==================== OPTIMIZED SAFETY FUNCTIONS ====================
def check_daily_limits_fast():
    global daily_message_count, hourly_message_count, daily_reset_time, hourly_reset_time
    
    # Fast reset checks
    current_time = time.time()
    if current_time - daily_reset_time > 86400:
        daily_message_count = 0
        daily_reset_time = current_time
    
    if current_time - hourly_reset_time > 3600:
        hourly_message_count = 0
        hourly_reset_time = current_time
    
    if daily_message_count >= MAX_DAILY_MESSAGES:
        print(f"🛑 DAILY LIMIT REACHED! ({MAX_DAILY_MESSAGES}/day)")
        return False
    
    if hourly_message_count >= MAX_HOURLY_MESSAGES:
        print(f"⏳ HOURLY LIMIT REACHED! ({MAX_HOURLY_MESSAGES}/hour)")
        time.sleep(300)  # 5 minutes instead of 10
        hourly_message_count = 0
        return True
    
    return True

def get_safe_send_delay_fast():
    base_delay = MIN_TIME_BETWEEN_SENDS
    if hourly_message_count > 30:  # Increase delay when approaching limit
        base_delay += 2
    return base_delay + random.uniform(0.5, 2)

# ==================== OPTIMIZED DEDUPLICATION FUNCTIONS ====================
def generate_message_hash_fast(text): 
    return hashlib.md5(text.encode()).hexdigest()

def is_duplicate_message_fast(text, url, platform):
    """Fast 3-layer duplicate detection"""
    if not text or not url:
        return True
    
    # Method 1: URL-based (fastest)
    clean_url = clean_and_normalize_url_fast(url)
    if clean_url in seen_urls:
        stats.increment_duplicates()
        return True
    
    # Method 2: Platform-specific ID
    if 'amazon' in platform.lower():
        asin = extract_amazon_asin_fast(url)
        if asin and asin in seen_asins:
            stats.increment_duplicates()
            return True
    else:
        product_id = extract_product_id_fast(url)
        if product_id and product_id in seen_product_ids:
            stats.increment_duplicates()
            return True
    
    # Method 3: Message hash
    message_hash = generate_message_hash_fast(text)
    if message_hash in seen_hashes:
        stats.increment_duplicates()
        return True
    
    return False

def add_to_dedup_fast(text, url, platform):
    """Fast duplicate tracking"""
    if not text or not url:
        return
    
    # Track clean URL
    clean_url = clean_and_normalize_url_fast(url)
    seen_urls.add(clean_url)
    
    # Track platform-specific IDs
    if 'amazon' in platform.lower():
        asin = extract_amazon_asin_fast(url)
        if asin:
            seen_asins.add(asin)
    else:
        product_id = extract_product_id_fast(url)
        if product_id:
            seen_product_ids.add(product_id)
    
    # Track message hash
    message_hash = generate_message_hash_fast(text)
    seen_hashes.add(message_hash)

# ==================== OPTIMIZED WAHA COMMUNICATION ====================
def get_waha_health_fast():
    try:
        response = requests.get(f"{WAHA_URL}/api/sessions", timeout=5)  # Faster timeout
        return response.status_code == 200
    except:
        return False

def send_whatsapp_message_optimized(text):
    global last_send_time, daily_message_count, hourly_message_count
    
    if not text or not text.strip(): 
        return False
    
    if not check_daily_limits_fast():
        return False
    
    current_time = time.time()
    time_since_last_send = current_time - last_send_time
    safe_delay = get_safe_send_delay_fast()
    
    if time_since_last_send < safe_delay:
        wait_time = safe_delay - time_since_last_send
        print(f"    ⏳ Safety delay: {wait_time:.1f}s")
        time.sleep(wait_time)
    
    payload = {"chatId": DESTINATION_CHANNEL, "text": text, "session": "default"}
    try: 
        response = requests.post(f"{WAHA_URL}/api/sendText", json=payload, timeout=10)  # Faster timeout
        
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

def get_channel_messages_fast(channel_id, limit=MESSAGE_LIMIT):
    try:
        response = requests.get(
            f"{WAHA_URL}/api/default/chats/{channel_id}/messages", 
            params={"limit": limit}, 
            timeout=8  # Faster timeout
        )
        return response.json() if response.status_code == 200 else []
    except Exception as e:
        print(f"    ❌ Error fetching messages: {e}")
        return []

# ==================== OPTIMIZED MESSAGE PROCESSING ====================
def process_message_balanced(text):
    if not text: 
        return None, None
    
    # Fast spam check first
    if is_spam_message_fast(text):
        stats.increment_spam()
        print("    🚫 Filtered: Spam message")
        return None, None
    
    # Quick source cleaning
    text = re.sub(r'From\s*\*\s*[^:]*:|### From.*', '', text)
    
    # Extract URLs
    urls = re.findall(r'https?://[^\s]+', text)
    if not urls: 
        return None, None
    
    # Use first safe URL
    safe_urls = [url for url in urls if is_safe_url_fast(url)]
    if not safe_urls: 
        return None, None
    
    main_url = safe_urls[0]
    
    # Fast platform detection
    if 'amazon' in main_url or 'amzn.to' in main_url:
        platform = "🛍️ Amazon"
        final_url = apply_amazon_affiliate_fast(main_url)
    elif 'flipkart' in main_url or 'fkrt.co' in main_url:
        platform = "📦 Flipkart"
        final_url = clean_and_normalize_url_fast(main_url)
    elif 'myntra' in main_url:
        platform = "👕 Myntra"
        final_url = clean_and_normalize_url_fast(main_url)
    elif 'ajio' in main_url:
        platform = "🛒 Ajio"
        final_url = clean_and_normalize_url_fast(main_url)
    else:
        platform = "🔗 Other"
        final_url = clean_and_normalize_url_fast(main_url)
    
    # Fast product name extraction
    clean_text = re.sub(r'https?://[^\s]+', '', text)
    lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
    
    product_name = "Hot Deal! 🔥"
    for line in lines:
        if len(line) > 8 and not re.search(r'f+a+s+t+', line.lower()):
            product_name = line[:80]  # Limit length for speed
            break
    
    # Fast price extraction
    price_match = re.search(r'[@₹]\s*(\d+,?\d*,?\d+)', text)
    price_info = f"💰 ₹{price_match.group(1)}" if price_match else "💰 Great Deal!"
    
    # Fast discount detection
    discount_match = re.search(r'(\d+%?\s*off)', text, re.IGNORECASE)
    discount_info = f"🎯 {discount_match.group(1)}" if discount_match else ""
    
    # Build message quickly with optimized hashtags
    rotating_hashtags = get_fast_hashtags(text, platform, stats.total_forwarded)
    
    message_parts = [
        platform, 
        f"\n{product_name}",
        f"\n{price_info}",
        f"\n{discount_info}" if discount_info else "",
        f"\n\n{final_url}",
        f"\n\n{rotating_hashtags}"
    ]
    
    final_message = ''.join(message_parts)
    return final_message, main_url

# ==================== OPTIMIZED CHANNEL PROCESSING ====================
def process_channel_balanced(channel_name, channel_id):
    deals_found = 0
    try:
        messages = get_channel_messages_fast(channel_id)
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
            
            # Process messages from last 10 minutes (increased window)
            if time.time() - message_timestamp > 600:
                stats.increment_missed()
                continue
            
            processed_message, original_url = process_message_balanced(message.get('body', ''))
            if not processed_message:
                continue
            
            # Fast duplicate check
            platform = "🛍️ Amazon" if 'amazon' in processed_message.lower() else "📦 Other"
            if is_duplicate_message_fast(processed_message, original_url, platform):
                continue
            
            if send_whatsapp_message_optimized(processed_message):
                deals_found += 1
                stats.increment_forwarded()
                add_to_dedup_fast(processed_message, original_url, platform)
                print(f"    🚀 {channel_name}: DEAL SENT!")
            
        last_processed_timestamps[channel_id] = new_last_timestamp
            
    except Exception as e:
        print(f"    ❌ {channel_name} error: {str(e)}")
        stats.increment_errors()
    
    return deals_found

# ==================== 24/7 OPTIMIZED MAIN LOOP ====================
def deal_forwarder_main():
    """OPTIMIZED MAIN LOOP - BALANCED SPEED & SAFETY"""
    channel_names = ["TechFactsDeals", "Loots4u", "Shopping Loot Offers", "Loot Deals Official", "Loot Bazaar"]
    
    print("🚀 BALANCED WhatsApp Forwarder - OPTIMIZED 24/7 OPERATION!")
    print("=" * 60)
    print(f"📡 WAHA URL: {WAHA_URL}")
    print(f"🎯 Destination: {DESTINATION_CHANNEL}")
    print(f"🛡️  Daily limit: {MAX_DAILY_MESSAGES} messages")
    print(f"🛡️  Hourly limit: {MAX_HOURLY_MESSAGES} messages")
    print(f"⚡ Check interval: {CHECK_INTERVAL} seconds")
    print(f"📨 Messages per check: {MESSAGE_LIMIT}")
    print(f"⏰ Send delay: {MIN_TIME_BETWEEN_SENDS} seconds")
    print("🔍 Optimized: Faster processing + All features + WhatsApp safe")
    print("=" * 60)
    
    # Initialize with wider time window
    current_time = time.time()
    for channel_id in SOURCE_CHANNELS:
        last_processed_timestamps[channel_id] = current_time - 600  # Start from 10 minutes ago
    
    # Fast WAHA connection check
    print("⏳ Waiting for WAHA connection...")
    for i in range(10):  # Reduced attempts
        if get_waha_health_fast():
            print("✅ WAHA connected successfully!")
            break
        print(f"   Waiting... ({i+1}/10)")
        time.sleep(3)  # Reduced delay
    else:
        print("⚠️  WAHA connection failed - will keep trying")
    
    # OPTIMIZED 24/7 LOOP
    loop_count = 0
    while True:
        try:
            stats.increment_check()
            loop_count += 1
            current_time_str = datetime.now().strftime("%H:%M:%S")
            current_hour = datetime.now().hour
            
            print(f"\n🔄 CHECK #{stats.check_count} at {current_time_str}")
            print("-" * 40)
            
            # Auto-reconnect every 30 loops (optimized)
            if loop_count % 30 == 0:
                if not get_waha_health_fast():
                    print("🔁 Reconnecting to WAHA...")
                    time.sleep(5)
                    continue
            
            # Smart night mode
            if current_hour >= 1 and current_hour < 7:
                print("💤 Late night hours (1AM-7AM) - Reduced activity")
                time.sleep(5)  # Small additional delay
            
            # Check safety limits
            if not check_daily_limits_fast():
                print("💤 Daily limit reached. Sleeping for 30 minutes...")
                time.sleep(1800)  # Reduced from 1 hour
                continue
            
            # Process all channels quickly
            total_forwarded = 0
            for name, channel_id in zip(channel_names, SOURCE_CHANNELS):
                deals = process_channel_balanced(name, channel_id)
                total_forwarded += deals
                time.sleep(0.5)  # Reduced delay between channels
            
            # Quick status update
            if total_forwarded > 0:
                print(f"🎉 {total_forwarded} deals forwarded!")
            else:
                print("👀 No new deals")
            
            print(f"📈 Total: {stats.total_forwarded} | Dupes: {stats.duplicates_blocked} | Spam: {stats.spam_filtered}")
            print(f"⏳ Next check in {CHECK_INTERVAL} seconds...\n")
            
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"💥 Critical error: {str(e)}")
            stats.increment_errors()
            print("🔄 Restarting in 15 seconds...")
            time.sleep(15)

# ==================== COMPLETE FLASK WEB SERVICE ====================
@app.route('/')
def home():
    waha_status = "✅ Connected" if get_waha_health_fast() else "❌ Disconnected"
    daily_remaining = MAX_DAILY_MESSAGES - daily_message_count
    hourly_remaining = MAX_HOURLY_MESSAGES - hourly_message_count
    uptime = stats.get_duration()
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>WhatsApp Deal Forwarder - BALANCED SPEED</title>
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
            .optimized {{ background: #d4edff; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 BALANCED WhatsApp Forwarder - OPTIMIZED SPEED</h1>
            
            <div class="status {('connected' if waha_status == '✅ Connected' else 'disconnected')}">
                <strong>Status:</strong> {waha_status} | Monitoring 5 channels | OPTIMIZED MODE
            </div>
            
            <div class="optimized">
                <strong>⚡ PERFORMANCE OPTIMIZED:</strong><br>
                • Faster Checking (15s) • Reduced Delays (5s) • More Messages (25/check)<br>
                • Quick Processing • All Features Active • WhatsApp Safe
            </div>
            
            <div class="stats">
                <h3>📊 Live Statistics</h3>
                <p><strong>WAHA Status:</strong> {waha_status}</p>
                <p><strong>Current WAHA:</strong> {WAHA_URL}</p>
                <p><strong>QR Code Dashboard:</strong> <a href="https://waha-1-v384.onrender.com/web" target="_blank">Click for QR Code</a></p>
                
                <p><strong>Forwarded Today:</strong> {daily_message_count}/{MAX_DAILY_MESSAGES} ({daily_remaining} remaining)</p>
                <div class="progress">
                    <div class="progress-bar" style="width: {(daily_message_count/MAX_DAILY_MESSAGES)*100}%"></div>
                </div>
                
                <p><strong>This Hour:</strong> {hourly_message_count}/{MAX_HOURLY_MESSAGES} ({hourly_remaining} remaining)</p>
                <div class="progress">
                    <div class="progress-bar" style="width: {(hourly_message_count/MAX_HOURLY_MESSAGES)*100}%"></div>
                </div>
                
                <p><strong>Total Forwarded:</strong> {stats.total_forwarded}</p>
                <p><strong>Duplicates Blocked:</strong> {stats.duplicates_blocked}</p>
                <p><strong>Spam Filtered:</strong> {stats.spam_filtered}</p>
                <p><strong>Errors:</strong> {stats.errors_count}</p>
                <p><strong>Uptime:</strong> {str(uptime).split('.')[0]}</p>
                <p><strong>Health Checks:</strong> {stats.check_count}</p>
            </div>
            
            <div style="margin-top: 20px;">
                <p><strong>🔗 Management Links:</strong></p>
                <a href="/health">Health Check</a> | 
                <a href="/ping">Keep-Alive Ping</a> | 
                <a href="/stats">Detailed Statistics</a> |
                <a href="/test-whatsapp">Test WhatsApp</a> |
                <a href="/waha-health">WAHA Health</a>
            </div>
            
            <hr>
            <p><em>✅ Balanced Speed • 24/7 Operation • All Features • WhatsApp Safe</em></p>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    waha_status = "✅ Connected" if get_waha_health_fast() else "❌ Disconnected"
    return {
        "status": "running", 
        "service": "balanced-deal-forwarder-optimized",
        "timestamp": datetime.now().isoformat(),
        "waha_status": waha_status,
        "performance": {
            "check_interval": CHECK_INTERVAL,
            "send_delay": MIN_TIME_BETWEEN_SENDS,
            "messages_per_check": MESSAGE_LIMIT,
            "hourly_limit": MAX_HOURLY_MESSAGES,
            "daily_limit": MAX_DAILY_MESSAGES
        },
        "message_limits": {
            "daily": f"{daily_message_count}/{MAX_DAILY_MESSAGES}",
            "hourly": f"{hourly_message_count}/{MAX_HOURLY_MESSAGES}"
        },
        "features": [
            "24_7_operation",
            "optimized_speed",
            "rotating_hashtags", 
            "spam_filtering",
            "4_layer_deduplication",
            "amazon_affiliate",
            "safety_limits",
            "auto_retry",
            "health_monitoring",
            "fast_processing"
        ]
    }

@app.route('/ping')
def ping():
    return {
        "status": "pong", 
        "timestamp": datetime.now().isoformat(),
        "service": "balanced-deal-forwarder-optimized",
        "message": "Optimized service running 24/7",
        "performance": "balanced_speed"
    }

@app.route('/stats')
def stats_page():
    daily_remaining = MAX_DAILY_MESSAGES - daily_message_count
    hourly_remaining = MAX_HOURLY_MESSAGES - hourly_message_count
    
    return {
        "service": "balanced-deal-forwarder-optimized",
        "timestamp": datetime.now().isoformat(),
        "performance": {
            "total_forwarded": stats.total_forwarded,
            "duplicates_blocked": stats.duplicates_blocked,
            "spam_filtered": stats.spam_filtered,
            "health_checks": stats.check_count,
            "uptime": str(stats.get_duration())
        },
        "configuration": {
            "check_interval": CHECK_INTERVAL,
            "min_send_delay": MIN_TIME_BETWEEN_SENDS,
            "message_limit_per_check": MESSAGE_LIMIT,
            "hourly_message_limit": MAX_HOURLY_MESSAGES,
            "daily_message_limit": MAX_DAILY_MESSAGES
        }
    }

@app.route('/test-whatsapp')
def test_whatsapp():
    test_message = f"""✅ TEST - Balanced Speed Forwarder

System Status: OPTIMIZED
• Speed: Enhanced
• Safety: Active  
• Features: All Working
• Messages Today: {daily_message_count}/{MAX_DAILY_MESSAGES}

Timestamp: {datetime.now().isoformat()}

#Optimized #Working #AllFeatures"""

    if send_whatsapp_message_optimized(test_message):
        return {"status": "success", "message": "Test message sent successfully"}
    else:
        return {"status": "error", "message": "Failed to send test message"}

@app.route('/waha-health')
def waha_health():
    health_status = get_waha_health_fast()
    return {
        "waha_url": WAHA_URL,
        "status": "healthy" if health_status else "unhealthy",
        "response_time": "fast_check"
    }

# ==================== AUTO-START SERVICES ====================
print("🎯 Starting BALANCED WhatsApp Forwarder - OPTIMIZED SPEED...")
print("💡 Active: Faster processing + All features + WhatsApp safety")
print("🌐 Web service starting on port 5000...")

# Start the forwarder in background thread
forwarder_thread = threading.Thread(target=deal_forwarder_main, daemon=True)
forwarder_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)