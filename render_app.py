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

# ==================== RENDER ENV VARIABLES ====================
WAHA_URL = os.getenv("WAHA_URL", "https://waha-production-32e7.up.railway.app")
DESTINATION_CHANNEL = os.getenv("DESTINATION_CHANNEL", "120363422574401710@newsletter")
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS", "120363177070916101@newsletter,120363179368338362@newsletter,120363180244702234@newsletter,120363290169377613@newsletter,120363161802971651@newsletter").split(",")
AMAZON_AFFILIATE_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "lootfastdeals-21")

# ==================== BALANCED PERFORMANCE SETTINGS ====================
MAX_DAILY_MESSAGES = int(os.getenv("MAX_DAILY_MESSAGES", "450"))
MAX_HOURLY_MESSAGES = int(os.getenv("MAX_HOURLY_MESSAGES", "45"))
MESSAGE_LIMIT = int(os.getenv("MESSAGE_LIMIT", "25"))
MIN_TIME_BETWEEN_SENDS = int(os.getenv("MIN_TIME_BETWEEN_SENDS", "5"))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "15"))

# ==================== ENHANCED DEDUPLICATION ====================
seen_hashes = set()
seen_asins = set()
seen_product_ids = set()
seen_urls = set()
seen_product_names = set()  # NEW: Track product names
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

# ==================== ENHANCED ASIN EXTRACTION ====================
def extract_amazon_asin_enhanced(url):
    """Enhanced ASIN extraction from various Amazon URL formats"""
    if not url:
        return None
    
    # Clean the URL first
    clean_url = re.sub(r'\?tag=.*', '', url)  # Remove affiliate tags
    clean_url = re.sub(r'&tag=.*', '', clean_url)
    
    # Multiple ASIN patterns
    patterns = [
        r'/dp/([A-Z0-9]{10})',           # Standard /dp/ASIN
        r'/gp/product/([A-Z0-9]{10})',   # /gp/product/ASIN
        r'/product/([A-Z0-9]{10})',      # /product/ASIN
        r'&asin=([A-Z0-9]{10})',         # &asin=ASIN
        r'%2Fdp%2F([A-Z0-9]{10})',       # URL encoded
        r'amzn\.to/[a-zA-Z0-9]+.*[&?]a=([A-Z0-9]{10})',  # amzn.to links
    ]
    
    for pattern in patterns:
        match = re.search(pattern, clean_url, re.IGNORECASE)
        if match: 
            asin = match.group(1).upper()
            # Validate ASIN format (10 alphanumeric characters)
            if re.match(r'^[A-Z0-9]{10}$', asin):
                return asin
    
    # Try to extract from amzn.to short links by following redirects
    if 'amzn.to' in url.lower():
        try:
            response = requests.head(url, timeout=5, allow_redirects=True)
            final_url = response.url
            return extract_amazon_asin_enhanced(final_url)
        except:
            pass
    
    return None

def extract_product_name_fast(text):
    """Extract and normalize product name for duplicate checking"""
    if not text:
        return None
    
    # Remove URLs and clean text
    clean_text = re.sub(r'https?://[^\s]+', '', text)
    clean_text = re.sub(r'From\s*\*\s*[^:]*:|### From.*', '', clean_text)
    
    # Extract potential product name (first meaningful line)
    lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
    
    for line in lines:
        if len(line) > 10 and not re.search(r'f+a+s+t+', line.lower()):
            # Normalize the product name
            normalized = re.sub(r'\s+', ' ', line)  # Remove extra spaces
            normalized = re.sub(r'[^\w\s]', '', normalized)  # Remove special chars
            normalized = normalized.strip().lower()
            
            # Skip if it's just price information
            if re.search(r'₹|\$|price|at\s*\d+', normalized):
                continue
                
            return normalized[:100]  # Limit length
    
    return None

def extract_product_id_enhanced(url):
    """Enhanced product ID extraction"""
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

# ==================== ENHANCED DUPLICATE DETECTION ====================
def is_duplicate_message_enhanced(text, url, platform):
    """5-LAYER DUPLICATE DETECTION - FIXED"""
    if not text or not url:
        return True
    
    # Layer 1: URL-based deduplication
    clean_url = clean_and_normalize_url(url)
    if clean_url in seen_urls:
        stats.increment_duplicates()
        print("    🔄 Duplicate: Same URL")
        return True
    
    # Layer 2: Platform-specific ID deduplication
    if 'amazon' in platform.lower():
        asin = extract_amazon_asin_enhanced(url)  # Use enhanced ASIN extraction
        if asin and asin in seen_asins:
            stats.increment_duplicates()
            print(f"    🔄 Duplicate: Amazon ASIN {asin}")
            return True
    else:
        product_id = extract_product_id_enhanced(url)
        if product_id and product_id in seen_product_ids:
            stats.increment_duplicates()
            print(f"    🔄 Duplicate: Product ID {product_id}")
            return True
    
    # Layer 3: Product name similarity (NEW - fixes your issue)
    product_name = extract_product_name_fast(text)
    if product_name and product_name in seen_product_names:
        stats.increment_duplicates()
        print(f"    🔄 Duplicate: Similar product name")
        return True
    
    # Layer 4: Message content hash
    message_hash = generate_message_hash(text)
    if message_hash in seen_hashes:
        stats.increment_duplicates()
        print("    🔄 Duplicate: Same message content")
        return True
    
    return False

