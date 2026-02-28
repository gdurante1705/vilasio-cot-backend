"""
Vilasio COT Backend
Fetches CFTC Commitment of Traders data and serves it as JSON API
Deploy on Render (free tier) — https://render.com
"""

import os
import io
import csv
import json
import zipfile
import datetime
import urllib.request
from flask import Flask, jsonify, request

app = Flask(__name__)

# ── CORS (manual, no flask-cors needed) ──────────────────────────────────────
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# ── CFTC CONFIG ───────────────────────────────────────────────────────────────
# Legacy COT report (Futures Only) - annual zip files
CFTC_BASE = "https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"

# Market name mapping — CFTC name → our symbol
MARKET_MAP = {
    "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE":           "ES",
    "E-MINI NASDAQ-100 - CHICAGO MERCANTILE EXCHANGE":        "NQ",
    "GOLD - COMMODITY EXCHANGE INC.":                         "GC",
    "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE":  "CL",
    "SILVER - COMMODITY EXCHANGE INC.":                       "SI",
    "U.S. TREASURY BONDS - CHICAGO BOARD OF TRADE":           "ZB",
    "EURO FX - CHICAGO MERCANTILE EXCHANGE":                  "6E",
    "BRITISH POUND STERLING - CHICAGO MERCANTILE EXCHANGE":   "6B",
    "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE":             "6J",
    "NATURAL GAS (NYMEX) - NEW YORK MERCANTILE EXCHANGE":     "NG",
    "CORN - CHICAGO BOARD OF TRADE":                          "ZC",
    "WHEAT-SRW - CHICAGO BOARD OF TRADE":                     "ZW",
}

# Cache
_cache = {}
_cache_time = {}
CACHE_TTL = 3600 * 6  # 6 hours

def fetch_cot_year(year):
    """Fetch and parse CFTC COT data for a given year"""
    url = CFTC_BASE.format(year=year)
    print(f"[COT] Fetching {url}")
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Vilasio/1.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            zip_data = resp.read()
    except Exception as e:
        print(f"[COT] Fetch error: {e}")
        return {}

    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            # Find the CSV file inside the zip
            csv_name = [n for n in zf.namelist() if n.endswith('.txt') or n.endswith('.csv')][0]
            with zf.open(csv_name) as f:
                content = f.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f"[COT] Zip error: {e}")
        return {}

    results = {}
    reader = csv.DictReader(io.StringIO(content))
    
    for row in reader:
        market_name = row.get('Market_and_Exchange_Names', '').strip().upper()
        symbol = MARKET_MAP.get(market_name)
        if not symbol:
            continue
        
        try:
            date_str = row.get('Report_Date_as_YYYY-MM-DD', '') or row.get('As_of_Date_In_Form_YYMMDD', '')
            
            # Parse date
            if len(date_str) == 8 and '-' not in date_str:
                d = datetime.datetime.strptime(date_str, '%y%m%d')
            else:
                d = datetime.datetime.strptime(date_str[:10], '%Y-%m-%d')
            
            date_iso = d.strftime('%Y-%m-%d')
            
            ls_long  = int(row.get('Lev_Money_Positions_Long_All', 0) or 0)
            ls_short = int(row.get('Lev_Money_Positions_Short_All', 0) or 0)
            cm_long  = int(row.get('M_Money_Positions_Long_All', 0) or 0)
            cm_short = int(row.get('M_Money_Positions_Short_All', 0) or 0)
            ss_long  = int(row.get('NonRept_Positions_Long_All', 0) or 0)
            ss_short = int(row.get('NonRept_Positions_Short_All', 0) or 0)
            oi       = int(row.get('Open_Interest_All', 0) or 0)
            
            entry = {
                'date':   date_iso,
                'ls_net': ls_long - ls_short,
                'cm_net': cm_long - cm_short,
                'ss_net': ss_long - ss_short,
                'oi':     oi,
            }
            
            if symbol not in results:
                results[symbol] = []
            results[symbol].append(entry)
            
        except Exception:
            continue
    
    # Sort by date
    for sym in results:
        results[sym].sort(key=lambda x: x['date'])
    
    return results

def get_cot_data():
    """Get COT data with cache — fetch current + previous year"""
    now = datetime.datetime.now()
    cache_key = 'cot_all'
    
    # Check cache
    if cache_key in _cache:
        age = (now - _cache_time[cache_key]).total_seconds()
        if age < CACHE_TTL:
            return _cache[cache_key]
    
    # Fetch current year and previous year
    current_year = now.year
    data = {}
    
    for year in [current_year - 1, current_year]:
        year_data = fetch_cot_year(year)
        for sym, entries in year_data.items():
            if sym not in data:
                data[sym] = []
            data[sym].extend(entries)
    
    # Sort and deduplicate
    for sym in data:
        seen = set()
        unique = []
        for e in sorted(data[sym], key=lambda x: x['date']):
            if e['date'] not in seen:
                seen.add(e['date'])
                unique.append(e)
        data[sym] = unique
    
    _cache[cache_key] = data
    _cache_time[cache_key] = now
    print(f"[COT] Cache updated — {sum(len(v) for v in data.values())} entries across {len(data)} markets")
    return data

# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return jsonify({
        'service': 'Vilasio COT API',
        'version': '1.0',
        'endpoints': ['/cot/<symbol>', '/cot/all', '/health']
    })

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.datetime.utcnow().isoformat()})

@app.route('/cot/all')
def cot_all():
    """Return all markets — last N weeks"""
    weeks = int(request.args.get('weeks', 52))
    data = get_cot_data()
    
    result = {}
    for sym, entries in data.items():
        result[sym] = entries[-weeks:] if len(entries) > weeks else entries
    
    return jsonify(result)

@app.route('/cot/<symbol>')
def cot_symbol(symbol):
    """Return COT data for a specific symbol"""
    symbol = symbol.upper()
    weeks = int(request.args.get('weeks', 52))
    data = get_cot_data()
    
    if symbol not in data:
        return jsonify({'error': f'Symbol {symbol} not found'}), 404
    
    entries = data[symbol]
    entries = entries[-weeks:] if len(entries) > weeks else entries
    
    return jsonify({
        'symbol': symbol,
        'weeks': len(entries),
        'data': entries
    })

# ── ENTRY POINT ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
