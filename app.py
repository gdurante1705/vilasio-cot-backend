"""
Vilasio COT Backend v3.0
Uses CFTC Socrata JSON API — no CSV header issues.

Data sources:
  - Legacy Futures Only API (6dca-aqww): NonComm/Comm for ALL markets
    This matches Tradingster's data exactly.

API docs: https://dev.socrata.com/foundry/publicreporting.cftc.gov/6dca-aqww
"""

import os
import json
import datetime
import urllib.request
import urllib.parse
from flask import Flask, jsonify, request

app = Flask(__name__)


@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


# ─── CFTC Socrata API ──────────────────────────────────
# Legacy Futures Only — has NonComm/Comm for ALL markets (matches Tradingster)
LEGACY_API = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"

# Page size — Socrata default limit is 1000, max is 50000
PAGE_SIZE = 50000


# ─── MARKET CONFIG ──────────────────────────────────────
# contract_market_name is the exact name used in the CFTC API
MARKETS = {
    "ES": {"name": "E-Mini S&P 500",    "exchange": "Chicago Mercantile Exchange", "cat": "Equity",
           "cftc_search": "S&P 500"},
    "NQ": {"name": "E-Mini Nasdaq 100", "exchange": "Chicago Mercantile Exchange", "cat": "Equity",
           "cftc_search": "NASDAQ-100"},
    "GC": {"name": "Gold",              "exchange": "Commodity Exchange Inc.",      "cat": "Metals",
           "cftc_search": "GOLD"},
    "CL": {"name": "Crude Oil WTI",     "exchange": "New York Mercantile Exchange","cat": "Energy",
           "cftc_search": "CRUDE OIL, LIGHT SWEET"},
    "SI": {"name": "Silver",            "exchange": "Commodity Exchange Inc.",      "cat": "Metals",
           "cftc_search": "SILVER"},
    "ZB": {"name": "30-Year T-Bond",    "exchange": "Chicago Board of Trade",      "cat": "Rates",
           "cftc_search": "U.S. TREASURY BONDS"},
    "6E": {"name": "Euro FX",           "exchange": "Chicago Mercantile Exchange", "cat": "FX",
           "cftc_search": "EURO FX"},
    "6B": {"name": "British Pound",     "exchange": "Chicago Mercantile Exchange", "cat": "FX",
           "cftc_search": "BRITISH POUND"},
    "6J": {"name": "Japanese Yen",      "exchange": "Chicago Mercantile Exchange", "cat": "FX",
           "cftc_search": "JAPANESE YEN"},
    "NG": {"name": "Natural Gas",       "exchange": "New York Mercantile Exchange","cat": "Energy",
           "cftc_search": "NATURAL GAS"},
    "ZC": {"name": "Corn",              "exchange": "Chicago Board of Trade",      "cat": "Agri",
           "cftc_search": "CORN"},
    "ZW": {"name": "Wheat",             "exchange": "Chicago Board of Trade",      "cat": "Agri",
           "cftc_search": "WHEAT-SRW"},
}


def safe_int(val):
    try:
        return int(float(str(val).strip()))
    except Exception:
        return 0


# ─── CACHE ──────────────────────────────────────────────
_cache = {}
_cache_time = {}
CACHE_TTL = 3600 * 6


def fetch_json(url, params=None):
    """Fetch JSON from CFTC Socrata API."""
    if params:
        url = url + '?' + urllib.parse.urlencode(params)
    print(f"[COT] Fetching: {url[:120]}...")
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Vilasio/3.0',
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode('utf-8'))


def fetch_market_data(symbol):
    """
    Fetch Legacy COT data for a single market from CFTC Socrata API.
    Returns list of entries sorted by date.
    """
    cfg = MARKETS[symbol]
    search_term = cfg["cftc_search"]

    # Calculate date range: 2.5 years back for Z-Score
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=365 * 3)

    # SoQL query
    params = {
        '$where': f"market_and_exchange_names like '%{search_term}%' "
                  f"AND report_date_as_yyyy_mm_dd >= '{start_date.isoformat()}'",
        '$order': 'report_date_as_yyyy_mm_dd ASC',
        '$limit': str(PAGE_SIZE),
    }

    rows = fetch_json(LEGACY_API, params)
    print(f"[COT] {symbol} ({search_term}): got {len(rows)} rows from API")

    if not rows:
        return []

    # If multiple contract names match, pick the one with highest OI (consolidated)
    # Group by date, keep the row with highest open_interest_all per date
    by_date = {}
    for row in rows:
        date_str = row.get('report_date_as_yyyy_mm_dd', '')
        if not date_str:
            continue
        date_iso = date_str[:10]  # Already YYYY-MM-DD format
        oi = safe_int(row.get('open_interest_all', 0))

        if date_iso not in by_date or oi > by_date[date_iso]['_oi']:
            by_date[date_iso] = {
                '_oi': oi,
                '_row': row,
                '_market_name': row.get('market_and_exchange_names', ''),
            }

    entries = []
    for date_iso in sorted(by_date.keys()):
        row = by_date[date_iso]['_row']
        bp_long  = safe_int(row.get('noncomm_positions_long_all', 0))
        bp_short = safe_int(row.get('noncomm_positions_short_all', 0))
        dl_long  = safe_int(row.get('comm_positions_long_all', 0))
        dl_short = safe_int(row.get('comm_positions_short_all', 0))
        oi       = safe_int(row.get('open_interest_all', 0))

        if oi == 0:
            continue

        entries.append({
            'date':    date_iso,
            'bpLong':  bp_long,
            'bpShort': bp_short,
            'bpNet':   bp_long - bp_short,
            'dlLong':  dl_long,
            'dlShort': dl_short,
            'dlNet':   dl_long - dl_short,
            'oi':      oi,
        })

    if entries:
        mkt_name = by_date[entries[-1]['date']]['_market_name']
        last = entries[-1]
        print(f"  {symbol}: matched '{mkt_name}', {len(entries)} weeks, "
              f"{entries[0]['date']} -> {last['date']}, "
              f"bpNet={last['bpNet']:+,}, dlNet={last['dlNet']:+,}, oi={last['oi']:,}")

    return entries


