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
USE_EARNKARO = os.getenv("USE_EARNKARO", "false").lower() == "true"

# ==================== SAFETY LIMITS ====================
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))
MIN_TIME_BETWEEN_SENDS = int(os.getenv("MIN_TIME_BETWEEN_SENDS", "8"))
MAX_DAILY_MESSAGES = int(os.getenv("MAX_DAILY_MESSAGES", "400"))
MAX_HOURLY_MESSAGES = int(os.getenv("MAX_HOURLY_MESSAGES", "35"))
MESSAGE_LIMIT = int(os.getenv("MESSAGE_LIMIT", "6"))

# ==================== ENHANCED ROTATING HASHTAGS ====================
HASHTAG_CATEGORIES = {
    'time_based': [
        "#MorningDeals", "#AfternoonDeals", "#EveningDeals", 
        "#LateNightDeals", "#NightOwlDeals", "#MidnightDeals",
        "#EarlyAccess", "#TodayDeals", "#DailyDeals", "#WeekendSale"
    ],
    'platform_based': [
        "#AmazonDeals", "#AmazonIndia", "#AmazonSale",
        "#FlipkartDeals", "#FlipkartSale", "#MyntraDeals", 
        "#AjioOffers", "#AjioLoot", "#FashionSale", "#TechDeals"
    ],
    'price_based': [
        "#Under500", "#Under1000", "#BudgetFriendly", "#ValueDeal",
        "#PremiumDeals", "#LuxuryDeals", "#Affordable", "#CheapDeals"
    ],
    'category_based': [
        "#Electronics", "#Fashion", "#HomeDecor", "#Kitchen", 
        "#Beauty", "#MobileDeals", "#LaptopDeals", "#GadgetDeals",
        "#HomeAppliances", "#KitchenEssentials", "#ClothingSale"
    ],
    'urgency_based': [
        "#LimitedTime", "#FlashSale", "#TodayOnly", "#Hurry",
        "#QuickDeal", "#HotDeal", "#SpecialOffer", "#ExclusiveDeal",
        "#LimitedStock", "#LastChance"
    ]
}

def get_rotating_hashtags(product_text, platform, message_count):
    """Get rotating hashtags that change based on multiple factors"""
    selected_hashtags = []
    
    # Platform-specific (always include 1)
    platform_lower = platform.lower()
    if "amazon" in platform_lower:
        platform_options = ["#AmazonDeals", "#AmazonIndia", "#AmazonSale"]
    elif "flipkart" in platform_lower:
        platform_options = ["#FlipkartDeals", "#FlipkartSale"]
    elif "myntra" in platform_lower:
        platform_options = ["#MyntraDeals", "#FashionSale"]
    elif "ajio" in platform_lower:
        platform_options = ["#AjioOffers", "#AjioLoot"]
    else:
        platform_options = ["#Deals", "#Offers"]
    
    # Rotate platform hashtags based on message count
    platform_idx = message_count % len(platform_options)
    selected_hashtags.append(platform_options[platform_idx])
    
    # Time-based (rotate every hour)
    current_hour = datetime.now().hour
    time_options = HASHTAG_CATEGORIES['time_based']
    time_idx = (current_hour + message_count) % len(time_options)
    selected_hashtags.append(time_options[time_idx])
    
    # Price-based (if price detected)
    price_match = re.search(r'₹(\d+,?\d+)', product_text)
    if price_match:
        price = int(price_match.group(1).replace(',', ''))
        if price < 500:
            price_tag = "#Under500"
        elif price < 1000:
            price_tag = "#Under1000"
        elif price < 2000:
            price_tag = "#BudgetFriendly"
        else:
            price_tag = "#PremiumDeals"
        selected_hashtags.append(price_tag)
    else:
        # Category-based as fallback
        text_lower = product_text.lower()
        if any(word in text_lower for word in ['laptop', 'mobile', 'headphone', 'earphone', 'tablet', 'camera']):
            category_tag = "#TechDeals"
        elif any(word in text_lower for word in ['shirt', 'dress', 'jeans', 'shoe', 'sandal', 'top', 'kurta']):
            category_tag = "#FashionDeals"
        elif any(word in text_lower for word in ['kitchen', 'cooker', 'home', 'furniture', 'decor', 'appliance']):
            category_tag = "#HomeDecor"
        elif any(word in text_lower for word in ['beauty', 'cream', 'lotion', 'makeup', 'skincare']):
            category_tag = "#BeautyDeals"
        else:
            # Random category based on message count
            categories = HASHTAG_CATEGORIES['category_based']
            category_idx = (message_count * 3) % len(categories)
            category_tag = categories[category_idx]
        selected_hashtags.append(category_tag)
    
    return ' '.join(selected_hashtags[:3])  # Max 3 hashtags

