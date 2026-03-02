"""
Vilasio COT Backend v2.0
CFTC Disaggregated Futures Only — all markets from one consistent source.
Serves data in the format expected by the new cot.html frontend.
"""

import os
import io
import csv
import zipfile
import datetime
import urllib.request
from flask import Flask, jsonify, request

app = Flask(__name__)


# ─── CORS ───────────────────────────────────────────────
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


# ─── CFTC URLs ──────────────────────────────────────────
# We use ONLY the Disaggregated Futures report for consistency.
# Current year (plain text, no zip):
CFTC_CURRENT = "https://www.cftc.gov/dea/newcot/f_disagg.txt"
# Historical (zip archive per year):
CFTC_HISTORY = "https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"


# ─── MARKET CONFIG ──────────────────────────────────────
# Maps our ticker to a match string found in the CFTC
# 'Market_and_Exchange_Names' column (case-insensitive).
MARKETS = {
    "ES": {"name": "E-Mini S&P 500",    "exchange": "Chicago Mercantile Exchange", "cat": "Equity",
           "match": "E-MINI S&P 500"},
    "NQ": {"name": "E-Mini Nasdaq 100", "exchange": "Chicago Mercantile Exchange", "cat": "Equity",
           "match": "NASDAQ-100 MINI"},
    "GC": {"name": "Gold",              "exchange": "Commodity Exchange Inc.",      "cat": "Metals",
           "match": "GOLD - COMMODITY EXCHANGE"},
    "CL": {"name": "Crude Oil WTI",     "exchange": "New York Mercantile Exchange","cat": "Energy",
           "match": "CRUDE OIL, LIGHT SWEET"},
    "SI": {"name": "Silver",            "exchange": "Commodity Exchange Inc.",      "cat": "Metals",
           "match": "SILVER - COMMODITY EXCHANGE"},
    "ZB": {"name": "30-Year T-Bond",    "exchange": "Chicago Board of Trade",      "cat": "Rates",
           "match": "U.S. TREASURY BONDS"},
    "6E": {"name": "Euro FX",           "exchange": "Chicago Mercantile Exchange", "cat": "FX",
           "match": "EURO FX"},
    "6B": {"name": "British Pound",     "exchange": "Chicago Mercantile Exchange", "cat": "FX",
           "match": "BRITISH POUND"},
    "6J": {"name": "Japanese Yen",      "exchange": "Chicago Mercantile Exchange", "cat": "FX",
           "match": "JAPANESE YEN"},
    "NG": {"name": "Natural Gas",       "exchange": "New York Mercantile Exchange","cat": "Energy",
           "match": "NATURAL GAS - NEW YORK MERCANTILE"},
    "ZC": {"name": "Corn",              "exchange": "Chicago Board of Trade",      "cat": "Agri",
           "match": "CORN - CHICAGO BOARD OF TRADE"},
    "ZW": {"name": "Wheat",             "exchange": "Chicago Board of Trade",      "cat": "Agri",
           "match": "WHEAT-SRW - CHICAGO BOARD OF TRADE"},
}


# ─── HELPERS ────────────────────────────────────────────
def safe_int(val):
    try:
        return int(str(val).strip().replace(',', ''))
    except Exception:
        return 0


def match_market(name):
    """Match a CFTC market name to our ticker symbol."""
    name_upper = name.upper()
    for symbol, cfg in MARKETS.items():
        if cfg["match"].upper() in name_upper:
            return symbol
    return None


# ─── CACHE ──────────────────────────────────────────────
_cache = {}
_cache_time = {}
CACHE_TTL = 3600 * 6  # 6 hours


