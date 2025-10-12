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
WAHA_URL = os.getenv("WAHA_URL", "http://localhost:3000")
DESTINATION_CHANNEL = os.getenv("DESTINATION_CHANNEL", "120363422574401710@newsletter")
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS", "120363177070916101@newsletter,120363179368338362@newsletter,120363180244702234@newsletter,120363290169377613@newsletter,120363161802971651@newsletter").split(",")
AMAZON_AFFILIATE_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "lootfastdeals-21")

# ==================== PERFORMANCE SETTINGS ====================
MAX_DAILY_MESSAGES = int(os.getenv("MAX_DAILY_MESSAGES", "450"))
MAX_HOURLY_MESSAGES = int(os.getenv("MAX_HOURLY_MESSAGES", "45"))
MESSAGE_LIMIT = int(os.getenv("MESSAGE_LIMIT", "25"))
MIN_TIME_BETWEEN_SENDS = int(os.getenv("MIN_TIME_BETWEEN_SENDS", "8"))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "15"))

# ==================== DEDUPLICATION ====================
seen_hashes = set()
seen_asins = set()
seen_product_ids = set()
seen_urls = set()
seen_product_names = set()
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

# ==================== CORE FUNCTIONS ====================
def extract_amazon_asin_enhanced(url):
    if not url: return None
    clean_url = re.sub(r'\?tag=.*', '', url)
    clean_url = re.sub(r'&tag=.*', '', clean_url)
    
    patterns = [
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})',
        r'/product/([A-Z0-9]{10})',
        r'&asin=([A-Z0-9]{10})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, clean_url, re.IGNORECASE)
        if match: 
            asin = match.group(1).upper()
            if re.match(r'^[A-Z0-9]{10}$', asin):
                return asin
    return None

def extract_product_name_fast(text):
    if not text: return None
    clean_text = re.sub(r'https?://[^\s]+', '', text)
    clean_text = re.sub(r'From\s*\*\s*[^:]*:|### From.*', '', clean_text)
    lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
    
    for line in lines:
        if len(line) > 10 and not re.search(r'f+a+s+t+', line.lower()):
            normalized = re.sub(r'\s+', ' ', line)
            normalized = re.sub(r'[^\w\s]', '', normalized)
            normalized = normalized.strip().lower()
            if re.search(r'₹|\$|price|at\s*\d+', normalized):
                continue
            return normalized[:100]
    return None

def clean_and_normalize_url(url):
    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        tracking_params = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'ref', 'cmpid', 'source', 'icid', 'linkCode']
        for param in tracking_params:
            query_params.pop(param, None)
        clean_query = '&'.join([f"{k}={v[0]}" for k, v in query_params.items()])
        cleaned_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if clean_query:
            cleaned_url += f"?{clean_query}"
        return cleaned_url
    except:
        return url

def apply_amazon_affiliate(url):
    if not url or ('amazon.' not in url.lower() and 'amzn.to' not in url.lower()):
        return url
    cleaned_url = clean_and_normalize_url(url)
    cleaned_url = re.sub(r'&tag=[^&]+', '', cleaned_url)
    cleaned_url = re.sub(r'\?tag=[^&]+', '', cleaned_url)
    separator = '&' if '?' in cleaned_url else '?'
    return f"{cleaned_url}{separator}tag={AMAZON_AFFILIATE_TAG}"

def is_duplicate_message_enhanced(text, url, platform):
    if not text or not url: return True
    
    clean_url = clean_and_normalize_url(url)
    if clean_url in seen_urls:
        stats.increment_duplicates()
        return True
    
    if 'amazon' in platform.lower():
        asin = extract_amazon_asin_enhanced(url)
        if asin and asin in seen_asins:
            stats.increment_duplicates()
            return True
    else:
        product_id = extract_product_id_enhanced(url)
        if product_id and product_id in seen_product_ids:
            stats.increment_duplicates()
            return True
    
    product_name = extract_product_name_fast(text)
    if product_name and product_name in seen_product_names:
        stats.increment_duplicates()
        return True
    
    message_hash = hashlib.md5(text.encode()).hexdigest()
    if message_hash in seen_hashes:
        stats.increment_duplicates()
        return True
    
    return False

def add_to_dedup_enhanced(text, url, platform):
    if not text or not url: return
    clean_url = clean_and_normalize_url(url)
    seen_urls.add(clean_url)
    
    if 'amazon' in platform.lower():
        asin = extract_amazon_asin_enhanced(url)
        if asin: seen_asins.add(asin)
    else:
        product_id = extract_product_id_enhanced(url)
        if product_id: seen_product_ids.add(product_id)
    
    product_name = extract_product_name_fast(text)
    if product_name: seen_product_names.add(product_name)
    
    message_hash = hashlib.md5(text.encode()).hexdigest()
    seen_hashes.add(message_hash)

def extract_product_id_enhanced(url):
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

def is_spam_message_fast(text):
    if not text or not text.strip(): return True
    text_lower = text.lower()
    spam_patterns = [r'f+a+s+t+', r'coupon.*none', r'^\s*[0-9,]+\s*$']
    for pattern in spam_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    urls = re.findall(r'https?://[^\s]+', text)
    if not urls: return True
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

def get_waha_health_fast():
    try:
        response = requests.get(f"{WAHA_URL}/api/sessions", timeout=5)
        return response.status_code == 200
    except:
        return False