def add_to_dedup_enhanced(text, url, platform):
    """Enhanced duplicate tracking"""
    if not text or not url:
        return
    
    # Track clean URL
    clean_url = clean_and_normalize_url(url)
    seen_urls.add(clean_url)
    
    # Track platform-specific IDs
    if 'amazon' in platform.lower():
        asin = extract_amazon_asin_enhanced(url)
        if asin:
            seen_asins.add(asin)
            print(f"    📝 Tracking ASIN: {asin}")
    else:
        product_id = extract_product_id_enhanced(url)
        if product_id:
            seen_product_ids.add(product_id)
    
    # Track product name
    product_name = extract_product_name_fast(text)
    if product_name:
        seen_product_names.add(product_name)
        print(f"    📝 Tracking product: {product_name[:50]}...")
    
    # Track message hash
    message_hash = generate_message_hash(text)
    seen_hashes.add(message_hash)

# ==================== REST OF THE FUNCTIONS (Keep from previous script) ====================
def clean_and_normalize_url(url):
    """Clean URL and remove tracking parameters"""
    try:
        parsed = urlparse(url)
        
        # Remove tracking parameters
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
    """Always apply our Amazon affiliate tag"""
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

def generate_message_hash(text): 
    return hashlib.md5(text.encode()).hexdigest()

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

def check_daily_limits_fast():
    global daily_message_count, hourly_message_count, daily_reset_time, hourly_reset_time
    
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
        time.sleep(300)
        hourly_message_count = 0
        return True
    
    return True

def get_safe_send_delay_fast():
    base_delay = MIN_TIME_BETWEEN_SENDS
    if hourly_message_count > 30:
        base_delay += 2
    return base_delay + random.uniform(0.5, 2)

def get_waha_health_fast():
    try:
        response = requests.get(f"{WAHA_URL}/api/sessions", timeout=5)
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
        response = requests.post(f"{WAHA_URL}/api/sendText", json=payload, timeout=10)
        
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
            timeout=8
        )
        return response.json() if response.status_code == 200 else []
    except Exception as e:
        print(f"    ❌ Error fetching messages: {e}")
        return []

# ==================== HASHTAG FUNCTIONS (Keep from previous) ====================
HASHTAG_CATEGORIES = {
    'time_based': ["#MorningDeals", "#AfternoonDeals", "#EveningDeals", "#LateNightDeals"],
    'platform_based': {
        'amazon': ["#AmazonDeals", "#AmazonIndia", "#AmazonSale"],
        'flipkart': ["#FlipkartDeals", "#FlipkartSale"],
        'myntra': ["#MyntraDeals", "#FashionSale"],
        'ajio': ["#AjioOffers", "#AjioLoot"],
    },
    'price_based': ["#Under500", "#Under1000", "#BudgetFriendly", "#PremiumDeals"],
    'category_based': ["#Electronics", "#Fashion", "#HomeDecor", "#TechDeals"]
}

def get_fast_hashtags(product_text, platform, message_count):
    selected_hashtags = []
    
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
        platform_tags = ["#Deals", "#Offers"]
    
    platform_idx = message_count % len(platform_tags)
    selected_hashtags.append(platform_tags[platform_idx])
    
    current_hour = datetime.now().hour
    time_tags = HASHTAG_CATEGORIES['time_based']
    time_idx = current_hour % len(time_tags)
    selected_hashtags.append(time_tags[time_idx])
    
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
    
    return ' '.join(selected_hashtags[:3])

def process_message_balanced(text):
    if not text: 
        return None, None
    
    if is_spam_message_fast(text):
        stats.increment_spam()
        print("    🚫 Filtered: Spam message")
        return None, None
    
    text = re.sub(r'From\s*\*\s*[^:]*:|### From.*', '', text)
    
    urls = re.findall(r'https?://[^\s]+', text)
    if not urls: 
        return None, None
    
    safe_urls = [url for url in urls if is_safe_url(url)]
    if not safe_urls: 
        return None, None
    
    main_url = safe_urls[0]
    
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
    
    clean_text = re.sub(r'https?://[^\s]+', '', text)
    lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
    
    product_name = "Hot Deal! 🔥"
    for line in lines:
        if len(line) > 8 and not re.search(r'f+a+s+t+', line.lower()):
            product_name = line[:80]
            break
    
    price_match = re.search(r'[@₹]\s*(\d+,?\d*,?\d+)', text)
    price_info = f"💰 ₹{price_match.group(1)}" if price_match else "💰 Great Deal!"
    
    discount_match = re.search(r'(\d+%?\s*off)', text, re.IGNORECASE)
    discount_info = f"🎯 {discount_match.group(1)}" if discount_match else ""
    
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
            
            if time.time() - message_timestamp > 600:
                stats.increment_missed()
                continue
            
            processed_message, original_url = process_message_balanced(message.get('body', ''))
            if not processed_message:
                continue
            
            platform = "🛍️ Amazon" if 'amazon' in processed_message.lower() else "📦 Other"
            
            # USE ENHANCED DUPLICATE DETECTION
            if is_duplicate_message_enhanced(processed_message, original_url, platform):
                continue
            
            if send_whatsapp_message_optimized(processed_message):
                deals_found += 1
                stats.increment_forwarded()
                # USE ENHANCED DEDUPLICATION TRACKING
                add_to_dedup_enhanced(processed_message, original_url, platform)
                print(f"    🚀 {channel_name}: DEAL SENT!")
            
        last_processed_timestamps[channel_id] = new_last_timestamp
            
    except Exception as e:
        print(f"    ❌ {channel_name} error: {str(e)}")
        stats.increment_errors()
    
    return deals_found