# ==================== ENHANCED DEDUPLICATION ====================
seen_hashes = set()  # Full message hashes
seen_asins = set()   # Amazon ASINs
seen_product_ids = set()  # Flipkart/Myntra/Ajio product IDs
seen_urls = set()    # Clean URLs
last_processed_timestamps = {}

# ==================== SAFETY TRACKING ====================
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
    
    def increment_forwarded(self): self.total_forwarded += 1
    def increment_check(self): self.check_count += 1
    def increment_missed(self): self.missed_deals += 1
    def increment_duplicates(self): self.duplicates_blocked += 1
    def get_duration(self): return datetime.now() - self.session_start

stats = Stats()

# ==================== ENHANCED URL PROCESSING ====================
def extract_amazon_asin(url):
    """Extract Amazon ASIN from URL"""
    patterns = [
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})',
        r'/product/([A-Z0-9]{10})',
        r'&asin=([A-Z0-9]{10})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match: 
            return match.group(1).upper()
    return None

def extract_product_id(url):
    """Extract product ID from various platforms"""
    if 'flipkart.com' in url:
        match = re.search(r'/p/([a-zA-Z0-9]+)', url)
        return f"flipkart_{match.group(1)}" if match else None
    elif 'myntra.com' in url:
        match = re.search(r'/product/([a-zA-Z0-9]+)', url)
        return f"myntra_{match.group(1)}" if match else None
    elif 'ajio.com' in url:
        match = re.search(r'/p/([a-zA-Z0-9]+)', url)
        return f"ajio_{match.group(1)}" if match else None
    return None

def clean_and_normalize_url(url):
    """Clean URL and remove tracking parameters"""
    try:
        parsed = urlparse(url)
        
        # Remove common tracking parameters
        query_params = parse_qs(parsed.query)
        tracking_params = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 
                          'utm_content', 'ref', 'cmpid', 'source', 'icid', 'linkCode']
        
        for param in tracking_params:
            query_params.pop(param, None)
        
        # Rebuild clean URL
        clean_query = '&'.join([f"{k}={v[0]}" for k, v in query_params.items()])
        cleaned_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if clean_query:
            cleaned_url += f"?{clean_query}"
        
        return cleaned_url
    except:
        return url

def apply_amazon_affiliate(url):
    """Always apply our Amazon affiliate tag, replacing any existing"""
    if not url or ('amazon.' not in url.lower() and 'amzn.to' not in url.lower()):
        return url
    
    # Clean the URL first
    cleaned_url = clean_and_normalize_url(url)
    
    # Remove any existing tag
    cleaned_url = re.sub(r'&tag=[^&]+', '', cleaned_url)
    cleaned_url = re.sub(r'\?tag=[^&]+', '', cleaned_url)
    
    # Add our tag
    separator = '&' if '?' in cleaned_url else '?'
    return f"{cleaned_url}{separator}tag={AMAZON_AFFILIATE_TAG}"

def is_safe_url(url):
    """Check if URL is from safe domains"""
    safe_domains = ['amazon.in', 'amzn.to', 'flipkart.com', 'fkrt.co', 
                   'myntra.com', 'ajio.com', 'flipkart.com']
    try: 
        domain = urlparse(url).netloc.lower()
        return any(safe_domain in domain for safe_domain in safe_domains)
    except: 
        return False

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

# ==================== ENHANCED DEDUPLICATION FUNCTIONS ====================
def generate_message_hash(text): 
    return hashlib.md5(text.encode()).hexdigest()

def is_duplicate_message(text, url, platform):
    """Enhanced duplicate detection using multiple methods"""
    if not text or not url:
        return True
    
    # Method 1: Full message hash
    message_hash = generate_message_hash(text)
    if message_hash in seen_hashes:
        stats.increment_duplicates()
        print("    🔄 Duplicate: Same message content")
        return True
    
    # Method 2: URL-based deduplication
    clean_url = clean_and_normalize_url(url)
    if clean_url in seen_urls:
        stats.increment_duplicates()
        print("    🔄 Duplicate: Same URL")
        return True
    
    # Method 3: Platform-specific ID deduplication
    if 'amazon' in platform.lower():
        asin = extract_amazon_asin(url)
        if asin and asin in seen_asins:
            stats.increment_duplicates()
            print(f"    🔄 Duplicate: Amazon ASIN {asin}")
            return True
    else:
        product_id = extract_product_id(url)
        if product_id and product_id in seen_product_ids:
            stats.increment_duplicates()
            print(f"    🔄 Duplicate: Product ID {product_id}")
            return True
    
    return False

