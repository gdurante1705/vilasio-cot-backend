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
    _cache.clear(); _cache_time.clear()
    data = load_all_data()
    return jsonify({'status': 'refreshed', 'markets': sorted(data.keys()), 'count': len(data)})

# ─── SENTIMENT ENDPOINTS ──────────────────────────────────────────────────────

def fetch_pcr():
    """Fetch CBOE equity put/call ratio from public CSV. Cache 6h.
    CSV format (after header junk):
      DATE,CALL,PUT,TOTAL,P/C Ratio
    We skip all lines until we find a header with 'P/C' then parse data rows.
    """
    ck = 'pcr_data'
    now = datetime.datetime.now()
    if ck in _cache and (now - _cache_time[ck]).total_seconds() < CACHE_TTL:
        return _cache[ck]
    url = 'https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypc.csv'
    req = urllib.request.Request(url, headers={'User-Agent': 'Vilasio/3.7'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode('utf-8')
    rows = []
    header_found = False
    for line in raw.splitlines():
        line = line.strip()
        if not line: continue
        # Detect the data header row
        if not header_found:
            if 'DATE' in line.upper() and ('P/C' in line.upper() or 'PUT' in line.upper()):
                header_found = True
            continue
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 4: continue
        date_str = parts[0]
        pc_str = parts[4] if len(parts) >= 5 else parts[3]
        try:
            # Accept MM/DD/YYYY or YYYY-MM-DD
            for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
                try:
                    datetime.datetime.strptime(date_str, fmt); break
                except: pass
            else:
                continue
            val = float(pc_str)
            if val <= 0 or val > 10: continue  # sanity check — PCR is always 0.3–2.0
            rows.append({'date': date_str, 'pcr': val})
        except: continue
    rows = rows[-30:]  # last 30 trading days
    last_pcr = rows[-1]['pcr'] if rows else None
    avg10 = round(sum(r['pcr'] for r in rows[-10:]) / min(10, len(rows)), 3) if rows else None
    result = {'latest': last_pcr, 'avg10': avg10, 'history': rows}
    _cache[ck] = result; _cache_time[ck] = now
    return result

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
        # Fed cuts — more cuts = bullish (dovish Fed supports markets)
        ('how-many-fed-rate-cuts-in-2026',    ['2 ', '3 ', '4 ', '5 ', '6 ', '7 ', '8 ', '9 ', '10', '11', '12'], ['0 ', 'no ']),
        ('how-many-fed-rate-cuts-in-2025',    ['2 ', '3 ', '4 ', '5 ', '6 '], ['0 ', 'no ']),
        ('fed-rate-cut-by-629',               ['yes', 'cut'], ['no ', 'pause']),
        # Recession — recession = bearish
        ('us-recession-in-2026',              [], ['yes', 'recession']),
        ('will-the-us-enter-a-recession-in-2025', [], ['yes', 'recession']),
        ('will-there-be-a-us-recession-in-2026',  [], ['yes', 'recession']),
        ('us-recession-2025',                 [], ['yes']),
        # S&P 500 — higher target = bullish
        ('sp-500-end-of-year-2025',           ['above', 'higher', '6000', '6500', '7000'], ['below', 'lower', '4000', '4500', '5000']),
        ('sp-500-in-2026',                    ['above', 'higher', '6000', '6500', '7000'], ['below', 'lower', '4000', '4500', '5000']),
        ('will-the-sp-500-go-up-in-q1-2026',  ['yes', 'up'], ['no ', 'down']),
        # CPI — lower inflation = bullish
        ('us-cpi-inflation-in-2026',          [], ['above', 'higher', 'exceed']),
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
                    q = m['question'].lower()
                    is_bullish = any(kw in q for kw in bullish_kw)
                    is_bearish = any(kw in q for kw in bearish_kw)
                    if is_bullish:
                        event_score = m['yesProb'] * 100
                    elif is_bearish:
                        event_score = (1 - m['yesProb']) * 100
                    else:
                        event_score = 50  # neutral if can't classify
                    display_prob = round(m['yesProb'] * 100, 1)
                    display_q = m['question']
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

    # Volume-weighted average score
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

@app.route('/api/sentiment/pcr')
def api_pcr():
    try:
        data = fetch_pcr()
        return jsonify({'status': 'ok', **data})
    except Exception as e:
        print('[PCR] Error: ' + str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/sentiment/polymarket')
def api_polymarket():
    try:
        data = fetch_polymarket_sentiment()
        return jsonify({'status': 'ok', **data})
    except Exception as e:
        print('[POLYMARKET] Error: ' + str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/sentiment')
def api_sentiment():
    """Combined sentiment endpoint: PCR (50%) + Polymarket (50%) → gauge score 0-100."""
    try:
        pcr_data = fetch_pcr()
        poly_data = fetch_polymarket_sentiment()

        # PCR score: lower PCR = more bullish
        # Typical range: 0.4 (extreme bullish) to 1.2 (extreme bearish)
        # Map to 0-100 score: PCR 0.4 → 100, PCR 1.2 → 0
        pcr_val = pcr_data.get('avg10')
        pcr_score = None
        if pcr_val is not None:
            pcr_score = round(max(0, min(100, (1.2 - pcr_val) / 0.8 * 100)), 1)

        # Polymarket score: avgProb already 0-100
        poly_score = poly_data.get('avgProb')

        # Composite: 50/50 average
        if pcr_score is not None and poly_score is not None:
            composite = round((pcr_score + poly_score) / 2, 1)
        elif pcr_score is not None:
            composite = pcr_score
        elif poly_score is not None:
            composite = poly_score
        else:
            composite = None

        # Label
        if composite is None: label = 'UNAVAILABLE'
        elif composite >= 70: label = 'EXTREME GREED'
        elif composite >= 55: label = 'GREED'
        elif composite >= 45: label = 'NEUTRAL'
        elif composite >= 30: label = 'FEAR'
        else: label = 'EXTREME FEAR'

        return jsonify({
            'status': 'ok',
            'composite': composite,
            'label': label,
            'components': {
                'pcr': {'score': pcr_score, 'latest': pcr_data.get('latest'), 'avg10': pcr_val},
                'polymarket': {'score': poly_score, 'markets': poly_data.get('markets', []), 'count': poly_data.get('count')}
            }
        })
    except Exception as e:
        print('[SENTIMENT] Error: ' + str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/markets')
def api_markets():
    result = []
    for sym in sorted(MARKETS.keys()):
        cfg = MARKETS[sym]
        result.append({'market': sym, 'name': cfg['name'], 'exchange': cfg['exchange'], 'cat': cfg['cat']})
    return jsonify({'markets': result, 'categories': FLOW_CATS, 'heatmap': HEATMAP_MARKETS})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