def send_whatsapp_message_optimized(text):
    global last_send_time, daily_message_count, hourly_message_count
    if not text or not text.strip(): return False
    if not check_daily_limits_fast(): return False
    
    current_time = time.time()
    time_since_last_send = current_time - last_send_time
    safe_delay = MIN_TIME_BETWEEN_SENDS + random.uniform(0.5, 2)
    
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

def process_message_balanced(text):
    if not text: return None, None
    if is_spam_message_fast(text):
        stats.increment_spam()
        return None, None
    
    text = re.sub(r'From\s*\*\s*[^:]*:|### From.*', '', text)
    urls = re.findall(r'https?://[^\s]+', text)
    if not urls: return None, None
    
    safe_urls = [url for url in urls if is_safe_url(url)]
    if not safe_urls: return None, None
    
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

def is_safe_url(url):
    safe_domains = ['amazon.in', 'amzn.to', 'flipkart.com', 'fkrt.co', 'myntra.com', 'ajio.com']
    try: 
        domain = urlparse(url).netloc.lower()
        return any(safe_domain in domain for safe_domain in safe_domains)
    except: 
        return False

def get_fast_hashtags(product_text, platform, message_count):
    platform_tags = {
        'amazon': ["#AmazonDeals", "#AmazonIndia", "#AmazonSale"],
        'flipkart': ["#FlipkartDeals", "#FlipkartSale"],
        'myntra': ["#MyntraDeals", "#FashionSale"],
        'ajio': ["#AjioOffers", "#AjioLoot"],
    }
    
    platform_lower = platform.lower()
    if "amazon" in platform_lower:
        tags = platform_tags['amazon']
    elif "flipkart" in platform_lower:
        tags = platform_tags['flipkart']
    elif "myntra" in platform_lower:
        tags = platform_tags['myntra']
    elif "ajio" in platform_lower:
        tags = platform_tags['ajio']
    else:
        tags = ["#Deals", "#Offers"]
    
    platform_idx = message_count % len(tags)
    selected_hashtags = [tags[platform_idx]]
    
    time_tags = ["#MorningDeals", "#AfternoonDeals", "#EveningDeals", "#LateNightDeals"]
    current_hour = datetime.now().hour
    time_idx = current_hour % len(time_tags)
    selected_hashtags.append(time_tags[time_idx])
    
    return ' '.join(selected_hashtags[:2])

def process_channel_balanced(channel_name, channel_id):
    deals_found = 0
    try:
        messages = get_channel_messages_fast(channel_id)
        if not messages: return 0
        
        last_timestamp = last_processed_timestamps.get(channel_id, 0)
        new_last_timestamp = last_timestamp
        
        for message in reversed(messages):
            if message.get('fromMe') or not message.get('body'): continue
            message_timestamp = message.get('timestamp', 0)
            if message_timestamp <= last_timestamp: continue
            if message_timestamp > new_last_timestamp:
                new_last_timestamp = message_timestamp
            if time.time() - message_timestamp > 600:
                stats.increment_missed()
                continue
            
            processed_message, original_url = process_message_balanced(message.get('body', ''))
            if not processed_message: continue
            
            platform = "🛍️ Amazon" if 'amazon' in processed_message.lower() else "📦 Other"
            if is_duplicate_message_enhanced(processed_message, original_url, platform):
                continue
            
            if send_whatsapp_message_optimized(processed_message):
                deals_found += 1
                stats.increment_forwarded()
                add_to_dedup_enhanced(processed_message, original_url, platform)
                print(f"    🚀 {channel_name}: DEAL SENT!")
            
        last_processed_timestamps[channel_id] = new_last_timestamp
    except Exception as e:
        print(f"    ❌ {channel_name} error: {str(e)}")
        stats.increment_errors()
    return deals_found

def deal_forwarder_main():
    channel_names = ["TechFactsDeals", "Loots4u", "Shopping Loot Offers", "Loot Deals Official", "Loot Bazaar"]
    
    print("🚀 WhatsApp Forwarder Starting...")
    print("=" * 60)
    print(f"📡 WAHA URL: {WAHA_URL}")
    print(f"🎯 Destination: {DESTINATION_CHANNEL}")
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

# Flask endpoints
@app.route('/')
def home():
    waha_status = "✅ Connected" if get_waha_health_fast() else "❌ Disconnected"
    daily_remaining = MAX_DAILY_MESSAGES - daily_message_count
    hourly_remaining = MAX_HOURLY_MESSAGES - hourly_message_count
    uptime = stats.get_duration()
    
    return f"""
    <html>
    <head><title>WhatsApp Forwarder</title></head>
    <body>
        <h1>🚀 WhatsApp Forwarder</h1>
        <p><strong>Status:</strong> {waha_status}</p>
        <p><strong>Forwarded Today:</strong> {daily_message_count}/{MAX_DAILY_MESSAGES}</p>
        <p><strong>This Hour:</strong> {hourly_message_count}/{MAX_HOURLY_MESSAGES}</p>
        <p><strong>Total Forwarded:</strong> {stats.total_forwarded}</p>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return {"status": "running"}

@app.route('/ping')
def ping():
    return {"status": "pong"}

@app.route('/stats')
def stats_page():
    return {
        "total_forwarded": stats.total_forwarded,
        "duplicates_blocked": stats.duplicates_blocked,
        "spam_filtered": stats.spam_filtered
    }

# Start services
print("🎯 Starting WhatsApp Forwarder...")
forwarder_thread = threading.Thread(target=deal_forwarder_main, daemon=True)
forwarder_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)