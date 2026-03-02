"""
Vilasio COT Backend v2.2
Uses TWO CFTC CSV sources for full coverage:
  - Traders in Financial Futures (TFF) for: ES, NQ, ZB, 6E, 6B, 6J
  - Disaggregated Futures for: GC, CL, SI, NG, ZC, ZW

Both are proper CSV with headers.
Maps all data to unified bpLong/bpShort/dlLong/dlShort format for the frontend.
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


# ─── CFTC CSV URLs (both have proper headers) ──────────
# TFF = Traders in Financial Futures (financial contracts: equity index, FX, rates)
TFF_CURRENT = "https://www.cftc.gov/dea/newcot/FinFutWk.txt"
TFF_HISTORY = "https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"
# Disaggregated (physical commodities: metals, energy, agriculture)
DISAGG_CURRENT = "https://www.cftc.gov/dea/newcot/f_disagg.txt"
DISAGG_HISTORY = "https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"


# ─── MARKET CONFIG ──────────────────────────────────────
# source: "tff" or "disagg"
MARKETS = {
    "ES": {"name": "E-Mini S&P 500",    "exchange": "Chicago Mercantile Exchange", "cat": "Equity",
           "source": "tff", "match": "E-MINI S&P 500"},
    "NQ": {"name": "E-Mini Nasdaq 100", "exchange": "Chicago Mercantile Exchange", "cat": "Equity",
           "source": "tff", "match": "NASDAQ MINI"},
    "ZB": {"name": "30-Year T-Bond",    "exchange": "Chicago Board of Trade",      "cat": "Rates",
           "source": "tff", "match": "UST BOND"},
    "6E": {"name": "Euro FX",           "exchange": "Chicago Mercantile Exchange", "cat": "FX",
           "source": "tff", "match": "EURO FX"},
    "6B": {"name": "British Pound",     "exchange": "Chicago Mercantile Exchange", "cat": "FX",
           "source": "tff", "match": "BRITISH POUND"},
    "6J": {"name": "Japanese Yen",      "exchange": "Chicago Mercantile Exchange", "cat": "FX",
           "source": "tff", "match": "JAPANESE YEN"},
    "GC": {"name": "Gold",              "exchange": "Commodity Exchange Inc.",      "cat": "Metals",
           "source": "disagg", "match": "GOLD - COMMODITY EXCHANGE"},
    "CL": {"name": "Crude Oil WTI",     "exchange": "New York Mercantile Exchange","cat": "Energy",
           "source": "disagg", "match": "CRUDE OIL, LIGHT SWEET"},
    "SI": {"name": "Silver",            "exchange": "Commodity Exchange Inc.",      "cat": "Metals",
           "source": "disagg", "match": "SILVER - COMMODITY EXCHANGE"},
    "NG": {"name": "Natural Gas",       "exchange": "New York Mercantile Exchange","cat": "Energy",
           "source": "disagg", "match": "NATURAL GAS - NEW YORK MERCANTILE"},
    "ZC": {"name": "Corn",              "exchange": "Chicago Board of Trade",      "cat": "Agri",
           "source": "disagg", "match": "CORN - CHICAGO BOARD OF TRADE"},
    "ZW": {"name": "Wheat",             "exchange": "Chicago Board of Trade",      "cat": "Agri",
           "source": "disagg", "match": "WHEAT-SRW - CHICAGO BOARD OF TRADE"},
}


def safe_int(val):
    try:
        return int(str(val).strip().replace(',', ''))
    except Exception:
        return 0


def match_market(name, source_filter):
    """Match a CFTC market name to our ticker symbol, filtered by source type."""
    name_upper = name.upper()
    for symbol, cfg in MARKETS.items():
        if cfg["source"] != source_filter:
            continue
        if cfg["match"].upper() in name_upper:
            return symbol
    return None


# ─── CACHE ──────────────────────────────────────────────
_cache = {}
_cache_time = {}
CACHE_TTL = 3600 * 6


def fetch_url(url, is_zip=True):
    print(f"[COT] Fetching: {url}")
    req = urllib.request.Request(url, headers={'User-Agent': 'Vilasio/2.2'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    if is_zip:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            txt_name = [n for n in zf.namelist()
                        if n.endswith('.txt') or n.endswith('.csv')][0]
            with zf.open(txt_name) as f:
                return f.read().decode('utf-8', errors='replace')
    else:
        return raw.decode('utf-8', errors='replace')


def parse_date(row):
    """Parse date from CFTC row, handling both date formats."""
    date_str = (row.get('Report_Date_as_YYYY-MM-DD', '') or
                row.get('As_of_Date_In_Form_YYMMDD', '')).strip()
    if not date_str:
        return None
    try:
        if '-' in date_str:
            return datetime.datetime.strptime(date_str[:10], '%Y-%m-%d').strftime('%Y-%m-%d')
        elif len(date_str) == 6:
            return datetime.datetime.strptime(date_str, '%y%m%d').strftime('%Y-%m-%d')
    except Exception:
        pass
    return None


def parse_tff_csv(content):
    """
    Parse TFF (Traders in Financial Futures) CSV.
    
    TFF columns mapping to our model:
    - Big Players = Lev_Money (Leveraged Funds = hedge funds/CTAs)
    - Dealers = Dealer_Positions (Dealer/Intermediary)
    
    This matches what Tradingster shows for financial contracts.
    Actually, Tradingster uses Legacy NonComm/Comm for these.
    
    For best match with Tradingster, we use:
    - Big Players = Asset_Mgr (Asset Manager/Institutional) — the big directional players
    - OR we combine: NonComm = Lev_Money + Asset_Mgr + Other_Rept
    
    To match Tradingster exactly (Legacy report), we need NonComm and Comm.
    TFF doesn't have NonComm/Comm directly but the file DOES have them 
    in some versions. Let's check what columns are available.
    """
    results = {}
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames:
        reader.fieldnames = [f.strip() for f in reader.fieldnames]

    for row in reader:
        market_name = row.get('Market_and_Exchange_Names', '').strip()
        symbol = match_market(market_name, 'tff')
        if not symbol:
            continue

        date_iso = parse_date(row)
        if not date_iso:
            continue

        try:
            # TFF has these trader categories:
            # Dealer, Asset_Mgr, Lev_Money, Other_Rept, NonRept
            # To approximate Legacy NonComm/Comm:
            #   NonComm (Big Players) = Lev_Money Long/Short (hedge funds, speculators)
            #   Comm (Dealers) = Dealer Long/Short (dealer/intermediary)
            #
            # BUT Tradingster's "Non-Commercial" for S&P 500 includes ALL non-commercial.
            # In TFF: NonComm ~ Lev_Money + Asset_Mgr + Other_Rept
            # In TFF: Comm ~ Dealer
            #
            # Let's provide Lev_Money as Big Players and Dealer as Dealers,
            # since these are the most meaningful categories for trading signals.
            
            bp_long  = safe_int(row.get('Lev_Money_Positions_Long_All', 0))
            bp_short = safe_int(row.get('Lev_Money_Positions_Short_All', 0))
            dl_long  = safe_int(row.get('Dealer_Positions_Long_All', 0))
            dl_short = safe_int(row.get('Dealer_Positions_Short_All', 0))
            oi       = safe_int(row.get('Open_Interest_All', 0))

            if oi == 0:
                continue

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

    for sym in results:
        results[sym].sort(key=lambda x: x['date'])
    return results


def parse_disagg_csv(content):
    """
    Parse Disaggregated Futures CSV.
    
    Disaggregated columns:
    - Prod_Merc = Producer/Merchant (hedgers, like Comm in Legacy)
    - Swap = Swap Dealers
    - M_Money = Managed Money (like NonComm speculators)
    - Other_Rept = Other Reportable
    
    Mapping:
    - Big Players = M_Money (Managed Money = hedge funds)
    - Dealers = Prod_Merc (Producer/Merchant = commercial hedgers)
    """
    results = {}
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames:
        reader.fieldnames = [f.strip() for f in reader.fieldnames]

    for row in reader:
        market_name = row.get('Market_and_Exchange_Names', '').strip()
        symbol = match_market(market_name, 'disagg')
        if not symbol:
            continue

        date_iso = parse_date(row)
        if not date_iso:
            continue

        try:
            # Managed Money = Big Players (speculators)
            bp_long  = safe_int(row.get('M_Money_Positions_Long_All', 0))
            bp_short = safe_int(row.get('M_Money_Positions_Short_All', 0))
            # Producer/Merchant = Dealers (commercial hedgers)
            dl_long  = safe_int(row.get('Prod_Merc_Positions_Long_All', 0))
            dl_short = safe_int(row.get('Prod_Merc_Positions_Short_All', 0))
            oi       = safe_int(row.get('Open_Interest_All', 0))

            if oi == 0:
                continue

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

    for sym in results:
        results[sym].sort(key=lambda x: x['date'])
    return results


def load_all_data():
    now = datetime.datetime.now()
    cache_key = 'cot_v2'
    if cache_key in _cache:
        age = (now - _cache_time[cache_key]).total_seconds()
        if age < CACHE_TTL:
            return _cache[cache_key]

    year = now.year
    data = {}

    # ── TFF (Financial markets: ES, NQ, ZB, 6E, 6B, 6J) ──
    for yr in [year - 2, year - 1]:
        try:
            content = fetch_url(TFF_HISTORY.format(year=yr), is_zip=True)
            yr_data = parse_tff_csv(content)
            for sym, entries in yr_data.items():
                data.setdefault(sym, []).extend(entries)
            print(f"[COT] TFF {yr}: {sum(len(v) for v in yr_data.values())} rows — {sorted(yr_data.keys())}")
        except Exception as e:
            print(f"[COT] TFF {yr} error: {e}")

    # TFF current year
    try:
        content = fetch_url(TFF_CURRENT, is_zip=False)
        yr_data = parse_tff_csv(content)
        for sym, entries in yr_data.items():
            data.setdefault(sym, []).extend(entries)
        print(f"[COT] TFF current: {sum(len(v) for v in yr_data.values())} rows — {sorted(yr_data.keys())}")
    except Exception as e:
        print(f"[COT] TFF current error: {e}")
        try:
            content = fetch_url(TFF_HISTORY.format(year=year), is_zip=True)
            yr_data = parse_tff_csv(content)
            for sym, entries in yr_data.items():
                data.setdefault(sym, []).extend(entries)
            print(f"[COT] TFF current (zip fallback): {sum(len(v) for v in yr_data.values())} rows")
        except Exception as e2:
            print(f"[COT] TFF current zip error: {e2}")

    # ── Disaggregated (Commodity markets: GC, CL, SI, NG, ZC, ZW) ──
    for yr in [year - 2, year - 1]:
        try:
            content = fetch_url(DISAGG_HISTORY.format(year=yr), is_zip=True)
            yr_data = parse_disagg_csv(content)
            for sym, entries in yr_data.items():
                data.setdefault(sym, []).extend(entries)
            print(f"[COT] Disagg {yr}: {sum(len(v) for v in yr_data.values())} rows — {sorted(yr_data.keys())}")
        except Exception as e:
            print(f"[COT] Disagg {yr} error: {e}")

    # Disaggregated current year
    try:
        content = fetch_url(DISAGG_CURRENT, is_zip=False)
        yr_data = parse_disagg_csv(content)
        for sym, entries in yr_data.items():
            data.setdefault(sym, []).extend(entries)
        print(f"[COT] Disagg current: {sum(len(v) for v in yr_data.values())} rows — {sorted(yr_data.keys())}")
    except Exception as e:
        print(f"[COT] Disagg current error: {e}")
        try:
            content = fetch_url(DISAGG_HISTORY.format(year=year), is_zip=True)
            yr_data = parse_disagg_csv(content)
            for sym, entries in yr_data.items():
                data.setdefault(sym, []).extend(entries)
            print(f"[COT] Disagg current (zip fallback): {sum(len(v) for v in yr_data.values())} rows")
        except Exception as e2:
            print(f"[COT] Disagg current zip error: {e2}")

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
    print(f"[COT] ═══ Cache ready — {len(data)} markets: {sorted(data.keys())} ═══")
    for sym in sorted(data.keys()):
        entries = data[sym]
        if entries:
            last = entries[-1]
            print(f"  {sym}: {len(entries)} wks, {entries[0]['date']} -> {last['date']}, "
                  f"bpNet={last['bpNet']:+,}, dlNet={last['dlNet']:+,}, oi={last['oi']:,}")
    return data


# ─── ENDPOINTS ──────────────────────────────────────────

@app.route('/')
def index():
    return jsonify({'service': 'Vilasio COT API', 'version': '2.2'})


@app.route('/health')
def health():
    data = load_all_data()
    return jsonify({
        'status': 'ok', 'version': '2.2',
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
        'lastFetch': _cache_time.get('cot_v2', datetime.datetime.now()).isoformat(),
    })


@app.route('/api/cot/refresh')
def api_refresh():
    _cache.clear()
    _cache_time.clear()
    data = load_all_data()
    return jsonify({'status': 'refreshed', 'markets': sorted(data.keys()),
                    'rows': {sym: len(e) for sym, e in data.items()}})


@app.route('/debug/columns')
def debug_columns():
    """Show actual CSV column names from both sources."""
    result = {}
    try:
        content = fetch_url(TFF_CURRENT, is_zip=False)
        reader = csv.DictReader(io.StringIO(content))
        if reader.fieldnames:
            reader.fieldnames = [f.strip() for f in reader.fieldnames]
            result['tff_columns'] = reader.fieldnames
    except Exception as e:
        result['tff_error'] = str(e)

    try:
        content = fetch_url(DISAGG_CURRENT, is_zip=False)
        reader = csv.DictReader(io.StringIO(content))
        if reader.fieldnames:
            reader.fieldnames = [f.strip() for f in reader.fieldnames]
            result['disagg_columns'] = reader.fieldnames
    except Exception as e:
        result['disagg_error'] = str(e)

    return jsonify(result)


@app.route('/debug/markets')
def debug_markets():
    """Show matched and unmatched market names."""
    result = {}
    for label, url, source in [('tff', TFF_CURRENT, 'tff'), ('disagg', DISAGG_CURRENT, 'disagg')]:
        try:
            content = fetch_url(url, is_zip=False)
            reader = csv.DictReader(io.StringIO(content))
            if reader.fieldnames:
                reader.fieldnames = [f.strip() for f in reader.fieldnames]
            names = sorted(set(
                row.get('Market_and_Exchange_Names', '').strip()
                for row in reader if row.get('Market_and_Exchange_Names', '').strip()
            ))
            matched = {}
            for n in names:
                sym = match_market(n, source)
                if sym:
                    matched[sym] = n
            result[label] = {'count': len(names), 'matched': matched, 'all': names}
        except Exception as e:
            result[label] = {'error': str(e)}
    return jsonify(result)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