# ─── DATA FETCHING ──────────────────────────────────────
def fetch_url(url, is_zip=True):
    """Download content from URL. If zip, extract the .txt file inside."""
    print(f"[COT] Fetching: {url}")
    req = urllib.request.Request(url, headers={'User-Agent': 'Vilasio/2.0'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()

    if is_zip:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            txt_name = [n for n in zf.namelist() if n.endswith('.txt') or n.endswith('.csv')][0]
            with zf.open(txt_name) as f:
                return f.read().decode('utf-8', errors='replace')
    else:
        return raw.decode('utf-8', errors='replace')


def parse_disagg_csv(content):
    """
    Parse disaggregated futures CSV content.
    Returns dict: {symbol: [list of weekly entries sorted by date]}

    Each entry:
    {
        date, bpLong, bpShort, bpNet,
        dlLong, dlShort, dlNet, oi
    }

    In the Disaggregated report:
    - NonComm = Non-Commercial (our "Big Players")
    - Comm    = Commercial (our "Dealers")
    """
    results = {}
    reader = csv.DictReader(io.StringIO(content))

    # Clean header names (CFTC sometimes has trailing spaces)
    if reader.fieldnames:
        reader.fieldnames = [f.strip() for f in reader.fieldnames]

    for row in reader:
        market_name = row.get('Market_and_Exchange_Names', '').strip()
        symbol = match_market(market_name)
        if not symbol:
            continue

        try:
            # Parse date — could be YYMMDD or YYYY-MM-DD depending on source
            date_str = (row.get('Report_Date_as_YYYY-MM-DD', '') or
                        row.get('As_of_Date_In_Form_YYMMDD', '')).strip()

            if not date_str:
                continue

            if '-' in date_str:
                d = datetime.datetime.strptime(date_str[:10], '%Y-%m-%d')
            elif len(date_str) == 6:
                d = datetime.datetime.strptime(date_str, '%y%m%d')
            else:
                continue

            date_iso = d.strftime('%Y-%m-%d')

            # Non-Commercial = Big Players
            bp_long  = safe_int(row.get('NonComm_Positions_Long_All', 0))
            bp_short = safe_int(row.get('NonComm_Positions_Short_All', 0))

            # Commercial = Dealers
            dl_long  = safe_int(row.get('Comm_Positions_Long_All', 0))
            dl_short = safe_int(row.get('Comm_Positions_Short_All', 0))

            # Open Interest
            oi = safe_int(row.get('Open_Interest_All', 0))

            entry = {
                'date':    date_iso,
                'bpLong':  bp_long,
                'bpShort': bp_short,
                'bpNet':   bp_long - bp_short,
                'dlLong':  dl_long,
                'dlShort': dl_short,
                'dlNet':   dl_long - dl_short,
                'oi':      oi,
            }

            results.setdefault(symbol, []).append(entry)

        except Exception:
            continue

    # Sort each market by date
    for sym in results:
        results[sym].sort(key=lambda x: x['date'])

    return results


def load_all_data():
    """
    Fetch current year + previous years of disaggregated data.
    Returns combined dict: {symbol: [entries]}
    """
    now = datetime.datetime.now()
    cache_key = 'cot_v2'

    if cache_key in _cache:
        age = (now - _cache_time[cache_key]).total_seconds()
        if age < CACHE_TTL:
            return _cache[cache_key]

    year = now.year
    data = {}

    # Historical years (year-1, year-2 for Z-Score 2Y)
    for yr in [year - 2, year - 1]:
        try:
            content = fetch_url(CFTC_HISTORY.format(year=yr), is_zip=True)
            yr_data = parse_disagg_csv(content)
            for sym, entries in yr_data.items():
                data.setdefault(sym, []).extend(entries)
            print(f"[COT] Disagg {yr}: loaded {sum(len(v) for v in yr_data.values())} rows for {list(yr_data.keys())}")
        except Exception as e:
            print(f"[COT] Disagg {yr} error: {e}")

    # Current year — try plain text first, fall back to zip
    try:
        content = fetch_url(CFTC_CURRENT, is_zip=False)
        yr_data = parse_disagg_csv(content)
        for sym, entries in yr_data.items():
            data.setdefault(sym, []).extend(entries)
        print(f"[COT] Current year: loaded {sum(len(v) for v in yr_data.values())} rows for {list(yr_data.keys())}")
    except Exception as e:
        print(f"[COT] Current year plain text error: {e}, trying zip...")
        try:
            content = fetch_url(CFTC_HISTORY.format(year=year), is_zip=True)
            yr_data = parse_disagg_csv(content)
            for sym, entries in yr_data.items():
                data.setdefault(sym, []).extend(entries)
            print(f"[COT] Current year zip: loaded {sum(len(v) for v in yr_data.values())} rows")
        except Exception as e2:
            print(f"[COT] Current year zip also failed: {e2}")

    # Deduplicate by date per symbol
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
    print(f"[COT] Cache ready — {len(data)} markets: {sorted(data.keys())}")
    for sym in sorted(data.keys()):
        entries = data[sym]
        print(f"  {sym}: {len(entries)} weeks, {entries[0]['date']} → {entries[-1]['date']}")

    return data


# ─── ENDPOINTS ──────────────────────────────────────────

@app.route('/')
def index():
    return jsonify({'service': 'Vilasio COT API', 'version': '2.0'})


@app.route('/health')
def health():
    data = load_all_data()
    return jsonify({
        'status': 'ok',
        'version': '2.0',
        'markets': sorted(data.keys()) if data else [],
        'totalRows': sum(len(v) for v in data.values()) if data else 0,
        'time': datetime.datetime.utcnow().isoformat(),
    })


@app.route('/api/cot')
def api_cot():
    """
    GET /api/cot?market=ES&weeks=52

    Returns the full data structure expected by the frontend:
    {
        market, name, exchange, cat, reportDate,
        labels, bpLong, bpShort, bpNet,
        dlLong, dlShort, dlNet, oi
    }
    """
    market = request.args.get('market', '').upper()
    weeks = int(request.args.get('weeks', 52))
    weeks = max(4, min(weeks, 260))  # Clamp 4-260

    if market not in MARKETS:
        return jsonify({
            'error': f'Unknown market: {market}',
            'available': sorted(MARKETS.keys())
        }), 400

    data = load_all_data()
    if market not in data or len(data[market]) == 0:
        return jsonify({'error': f'No data for {market}'}), 404

    entries = data[market]
    # Take last N+1 weeks (so we have N periods of change)
    entries = entries[-(weeks + 1):] if len(entries) > weeks + 1 else entries

    cfg = MARKETS[market]

    result = {
        'market':     market,
        'name':       cfg['name'],
        'exchange':   cfg['exchange'],
        'cat':        cfg['cat'],
        'reportDate': entries[-1]['date'],
        'labels':     [e['date'] for e in entries],
        'bpLong':     [e['bpLong'] for e in entries],
        'bpShort':    [e['bpShort'] for e in entries],
        'bpNet':      [e['bpNet'] for e in entries],
        'dlLong':     [e['dlLong'] for e in entries],
        'dlShort':    [e['dlShort'] for e in entries],
        'dlNet':      [e['dlNet'] for e in entries],
        'oi':         [e['oi'] for e in entries],
    }

    return jsonify(result)


@app.route('/api/cot/summary')
def api_cot_summary():
    """
    GET /api/cot/summary

    Returns summary for all markets (for heatmap):
    { markets: [{market, name, cat, bpNet, bpNetChg, dlNet, oi, reportDate}, ...] }
    """
    data = load_all_data()
    results = []

    for sym in sorted(MARKETS.keys()):
        if sym not in data or len(data[sym]) < 2:
            continue
        entries = data[sym]
        last = entries[-1]
        prev = entries[-2]

        results.append({
            'market':    sym,
            'name':      MARKETS[sym]['name'],
            'cat':       MARKETS[sym]['cat'],
            'bpNet':     last['bpNet'],
            'bpNetChg':  last['bpNet'] - prev['bpNet'],
            'dlNet':     last['dlNet'],
            'oi':        last['oi'],
            'reportDate': last['date'],
        })

    return jsonify({
        'markets': results,
        'lastFetch': _cache_time.get('cot_v2', datetime.datetime.now()).isoformat(),
    })


@app.route('/api/cot/refresh')
def api_refresh():
    """Force cache clear and reload."""
    _cache.clear()
    _cache_time.clear()
    data = load_all_data()
    return jsonify({
        'status': 'refreshed',
        'markets': sorted(data.keys()),
    })


@app.route('/debug/markets')
def debug_markets():
    """List all market names in the current year's CFTC file."""
    try:
        content = fetch_url(CFTC_CURRENT, is_zip=False)
        reader = csv.DictReader(io.StringIO(content))
        if reader.fieldnames:
            reader.fieldnames = [f.strip() for f in reader.fieldnames]
        names = sorted(set(
            row.get('Market_and_Exchange_Names', '').strip()
            for row in reader
            if row.get('Market_and_Exchange_Names', '').strip()
        ))
        return jsonify({'count': len(names), 'markets': names})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
