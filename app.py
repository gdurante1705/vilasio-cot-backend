"""
Vilasio COT Backend v1.3
Fetches CFTC COT data from both Financials and Disaggregated reports
"""

import os
import io
import csv
import zipfile
import datetime
import urllib.request
from flask import Flask, jsonify, request

app = Flask(__name__)

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# Financial futures (FX, Equities) 
CFTC_FIN = "https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"
# Disaggregated (Commodities: Gold, Oil, etc.)
CFTC_LEG = "https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"

# Financial markets
FIN_MAP = [
    ("E-MINI S&P 500 -",    "ES"),
    ("NASDAQ MINI -",        "NQ"),
    ("EURO FX -",            "6E"),
    ("BRITISH POUND -",      "6B"),
    ("JAPANESE YEN -",       "6J"),
    ("CANADIAN DOLLAR -",    "6C"),
    ("UST BOND -",           "ZB"),
    ("UST 10Y NOTE -",       "ZN"),
]

# Disaggregated/commodity markets
LEG_MAP = [
    ("GOLD -",               "GC"),
    ("SILVER -",             "SI"),
    ("CRUDE OIL, LIGHT SWEET", "CL"),
    ("NATURAL GAS (NYMEX)",  "NG"),
    ("CORN -",               "ZC"),
    ("WHEAT-SRW",            "ZW"),
]

def match_market(name, market_map):
    name = name.upper()
    for pattern, symbol in market_map:
        if pattern.upper() in name:
            return symbol
    return None

def safe_int(val):
    try:
        return int(str(val).strip())
    except:
        return 0

_cache = {}
_cache_time = {}
CACHE_TTL = 3600 * 6

def fetch_zip_csv(url):
    """Download zip and return CSV content"""
    req = urllib.request.Request(url, headers={'User-Agent': 'Vilasio/1.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        zip_data = resp.read()
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        csv_name = [n for n in zf.namelist() if n.endswith('.txt') or n.endswith('.csv')][0]
        with zf.open(csv_name) as f:
            return f.read().decode('utf-8', errors='replace')

def parse_rows(content, market_map):
    """Parse CSV rows into symbol-keyed dict"""
    results = {}
    reader = csv.DictReader(io.StringIO(content))
    
    for row in reader:
        market_name = row.get('Market_and_Exchange_Names', '').strip()
        symbol = match_market(market_name, market_map)
        if not symbol:
            continue
        
        try:
            date_str = row.get('Report_Date_as_YYYY-MM-DD', '') or row.get('As_of_Date_In_Form_YYMMDD', '')
            if len(date_str.strip()) == 6 and '-' not in date_str:
                d = datetime.datetime.strptime(date_str.strip(), '%y%m%d')
            else:
                d = datetime.datetime.strptime(date_str.strip()[:10], '%Y-%m-%d')
            date_iso = d.strftime('%Y-%m-%d')

            # For financial report: Lev Money = hedge funds, Asset Mgr = institutional
            # For disaggregated: Managed Money = hedge funds, use same fields
            ls_long  = safe_int(row.get('Lev_Money_Positions_Long_All',  0) or row.get('M_Money_Positions_Long_All',  0))
            ls_short = safe_int(row.get('Lev_Money_Positions_Short_All', 0) or row.get('M_Money_Positions_Short_All', 0))
            cm_long  = safe_int(row.get('Asset_Mgr_Positions_Long_All',  0) or row.get('Prod_Merc_Positions_Long_All', 0))
            cm_short = safe_int(row.get('Asset_Mgr_Positions_Short_All', 0) or row.get('Prod_Merc_Positions_Short_All',0))
            ss_long  = safe_int(row.get('NonRept_Positions_Long_All',  0))
            ss_short = safe_int(row.get('NonRept_Positions_Short_All', 0))
            oi       = safe_int(row.get('Open_Interest_All', 0))

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

    for sym in results:
        results[sym].sort(key=lambda x: x['date'])

    return results

def get_cot_data():
    now = datetime.datetime.now()
    cache_key = 'cot_all'

    if cache_key in _cache:
        age = (now - _cache_time[cache_key]).total_seconds()
        if age < CACHE_TTL:
            return _cache[cache_key]

    year = now.year
    data = {}

    for yr in [year - 1, year]:
        # Financial futures
        try:
            content = fetch_zip_csv(CFTC_FIN.format(year=yr))
            yr_data = parse_rows(content, FIN_MAP)
            for sym, entries in yr_data.items():
                data.setdefault(sym, []).extend(entries)
            print(f"[COT] FIN {yr}: {list(yr_data.keys())}")
        except Exception as e:
            print(f"[COT] FIN {yr} error: {e}")

        # Disaggregated commodities
        try:
            content = fetch_zip_csv(CFTC_LEG.format(year=yr))
            yr_data = parse_rows(content, LEG_MAP)
            for sym, entries in yr_data.items():
                data.setdefault(sym, []).extend(entries)
            print(f"[COT] LEG {yr}: {list(yr_data.keys())}")
        except Exception as e:
            print(f"[COT] LEG {yr} error: {e}")

    # Deduplicate and sort
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
    print(f"[COT] Cache ready — markets: {list(data.keys())}")
    return data

@app.route('/')
def index():
    return jsonify({'service': 'Vilasio COT API', 'version': '1.3'})

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': '1.3', 'time': datetime.datetime.utcnow().isoformat()})

@app.route('/cot/all')
def cot_all():
    weeks = int(request.args.get('weeks', 52))
    data = get_cot_data()
    result = {}
    for sym, entries in data.items():
        result[sym] = entries[-weeks:] if len(entries) > weeks else entries
    return jsonify(result)

@app.route('/cot/<symbol>')
def cot_symbol(symbol):
    symbol = symbol.upper()
    weeks = int(request.args.get('weeks', 52))
    data = get_cot_data()
    if symbol not in data:
        return jsonify({'error': f'Symbol {symbol} not found', 'available': list(data.keys())}), 404
    entries = data[symbol]
    return jsonify({'symbol': symbol, 'weeks': len(entries), 'data': entries[-weeks:]})

@app.route('/debug/markets')
def debug_markets():
    year = datetime.datetime.now().year
    all_markets = {}
    for label, url in [('fin', CFTC_FIN), ('leg', CFTC_LEG)]:
        try:
            content = fetch_zip_csv(url.format(year=year))
            reader = csv.DictReader(io.StringIO(content))
            markets = sorted(set(row.get('Market_and_Exchange_Names','').strip() for row in reader))
            all_markets[label] = markets
        except Exception as e:
            all_markets[label] = str(e)
    return jsonify(all_markets)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