def load_all_data():
    """Load data for all markets."""
    now = datetime.datetime.now()
    cache_key = 'cot_v3'
    if cache_key in _cache:
        age = (now - _cache_time[cache_key]).total_seconds()
        if age < CACHE_TTL:
            return _cache[cache_key]

    print(f"[COT] ═══ Loading all markets from CFTC Legacy API... ═══")
    data = {}
    for symbol in sorted(MARKETS.keys()):
        try:
            entries = fetch_market_data(symbol)
            if entries:
                data[symbol] = entries
        except Exception as e:
            print(f"[COT] {symbol} error: {e}")

    _cache[cache_key] = data
    _cache_time[cache_key] = now
    print(f"[COT] ═══ Cache ready — {len(data)} markets: {sorted(data.keys())} ═══")
    return data


# ─── ENDPOINTS ──────────────────────────────────────────

@app.route('/')
def index():
    return jsonify({'service': 'Vilasio COT API', 'version': '3.0', 'source': 'CFTC Legacy Futures Only (Socrata API)'})

@app.route('/health')
def health():
    data = load_all_data()
    return jsonify({
        'status': 'ok', 'version': '3.0',
        'markets': sorted(data.keys()) if data else [],
        'totalRows': sum(len(v) for v in data.values()) if data else 0,
        'time': datetime.datetime.utcnow().isoformat(),
    })

@app.route('/api/cot')
def api_cot():
    market = request.args.get('market', '').upper()
    weeks = max(4, min(int(request.args.get('weeks', 52)), 260))
    if market not in MARKETS:
        return jsonify({'error': f'Unknown market: {market}', 'available': sorted(MARKETS.keys())}), 400
    data = load_all_data()
    if market not in data or not data[market]:
        return jsonify({'error': f'No data for {market}'}), 404
    entries = data[market]
    entries = entries[-(weeks + 1):] if len(entries) > weeks + 1 else entries
    cfg = MARKETS[market]
    return jsonify({
        'market': market, 'name': cfg['name'], 'exchange': cfg['exchange'], 'cat': cfg['cat'],
        'reportDate': entries[-1]['date'],
        'labels':  [e['date'] for e in entries],
        'bpLong':  [e['bpLong'] for e in entries],
        'bpShort': [e['bpShort'] for e in entries],
        'bpNet':   [e['bpNet'] for e in entries],
        'dlLong':  [e['dlLong'] for e in entries],
        'dlShort': [e['dlShort'] for e in entries],
        'dlNet':   [e['dlNet'] for e in entries],
        'oi':      [e['oi'] for e in entries],
    })

@app.route('/api/cot/summary')
def api_cot_summary():
    data = load_all_data()
    results = []
    for sym in sorted(MARKETS.keys()):
        if sym not in data or len(data[sym]) < 2:
            continue
        last, prev = data[sym][-1], data[sym][-2]
        results.append({
            'market': sym, 'name': MARKETS[sym]['name'], 'cat': MARKETS[sym]['cat'],
            'bpNet': last['bpNet'], 'bpNetChg': last['bpNet'] - prev['bpNet'],
            'dlNet': last['dlNet'], 'oi': last['oi'], 'reportDate': last['date'],
        })
    return jsonify({
        'markets': results,
        'lastFetch': _cache_time.get('cot_v3', datetime.datetime.now()).isoformat(),
    })

@app.route('/api/cot/refresh')
def api_refresh():
    _cache.clear()
    _cache_time.clear()
    data = load_all_data()
    return jsonify({'status': 'refreshed', 'markets': sorted(data.keys()),
                    'rows': {sym: len(e) for sym, e in data.items()}})

@app.route('/debug/raw/<symbol>')
def debug_raw(symbol):
    """Show raw CFTC API response for a market (latest 2 rows)."""
    symbol = symbol.upper()
    if symbol not in MARKETS:
        return jsonify({'error': 'Unknown', 'available': sorted(MARKETS.keys())}), 400
    cfg = MARKETS[symbol]
    params = {
        '$where': f"market_and_exchange_names like '%{cfg['cftc_search']}%'",
        '$order': 'report_date_as_yyyy_mm_dd DESC',
        '$limit': '2',
    }
    rows = fetch_json(LEGACY_API, params)
    return jsonify({'symbol': symbol, 'search': cfg['cftc_search'], 'rows': rows})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
