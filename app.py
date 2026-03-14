"""
Vilasio COT Backend v3.5
CFTC Socrata + Yahoo Finance daily prices.
Expanded markets with corrected CFTC names.
"""
import os, json, datetime, urllib.request, urllib.parse
from flask import Flask, jsonify, request

app = Flask(__name__)

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

LEGACY_API = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
PAGE_SIZE = 50000

MARKETS = {
    # EQUITY
    "ES":  {"name":"E-Mini S&P 500",     "exchange":"CME","cat":"Equity","cftc_name":"S&P 500 Consolidated","yf":"ES=F"},
    "NQ":  {"name":"E-Mini Nasdaq 100",  "exchange":"CME","cat":"Equity","cftc_name":"NASDAQ-100 Consolidated","yf":"NQ=F"},
    "YM":  {"name":"E-Mini Dow Jones",   "exchange":"CBOT","cat":"Equity","cftc_name":"DJIA Consolidated","yf":"YM=F"},
    "RTY": {"name":"E-Mini Russell 2000","exchange":"CME","cat":"Equity","cftc_name":"RUSSELL E-MINI","yf":"RTY=F"},
    "VIX": {"name":"VIX Futures",        "exchange":"CBOE","cat":"Equity","cftc_name":"VIX FUTURES","yf":"^VIX"},
    # ENERGY
    "CL":  {"name":"Crude Oil WTI",  "exchange":"NYMEX","cat":"Energy","cftc_name":"WTI-PHYSICAL","yf":"CL=F"},
    "NG":  {"name":"Natural Gas",    "exchange":"NYMEX","cat":"Energy","cftc_name":"NAT GAS NYME","yf":"NG=F"},
    # METALS
    "GC":  {"name":"Gold",     "exchange":"COMEX","cat":"Metals","cftc_name":"GOLD","yf":"GC=F"},
    "SI":  {"name":"Silver",   "exchange":"COMEX","cat":"Metals","cftc_name":"SILVER","yf":"SI=F"},
    "HG":  {"name":"Copper",   "exchange":"COMEX","cat":"Metals","cftc_name":"COPPER","yf":"HG=F"},
    "PL":  {"name":"Platinum", "exchange":"NYMEX","cat":"Metals","cftc_name":"PLATINUM","yf":"PL=F"},
    "PA":  {"name":"Palladium","exchange":"NYMEX","cat":"Metals","cftc_name":"PALLADIUM","yf":"PA=F"},
    # FX
    "6E":  {"name":"Euro FX",          "exchange":"CME","cat":"FX","cftc_name":"EURO FX","yf":"EURUSD=X"},
    "6B":  {"name":"British Pound",    "exchange":"CME","cat":"FX","cftc_name":"BRITISH POUND","yf":"GBPUSD=X"},
    "6J":  {"name":"Japanese Yen",     "exchange":"CME","cat":"FX","cftc_name":"JAPANESE YEN","yf":"JPY=X"},
    "6A":  {"name":"Australian Dollar","exchange":"CME","cat":"FX","cftc_name":"AUSTRALIAN DOLLAR","yf":"AUDUSD=X"},
    "6C":  {"name":"Canadian Dollar",  "exchange":"CME","cat":"FX","cftc_name":"CANADIAN DOLLAR","yf":"CADUSD=X"},
    "6S":  {"name":"Swiss Franc",      "exchange":"CME","cat":"FX","cftc_name":"SWISS FRANC","yf":"CHFUSD=X"},
    "6N":  {"name":"New Zealand Dollar","exchange":"CME","cat":"FX","cftc_name":"NZ DOLLAR","yf":"NZDUSD=X"},
    "DX":  {"name":"US Dollar Index",  "exchange":"ICE","cat":"FX","cftc_name":"USD INDEX","yf":"DX-Y.NYB"},
    # RATES
    "ZB":  {"name":"30-Year T-Bond",  "exchange":"CBOT","cat":"Rates","cftc_name":"UST BOND","yf":"ZB=F"},
    "ZN":  {"name":"10-Year T-Note",  "exchange":"CBOT","cat":"Rates","cftc_name":"UST 10Y NOTE","yf":"ZN=F"},
    "ZF":  {"name":"5-Year T-Note",   "exchange":"CBOT","cat":"Rates","cftc_name":"UST 5Y NOTE","yf":"ZF=F"},
    "ZT":  {"name":"2-Year T-Note",   "exchange":"CBOT","cat":"Rates","cftc_name":"UST 2Y NOTE","yf":"ZT=F"},
    "ZQ":  {"name":"30-Day Fed Funds","exchange":"CBOT","cat":"Rates","cftc_name":"FED FUNDS","yf":"ZQ=F"},
    # GRAINS
    "ZC":  {"name":"Corn",        "exchange":"CBOT","cat":"Grains","cftc_name":"CORN","yf":"ZC=F"},
    "ZW":  {"name":"Wheat SRW",   "exchange":"CBOT","cat":"Grains","cftc_name":"WHEAT-SRW","yf":"ZW=F"},
    "KE":  {"name":"Wheat HRW",   "exchange":"KCBT","cat":"Grains","cftc_name":"WHEAT-HRW","yf":"KE=F"},
    "ZS":  {"name":"Soybeans",    "exchange":"CBOT","cat":"Grains","cftc_name":"SOYBEANS","yf":"ZS=F"},
    "ZL":  {"name":"Soybean Oil", "exchange":"CBOT","cat":"Grains","cftc_name":"SOYBEAN OIL","yf":"ZL=F"},
    "ZM":  {"name":"Soybean Meal","exchange":"CBOT","cat":"Grains","cftc_name":"SOYBEAN MEAL","yf":"ZM=F"},
    # SOFTS
    "CC":  {"name":"Cocoa",       "exchange":"ICE","cat":"Softs","cftc_name":"COCOA","yf":"CC=F"},
    "KC":  {"name":"Coffee",      "exchange":"ICE","cat":"Softs","cftc_name":"COFFEE C","yf":"KC=F"},
    "CT":  {"name":"Cotton",      "exchange":"ICE","cat":"Softs","cftc_name":"COTTON NO. 2","yf":"CT=F"},
    "SB":  {"name":"Sugar",       "exchange":"ICE","cat":"Softs","cftc_name":"SUGAR NO. 11","yf":"SB=F"},
    "OJ":  {"name":"Orange Juice","exchange":"ICE","cat":"Softs","cftc_name":"FRZN CONCENTRATED ORANGE JUICE","yf":"OJ=F"},
    # LIVESTOCK
    "LE":  {"name":"Live Cattle",  "exchange":"CME","cat":"Livestock","cftc_name":"LIVE CATTLE","yf":"LE=F"},
    "GF":  {"name":"Feeder Cattle","exchange":"CME","cat":"Livestock","cftc_name":"FEEDER CATTLE","yf":"GF=F"},
    "HE":  {"name":"Lean Hogs",   "exchange":"CME","cat":"Livestock","cftc_name":"LEAN HOGS","yf":"HE=F"},
}

HEATMAP_MARKETS = ["ES","NQ","GC","CL","SI","ZB","6E","6B","6J","NG","ZC","ZW"]
FLOW_CATS = ["Equity","Energy","Metals","FX","Rates","Grains","Softs","Livestock"]

def safe_int(val):
    try: return int(float(str(val).strip()))
    except: return 0

_cache = {}
_cache_time = {}
CACHE_TTL = 3600 * 6

def fetch_json(url, params=None):
    if params: url = url + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': 'Vilasio/3.5', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))

def fetch_market_data(symbol):
    cfg = MARKETS[symbol]
    cn = cfg['cftc_name']
    start_date = (datetime.date.today() - datetime.timedelta(days=365*3)).isoformat()
    # Try exact match first, then LIKE match for partial names
    params = {
        '$where': "contract_market_name='" + cn + "' AND report_date_as_yyyy_mm_dd >= '" + start_date + "'",
        '$order': 'report_date_as_yyyy_mm_dd ASC',
        '$limit': str(PAGE_SIZE)
    }
    try:
        rows = fetch_json(LEGACY_API, params)
        # If no exact match, try LIKE match
        if not rows:
            params['$where'] = "starts_with(contract_market_name, '" + cn + "') AND report_date_as_yyyy_mm_dd >= '" + start_date + "'"
            rows = fetch_json(LEGACY_API, params)
    except Exception as e:
        print("[COT] " + symbol + " fetch error: " + str(e))
        return []
    if not rows:
        print("[COT] " + symbol + " (" + cn + "): no data found")
        return []
    entries, seen = [], set()
    for row in rows:
        ds = row.get('report_date_as_yyyy_mm_dd', '')
        if not ds: continue
        di = ds[:10]
        if di in seen: continue
        seen.add(di)
        bl = safe_int(row.get('noncomm_positions_long_all', 0))
        bs = safe_int(row.get('noncomm_positions_short_all', 0))
        dl = safe_int(row.get('comm_positions_long_all', 0))
        ds2 = safe_int(row.get('comm_positions_short_all', 0))
        oi = safe_int(row.get('open_interest_all', 0))
        if oi == 0: continue
        entries.append({'date': di, 'bpLong': bl, 'bpShort': bs, 'bpNet': bl-bs, 'dlLong': dl, 'dlShort': ds2, 'dlNet': dl-ds2, 'oi': oi})
    entries.sort(key=lambda x: x['date'])
    return entries

def load_all_data():
    now = datetime.datetime.now()
    ck = 'cot_v35'
    if ck in _cache and (now - _cache_time[ck]).total_seconds() < CACHE_TTL:
        return _cache[ck]
    print("[COT] Loading all " + str(len(MARKETS)) + " markets...")
    data = {}
    for sym in sorted(MARKETS.keys()):
        try:
            e = fetch_market_data(sym)
            if e:
                data[sym] = e
                print("[COT] " + sym + ": " + str(len(e)) + " rows")
            else:
                print("[COT] " + sym + ": no data")
        except Exception as ex:
            print("[COT] " + sym + " error: " + str(ex))
    _cache[ck] = data
    _cache_time[ck] = now
    print("[COT] Done - " + str(len(data)) + "/" + str(len(MARKETS)) + " markets loaded")
    return data

def load_price_map(symbol):
    ck = 'price_' + symbol
    now = datetime.datetime.now()
    if ck in _cache and (now - _cache_time[ck]).total_seconds() < CACHE_TTL:
        return _cache[ck]
    import yfinance as yf
    yf_sym = MARKETS[symbol]["yf"]
    start = (datetime.date.today() - datetime.timedelta(days=365*3+30)).isoformat()
    end = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    try:
        df = yf.Ticker(yf_sym).history(start=start, end=end, interval="1d")
        if df.empty:
            _cache[ck] = {}; _cache_time[ck] = now; return {}
        pm = {}
        for idx, row in df.iterrows():
            pm[idx.strftime('%Y-%m-%d')] = round(float(row['Close']), 4)
        _cache[ck] = pm; _cache_time[ck] = now; return pm
    except Exception as e:
        print("[PRICE] Error " + yf_sym + ": " + str(e))
        _cache[ck] = {}; _cache_time[ck] = now; return {}

def align_prices(symbol, cot_dates):
    pm = load_price_map(symbol)
    if not pm: return [None]*len(cot_dates)
    result = []
    for cd in cot_dates:
        dt = datetime.date.fromisoformat(cd)
        found = None
        for off in range(7):
            check = (dt - datetime.timedelta(days=off)).isoformat()
            if check in pm: found = pm[check]; break
        result.append(found)
    return result