def add_to_dedup(text, url, platform):
    """Add message to duplicate tracking"""
    if not text or not url:
        return
    
    # Track full message hash
    message_hash = generate_message_hash(text)
    seen_hashes.add(message_hash)
    
    # Track clean URL
    clean_url = clean_and_normalize_url(url)
    seen_urls.add(clean_url)
    
    # Track platform-specific IDs
    if 'amazon' in platform.lower():
        asin = extract_amazon_asin(url)
        if asin:
            seen_asins.add(asin)
    else:
        product_id = extract_product_id(url)
        if product_id:
            seen_product_ids.add(product_id)

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

# ==================== ENHANCED MESSAGE PROCESSING ====================
def process_message_ultra_fast(text):
    if not text: 
        return None, None
    
    # Clean source info
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
    
    # Platform detection
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
    
    # Extract product name
    clean_text = re.sub(r'https?://[^\s]+', '', text)
    lines = [line.strip() for line in clean_text.split('\n') if line.strip() and len(line) > 8]
    product_name = lines[0] if lines else "Hot Deal! 🔥"
    
    # Extract price & discount
    price_match = re.search(r'@\s*(\d+,?\d*)|₹\s*(\d+,?\d*)', text)
    price_info = f"💰 ₹{price_match.group(1)}" if price_match else ""
    
    discount_match = re.search(r'(\d+%)', text)
    discount_info = f"🎯 {discount_match.group(1)}" if discount_match else ""
    
    # Build message with rotating hashtags
    message_parts = [platform, f"\n{product_name}"]
    if price_info:
        message_parts.append(f"\n{price_info}")
    if discount_info:
        message_parts.append(f"\n{discount_info}")
    
    message_parts.append(f"\n\n{final_url}")
    
    # Add rotating hashtags based on message count
    rotating_hashtags = get_rotating_hashtags(text, platform, stats.total_forwarded)
    message_parts.append(f"\n\n{rotating_hashtags}")
    
    final_message = ''.join(message_parts)
    return final_message, main_url

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
            if message.get('fromMe') or not message.get('body'): 
                continue
            
            message_timestamp = message.get('timestamp', 0)
            if message_timestamp <= last_timestamp: 
                continue
                
            if message_timestamp > new_last_timestamp:
                new_last_timestamp = message_timestamp
            
            # Process messages from last 5 minutes only
            if time.time() - message_timestamp > 300:
                stats.increment_missed()
                continue
            
            processed_message, original_url = process_message_ultra_fast(message.get('body', ''))
            if not processed_message:
                continue
            
            # Enhanced duplicate check
            platform = "🛍️ Amazon" if 'amazon' in processed_message.lower() else "📦 Other"
            if is_duplicate_message(processed_message, original_url, platform):
                continue
            
            if send_whatsapp_message_optimized(processed_message):
                deals_found += 1
                stats.increment_forwarded()
                add_to_dedup(processed_message, original_url, platform)
                print(f"    🚀 {channel_name}: DEAL SENT!")
            
        last_processed_timestamps[channel_id] = new_last_timestamp
            
    except Exception as e:
        print(f"    ❌ {channel_name} error: {str(e)}")
    
    return deals_found

