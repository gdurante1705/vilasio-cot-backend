"""
Vilasio COT Backend v1.2
Fetches CFTC Commitment of Traders data and serves it as JSON API
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

CFTC_BASE = "https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"

MARKET_MAP = [
    ("E-MINI S&P 500",         "ES"),
    ("E-MINI NASDAQ-100",       "NQ"),
    ("GOLD -",                  "GC"),
    ("CRUDE OIL, LIGHT SWEET",  "CL"),
    ("SILVER -",                "SI"),
    ("U.S. TREASURY BONDS",     "ZB"),
    ("EURO FX",                 "6E"),
    ("BRITISH POUND",           "6B"),
    ("JAPANESE YEN",            "6J"),
    ("NATURAL GAS (NYMEX)",     "NG"),
    ("CORN -",                  "ZC"),
    ("WHEAT-SRW",               "ZW"),
    ("CANADIAN DOLLAR",         "6C"),
]

def match_market(name):
    name = name.upper()
    for pattern, symbol in MARKET_MAP:
        if pattern in name:
            return symbol
    return None

def safe_int(val):
    """Parse int from CFTC value which may have leading spaces"""
    try:
        return int(str(val).strip())
    except:
        return 0

_cache = {}
_cache_time = {}
CACHE_TTL = 3600 * 6

def fetch_cot_year(year):
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
            csv_name = [n for n in zf.namelist() if n.endswith('.txt') or n.endswith('.csv')][0]
            with zf.open(csv_name) as f:
                content = f.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f"[COT] Zip error: {e}")
        return {}

    results = {}
    reader = csv.DictReader(io.StringIO(content))

    for row in reader:
        market_name = row.get('Market_and_Exchange_Names', '').strip()
        symbol = match_market(market_name)
        if not symbol:
            continue

        try:
            date_str = row.get('Report_Date_as_YYYY-MM-DD', '') or row.get('As_of_Date_In_Form_YYMMDD', '')
            if len(date_str) == 6 and '-' not in date_str:
                d = datetime.datetime.strptime(date_str, '%y%m%d')
            else:
                d = datetime.datetime.strptime(date_str[:10], '%Y-%m-%d')
            date_iso = d.strftime('%Y-%m-%d')

            # Leveraged Money = Hedge Funds / Big Players
            ls_long  = safe_int(row.get('Lev_Money_Positions_Long_All', 0))
            ls_short = safe_int(row.get('Lev_Money_Positions_Short_All', 0))

            # Asset Manager = Smart Money / Institutionals
            cm_long  = safe_int(row.get('Asset_Mgr_Positions_Long_All', 0))
            cm_short = safe_int(row.get('Asset_Mgr_Positions_Short_All', 0))

            # Non-Reportable = Small Specs / Dumb Money
            ss_long  = safe_int(row.get('NonRept_Positions_Long_All', 0))
            ss_short = safe_int(row.get('NonRept_Positions_Short_All', 0))

            oi = safe_int(row.get('Open_Interest_All', 0))

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

        except Exception as ex:
            continue

    for sym in results:
        results[sym].sort(key=lambda x: x['date'])

    print(f"[COT] Year {year}: found {list(results.keys())}")
    return results

def get_cot_data():
    now = datetime.datetime.now()
    cache_key = 'cot_all'

    if cache_key in _cache:
        age = (now - _cache_time[cache_key]).total_seconds()
        if age < CACHE_TTL:
            return _cache[cache_key]

    current_year = now.year
    data = {}

    for year in [current_year - 1, current_year]:
        year_data = fetch_cot_year(year)
        for sym, entries in year_data.items():
            if sym not in data:
                data[sym] = []
            data[sym].extend(entries)

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
    print(f"[COT] Cache updated — markets: {list(data.keys())}")
    return data

@app.route('/')
def index():
    return jsonify({'service': 'Vilasio COT API', 'version': '1.2'})

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': '1.2', 'time': datetime.datetime.utcnow().isoformat()})

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
        return jsonify({'error': f'Symbol {symbol} not found'}), 404
    entries = data[symbol]
    entries = entries[-weeks:] if len(entries) > weeks else entries
    return jsonify({'symbol': symbol, 'weeks': len(entries), 'data': entries})

@app.route('/debug/columns')
def debug_columns():
    year = datetime.datetime.now().year
    url = CFTC_BASE.format(year=year)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Vilasio/1.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            zip_data = resp.read()
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            csv_name = [n for n in zf.namelist() if n.endswith('.txt') or n.endswith('.csv')][0]
            with zf.open(csv_name) as f:
                content = f.read().decode('utf-8', errors='replace')
        reader = csv.DictReader(io.StringIO(content))
        row = next(reader)
        return jsonify({'columns': list(row.keys()), 'sample_market': row.get('Market_and_Exchange_Names','')})
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