def get_daily_prices(symbol, start_date, end_date):
    pm = load_price_map(symbol)
    if not pm: return [], []
    dates = sorted([d for d in pm.keys() if start_date <= d <= end_date])
    return dates, [pm[d] for d in dates]

@app.route('/')
def index():
    return jsonify({'service': 'Vilasio COT API', 'version': '3.5', 'markets': len(MARKETS)})

@app.route('/health')
def health():
    data = load_all_data()
    return jsonify({
        'status': 'ok', 'version': '3.5',
        'markets': sorted(data.keys()) if data else [],
        'totalMarkets': len(MARKETS),
        'loadedMarkets': len(data) if data else 0,
        'totalRows': sum(len(v) for v in data.values()) if data else 0
    })

@app.route('/api/cot')
def api_cot():
    market = request.args.get('market', '').upper()
    weeks = max(4, min(int(request.args.get('weeks', 52)), 260))
    if market not in MARKETS:
        return jsonify({'error': 'Unknown: ' + market, 'available': sorted(MARKETS.keys())}), 400
    data = load_all_data()
    if market not in data or not data[market]:
        return jsonify({'error': 'No data for ' + market}), 404
    entries = data[market]
    entries = entries[-(weeks+1):] if len(entries) > weeks+1 else entries
    cfg = MARKETS[market]
    dates = [e['date'] for e in entries]
    try: prices = align_prices(market, dates)
    except: prices = [None]*len(entries)
    dd, dp = [], []
    try:
        end_dt = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        dd, dp = get_daily_prices(market, dates[0], end_dt)
    except: pass
    return jsonify({
        'market': market, 'name': cfg['name'], 'exchange': cfg['exchange'], 'cat': cfg['cat'],
        'reportDate': entries[-1]['date'], 'labels': dates,
        'bpLong': [e['bpLong'] for e in entries], 'bpShort': [e['bpShort'] for e in entries],
        'bpNet': [e['bpNet'] for e in entries], 'dlLong': [e['dlLong'] for e in entries],
        'dlShort': [e['dlShort'] for e in entries], 'dlNet': [e['dlNet'] for e in entries],
        'oi': [e['oi'] for e in entries], 'price': prices,
        'dailyDates': dd, 'dailyPrice': dp,
    })

@app.route('/api/cot/summary')
def api_cot_summary():
    data = load_all_data()
    results = []
    for sym in sorted(MARKETS.keys()):
        if sym not in data or len(data[sym]) < 2: continue
        last, prev = data[sym][-1], data[sym][-2]
        cfg = MARKETS[sym]
        results.append({
            'market': sym, 'name': cfg['name'], 'cat': cfg['cat'],
            'bpNet': last['bpNet'], 'bpNetChg': last['bpNet'] - prev['bpNet'],
            'dlNet': last['dlNet'], 'dlNetChg': last['dlNet'] - prev['dlNet'],
            'oi': last['oi'], 'oiChg': last['oi'] - prev['oi'],
            'reportDate': last['date']
        })
    return jsonify({'markets': results, 'categories': FLOW_CATS})

@app.route('/api/cot/flow')
def api_flow():
    data = load_all_data()
    weeks = max(1, min(int(request.args.get('weeks', 1)), 52))
    cats = {}
    for cat in FLOW_CATS:
        cats[cat] = {'bpNetChg': 0, 'dlNetChg': 0, 'oiChg': 0, 'markets': []}
    for sym in sorted(MARKETS.keys()):
        if sym not in data or len(data[sym]) < weeks + 1: continue
        last = data[sym][-1]
        prev = data[sym][-(weeks + 1)]
        cat = MARKETS[sym]['cat']
        if cat not in cats: continue
        bpChg = last['bpNet'] - prev['bpNet']
        dlChg = last['dlNet'] - prev['dlNet']
        oiChg = last['oi'] - prev['oi']
        cats[cat]['bpNetChg'] += bpChg
        cats[cat]['dlNetChg'] += dlChg
        cats[cat]['oiChg'] += oiChg
        cats[cat]['markets'].append({
            'market': sym, 'name': MARKETS[sym]['name'],
            'bpNetChg': bpChg, 'dlNetChg': dlChg, 'oiChg': oiChg
        })
    eq = cats.get('Equity', {}).get('bpNetChg', 0)
    safe = cats.get('Metals', {}).get('bpNetChg', 0) + cats.get('Rates', {}).get('bpNetChg', 0)
    if eq > 10000 and safe < -5000:
        regime = 'RISK-ON'
    elif eq < -10000 and safe > 5000:
        regime = 'RISK-OFF'
    else:
        regime = 'ROTATION'
    # Compute correlation-based flow matrix between categories
    # Uses inverse correlation of WoW changes over last 26 weeks
    flow_links = []
    outflows = [c for c in FLOW_CATS if cats.get(c, {}).get('bpNetChg', 0) < 0]
    inflows = [c for c in FLOW_CATS if cats.get(c, {}).get('bpNetChg', 0) > 0]
    if outflows and inflows:
        # Build weekly change series per category over 26 weeks
        cat_series = {}
        for cat in FLOW_CATS:
            series = []
            for w in range(min(26, min(len(v) for v in data.values() if v) - 1)):
                total = 0
                for sym in MARKETS:
                    if MARKETS[sym]['cat'] != cat or sym not in data: continue
                    entries = data[sym]
                    if len(entries) < w + 2: continue
                    total += entries[-(w+1)]['bpNet'] - entries[-(w+2)]['bpNet']
                series.append(total)
            cat_series[cat] = series
        # For each outflow-inflow pair, compute inverse correlation strength
        for src in outflows:
            src_val = abs(cats[src]['bpNetChg'])
            for dst in inflows:
                dst_val = cats[dst]['bpNetChg']
                s1, s2 = cat_series.get(src, []), cat_series.get(dst, [])
                n = min(len(s1), len(s2))
                if n < 4:
                    # Not enough data, use proportional fallback
                    strength = dst_val / sum(cats[c]['bpNetChg'] for c in inflows)
                else:
                    # Inverse correlation: when src goes down, does dst go up?
                    m1, m2 = sum(s1[:n])/n, sum(s2[:n])/n
                    num = sum((s1[i]-m1)*(s2[i]-m2) for i in range(n))
                    d1 = max(1, sum((s1[i]-m1)**2 for i in range(n))**0.5)
                    d2 = max(1, sum((s2[i]-m2)**2 for i in range(n))**0.5)
                    corr = num / (d1 * d2)
                    # Negative correlation = money flowing from src to dst
                    # Scale: -1 (strong flow) to +1 (no flow)
                    weight = max(0, -corr)
                    total_weight = 0.001
                    for d2c in inflows:
                        s2b = cat_series.get(d2c, [])
                        nb = min(len(s1), len(s2b))
                        if nb < 4: continue
                        m2b = sum(s2b[:nb])/nb
                        numb = sum((s1[i]-m1)*(s2b[i]-m2b) for i in range(nb))
                        d1b = max(1, sum((s1[i]-m1)**2 for i in range(nb))**0.5)
                        d2b2 = max(1, sum((s2b[i]-m2b)**2 for i in range(nb))**0.5)
                        corrb = numb / (d1b * d2b2)
                        total_weight += max(0, -corrb)
                    strength = weight / total_weight if total_weight > 0 else 0
                flow = round(src_val * strength)
                if flow > 0:
                    flow_links.append({'from': src, 'to': dst, 'value': flow})
    return jsonify({'categories': cats, 'regime': regime, 'catOrder': FLOW_CATS, 'flowLinks': flow_links})

@app.route('/api/cot/refresh')
def api_refresh():
    # Clear only COT-related cache entries (preserve FRED cache)
    cot_keys = [k for k in _cache if not k.startswith('fred_')]
    for k in cot_keys:
        _cache.pop(k, None)
        _cache_time.pop(k, None)
    print('[COT] Cache cleared (' + str(len(cot_keys)) + ' keys), refetching...')
    data = load_all_data()
    return jsonify({'status': 'refreshed', 'markets': sorted(data.keys()), 'count': len(data)})

# ─── SENTIMENT ENDPOINTS ──────────────────────────────────────────────────────