# ==================== MAIN FORWARDER LOOP ====================
def deal_forwarder_main():
    """MAIN DEAL FORWARDER LOOP - 24/7 OPERATION"""
    channel_names = ["TechFactsDeals", "Loots4u", "Shopping Loot Offers", "Loot Deals Official", "Loot Bazaar"]
    
    print("🚀 ENHANCED WhatsApp Forwarder - 24/7 Cloud Operation!")
    print("=" * 60)
    print(f"📡 WAHA URL: {WAHA_URL}")
    print(f"🎯 Destination: {DESTINATION_CHANNEL}")
    print(f"🛡️  Daily limit: {MAX_DAILY_MESSAGES} messages")
    print(f"⚡ Check interval: {CHECK_INTERVAL} seconds")
    print(f"🔍 Enhanced deduplication: ASIN + Product ID + URL + Text hash")
    print(f"🏷️  Rotating hashtags: Platform + Time + Price/Category")
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
            print(f"🚫 Duplicates blocked: {stats.duplicates_blocked}")
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
            .warning {{ background: #fff3cd; color: #856404; padding: 10px; border-radius: 5px; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 ENHANCED WhatsApp Deal Forwarder Running 24/7!</h1>
            
            <div class="status {('connected' if waha_status == '✅ Connected' else 'disconnected')}">
                <strong>Status:</strong> Monitoring 5 channels for deals
            </div>
            
            <div class="warning">
                <strong>⚠️ Note:</strong> Use the link below for QR Code scanning
            </div>
            
            <div class="stats">
                <p><strong>WAHA Status:</strong> {waha_status}</p>
                <p><strong>Current WAHA:</strong> {WAHA_URL}</p>
                <p><strong>QR Code Dashboard:</strong> <a href="https://waha-1-v384.onrender.com/web" target="_blank">Click here for QR Code</a></p>
                
                <p><strong>Forwarded Today:</strong> {daily_message_count}/{MAX_DAILY_MESSAGES} ({daily_remaining} remaining)</p>
                <div class="progress">
                    <div class="progress-bar" style="width: {(daily_message_count/MAX_DAILY_MESSAGES)*100}%"></div>
                </div>
                
                <p><strong>Total Forwarded:</strong> {stats.total_forwarded}</p>
                <p><strong>Duplicates Blocked:</strong> {stats.duplicates_blocked}</p>
                <p><strong>Uptime:</strong> {str(uptime).split('.')[0]}</p>
                <p><strong>Health Checks:</strong> {stats.check_count}</p>
            </div>
            
            <div style="margin-top: 20px;">
                <p><strong>Quick Links:</strong></p>
                <a href="/health">Health Check</a> | 
                <a href="/ping">Ping</a> | 
                <a href="/stats">Statistics</a> |
                <a href="/test-whatsapp">Test WhatsApp</a> |
                <a href="/waha-health">WAHA Health</a>
            </div>
            
            <hr>
            <p><em>✅ Enhanced Features: Rotating Hashtags + Strict Deduplication + 24/7 Operation!</em></p>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    waha_status = "✅ Connected" if get_waha_health() else "❌ Disconnected"
    return {
        "status": "running", 
        "service": "enhanced-deal-forwarder",
        "timestamp": datetime.now().isoformat(),
        "waha_status": waha_status,
        "waha_url": WAHA_URL,
        "forwarded_today": daily_message_count,
        "total_forwarded": stats.total_forwarded,
        "duplicates_blocked": stats.duplicates_blocked,
        "uptime": str(stats.get_duration()),
        "health_checks": stats.check_count,
        "features": [
            "rotating_hashtags",
            "strict_deduplication", 
            "amazon_affiliate_forced",
            "24_7_operation",
            "safety_limits",
            "multi_platform_support"
        ]
    }

@app.route('/ping')
def ping():
    """Keep-alive endpoint to prevent Render sleep"""
    return {
        "status": "pong", 
        "timestamp": datetime.now().isoformat(),
        "service": "enhanced-deal-forwarder",
        "message": "Service is alive and running"
    }

@app.route('/stats')
def stats_page():
    """Detailed statistics"""
    daily_remaining = MAX_DAILY_MESSAGES - daily_message_count
    hourly_remaining = MAX_HOURLY_MESSAGES - hourly_message_count
    
    return {
        "service": "enhanced-deal-forwarder",
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
            "duplicates_blocked": stats.duplicates_blocked,
            "health_checks": stats.check_count,
            "uptime": str(stats.get_duration())
        },
        "deduplication": {
            "tracked_hashes": len(seen_hashes),
            "tracked_asins": len(seen_asins),
            "tracked_product_ids": len(seen_product_ids),
            "tracked_urls": len(seen_urls)
        },
        "configuration": {
            "check_interval": CHECK_INTERVAL,
            "min_send_delay": MIN_TIME_BETWEEN_SENDS,
            "message_limit_per_check": MESSAGE_LIMIT,
            "amazon_affiliate_tag": AMAZON_AFFILIATE_TAG,
            "use_earnkaro": USE_EARNKARO
        }
    }

@app.route('/test-whatsapp')
def test_whatsapp():
    """Test WhatsApp sending"""
    test_message = "✅ Test message from Enhanced Deal Forwarder\nThis confirms your system is working!\n\nTimestamp: " + datetime.now().isoformat()
    
    if send_whatsapp_message_optimized(test_message):
        return {"status": "success", "message": "Test message sent successfully"}
    else:
        return {"status": "error", "message": "Failed to send test message"}

@app.route('/waha-health')
def waha_health():
    """Check WAHA health status"""
    health_status = get_waha_health()
    return {
        "waha_url": WAHA_URL,
        "status": "healthy" if health_status else "unhealthy",
        "timestamp": datetime.now().isoformat()
    }

@app.route('/update-waha-url', methods=['GET'])
def update_waha_url():
    """Update WAHA URL (for manual use)"""
    new_url = request.args.get('url')
    if new_url:
        global WAHA_URL
        WAHA_URL = new_url
        return {"status": "success", "message": f"WAHA URL updated to: {new_url}"}
    else:
        return {"status": "error", "message": "No URL provided"}

# ==================== START SERVICES ====================
print("🎯 Starting ENHANCED WhatsApp Forwarder...")
print("💡 Features: Rotating Hashtags + Strict Deduplication + 24/7 Operation")
print("🌐 Web service starting on port 5000...")

# Start the forwarder in background thread
forwarder_thread = threading.Thread(target=deal_forwarder_main, daemon=True)
forwarder_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)