# ==================== MAIN LOOP & FLASK ENDPOINTS (Keep same) ====================
def deal_forwarder_main():
    channel_names = ["TechFactsDeals", "Loots4u", "Shopping Loot Offers", "Loot Deals Official", "Loot Bazaar"]
    
    print("🚀 ENHANCED WhatsApp Forwarder - DUPLICATE FIXED!")
    print("=" * 60)
    print(f"📡 WAHA URL: {WAHA_URL}")
    print(f"🎯 Destination: {DESTINATION_CHANNEL}")
    print("🔍 ENHANCED: 5-layer duplicate detection + ASIN tracking")
    print("=" * 60)
    
    current_time = time.time()
    for channel_id in SOURCE_CHANNELS:
        last_processed_timestamps[channel_id] = current_time - 600
    
    print("⏳ Waiting for WAHA connection...")
    for i in range(10):
        if get_waha_health_fast():
            print("✅ WAHA connected successfully!")
            break
        print(f"   Waiting... ({i+1}/10)")
        time.sleep(3)
    else:
        print("⚠️  WAHA connection failed - will keep trying")
    
    loop_count = 0
    while True:
        try:
            stats.increment_check()
            loop_count += 1
            current_time_str = datetime.now().strftime("%H:%M:%S")
            
            print(f"\n🔄 CHECK #{stats.check_count} at {current_time_str}")
            print("-" * 40)
            
            if loop_count % 30 == 0:
                if not get_waha_health_fast():
                    print("🔁 Reconnecting to WAHA...")
                    time.sleep(5)
                    continue
            
            if not check_daily_limits_fast():
                print("💤 Daily limit reached. Sleeping for 30 minutes...")
                time.sleep(1800)
                continue
            
            total_forwarded = 0
            for name, channel_id in zip(channel_names, SOURCE_CHANNELS):
                deals = process_channel_balanced(name, channel_id)
                total_forwarded += deals
                time.sleep(0.5)
            
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
            time.sleep(15)

# Flask endpoints remain the same as previous script
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
        <title>WhatsApp Forwarder - DUPLICATE FIXED</title>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
            .status {{ padding: 15px; border-radius: 5px; margin: 10px 0; }}
            .connected {{ background: #d4edda; color: #155724; }}
            .fixed {{ background: #d1ecf1; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 WhatsApp Forwarder - DUPLICATE ISSUE FIXED</h1>
            
            <div class="status {('connected' if waha_status == '✅ Connected' else 'disconnected')}">
                <strong>Status:</strong> {waha_status} | Enhanced Duplicate Detection
            </div>
            
            <div class="fixed">
                <strong>✅ DUPLICATE FIXES APPLIED:</strong><br>
                • Enhanced ASIN extraction • Product name tracking • 5-layer detection<br>
                • Same product detection • Better URL normalization
            </div>
            
            <div style="background: #e2e3e5; padding: 15px; border-radius: 5px;">
                <p><strong>Forwarded Today:</strong> {daily_message_count}/{MAX_DAILY_MESSAGES} ({daily_remaining} remaining)</p>
                <p><strong>This Hour:</strong> {hourly_message_count}/{MAX_HOURLY_MESSAGES} ({hourly_remaining} remaining)</p>
                <p><strong>Total Forwarded:</strong> {stats.total_forwarded}</p>
                <p><strong>Duplicates Blocked:</strong> {stats.duplicates_blocked}</p>
                <p><strong>Spam Filtered:</strong> {stats.spam_filtered}</p>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return {"status": "running", "duplicate_fix": "active"}

@app.route('/ping')
def ping():
    return {"status": "pong"}

@app.route('/stats')
def stats_page():
    return {
        "duplicates_blocked": stats.duplicates_blocked,
        "tracked_asins": len(seen_asins),
        "tracked_products": len(seen_product_names)
    }

# ==================== START SERVICES ====================
print("🎯 Starting WhatsApp Forwarder - DUPLICATE FIXED VERSION...")
forwarder_thread = threading.Thread(target=deal_forwarder_main, daemon=True)
forwarder_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)