def fetch_polymarket_sentiment():
    """Fetch macro markets from Polymarket using known event slugs. Cache 1h."""
    ck = 'polymarket_sentiment'
    now = datetime.datetime.now()
    if ck in _cache and (now - _cache_time[ck]).total_seconds() < 3600:
        return _cache[ck]

    today = datetime.date.today().isoformat()

    # Each entry: (slug, bullish_keywords, bearish_keywords)
    # bullish_keywords: if question contains these, yes_prob is BULLISH (score goes up)
    # bearish_keywords: if question contains these, yes_prob is BEARISH (score goes down)
    # If neither, skip (ambiguous multi-outcome sub-market)
    MACRO_EVENTS = [
        # Fed cuts — more cuts = bullish
        ('how-many-fed-rate-cuts-in-2026',    ['2 ', '3 ', '4 ', '5 ', '6 ', '7 ', '8 ', '9 ', '10', '11', '12'], ['0 ', 'no ']),
        ('how-many-fed-rate-cuts-in-2025',    ['2 ', '3 ', '4 ', '5 ', '6 '], ['0 ', 'no ']),
        ('fed-rate-cut-by-629',               ['yes', 'cut'], ['no ', 'pause']),
        ('fed-decision-march-2026',           ['cut', '25bps', '50bps'], ['pause', 'hike', 'increase']),
        ('fed-decision-in-march',             ['cut', '25bps', '50bps'], ['pause', 'hike', 'no change']),
        ('fed-rate-cut-march-2026',           ['yes', 'cut'], ['no', 'pause']),
        # Recession — any "recession" or "yes" in question = bearish outcome
        ('us-recession-in-2026',              [], ['yes', 'recession', 'will']),
        ('will-the-us-enter-a-recession-in-2025', [], ['yes']),
        ('will-there-be-a-us-recession-in-2026',  [], ['yes']),
        ('us-recession-2025',                 [], ['yes']),
        ('us-recession-2026',                 [], ['yes']),
        ('recession-in-2026',                 [], ['yes']),
        ('will-there-be-a-us-recession',      [], ['yes']),
        ('us-recession-by-end-of-2026',       [], ['yes', 'recession', 'end of 2026']),
        ('us-enter-recession-2026',           [], ['yes']),
        # S&P 500
        ('sp-500-end-of-year-2025',           ['above', '6000', '6500', '7000'], ['below', '4000', '4500', '5000']),
        ('sp-500-in-2026',                    ['above', '6000', '6500', '7000'], ['below', '4000', '4500', '5000']),
        ('will-the-sp-500-go-up-in-q1-2026',  ['yes', 'up'], ['no', 'down']),
        ('sp500-2026',                        ['above', '6000', '6500'], ['below', '4000', '4500']),
        ('will-the-sp-500-hit-6000',          ['yes'], ['no']),
        ('will-the-sp-500-hit-7000',          ['yes'], ['no']),
        ('sp-500-year-end-2025',              ['above', '6000', '6500'], ['below', '4000', '4500']),
        ('will-sp-500-hit-6000-in-2026',      ['yes'], ['no']),
        ('sp-500-2026',                       ['above', '6000', '6500'], ['below', '4000', '4500']),
        # CPI
        ('us-cpi-inflation-in-2026',          [], ['above', 'higher', 'exceed']),
        ('us-cpi-2026',                       [], ['above', 'higher']),
        ('will-us-cpi-exceed',                [], ['yes', 'exceed', 'above']),
    ]

    events_base = 'https://gamma-api.polymarket.com/events'
    display_markets = []   # for the UI table — one row per event
    score_inputs = []      # (score_0_100, volume_weight) pairs

    for slug, bullish_kw, bearish_kw in MACRO_EVENTS:
        try:
            params = urllib.parse.urlencode({'slug': slug})
            req = urllib.request.Request(
                events_base + '?' + params,
                headers={'User-Agent': 'Vilasio/3.7', 'Accept': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            events = data if isinstance(data, list) else [data]
            for ev in events:
                if not ev or not isinstance(ev, dict): continue
                markets = ev.get('markets', [])
                if not markets: continue

                event_title = ev.get('title', slug)
                total_volume = sum(float(m.get('volumeNum', 0) or 0) for m in markets)
                if total_volume < 10000: continue

                # Collect active markets with valid prices
                active = []
                for m in markets:
                    if m.get('closed') or m.get('archived'): continue
                    end_date = m.get('endDate', '') or ''
                    if end_date and end_date[:10] < today: continue
                    raw_prices = m.get('outcomePrices', '[]')
                    try:
                        prices = json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices
                        yes_prob = float(prices[0]) if prices else None
                    except: yes_prob = None
                    if yes_prob is None: continue
                    active.append({
                        'question': m.get('question', ''),
                        'yesProb': yes_prob,
                        'volume': float(m.get('volumeNum', 0) or 0)
                    })

                if not active: continue

                # Compute event-level bullish score
                # For binary events (1 market): direct yes/no classification
                if len(active) == 1:
                    m = active[0]
                    q = (m['question'] + ' ' + event_title).lower()
                    is_bullish = any(kw.lower() in q for kw in bullish_kw)
                    is_bearish = any(kw.lower() in q for kw in bearish_kw)
                    # For recession-type slugs: event itself is the bearish signal
                    if not is_bullish and not is_bearish:
                        if 'recession' in (slug + ' ' + event_title).lower():
                            is_bearish = True
                        elif 'rate cut' in (slug + ' ' + event_title).lower() or 'fed cut' in (slug + ' ' + event_title).lower():
                            is_bullish = True
                    if is_bullish:
                        event_score = m['yesProb'] * 100
                    elif is_bearish:
                        event_score = (1 - m['yesProb']) * 100
                    else:
                        event_score = 50
                    display_prob = round(m['yesProb'] * 100, 1)
                    display_q = m['question'] if m['question'] else event_title
                else:
                    # Multi-outcome: sum yesProb of bullish outcomes, subtract bearish
                    bullish_prob = 0.0
                    bearish_prob = 0.0
                    for m in active:
                        q = m['question'].lower()
                        if any(kw.lower() in q for kw in bullish_kw):
                            bullish_prob += m['yesProb']
                        elif any(kw.lower() in q for kw in bearish_kw):
                            bearish_prob += m['yesProb']
                    # Score: bullish_prob mapped to 0-100
                    # If no classification possible, skip
                    if bullish_prob == 0 and bearish_prob == 0:
                        continue
                    event_score = min(100, bullish_prob * 100)
                    if bearish_prob > 0 and bullish_prob == 0:
                        event_score = max(0, (1 - bearish_prob) * 100)
                    # Display: show the most meaningful single probability
                    best = max(active, key=lambda x: x['volume'])
                    display_prob = round(best['yesProb'] * 100, 1)
                    display_q = event_title

                score_inputs.append((event_score, total_volume))
                display_markets.append({
                    'question': display_q,
                    'yesProb': display_prob,
                    'volume': total_volume,
                    'endDate': '',
                    'score': round(event_score, 1)
                })

        except Exception as e:
            print('[POLYMARKET] slug "' + slug + '" error: ' + str(e))

    print('[POLYMARKET] Found ' + str(len(display_markets)) + ' events: ' + str([m['question'][:40] for m in display_markets]))
    if score_inputs:
        total_vol = sum(v for _, v in score_inputs)
        avg_score = round(sum(s * v for s, v in score_inputs) / max(total_vol, 1), 1) if total_vol else None
    else:
        avg_score = None

    display_markets.sort(key=lambda x: -x['volume'])
    result = {
        'markets': display_markets[:10],
        'avgProb': avg_score,
        'count': len(display_markets)
    }
    _cache[ck] = result; _cache_time[ck] = now
    return result

# ── CBOE per-symbol PCR CSVs (SPX, QQQ proxy for NQ) ─────────────────────────
PCR_SYMBOL_URLS = {
    'SPX': 'https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/spxpc.csv',
    'EQUITY': 'https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypc.csv',
}

def _parse_cboe_csv(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Vilasio/3.7'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode('latin-1')
    rows = []
    header_found = False
    for line in raw.splitlines():
        line = line.strip()
        if not line: continue
        if not header_found:
            if 'DATE' in line.upper() and ('P/C' in line.upper() or 'PUT' in line.upper()):
                header_found = True
            continue
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 4: continue
        date_str = parts[0]
        pc_str = parts[4] if len(parts) >= 5 else parts[3]
        try:
            for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
                try: datetime.datetime.strptime(date_str, fmt); break
                except: pass
            else: continue
            val = float(pc_str)
            if val <= 0 or val > 10: continue
            rows.append({'date': date_str, 'pcr': val})
        except: continue
    return rows[-30:]

def fetch_pcr_symbol(symbol):
    ck = 'pcr_' + symbol
    now = datetime.datetime.now()
    if ck in _cache and (now - _cache_time[ck]).total_seconds() < CACHE_TTL:
        return _cache[ck]
    url = PCR_SYMBOL_URLS.get(symbol)
    if not url: return None
    rows = _parse_cboe_csv(url)
    if not rows: return None
    latest = rows[-1]['pcr']
    avg10 = round(sum(r['pcr'] for r in rows[-10:]) / min(10, len(rows)), 3)
    result = {'latest': latest, 'avg10': avg10, 'history': rows}
    _cache[ck] = result; _cache_time[ck] = now
    return result

def pcr_to_score(avg10, lo=0.4, hi=1.4):
    """Map PCR avg10 to 0-100 bullish score. Lower PCR = more bullish."""
    if avg10 is None: return None
    return round(max(0, min(100, (hi - avg10) / (hi - lo) * 100)), 1)

def fetch_pcr():
    return fetch_pcr_symbol('EQUITY')

# ── BLS API — macro release trend ────────────────────────────────────────────
BLS_SERIES = {
    'CPI':     'CUUR0000SA0',   # CPI-U All items NSA
    'NFP':     'CES0000000001', # Total nonfarm payroll (thousands)
    'ICSA':    'ICSA',          # Initial claims SA (weekly, via BLS)
    'CCSA':    'CCSA',          # Continued claims SA
    'UNRATE':  'LNS14000000',   # Unemployment rate
}

def fetch_bls_series(series_id, n=13):
    """Fetch last n observations from BLS v1 API (no key needed)."""
    ck = 'bls_' + series_id
    now = datetime.datetime.now()
    if ck in _cache and (now - _cache_time[ck]).total_seconds() < CACHE_TTL:
        return _cache[ck]
    url = 'https://api.bls.gov/publicAPI/v1/timeseries/data/' + series_id
    req = urllib.request.Request(url, headers={'User-Agent': 'Vilasio/3.7', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    series_data = data.get('Results', {}).get('series', [{}])[0].get('data', [])
    # BLS returns newest first — reverse for chronological order
    series_data = list(reversed(series_data[:n]))
    result = [{'period': d['year'] + '-' + d['period'], 'value': float(d['value'].replace(',',''))} for d in series_data if d.get('value') not in ('', '-')]
    _cache[ck] = result; _cache_time[ck] = now
    return result

def macro_trend_score(observations, direction='neutral'):
    """
    Compute 0-100 bullish score from recent trend.
    direction: 'up_bullish' (NFP, good when rising),
               'down_bullish' (CPI, ICSA, good when falling),
               'neutral'
    Uses: is latest above/below 6m average, and momentum of last 3 readings.
    """
    if not observations or len(observations) < 3: return None
    vals = [o['value'] for o in observations]
    latest = vals[-1]
    avg6 = sum(vals[-7:-1]) / min(6, len(vals)-1) if len(vals) > 1 else latest
    # Momentum: slope of last 3
    last3 = vals[-3:]
    slope = (last3[-1] - last3[0]) / max(abs(last3[0]), 1) * 100  # % change

    if direction == 'up_bullish':
        # Higher = bullish: latest vs avg, slope up = good
        pos_vs_avg = 1 if latest > avg6 else 0
        pos_slope = 1 if slope > 0 else 0
        score = (pos_vs_avg * 40 + pos_slope * 30 + 30)  # base 30, up to 100
        # Scale by magnitude
        pct = (latest - avg6) / max(abs(avg6), 1) * 100
        score = min(100, max(0, 50 + pct * 2 + (10 if slope > 0 else -10)))
    elif direction == 'down_bullish':
        # Lower = bullish
        pct = (avg6 - latest) / max(abs(avg6), 1) * 100  # positive when falling
        score = min(100, max(0, 50 + pct * 2 + (-10 if slope > 0 else 10)))
    else:
        score = 50
    return round(score, 1)

# ── Polymarket asset slugs ────────────────────────────────────────────────────
ASSET_POLY_SLUGS = {
    'CL': [('will-wti-crude-oil-hit-80-in-2026', ['yes'], ['no']),
           ('will-wti-crude-oil-hit-100-in-2026', ['yes'], ['no']),
           ('oil-price-2026', ['above', '80', '100'], ['below', '50', '60'])],
    'GC': [('will-gold-hit-3000-in-2025', ['yes'], ['no']),
           ('will-gold-hit-3500-in-2025', ['yes'], ['no']),
           ('will-gold-hit-3000', ['yes'], ['no']),
           ('gold-price-2026', ['above', '3000', '3500'], ['below', '2000', '2500'])],
    '6E': [('eurusd-2026', ['above', 'higher', '1.10', '1.15'], ['below', 'lower', '0.95', '1.00']),
           ('will-eurusd-hit-110', ['yes'], ['no'])],
    '6B': [('gbpusd-2026', ['above', 'higher'], ['below', 'lower']),
           ('will-gbpusd-hit-130', ['yes'], ['no'])],
    'DX': [('will-dxy-hit-110', ['yes'], ['no']),
           ('usd-index-2026', ['above', 'stronger'], ['below', 'weaker'])],
}

MACRO_POLY_SLUGS = [
    ('how-many-fed-rate-cuts-in-2026',    ['2 ', '3 ', '4 ', '5 ', '6 ', '7 ', '8 ', '9 ', '10', '11', '12'], ['0 ', 'no ']),
    ('how-many-fed-rate-cuts-in-2025',    ['2 ', '3 ', '4 ', '5 ', '6 '], ['0 ', 'no ']),
    ('fed-rate-cut-by-629',               ['yes', 'cut'], ['no ', 'pause']),
    ('us-recession-by-end-of-2026',       [], ['yes', 'recession']),
    ('us-recession-in-2026',              [], ['yes', 'recession']),
    ('will-the-us-enter-a-recession-in-2025', [], ['yes']),
]

def _poly_fetch_slug(slug, bullish_kw, bearish_kw, today):
    """Fetch one Polymarket event slug and return (score, volume, title, display_prob) or None."""
    try:
        params = urllib.parse.urlencode({'slug': slug})
        req = urllib.request.Request(
            'https://gamma-api.polymarket.com/events?' + params,
            headers={'User-Agent': 'Vilasio/3.7', 'Accept': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        events = data if isinstance(data, list) else [data]
        for ev in events:
            if not ev or not isinstance(ev, dict): continue
            markets = ev.get('markets', [])
            if not markets: continue
            event_title = ev.get('title', slug)
            total_vol = sum(float(m.get('volumeNum', 0) or 0) for m in markets)
            if total_vol < 5000: continue
            active = []
            for m in markets:
                if m.get('closed') or m.get('archived'): continue
                end_date = (m.get('endDate', '') or '')[:10]
                if end_date and end_date < today: continue
                raw_prices = m.get('outcomePrices', '[]')
                try:
                    prices = json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices
                    yp = float(prices[0]) if prices else None
                except: yp = None
                if yp is None: continue
                active.append({'question': m.get('question',''), 'yesProb': yp, 'volume': float(m.get('volumeNum',0) or 0)})
            if not active: continue
            if len(active) == 1:
                m = active[0]
                q = (m['question'] + ' ' + event_title + ' ' + slug).lower()
                is_bull = any(kw.lower() in q for kw in bullish_kw)
                is_bear = any(kw.lower() in q for kw in bearish_kw)
                if not is_bull and not is_bear:
                    is_bear = 'recession' in q
                score = (m['yesProb']*100 if is_bull else (1-m['yesProb'])*100 if is_bear else 50)
                return (score, total_vol, event_title, round(m['yesProb']*100,1))
            else:
                bp = sum(m['yesProb'] for m in active if any(kw.lower() in m['question'].lower() for kw in bullish_kw))
                brp = sum(m['yesProb'] for m in active if any(kw.lower() in m['question'].lower() for kw in bearish_kw))
                if bp == 0 and brp == 0: continue
                score = min(100, bp*100) if bp > 0 else max(0, (1-brp)*100)
                best = max(active, key=lambda x: x['volume'])
                return (score, total_vol, event_title, round(best['yesProb']*100,1))
    except Exception as e:
        print('[POLY_SLUG] ' + slug + ': ' + str(e))
    return None

def fetch_asset_sentiment():
    """Asset-level sentiment: PCR for ES/NQ, Polymarket for CL/GC/6E/6B/DX."""
    ck = 'asset_sentiment'
    now = datetime.datetime.now()
    if ck in _cache and (now - _cache_time[ck]).total_seconds() < 3600:
        return _cache[ck]

    today = datetime.date.today().isoformat()
    assets = {}

    # ES — SPX PCR
    spx = fetch_pcr_symbol('SPX')
    if spx:
        score = pcr_to_score(spx['avg10'], lo=0.8, hi=2.5)  # SPX PCR range is higher (index options)
        assets['ES'] = {'name': 'E-Mini S&P 500', 'score': score, 'source': 'PCR',
                        'detail': 'SPX PCR 10d avg: ' + str(spx['avg10']), 'cat': 'Indices'}

    # NQ — use equity PCR as proxy (no QQQ-specific CSV from CBOE)
    eq = fetch_pcr_symbol('EQUITY')
    if eq:
        score = pcr_to_score(eq['avg10'])
        assets['NQ'] = {'name': 'E-Mini Nasdaq', 'score': score, 'source': 'PCR',
                        'detail': 'Equity PCR 10d avg: ' + str(eq['avg10']), 'cat': 'Indices'}

    # CL, GC, 6E, 6B, DX — Polymarket
    for sym, slugs in ASSET_POLY_SLUGS.items():
        name_map = {'CL':'Crude Oil WTI','GC':'Gold','6E':'Euro FX','6B':'British Pound','DX':'US Dollar Index'}
        cat_map  = {'CL':'Energy','GC':'Metals','6E':'FX','6B':'FX','DX':'FX'}
        scores, vols = [], []
        for slug, bkw, brw in slugs:
            res = _poly_fetch_slug(slug, bkw, brw, today)
            if res:
                score, vol, title, _ = res
                scores.append(score); vols.append(vol)
        if scores:
            total_vol = sum(vols)
            wavg = sum(s*v for s,v in zip(scores,vols)) / max(total_vol, 1)
            assets[sym] = {'name': name_map.get(sym, sym), 'score': round(wavg, 1),
                           'source': 'Polymarket', 'detail': str(len(scores)) + ' markets',
                           'cat': cat_map.get(sym, 'Other')}
        else:
            assets[sym] = {'name': name_map.get(sym, sym), 'score': None,
                           'source': 'N/A', 'detail': 'No data available', 'cat': cat_map.get(sym, 'Other')}

    _cache[ck] = assets; _cache_time[ck] = now
    return assets

def fetch_macro_sentiment():
    """Macro releases sentiment: BLS trend + Polymarket Fed."""
    ck = 'macro_sentiment'
    now = datetime.datetime.now()
    if ck in _cache and (now - _cache_time[ck]).total_seconds() < 3600:
        return _cache[ck]

    today = datetime.date.today().isoformat()
    macro = {}

    # CPI — lower is bullish
    try:
        obs = fetch_bls_series('CUUR0000SA0', n=13)
        if obs and len(obs) >= 3:
            # Compute MoM % change for last 6 readings
            changes = []
            for i in range(1, len(obs)):
                prev = obs[i-1]['value']
                curr = obs[i]['value']
                if prev: changes.append((curr - prev) / prev * 100)
            latest_chg = changes[-1] if changes else None
            avg_chg = sum(changes[-6:]) / min(6, len(changes)) if changes else None
            score = macro_trend_score(obs, 'down_bullish')
            macro['CPI'] = {
                'name': 'CPI Inflation', 'score': score, 'source': 'BLS',
                'latest': round(obs[-1]['value'], 3),
                'latestChg': round(latest_chg, 2) if latest_chg else None,
                'avg6mChg': round(avg_chg, 2) if avg_chg else None,
                'period': obs[-1]['period'],
                'detail': 'MoM chg: ' + (str(round(latest_chg,2))+'%' if latest_chg else 'N/A'),
                'history': [{'period': o['period'], 'value': o['value']} for o in obs[-7:]]
            }
    except Exception as e:
        print('[BLS CPI] ' + str(e))
        macro['CPI'] = {'name': 'CPI Inflation', 'score': None, 'source': 'BLS', 'detail': 'Error fetching data', 'history': []}

    # NFP — higher is bullish
    try:
        obs = fetch_bls_series('CES0000000001', n=13)
        if obs and len(obs) >= 3:
            # Convert to monthly change (thousands)
            changes = [{'period': obs[i]['period'], 'value': obs[i]['value'] - obs[i-1]['value']} for i in range(1, len(obs))]
            score = macro_trend_score(changes, 'up_bullish')
            latest_chg = changes[-1]['value'] if changes else None
            avg_chg = sum(c['value'] for c in changes[-6:]) / min(6, len(changes)) if changes else None
            macro['NFP'] = {
                'name': 'Non-Farm Payrolls', 'score': score, 'source': 'BLS',
                'latest': round(latest_chg, 0) if latest_chg else None,
                'latestChg': round(latest_chg, 0) if latest_chg else None,
                'avg6mChg': round(avg_chg, 0) if avg_chg else None,
                'period': obs[-1]['period'],
                'detail': 'Monthly add: ' + (str(int(latest_chg))+'K' if latest_chg else 'N/A'),
                'history': [{'period': c['period'], 'value': c['value']} for c in changes[-6:]]
            }
    except Exception as e:
        print('[BLS NFP] ' + str(e))
        macro['NFP'] = {'name': 'Non-Farm Payrolls', 'score': None, 'source': 'BLS', 'detail': 'Error fetching data', 'history': []}

    # Initial Jobless Claims — lower is bullish
    try:
        obs = fetch_bls_series('ICSA', n=13)
        if obs and len(obs) >= 3:
            score = macro_trend_score(obs, 'down_bullish')
            latest = obs[-1]['value']
            avg6 = sum(o['value'] for o in obs[-7:-1]) / min(6, len(obs)-1) if len(obs) > 1 else latest
            macro['ICSA'] = {
                'name': 'Initial Jobless Claims', 'score': score, 'source': 'BLS',
                'latest': int(latest),
                'latestChg': None,
                'avg6mChg': round(avg6, 0),
                'period': obs[-1]['period'],
                'detail': 'Latest: ' + str(int(latest)) + ' · 6w avg: ' + str(int(avg6)),
                'history': [{'period': o['period'], 'value': o['value']} for o in obs[-7:]]
            }
    except Exception as e:
        print('[BLS ICSA] ' + str(e))
        macro['ICSA'] = {'name': 'Initial Jobless Claims', 'score': None, 'source': 'BLS', 'detail': 'Error fetching data', 'history': []}

    # Continued Claims — lower is bullish
    try:
        obs = fetch_bls_series('CCSA', n=13)
        if obs and len(obs) >= 3:
            score = macro_trend_score(obs, 'down_bullish')
            latest = obs[-1]['value']
            avg6 = sum(o['value'] for o in obs[-7:-1]) / min(6, len(obs)-1) if len(obs) > 1 else latest
            macro['CCSA'] = {
                'name': 'Continued Claims', 'score': score, 'source': 'BLS',
                'latest': int(latest),
                'latestChg': None,
                'avg6mChg': round(avg6, 0),
                'period': obs[-1]['period'],
                'detail': 'Latest: ' + str(int(latest)) + ' · 6w avg: ' + str(int(avg6)),
                'history': [{'period': o['period'], 'value': o['value']} for o in obs[-7:]]
            }
    except Exception as e:
        print('[BLS CCSA] ' + str(e))
        macro['CCSA'] = {'name': 'Continued Claims', 'score': None, 'source': 'BLS', 'detail': 'Error fetching data', 'history': []}

    # Interest Rates — Polymarket Fed
    fed_scores, fed_vols = [], []
    for slug, bkw, brw in MACRO_POLY_SLUGS[:3]:  # only Fed slugs
        res = _poly_fetch_slug(slug, bkw, brw, today)
        if res:
            score, vol, title, _ = res
            fed_scores.append(score); fed_vols.append(vol)
    if fed_scores:
        total_vol = sum(fed_vols)
        wavg = sum(s*v for s,v in zip(fed_scores,fed_vols)) / max(total_vol,1)
        macro['RATES'] = {
            'name': 'Interest Rates (Fed)', 'score': round(wavg,1), 'source': 'Polymarket',
            'latest': None, 'latestChg': None, 'avg6mChg': None, 'period': '2026',
            'detail': str(len(fed_scores)) + ' Fed markets',
            'history': []
        }
    else:
        macro['RATES'] = {'name': 'Interest Rates (Fed)', 'score': None, 'source': 'Polymarket',
                          'detail': 'No data', 'history': []}

    _cache[ck] = macro; _cache_time[ck] = now
    return macro

@app.route('/api/sentiment/assets')
def api_sentiment_assets():
    try:
        return jsonify({'status': 'ok', 'assets': fetch_asset_sentiment()})
    except Exception as e:
        print('[SENTIMENT_ASSETS] ' + str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/sentiment/macro')
def api_sentiment_macro():
    try:
        return jsonify({'status': 'ok', 'macro': fetch_macro_sentiment()})
    except Exception as e:
        print('[SENTIMENT_MACRO] ' + str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/sentiment')
def api_sentiment():
    """Master sentiment endpoint combining assets + macro."""
    try:
        assets = fetch_asset_sentiment()
        macro = fetch_macro_sentiment()
        # Overall score: avg of all available scores
        all_scores = [v['score'] for v in list(assets.values()) + list(macro.values()) if v.get('score') is not None]
        composite = round(sum(all_scores) / len(all_scores), 1) if all_scores else None
        if composite is None: label = 'UNAVAILABLE'
        elif composite >= 70: label = 'EXTREME GREED'
        elif composite >= 55: label = 'GREED'
        elif composite >= 45: label = 'NEUTRAL'
        elif composite >= 30: label = 'FEAR'
        else: label = 'EXTREME FEAR'
        return jsonify({'status': 'ok', 'composite': composite, 'label': label,
                        'assets': assets, 'macro': macro})
    except Exception as e:
        print('[SENTIMENT] ' + str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/markets')
def api_markets():
    result = []
    for sym in sorted(MARKETS.keys()):
        cfg = MARKETS[sym]
        result.append({'market': sym, 'name': cfg['name'], 'exchange': cfg['exchange'], 'cat': cfg['cat']})
    return jsonify({'markets': result, 'categories': FLOW_CATS, 'heatmap': HEATMAP_MARKETS})

# ─── LIQUIDITY MONITOR (FRED API) ──────────────────────────────────────────

FRED_API_KEY = os.environ.get('FRED_API_KEY', '0054b7d2aa4634dd19a108d211a50e7f')
FRED_BASE = 'https://api.stlouisfed.org/fred/series/observations'

# Divisor to convert FRED native units to billions USD
FRED_DIV = {
    'WALCL': 1000, 'WTREGEN': 1000, 'RRPONTSYD': 1, 'WRESBAL': 1,
    'TREAST': 1000, 'WSHOMCB': 1000, 'M1SL': 1, 'M2SL': 1, 'MTSDS133FMS': 1000
}

def fetch_fred(series_id, years=3):
    ck = 'fred_' + series_id
    now = datetime.datetime.now()
    if ck in _cache and (now - _cache_time[ck]).total_seconds() < CACHE_TTL:
        return _cache[ck]
    start = (datetime.date.today() - datetime.timedelta(days=365 * years)).isoformat()
    try:
        data = fetch_json(FRED_BASE, {
            'series_id': series_id, 'api_key': FRED_API_KEY,
            'file_type': 'json', 'observation_start': start, 'sort_order': 'asc'
        })
        div = FRED_DIV.get(series_id, 1)
        obs = []
        for o in data.get('observations', []):
            v = o.get('value', '.')
            if v == '.': continue
            try: obs.append({'date': o['date'], 'value': round(float(v) / div, 4)})
            except: continue
        _cache[ck] = obs
        _cache_time[ck] = now
        return obs
    except Exception as e:
        print('[FRED] ' + series_id + ': ' + str(e))
        return _cache.get(ck, [])

def nearest_val(lookup, dt_str, max_days=7):
    for off in range(max_days):
        check = (datetime.date.fromisoformat(dt_str) - datetime.timedelta(days=off)).isoformat()
        if check in lookup: return lookup[check]
    return None

@app.route('/api/liquidity')
def api_liquidity():
    if not FRED_API_KEY:
        return jsonify({'status': 'error', 'message': 'FRED_API_KEY not set'}), 500
    try:
        walcl = fetch_fred('WALCL')
        tga_raw = fetch_fred('WTREGEN')
        rrp_raw = fetch_fred('RRPONTSYD')
        reserves = fetch_fred('WRESBAL')
        treasury = fetch_fred('TREAST')
        mbs = fetch_fred('WSHOMCB')
        m1 = fetch_fred('M1SL')
        m2 = fetch_fred('M2SL')
        deficit = fetch_fred('MTSDS133FMS')

        # --- Net Liquidity: WALCL - TGA - RRP (aligned on WALCL weekly dates) ---
        tga_map = {o['date']: o['value'] for o in tga_raw}
        rrp_map = {o['date']: o['value'] for o in rrp_raw}
        nl_dates, nl_walcl, nl_tga, nl_rrp, nl_net = [], [], [], [], []
        for w in walcl:
            tv = nearest_val(tga_map, w['date']) or 0
            rv = nearest_val(rrp_map, w['date']) or 0
            nl_dates.append(w['date'])
            nl_walcl.append(round(w['value'], 2))
            nl_tga.append(round(tv, 2))
            nl_rrp.append(round(rv, 2))
            nl_net.append(round(w['value'] - tv - rv, 2))

        # --- Balance Sheet Decomposition ---
        t_map = {o['date']: o['value'] for o in treasury}
        m_map = {o['date']: o['value'] for o in mbs}
        bs_dates, bs_total, bs_tres, bs_mbs, bs_other = [], [], [], [], []
        for w in walcl:
            tv = t_map.get(w['date'], 0)
            mv = m_map.get(w['date'], 0)
            bs_dates.append(w['date'])
            bs_total.append(round(w['value'], 2))
            bs_tres.append(round(tv, 2))
            bs_mbs.append(round(mv, 2))
            bs_other.append(round(w['value'] - tv - mv, 2))

        # --- QE/QT: weekly change in WALCL ---
        qeqt_dates, qeqt_chg = [], []
        for i in range(1, len(walcl)):
            qeqt_dates.append(walcl[i]['date'])
            qeqt_chg.append(round(walcl[i]['value'] - walcl[i-1]['value'], 2))
        recent = qeqt_chg[-13:] if len(qeqt_chg) >= 13 else qeqt_chg
        avg_chg = sum(recent) / len(recent) if recent else 0
        qe_status = 'QE' if avg_chg > 1 else ('QT' if avg_chg < -1 else 'NEUTRAL')

        # --- M2 YoY growth ---
        m2_map = {o['date']: o['value'] for o in m2}
        m2y_dates, m2y_vals = [], []
        for d in sorted(m2_map.keys()):
            dt = datetime.date.fromisoformat(d)
            prev = None
            for off in range(-15, 16):
                check = (dt - datetime.timedelta(days=365) + datetime.timedelta(days=off)).isoformat()
                if check in m2_map: prev = m2_map[check]; break
            if prev and prev > 0:
                m2y_dates.append(d)
                m2y_vals.append(round((m2_map[d] - prev) / prev * 100, 2))

        # --- S&P 500 weekly (overlay) ---
        sp_dates, sp_vals = [], []
        try:
            import yfinance as yf
            start = (datetime.date.today() - datetime.timedelta(days=365 * 3)).isoformat()
            df = yf.Ticker('^GSPC').history(start=start, interval='1wk')
            for idx, row in df.iterrows():
                sp_dates.append(idx.strftime('%Y-%m-%d'))
                sp_vals.append(round(float(row['Close']), 2))
        except Exception as e:
            print('[LIQUIDITY] S&P 500: ' + str(e))

        last_update = nl_dates[-1] if nl_dates else None

        return jsonify({
            'status': 'ok',
            'lastUpdate': last_update,
            'netLiquidity': {'dates': nl_dates, 'walcl': nl_walcl, 'tga': nl_tga, 'rrp': nl_rrp, 'netLiq': nl_net},
            'balanceSheet': {'dates': bs_dates, 'total': bs_total, 'treasury': bs_tres, 'mbs': bs_mbs, 'other': bs_other},
            'reserves': {'dates': [o['date'] for o in reserves], 'values': [o['value'] for o in reserves]},
            'rrp': {'dates': [o['date'] for o in rrp_raw], 'values': [o['value'] for o in rrp_raw]},
            'tga': {'dates': [o['date'] for o in tga_raw], 'values': [o['value'] for o in tga_raw]},
            'moneySupply': {
                'm1': {'dates': [o['date'] for o in m1], 'values': [o['value'] for o in m1]},
                'm2': {'dates': [o['date'] for o in m2], 'values': [o['value'] for o in m2]},
                'm2yoy': {'dates': m2y_dates, 'values': m2y_vals}
            },
            'deficit': {'dates': [o['date'] for o in deficit], 'values': [o['value'] for o in deficit]},
            'sp500': {'dates': sp_dates, 'values': sp_vals},
            'qeqt': {'dates': qeqt_dates, 'changes': qeqt_chg, 'status': qe_status, 'avgWeekly': round(avg_chg, 2)}
        })
    except Exception as e:
        print('[LIQUIDITY] ' + str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/liquidity/refresh')
def api_liquidity_refresh():
    # Clear only FRED-related cache entries
    fred_keys = [k for k in _cache if k.startswith('fred_') or k.startswith('price_^GSPC')]
    for k in fred_keys:
        _cache.pop(k, None)
        _cache_time.pop(k, None)
    print('[LIQUIDITY] Cache cleared (' + str(len(fred_keys)) + ' keys), refetching...')
    return api_liquidity()

# ─── BOND & YIELD MONITOR (FRED API) ───────────────────────────────────────

# 2026 FOMC meeting dates (announcement day = day 2)
FOMC_DATES = [
    '2026-01-29', '2026-03-19', '2026-05-07', '2026-06-18',
    '2026-07-30', '2026-09-17', '2026-11-05', '2026-12-17'
]

def align_on_dates(base_dates, series_map):
    """Align multiple series on a common set of dates using nearest-value lookup."""
    result = {}
    for key, raw in series_map.items():
        lookup = {o['date']: o['value'] for o in raw}
        vals = []
        for d in base_dates:
            v = lookup.get(d)
            if v is None:
                v = nearest_val(lookup, d, 5)
            vals.append(v)
        result[key] = vals
    return result

@app.route('/api/bonds')
def api_bonds():
    if not FRED_API_KEY:
        return jsonify({'status': 'error', 'message': 'FRED_API_KEY not set'}), 500
    try:
        # --- Fetch all series ---
        dgs2 = fetch_fred('DGS2')
        dgs5 = fetch_fred('DGS5')
        dgs10 = fetch_fred('DGS10')
        dgs30 = fetch_fred('DGS30')
        t10y2y = fetch_fred('T10Y2Y')
        dfii5 = fetch_fred('DFII5')
        dfii10 = fetch_fred('DFII10')
        t5yie = fetch_fred('T5YIE')
        t10yie = fetch_fred('T10YIE')
        ig = fetch_fred('BAMLC0A0CM')
        hy = fetch_fred('BAMLH0A0HYM2')
        dff = fetch_fred('DFF')
        upper = fetch_fred('DFEDTARU')
        lower = fetch_fred('DFEDTARL')

        # --- Yields: align on DGS10 dates (most complete daily series) ---
        base_dates = [o['date'] for o in dgs10]
        aligned = align_on_dates(base_dates, {
            'dgs2': dgs2, 'dgs5': dgs5, 'dgs10': dgs10, 'dgs30': dgs30
        })

        # --- 2Y-10Y Spread ---
        sp_dates = [o['date'] for o in t10y2y]
        sp_vals = [o['value'] for o in t10y2y]

        # --- Real Yields: align on DFII10 dates ---
        ry_dates = [o['date'] for o in dfii10]
        ry_aligned = align_on_dates(ry_dates, {'dfii5': dfii5, 'dfii10': dfii10})

        # --- Breakeven: align on T10YIE dates ---
        be_dates = [o['date'] for o in t10yie]
        be_aligned = align_on_dates(be_dates, {'t5yie': t5yie, 't10yie': t10yie})

        # --- Credit Spreads ---
        ig_dates = [o['date'] for o in ig]
        ig_vals = [o['value'] for o in ig]
        hy_dates = [o['date'] for o in hy]
        hy_vals = [o['value'] for o in hy]

        # --- Fed Funds: align on DFF dates ---
        ff_dates = [o['date'] for o in dff]
        ff_aligned = align_on_dates(ff_dates, {
            'effective': dff, 'upper': upper, 'lower': lower
        })

        # --- Gold price (for real yield correlation) ---
        gold_dates, gold_vals = [], []
        try:
            import yfinance as yf
            start = (datetime.date.today() - datetime.timedelta(days=365 * 3)).isoformat()
            df = yf.Ticker('GC=F').history(start=start, interval='1wk')
            for idx, row in df.iterrows():
                gold_dates.append(idx.strftime('%Y-%m-%d'))
                gold_vals.append(round(float(row['Close']), 2))
        except Exception as e:
            print('[BONDS] Gold: ' + str(e))

        # --- DXY (for intermarket) ---
        dxy_dates, dxy_vals = [], []
        try:
            import yfinance as yf
            start = (datetime.date.today() - datetime.timedelta(days=365 * 3)).isoformat()
            df = yf.Ticker('DX-Y.NYB').history(start=start, interval='1wk')
            for idx, row in df.iterrows():
                dxy_dates.append(idx.strftime('%Y-%m-%d'))
                dxy_vals.append(round(float(row['Close']), 2))
        except Exception as e:
            print('[BONDS] DXY: ' + str(e))

        # --- FOMC Calendar ---
        today = datetime.date.today().isoformat()
        fomc = []
        for fd in FOMC_DATES:
            dt = datetime.date.fromisoformat(fd)
            delta = (dt - datetime.date.today()).days
            status = 'past' if delta < 0 else ('next' if not fomc or all(f['status'] == 'past' for f in fomc) else 'upcoming')
            if delta >= 0 and not any(f['status'] == 'next' for f in fomc):
                status = 'next'
            fomc.append({'date': fd, 'daysUntil': delta, 'status': status})

        last_update = base_dates[-1] if base_dates else None

        return jsonify({
            'status': 'ok',
            'lastUpdate': last_update,
            'yields': {
                'dates': base_dates,
                'dgs2': aligned['dgs2'], 'dgs5': aligned['dgs5'],
                'dgs10': aligned['dgs10'], 'dgs30': aligned['dgs30']
            },
            'spread': {'dates': sp_dates, 'values': sp_vals},
            'realYields': {
                'dates': ry_dates,
                'dfii5': ry_aligned['dfii5'], 'dfii10': ry_aligned['dfii10']
            },
            'breakeven': {
                'dates': be_dates,
                't5yie': be_aligned['t5yie'], 't10yie': be_aligned['t10yie']
            },
            'credit': {
                'ig': {'dates': ig_dates, 'values': ig_vals},
                'hy': {'dates': hy_dates, 'values': hy_vals}
            },
            'fedFunds': {
                'dates': ff_dates,
                'effective': ff_aligned['effective'],
                'upper': ff_aligned['upper'],
                'lower': ff_aligned['lower']
            },
            'gold': {'dates': gold_dates, 'values': gold_vals},
            'dxy': {'dates': dxy_dates, 'values': dxy_vals},
            'fomc': fomc
        })
    except Exception as e:
        print('[BONDS] ' + str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/bonds/refresh')
def api_bonds_refresh():
    fred_keys = [k for k in _cache if k.startswith('fred_') or k.startswith('price_GC') or k.startswith('price_DX')]
    for k in fred_keys:
        _cache.pop(k, None)
        _cache_time.pop(k, None)
    print('[BONDS] Cache cleared (' + str(len(fred_keys)) + ' keys), refetching...')
    return api_bonds()

# ─── MACRO REGIME DASHBOARD (FRED API) ─────────────────────────────────────

def compute_yoy_from_index(series):
    """Compute YoY % change from a monthly index series."""
    by_date = {o['date']: o['value'] for o in series}
    dates = sorted(by_date.keys())
    out_d, out_v = [], []
    for d in dates:
        dt = datetime.date.fromisoformat(d)
        prev = None
        for off in range(-15, 16):
            ck = (dt - datetime.timedelta(days=365) + datetime.timedelta(days=off)).isoformat()
            if ck in by_date: prev = by_date[ck]; break
        if prev and prev > 0:
            out_d.append(d)
            out_v.append(round((by_date[d] - prev) / prev * 100, 2))
    return out_d, out_v

def compute_mom_from_index(series):
    """Compute MoM % change from a monthly index series."""
    out_d, out_v = [], []
    for i in range(1, len(series)):
        prev = series[i-1]['value']
        cur = series[i]['value']
        if prev and prev > 0:
            out_d.append(series[i]['date'])
            out_v.append(round((cur - prev) / prev * 100, 2))
    return out_d, out_v

def morpheus_rank(values, lookback):
    """Compute percent rank (0-100) of each value against its trailing window.
    No SMA — ranks raw releases directly per the Macro Regime Oscillator spec."""
    ranks = []
    for i in range(len(values)):
        if i < lookback - 1:
            ranks.append(None)
            continue
        cur = values[i]
        window = [v for v in values[max(0, i - lookback + 1):i + 1] if v is not None]
        if len(window) < 2:
            ranks.append(None)
            continue
        below = sum(1 for v in window if v < cur)
        ranks.append(round(below / (len(window) - 1) * 100, 1))
    return ranks

@app.route('/api/macro')
def api_macro():
    if not FRED_API_KEY:
        return jsonify({'status': 'error', 'message': 'FRED_API_KEY not set'}), 500
    try:
        cpi = fetch_fred('CPIAUCSL', 10)
        core_cpi = fetch_fred('CPILFESL', 10)
        pce = fetch_fred('PCEPI', 10)
        core_pce = fetch_fred('PCEPILFE', 10)
        ppifis = fetch_fred('PPIFIS', 10)
        unrate = fetch_fred('UNRATE', 10)
        payems = fetch_fred('PAYEMS', 10)
        icsa = fetch_fred('ICSA', 4)
        gdpc1 = fetch_fred('GDPC1', 6)
        jtsjol = fetch_fred('JTSJOL', 4)

        # --- YoY & MoM ---
        cpi_yoy_d, cpi_yoy_v = compute_yoy_from_index(cpi)
        ccpi_yoy_d, ccpi_yoy_v = compute_yoy_from_index(core_cpi)
        pce_yoy_d, pce_yoy_v = compute_yoy_from_index(pce)
        cpce_yoy_d, cpce_yoy_v = compute_yoy_from_index(core_pce)
        ppi_yoy_d, ppi_yoy_v = compute_yoy_from_index(ppifis)

        # --- NFP monthly change (thousands) ---
        nfp_d, nfp_v = [], []
        for i in range(1, len(payems)):
            nfp_d.append(payems[i]['date'])
            nfp_v.append(round(payems[i]['value'] - payems[i-1]['value'], 1))

        # --- Morpheus Trade Off ---
        # Align inflation YoY and unemployment on common dates
        inf_map = {d: v for d, v in zip(cpi_yoy_d, cpi_yoy_v)}
        ur_map = {o['date']: o['value'] for o in unrate}
        morph_dates = sorted(set(cpi_yoy_d) & set(ur_map.keys()))
        morph_inf = [inf_map[d] for d in morph_dates]
        morph_ur = [ur_map[d] for d in morph_dates]

        # Short-term (12 months) and long-term (52 months) ranks
        inf_rank_12 = morpheus_rank(morph_inf, 12)
        ur_rank_12 = morpheus_rank(morph_ur, 12)
        inf_rank_52 = morpheus_rank(morph_inf, 52)
        ur_rank_52 = morpheus_rank(morph_ur, 52)

        # Policy switch detection (using 52M lookback for stability)
        policy = 'NEUTRAL'
        n_mr = len(inf_rank_52)
        if n_mr > 0 and inf_rank_52[-1] is not None and ur_rank_52[-1] is not None:
            ir, ur_val = inf_rank_52[-1], ur_rank_52[-1]
            if ur_val > 80 and ir < 20: policy = 'DOVISH'
            elif ir > 80 and ur_val < 20: policy = 'HAWKISH'

        # --- 4-Regime Model (Casario) ---
        # Growth: NFP trend (avg last 3 months)
        # Inflation: CPI YoY trend (latest vs 3 months ago)
        regime = 'UNKNOWN'
        if len(nfp_v) >= 3 and len(cpi_yoy_v) >= 4:
            nfp_avg = sum(nfp_v[-3:]) / 3
            inf_now = cpi_yoy_v[-1]
            inf_prev = cpi_yoy_v[-4]
            growth_up = nfp_avg > 0
            inf_rising = inf_now > inf_prev
            if growth_up and inf_rising: regime = 'EXPANSION'
            elif growth_up and not inf_rising: regime = 'REFLATION'
            elif not growth_up and inf_rising: regime = 'STAGNATION'
            else: regime = 'SLOWDOWN'

        last_update = cpi_yoy_d[-1] if cpi_yoy_d else None

        return jsonify({
            'status': 'ok',
            'lastUpdate': last_update,
            'regime': regime,
            'policySwitch': policy,
            'inflation': {
                'cpiYoY': {'dates': cpi_yoy_d, 'values': cpi_yoy_v},
                'coreCpiYoY': {'dates': ccpi_yoy_d, 'values': ccpi_yoy_v},
                'pceYoY': {'dates': pce_yoy_d, 'values': pce_yoy_v},
                'corePceYoY': {'dates': cpce_yoy_d, 'values': cpce_yoy_v},
                'ppiYoY': {'dates': ppi_yoy_d, 'values': ppi_yoy_v},
            },
            'labor': {
                'unrate': {'dates': [o['date'] for o in unrate], 'values': [o['value'] for o in unrate]},
                'nfp': {'dates': nfp_d, 'values': nfp_v},
                'icsa': {'dates': [o['date'] for o in icsa], 'values': [o['value'] for o in icsa]},
                'jolts': {'dates': [o['date'] for o in jtsjol], 'values': [o['value'] for o in jtsjol]},
            },
            'morpheus': {
                'dates': morph_dates,
                'infYoY': morph_inf,
                'unrate': morph_ur,
                'infRank12': inf_rank_12,
                'urRank12': ur_rank_12,
                'infRank52': inf_rank_52,
                'urRank52': ur_rank_52,
            },
            'gdp': {'dates': [o['date'] for o in gdpc1], 'values': [o['value'] for o in gdpc1]},
        })
    except Exception as e:
        print('[MACRO] ' + str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/macro/refresh')
def api_macro_refresh():
    fred_keys = [k for k in _cache if k.startswith('fred_')]
    for k in fred_keys:
        _cache.pop(k, None)
        _cache_time.pop(k, None)
    print('[MACRO] Cache cleared (' + str(len(fred_keys)) + ' keys), refetching...')
    return api_macro()

# ─── MACRO CONSENSUS (Kalshi) ───────────────────────────────────────────────

MACRO_KEYWORDS = ['fed', 'recession', 'inflation', 'cpi', 'rate cut', 'rate hike',
                  'fomc', 'interest rate', 'gdp', 'unemployment', 'tariff', 'pce',
                  'treasury', 'deficit', 'debt ceiling', 'stagflation']

def _categorize_market(text):
    t = text.lower()
    if 'recession' in t or 'gdp' in t:
        return 'Recession'
    if any(w in t for w in ['fed', 'fomc', 'rate cut', 'rate hike', 'interest rate', 'federal']):
        return 'Fed Policy'
    if any(w in t for w in ['inflation', 'cpi', 'pce', 'stagflation']):
        return 'Inflation'
    return 'Macro'

def fetch_consensus_markets():
    """Fetch macro-relevant prediction markets from Kalshi public API."""
    ck = 'consensus_markets'
    now = datetime.datetime.now()
    if ck in _cache and (now - _cache_time[ck]).total_seconds() < 3600:
        return _cache[ck]

    url = 'https://api.elections.kalshi.com/trade-api/v2/markets?status=open&limit=200'
    print('[KALSHI] GET ' + url)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Vilasio/3.7', 'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode('utf-8')
        print('[KALSHI] HTTP ' + str(len(body)) + ' chars')
        data = json.loads(body)
        markets = data.get('markets', []) if isinstance(data, dict) else data if isinstance(data, list) else []
        print('[KALSHI] ' + str(len(markets)) + ' markets fetched')
        print('[KALSHI] Sample titles: ' + str([(m.get('title', '')[:50], m.get('ticker', '')) for m in markets[:10] if isinstance(m, dict)]))
        broad = [m.get('title', '')[:60] for m in markets if isinstance(m, dict) and any(w in (m.get('title', '') + ' ' + m.get('subtitle', '')).lower() for w in ['rate', 'fed', 'recession', 'inflation', 'economy', 'gdp', 'cpi', 'price', 'treasury', 'employment', 'job'])]
        print('[KALSHI] Broad keyword matches: ' + str(broad[:15]))
    except Exception as e:
        print('[KALSHI] FAILED: ' + str(e))
        markets = []

    found = {}
    for m in markets:
        if not isinstance(m, dict):
            continue
        title = m.get('title', '') or ''
        subtitle = m.get('subtitle', '') or ''
        ticker = m.get('ticker', '') or ''
        text = (title + ' ' + subtitle + ' ' + ticker).lower()
        if not any(kw in text for kw in MACRO_KEYWORDS):
            continue
        # Kalshi: yes_ask is the YES probability (cents, 0-100)
        prob = None
        for key in ['yes_ask', 'last_price', 'yes_bid']:
            v = m.get(key)
            if v is not None:
                try:
                    prob = round(float(v), 1)
                    if prob > 0:
                        break
                except:
                    pass
        if not prob or prob <= 0:
            continue
        vol = int(m.get('volume', 0) or 0)
        question = title
        if subtitle:
            question = title + ' — ' + subtitle
        found[ticker] = {
            'question': question,
            'probability': prob,
            'volume': vol,
            'liquidity': int(m.get('open_interest', 0) or 0),
            'slug': ticker,
            'category': _categorize_market(text)
        }

    result = sorted(found.values(), key=lambda x: -x['volume'])[:12]
    print('[KALSHI] ' + str(len(found)) + ' matched keywords, returning ' + str(len(result)))
    _cache[ck] = result
    _cache_time[ck] = now
    return result

@app.route('/api/macro/consensus')
def api_macro_consensus():
    try:
        markets = fetch_consensus_markets()
        return jsonify({'status': 'ok', 'markets': markets})
    except Exception as e:
        print('[KALSHI] ' + str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ─── CROSS-MARKET & INTERMARKET ANALYSIS ────────────────────────────────────

def fetch_yf_weekly(symbol, years=2):
    """Fetch weekly prices from yfinance with caching."""
    ck = 'yf_weekly_' + symbol.replace('=', '').replace('^', '').replace('-', '')
    now = datetime.datetime.now()
    if ck in _cache and (now - _cache_time[ck]).total_seconds() < CACHE_TTL:
        return _cache[ck]
    import yfinance as yf
    start = (datetime.date.today() - datetime.timedelta(days=365 * years)).isoformat()
    try:
        df = yf.Ticker(symbol).history(start=start, interval='1wk')
        dates, vals = [], []
        for idx, row in df.iterrows():
            dates.append(idx.strftime('%Y-%m-%d'))
            vals.append(round(float(row['Close']), 4))
        result = {'dates': dates, 'values': vals}
        _cache[ck] = result
        _cache_time[ck] = now
        return result
    except Exception as e:
        print('[YF] ' + symbol + ': ' + str(e))
        result = {'dates': [], 'values': []}
        _cache[ck] = result
        _cache_time[ck] = now
        return result

def fetch_yf_daily(symbol, years=2):
    """Fetch daily prices from yfinance with caching."""
    ck = 'yf_daily_' + symbol.replace('=', '').replace('^', '').replace('-', '')
    now = datetime.datetime.now()
    if ck in _cache and (now - _cache_time[ck]).total_seconds() < CACHE_TTL:
        return _cache[ck]
    import yfinance as yf
    start = (datetime.date.today() - datetime.timedelta(days=365 * years)).isoformat()
    try:
        df = yf.Ticker(symbol).history(start=start, interval='1d')
        dates, vals = [], []
        for idx, row in df.iterrows():
            dates.append(idx.strftime('%Y-%m-%d'))
            vals.append(round(float(row['Close']), 4))
        result = {'dates': dates, 'values': vals}
        _cache[ck] = result
        _cache_time[ck] = now
        return result
    except Exception as e:
        print('[YF] ' + symbol + ': ' + str(e))
        result = {'dates': [], 'values': []}
        _cache[ck] = result
        _cache_time[ck] = now
        return result

def build_status_prices():
    """Fetch latest DXY and EUR/USD for status cards."""
    dxy = fetch_yf_daily('DX-Y.NYB', 1)
    eur = fetch_yf_daily('EURUSD=X', 1)
    result = {}
    for key, data in [('DXY', dxy), ('EURUSD', eur)]:
        if data['values'] and len(data['values']) >= 2:
            v = data['values']
            result[key] = {'price': v[-1], 'prev': v[-2]}
        else:
            result[key] = {'price': None, 'prev': None}
    return result

def build_correlation_matrix():
    """Build 7x7 correlation matrix from daily returns."""
    assets = {
        'SPX': '^GSPC',
        'Gold': 'GC=F',
        'DXY': 'DX-Y.NYB',
        'US10Y': '^TNX',
        'Oil': 'CL=F',
        'EURUSD': 'EURUSD=X',
        'BTC': 'BTC-USD'
    }
    # Fetch daily data
    price_data = {}
    for key, sym in assets.items():
        data = fetch_yf_daily(sym, 2)
        price_data[key] = data

    asset_keys = list(assets.keys())
    n = len(asset_keys)

    # Build aligned return series on common dates
    all_dates = None
    for key in asset_keys:
        s = set(price_data[key]['dates'])
        if all_dates is None:
            all_dates = s
        else:
            all_dates = all_dates & s
    if not all_dates or len(all_dates) < 30:
        # Fallback: empty matrix
        return {'labels': asset_keys, 'current': [[0]*n for _ in range(n)], 'previous': [[0]*n for _ in range(n)]}

    common_dates = sorted(all_dates)
    # Build price lookup and compute returns
    returns = {}
    for key in asset_keys:
        lookup = {d: v for d, v in zip(price_data[key]['dates'], price_data[key]['values'])}
        prices = [lookup[d] for d in common_dates]
        rets = []
        for i in range(1, len(prices)):
            if prices[i-1] and prices[i-1] != 0:
                rets.append((prices[i] - prices[i-1]) / prices[i-1])
            else:
                rets.append(0)
        returns[key] = rets

    # Rolling 90-day correlation
    window = 90
    total_rets = len(returns[asset_keys[0]])
    if total_rets < window:
        window = total_rets

    def corr_matrix(start, end):
        matrix = []
        for i in range(n):
            row = []
            for j in range(n):
                if i == j:
                    row.append(1.0)
                else:
                    r1 = returns[asset_keys[i]][start:end]
                    r2 = returns[asset_keys[j]][start:end]
                    k = len(r1)
                    if k < 10:
                        row.append(0)
                        continue
                    m1 = sum(r1) / k
                    m2 = sum(r2) / k
                    num = sum((r1[x]-m1)*(r2[x]-m2) for x in range(k))
                    d1 = max(1e-10, sum((r1[x]-m1)**2 for x in range(k))**0.5)
                    d2 = max(1e-10, sum((r2[x]-m2)**2 for x in range(k))**0.5)
                    row.append(round(num / (d1 * d2), 2))
            matrix.append(row)
        return matrix

    # Current (last 90 days)
    current = corr_matrix(total_rets - window, total_rets)
    # Previous (90 days before that)
    prev_end = max(0, total_rets - window)
    prev_start = max(0, prev_end - window)
    previous = corr_matrix(prev_start, prev_end) if prev_end - prev_start >= 30 else current

    return {'labels': asset_keys, 'current': current, 'previous': previous}

def pct_change(prices, days_back):
    """Calculate % change from days_back ago to latest."""
    if len(prices) < days_back + 1:
        return None
    p_now = prices[-1]
    p_prev = prices[-(days_back + 1)]
    if p_prev and p_prev != 0:
        return round((p_now - p_prev) / p_prev * 100, 2)
    return None

def ytd_change(dates, prices):
    """Calculate YTD % change (from first trading day of current year)."""
    year = str(datetime.date.today().year)
    for i, d in enumerate(dates):
        if d.startswith(year):
            if prices[i] and prices[i] != 0 and prices[-1]:
                return round((prices[-1] - prices[i]) / prices[i] * 100, 2)
            break
    return None

def fetch_yf_hourly(symbol, days=30):
    """Fetch hourly prices from yfinance with caching."""
    ck = 'yf_hourly_' + symbol.replace('=', '').replace('^', '').replace('-', '')
    now = datetime.datetime.now()
    if ck in _cache and (now - _cache_time[ck]).total_seconds() < CACHE_TTL:
        return _cache[ck]
    import yfinance as yf
    period = str(min(days, 729)) + 'd'
    try:
        df = yf.Ticker(symbol).history(period=period, interval='1h')
        dates, vals = [], []
        for idx, row in df.iterrows():
            dates.append(idx.strftime('%Y-%m-%d %H:%M'))
            vals.append(round(float(row['Close']), 4))
        result = {'dates': dates, 'values': vals}
        _cache[ck] = result
        _cache_time[ck] = now
        return result
    except Exception as e:
        print('[YF] hourly ' + symbol + ': ' + str(e))
        result = {'dates': [], 'values': []}
        _cache[ck] = result
        _cache_time[ck] = now
        return result

def fetch_yf_15min(symbol, days=30):
    """Fetch 15-minute prices from yfinance with caching."""
    ck = 'yf_15m_' + symbol.replace('=', '').replace('^', '').replace('-', '')
    now = datetime.datetime.now()
    if ck in _cache and (now - _cache_time[ck]).total_seconds() < CACHE_TTL:
        return _cache[ck]
    import yfinance as yf
    period = str(min(days, 59)) + 'd'
    try:
        df = yf.Ticker(symbol).history(period=period, interval='15m')
        dates, vals = [], []
        for idx, row in df.iterrows():
            dates.append(idx.strftime('%Y-%m-%d %H:%M'))
            vals.append(round(float(row['Close']), 4))
        result = {'dates': dates, 'values': vals}
        _cache[ck] = result
        _cache_time[ck] = now
        return result
    except Exception as e:
        print('[YF] 15m ' + symbol + ': ' + str(e))
        result = {'dates': [], 'values': []}
        _cache[ck] = result
        _cache_time[ck] = now
        return result

def compute_strength(pair_data, currencies):
    """Compute currency strength index from pair data. Returns {dates, series, performance}."""
    all_date_sets = [set(pd['data']['dates']) for pd in pair_data.values() if pd['data']['dates']]
    if not all_date_sets:
        return {'dates': [], 'series': {}, 'performance': {}}
    common = sorted(set.intersection(*all_date_sets))
    if len(common) < 4:
        return {'dates': [], 'series': {}, 'performance': {}}
    ccy_returns = {c: [0.0] * (len(common) - 1) for c in currencies}
    ccy_counts = {c: [0] * (len(common) - 1) for c in currencies}
    for sym, info in pair_data.items():
        lookup = {d: v for d, v in zip(info['data']['dates'], info['data']['values'])}
        prices = [lookup.get(d) for d in common]
        base, quote = info['base'], info['quote']
        for i in range(1, len(prices)):
            if prices[i] and prices[i-1] and prices[i-1] != 0:
                ret = (prices[i] - prices[i-1]) / prices[i-1]
                ccy_returns[base][i-1] += ret
                ccy_counts[base][i-1] += 1
                ccy_returns[quote][i-1] -= ret
                ccy_counts[quote][i-1] += 1
    series = {}
    performance = {}
    for c in currencies:
        avg_rets = [ccy_returns[c][i] / ccy_counts[c][i] if ccy_counts[c][i] > 0 else 0 for i in range(len(ccy_returns[c]))]
        idx = [100.0]
        for r in avg_rets:
            idx.append(round(idx[-1] * (1 + r), 2))
        series[c] = idx
        n = len(idx)
        performance[c] = {
            'current': idx[-1],
            'chg1W': round(idx[-1] - idx[-2], 2) if n > 1 else 0,
            'chg1M': round(idx[-1] - idx[max(0, n-5)], 2) if n > 4 else 0,
            'chg3M': round(idx[-1] - idx[max(0, n-13)], 2) if n > 12 else 0,
        }
    return {'dates': common, 'series': series, 'performance': performance}

def build_currency_strength():
    """Calculate relative strength index for 8 major currencies. Hourly + daily."""
    pairs_config = [
        ('EURUSD=X', 'EUR', 'USD'), ('GBPUSD=X', 'GBP', 'USD'),
        ('USDJPY=X', 'USD', 'JPY'), ('AUDUSD=X', 'AUD', 'USD'),
        ('USDCAD=X', 'USD', 'CAD'), ('USDCHF=X', 'USD', 'CHF'),
        ('NZDUSD=X', 'NZD', 'USD'), ('EURGBP=X', 'EUR', 'GBP'),
        ('EURJPY=X', 'EUR', 'JPY'), ('GBPJPY=X', 'GBP', 'JPY'),
        ('AUDJPY=X', 'AUD', 'JPY'), ('CADJPY=X', 'CAD', 'JPY'),
    ]
    currencies = ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF', 'NZD']

    # Daily (1 year)
    daily_pairs = {}
    for sym, base, quote in pairs_config:
        data = fetch_yf_daily(sym, 1)
        if data['dates']:
            daily_pairs[sym] = {'data': data, 'base': base, 'quote': quote}
    daily = compute_strength(daily_pairs, currencies)

    # Hourly (30 days)
    hourly_pairs = {}
    for sym, base, quote in pairs_config:
        data = fetch_yf_hourly(sym, 30)
        if data['dates']:
            hourly_pairs[sym] = {'data': data, 'base': base, 'quote': quote}
    hourly = compute_strength(hourly_pairs, currencies)

    return {
        'currencies': currencies,
        'daily': {'dates': daily['dates'], 'series': daily['series']},
        'hourly': {'dates': hourly['dates'], 'series': hourly['series']},
        'performance': daily.get('performance', {})
    }

def build_sector_rotation():
    """Fetch sector ETF performance data."""
    etfs = {
        'XLK': 'Technology', 'XLF': 'Financials', 'XLE': 'Energy',
        'XLV': 'Health Care', 'XLU': 'Utilities', 'XLP': 'Consumer Staples',
        'XLRE': 'Real Estate', 'XLB': 'Materials', 'XLY': 'Consumer Discretionary',
        'XLI': 'Industrials', 'XLC': 'Communication Services'
    }
    result = []
    for sym, name in etfs.items():
        data = fetch_yf_daily(sym, 1)
        if not data['dates'] or len(data['values']) < 5:
            continue
        d, v = data['dates'], data['values']
        result.append({
            'symbol': sym, 'name': name, 'price': v[-1],
            'chg1W': pct_change(v, 5),
            'chg1M': pct_change(v, 21),
            'chg3M': pct_change(v, 63),
            'chgYTD': ytd_change(d, v)
        })
    result.sort(key=lambda x: x.get('chg1M') or 0, reverse=True)
    return result

def build_commodities():
    """Fetch commodity performance data."""
    commodities = {
        'GC=F': 'Gold', 'SI=F': 'Silver', 'CL=F': 'Crude Oil',
        'NG=F': 'Natural Gas', 'HG=F': 'Copper',
        'ZC=F': 'Corn', 'ZS=F': 'Soybeans'
    }
    table = []
    chart_data = {}
    for sym, name in commodities.items():
        daily = fetch_yf_daily(sym, 1)
        weekly = fetch_yf_weekly(sym, 2)
        if not daily['dates'] or len(daily['values']) < 5:
            continue
        d, v = daily['dates'], daily['values']
        table.append({
            'symbol': sym.replace('=F', ''), 'name': name, 'price': v[-1],
            'chg1W': pct_change(v, 5),
            'chg1M': pct_change(v, 21),
            'chg3M': pct_change(v, 63),
            'chgYTD': ytd_change(d, v)
        })
        chart_data[sym.replace('=F', '')] = weekly
    table.sort(key=lambda x: x.get('chg1M') or 0, reverse=True)
    return {'table': table, 'charts': chart_data}

def build_value_growth():
    """Fetch Value vs Growth ratio (IWD/IWF)."""
    iwd = fetch_yf_weekly('IWD', 2)
    iwf = fetch_yf_weekly('IWF', 2)
    if not iwd['dates'] or not iwf['dates']:
        return {'dates': [], 'ratio': [], 'iwd': iwd, 'iwf': iwf}
    # Align on common dates
    iwf_map = {d: v for d, v in zip(iwf['dates'], iwf['values'])}
    dates, ratio = [], []
    for i, d in enumerate(iwd['dates']):
        if d in iwf_map and iwf_map[d] and iwf_map[d] != 0:
            dates.append(d)
            ratio.append(round(iwd['values'][i] / iwf_map[d], 4))
    return {'dates': dates, 'ratio': ratio, 'iwd': iwd, 'iwf': iwf}

def normalize_cluster(assets_data):
    """Normalize multiple daily series to % change from first data point.
    Uses union of all dates; fills gaps with nearest available value."""
    all_sets = [set(d['dates']) for d in assets_data.values() if d['dates']]
    if not all_sets:
        return {'dates': [], 'series': {}}
    all_dates = sorted(set.union(*all_sets))
    if len(all_dates) < 5:
        return {'dates': [], 'series': {}}
    series = {}
    for name, data in assets_data.items():
        if not data['dates']:
            continue
        lookup = {d: v for d, v in zip(data['dates'], data['values'])}
        # Fill gaps with last known value (forward fill)
        vals = []
        last_known = None
        for d in all_dates:
            v = lookup.get(d)
            if v is not None:
                last_known = v
            vals.append(last_known)
        # % change from first valid value
        base = None
        for v in vals:
            if v and v > 0:
                base = v
                break
        if base:
            series[name] = [round((v - base) / base * 100, 2) if v else None for v in vals]
        else:
            series[name] = [None] * len(all_dates)
        print('[COINT] ' + name + ': ' + str(len(data['dates'])) + ' raw -> ' + str(len(vals)) + ' aligned')
    return {'dates': all_dates, 'series': series}

def build_cointegration():
    """Build 3 cointegration clusters with hourly + daily data."""
    clusters = {
        'metals': {'Gold': 'GC=F', 'Silver': 'SI=F', 'Platinum': 'PL=F', 'Copper': 'HG=F', 'Palladium': 'PA=F'},
        'equities': {'S&P 500': '^GSPC', 'Nasdaq 100': '^NDX', 'Russell 2000': '^RUT', 'Dow Jones': '^DJI'},
        'crypto': {'Bitcoin': 'BTC-USD', 'Ethereum': 'ETH-USD', 'Solana': 'SOL-USD', 'XRP': 'XRP-USD', 'BNB': 'BNB-USD'}
    }
    result = {}
    for cluster_name, syms in clusters.items():
        # Daily (1 year)
        daily_data = {}
        for name, sym in syms.items():
            daily_data[name] = fetch_yf_daily(sym, 1)
        # Intraday (30 days) — 30min for equities, hourly for rest
        intra_data = {}
        fetch_fn = fetch_yf_15min if cluster_name == 'equities' else fetch_yf_hourly
        for name, sym in syms.items():
            intra_data[name] = fetch_fn(sym, 30)
        result[cluster_name] = {
            'daily': normalize_cluster(daily_data),
            'hourly': normalize_cluster(intra_data)
        }
    return result

@app.route('/api/crossmarket')
def api_crossmarket():
    try:
        ck = 'crossmarket_main'
        now = datetime.datetime.now()
        if ck in _cache and (now - _cache_time[ck]).total_seconds() < 3600:
            return jsonify(_cache[ck])

        status_prices = build_status_prices()
        corr = build_correlation_matrix()
        currency = build_currency_strength()
        sectors = build_sector_rotation()
        commodities = build_commodities()
        vg = build_value_growth()
        coint = build_cointegration()

        result = {
            'status': 'ok',
            'lastUpdate': datetime.date.today().isoformat(),
            'statusPrices': status_prices,
            'correlation': corr,
            'currencyStrength': currency,
            'sectorRotation': sectors,
            'commodities': commodities,
            'valueGrowth': vg,
            'cointegration': coint
        }
        _cache[ck] = result
        _cache_time[ck] = now
        return jsonify(result)
    except Exception as e:
        print('[CROSSMARKET] ' + str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/crossmarket/refresh')
def api_crossmarket_refresh():
    cm_keys = [k for k in _cache if k.startswith('crossmarket_') or k.startswith('yf_')]
    for k in cm_keys:
        _cache.pop(k, None)
        _cache_time.pop(k, None)
    print('[CROSSMARKET] Cache cleared (' + str(len(cm_keys)) + ' keys), refetching...')
    return api_crossmarket()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
