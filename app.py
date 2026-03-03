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
    return jsonify({'categories': cats, 'regime': regime, 'catOrder': FLOW_CATS})

@app.route('/api/cot/refresh')
def api_refresh():
    _cache.clear(); _cache_time.clear()
    data = load_all_data()
    return jsonify({'status': 'refreshed', 'markets': sorted(data.keys()), 'count': len(data)})

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
