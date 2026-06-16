"""
╔══════════════════════════════════════════════════════════════╗
║         VRSO LIVE SCANNER — S&P 500                         ║
║   Dagelijkse scan na market close                           ║
║   Output: data/signals.json + email notificatie             ║
╚══════════════════════════════════════════════════════════════╝

GEBRUIK:
  python scanner.py

  Of automatisch via GitHub Actions (zie .github/workflows/scan.yml)

VEREISTEN:
  pip install yfinance pandas numpy requests

EMAIL SETUP:
  Zet in GitHub Secrets (of lokaal als environment variables):
    GMAIL_USER     = jouw.email@gmail.com
    GMAIL_PASSWORD = jouw-app-wachtwoord   (niet je echte wachtwoord!)
    NOTIFY_EMAIL   = ontvanger@email.com   (mag hetzelfde zijn)

  Gmail app-wachtwoord aanmaken:
    1. Ga naar myaccount.google.com/security
    2. Zet 2-staps verificatie aan
    3. Zoek "App-wachtwoorden"
    4. Maak nieuw wachtwoord aan voor "Mail"
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────
# CONFIGURATIE — zelfde als backtester v1
# ─────────────────────────────────────────────────────────────
CONFIG = {
    "ema_fast": 21,
    "ema_slow": 50,
    "ema_trend": 200,
    "rsi_period": 14,
    "rsi_min": 30,
    "rsi_max": 70,
    "vol_ma_period": 50,
    "atr_period": 14,
    "rs_period": 63,
    "vol_dry_threshold": 0.85,
    "pullback_max_pct": 0.05,
    "rs_slope_weak": 0.0,
    "target1_pct": 0.12,
    "target2_pct": 0.25,
    "atr_multiplier": 2.0,
    "max_stop_pct": 0.10,
    "min_score": 5.0,
    "lookback_days": 550,   # ruim genoeg voor EMA200 warmup na dropna (~200 handelsdagen = ~280 kalenderdagen + buffer)
    "history_days": 5,      # hoeveel handelsdagen history tonen
}

# ─────────────────────────────────────────────────────────────
# S&P 500 TICKERS
# ─────────────────────────────────────────────────────────────
SP500_TICKERS = [
    "MMM","AOS","ABT","ABBV","ACN","ADBE","AMD","AES","AFL","A","APD","ABNB",
    "AKAM","ALB","ARE","ALGN","ALLE","LNT","ALL","GOOGL","GOOG","MO","AMZN",
    "AMCR","AEE","AEP","AXP","AIG","AMT","AWK","AMP","AME","AMGN","APH","ADI",
    "ANSS","AON","APA","APO","AAPL","AMAT","APTV","ACGL","ADM","ANET","AJG",
    "AIZ","T","ATO","ADSK","ADP","AZO","AVB","AVY","AXON","BKR","BALL","BAC",
    "BAX","BDX","BRK-B","BBY","TECH","BIIB","BLK","BX","BA","BCH","BSX","BMY",
    "AVGO","BR","BRO","BF-B","BLDR","BG","CDNS","CZR","CPT","CPB","COF","CAH",
    "KMX","CCL","CARR","CTLT","CAT","CBOE","CBRE","CDW","CE","COR","CNC","CNX",
    "CDAY","CF","CRL","SCHW","CHTR","CVX","CMG","CB","CHD","CI","CINF","CTAS",
    "CSCO","C","CFG","CLX","CME","CMS","KO","CTSH","CL","CMCSA","CAG","COP",
    "ED","STZ","CEG","COO","CPRT","GLW","CPAY","CTVA","CSGP","COST","CTRA",
    "CRWD","CCI","CSX","CMI","CVS","DHR","DRI","DVA","DAY","DE","DELL","DAL",
    "DVN","DXCM","FANG","DLR","DFS","DG","DLTR","D","DPZ","DOV","DOW","DHI",
    "DTE","DUK","DD","EMN","ETN","EBAY","ECL","EIX","EW","EA","ELV","EMR",
    "ENPH","ETR","EOG","EPAM","EQT","EFX","EQIX","EQR","ESS","EL","ETSY","EG",
    "EVRG","ES","EXC","EXPE","EXPD","EXR","XOM","FFIV","FDS","FICO","FAST",
    "FRT","FDX","FIS","FITB","FSLR","FE","FI","FMC","F","FTNT","FTV","FOXA",
    "FOX","BEN","FCX","GRMN","IT","GE","GEHC","GEV","GEN","GNRC","GD","GIS",
    "GM","GPC","GILD","GPN","GL","GDDY","GS","HAL","HIG","HAS","HCA","DOC",
    "HSIC","HSY","HES","HPE","HLT","HOLX","HD","HON","HRL","HST","HWM","HPQ",
    "HUBB","HUM","HBAN","HII","IBM","IEX","IDXX","ITW","INCY","IR","PODD",
    "INTC","ICE","IFF","IP","IPG","INTU","ISRG","IVZ","INVH","IQV","IRM",
    "JBHT","J","JBL","JKHY","JNJ","JCI","JPM","JNPR","K","KVUE","KDP","KEY",
    "KEYS","KMB","KIM","KMI","KKR","KLAC","KHC","KR","LHX","LH","LRCX","LW",
    "LVS","LDOS","LEN","LLY","LIN","LYV","LKQ","LMT","L","LOW","LULU","LYB",
    "MTB","MRO","MPC","MKTX","MAR","MMC","MLM","MAS","MA","MTCH","MKC","MCD",
    "MCK","MDT","MRK","META","MET","MTD","MGM","MCHP","MU","MSFT","MAA","MRNA",
    "MHK","MOH","TAP","MDLZ","MPWR","MNST","MCO","MS","MOS","MSI","MSCI","NDAQ",
    "NTAP","NOV","NWSA","NWS","NEE","NKE","NEM","NFLX","NWL","NRG","NUE","NVDA",
    "NVR","NXPI","ORLY","OXY","ODFL","OMC","ON","OKE","ORCL","OTIS","PCAR",
    "PKG","PLTR","PH","PAYX","PAYC","PYPL","PNR","PEP","PFE","PCG","PM","PSX",
    "PNW","PNC","POOL","PPG","PPL","PFG","PG","PGR","PLD","PRU","PEG","PTC",
    "PSA","PHM","QRVO","PWR","QCOM","DGX","RL","RJF","RTX","O","REG","REGN",
    "RF","RSG","RMD","RVTY","ROK","ROL","ROP","ROST","RCL","SPGI","CRM","SBAC",
    "SLB","STX","SRE","NOW","SHW","SPG","SWKS","SJM","SW","SNA","SOLV","SO",
    "LUV","SWK","SBUX","STT","STLD","STE","SYK","SMCI","SYF","SNPS","SYY","TMUS",
    "TROW","TTWO","TPR","TRGP","TGT","TEL","TDY","TFX","TER","TSLA","TXN",
    "TXT","TMO","TJX","TSCO","TT","TDG","TRV","TRMB","TFC","TYL","TSN","USB",
    "UBER","UDR","UHS","UNP","UAL","UPS","URI","UNH","UHS","VLO","VTR","VLTO",
    "VRSN","VRSK","VZ","VRTX","VTRS","VICI","V","VMC","WRB","GWW","WAB","WBA",
    "WMT","DIS","WBD","WM","WAT","WEC","WFC","WELL","WST","WDC","WRK","WY",
    "WHR","WMB","WTW","WYNN","XEL","XYL","YUM","ZBRA","ZBH","ZTS"
]

# Dedupliceer
SP500_TICKERS = list(dict.fromkeys(SP500_TICKERS))

# ─────────────────────────────────────────────────────────────
# BEDRIJFSNAMEN — kortere handelsnamen voor snelle herkenning
# ─────────────────────────────────────────────────────────────
COMPANY_NAMES = {
    "A":"Agilent","AAL":"American Airlines","AAPL":"Apple","ABBV":"AbbVie",
    "ABNB":"Airbnb","ABT":"Abbott","ACGL":"Arch Capital","ACN":"Accenture",
    "ADBE":"Adobe","ADI":"Analog Devices","ADM":"Archer-Daniels","ADP":"ADP",
    "ADSK":"Autodesk","AEE":"Ameren","AEP":"AEP","AES":"AES Corp",
    "AFL":"Aflac","AIG":"AIG","AIZ":"Assurant","AJG":"Arthur Gallagher",
    "AKAM":"Akamai","ALB":"Albemarle","ALGN":"Align Tech","ALL":"Allstate",
    "ALLE":"Allegion","AMD":"AMD","AME":"AMETEK","AMGN":"Amgen",
    "AMCR":"Amcor","AMP":"Ameriprise","AMT":"American Tower","AMZN":"Amazon",
    "ANSS":"Ansys","AON":"Aon","AOS":"A.O. Smith","APA":"APA Corp",
    "APD":"Air Products","APH":"Amphenol","APO":"Apollo Global","APTV":"Aptiv",
    "ARE":"Alexandria RE","ATI":"ATI Inc","ATO":"Atmos Energy","AVB":"AvalonBay",
    "AVGO":"Broadcom","AVY":"Avery Dennison","AXON":"Axon","AXP":"Amex",
    "AZO":"AutoZone","BA":"Boeing","BAC":"Bank of America","BALL":"Ball Corp",
    "BAX":"Baxter","BBY":"Best Buy","BDX":"Becton Dickinson","BEN":"Franklin Templeton",
    "BIIB":"Biogen","BKR":"Baker Hughes","BLK":"BlackRock","BLDR":"Builders FirstSource",
    "BMY":"Bristol-Myers","BRK-B":"Berkshire Hathaway","BRO":"Brown & Brown",
    "BSX":"Boston Scientific","BX":"Blackstone","BF-B":"Brown-Forman","BG":"Bunge",
    "BCH":"Banco de Chile","BR":"Broadridge","C":"Citigroup","CAG":"Conagra",
    "CAH":"Cardinal Health","CAT":"Caterpillar","CB":"Chubb","CBOE":"Cboe Global",
    "CBRE":"CBRE Group","CCL":"Carnival","CDNS":"Cadence","CDW":"CDW Corp",
    "CE":"Celanese","CEG":"Constellation Energy","CF":"CF Industries","CFG":"Citizens Financial",
    "CHD":"Church & Dwight","CHTR":"Charter Comm","CI":"Cigna","CINF":"Cincinnati Financial",
    "CL":"Colgate","CLX":"Clorox","CME":"CME Group","CMG":"Chipotle",
    "CMI":"Cummins","CMS":"CMS Energy","CNC":"Centene","CNX":"CNX Resources",
    "KO":"Coca-Cola","COF":"Capital One","COO":"Cooper Companies","COP":"ConocoPhillips",
    "COR":"Cencora","COST":"Costco","CPAY":"Corpay","CPRT":"Copart",
    "CPB":"Campbell Soup","CPT":"Camden Property","CRL":"Charles River","CRM":"Salesforce",
    "CRWD":"CrowdStrike","CSCO":"Cisco","CSGP":"CoStar","CSX":"CSX Corp",
    "CTLT":"Catalent","CTAS":"Cintas","CTSH":"Cognizant","CTVA":"Corteva",
    "CTRA":"Coterra","CVS":"CVS Health","CVX":"Chevron","CCI":"Crown Castle",
    "CZR":"Caesars","D":"Dominion","DAL":"Delta Air","DAY":"Dayforce",
    "DD":"DuPont","DE":"Deere","DELL":"Dell","DFS":"Discover Financial",
    "DG":"Dollar General","DHI":"D.R. Horton","DHR":"Danaher","DIS":"Disney",
    "DLTR":"Dollar Tree","DLR":"Digital Realty","DOC":"Healthpeak","DOV":"Dover",
    "DOW":"Dow Inc","DPZ":"Domino's","DRI":"Darden","DTE":"DTE Energy",
    "DUK":"Duke Energy","DVA":"DaVita","DVN":"Devon Energy","DXCM":"Dexcom",
    "EA":"Electronic Arts","EBAY":"eBay","ECL":"Ecolab","ED":"ConEd",
    "EFX":"Equifax","EG":"Everest Group","EIX":"Edison Int'l","EL":"Estée Lauder",
    "ELV":"Elevance","EMN":"Eastman Chemical","EMR":"Emerson","ENPH":"Enphase",
    "EOG":"EOG Resources","EPAM":"EPAM Systems","EQIX":"Equinix","EQR":"Equity Residential",
    "EQT":"EQT Corp","ES":"Eversource","ESS":"Essex Property","ETN":"Eaton",
    "ETR":"Entergy","ETSY":"Etsy","EVRG":"Evergy","EW":"Edwards Lifesciences",
    "EXC":"Exelon","EXPE":"Expedia","EXPD":"Expeditors","EXR":"Extra Space",
    "XOM":"ExxonMobil","F":"Ford","FANG":"Diamondback Energy","FAST":"Fastenal",
    "FCX":"Freeport-McMoRan","FDS":"FactSet","FDX":"FedEx","FE":"FirstEnergy",
    "FFIV":"F5 Networks","FICO":"FICO","FI":"Fiserv","FIS":"FIS",
    "FITB":"Fifth Third","FSLR":"First Solar","FMC":"FMC Corp","FOX":"Fox Corp",
    "FOXA":"Fox Corp A","FRT":"Federal Realty","FTNT":"Fortinet","FTV":"Fortive",
    "GD":"General Dynamics","GE":"GE Aerospace","GEHC":"GE HealthCare","GEN":"Gen Digital",
    "GEV":"GE Vernova","GILD":"Gilead","GIS":"General Mills","GL":"Globe Life",
    "GLW":"Corning","GM":"General Motors","GNRC":"Generac","GOOG":"Alphabet C",
    "GOOGL":"Alphabet A","GPC":"Genuine Parts","GPN":"Global Payments","GRMN":"Garmin",
    "GS":"Goldman Sachs","GWW":"Grainger","HAL":"Halliburton","HAS":"Hasbro",
    "HCA":"HCA Healthcare","HD":"Home Depot","HES":"Hess","HIG":"Hartford Financial",
    "HII":"Huntington Ingalls","HLT":"Hilton","HOLX":"Hologic","HON":"Honeywell",
    "HPE":"HP Enterprise","HPQ":"HP Inc","HRL":"Hormel","HSIC":"Henry Schein",
    "HST":"Host Hotels","HSY":"Hershey","HUBB":"Hubbell","HUM":"Humana",
    "HWM":"Howmet","HBAN":"Huntington Bancshares","IBM":"IBM","ICE":"Intercontinental Exchange",
    "IDXX":"IDEXX Labs","IEX":"IDEX Corp","IFF":"IFF","INCY":"Incyte",
    "INTC":"Intel","INTU":"Intuit","INVH":"Invitation Homes","IP":"Int'l Paper",
    "IPG":"Interpublic","IQV":"IQVIA","IR":"Ingersoll Rand","IRM":"Iron Mountain",
    "ISRG":"Intuitive Surgical","IT":"Gartner","ITW":"Illinois Tool","IVZ":"Invesco",
    "J":"Jacobs Solutions","JBL":"Jabil","JBHT":"J.B. Hunt","JCI":"Johnson Controls",
    "JKHY":"Jack Henry","JNJ":"Johnson & Johnson","JPM":"JPMorgan","JNPR":"Juniper Networks",
    "K":"Kellanova","KDP":"Keurig Dr Pepper","KEY":"KeyCorp","KEYS":"Keysight",
    "KHC":"Kraft Heinz","KIM":"Kimco Realty","KKR":"KKR","KLAC":"KLA Corp",
    "KMB":"Kimberly-Clark","KMI":"Kinder Morgan","KO":"Coca-Cola","KR":"Kroger",
    "KVUE":"Kenvue","L":"Loews","LEN":"Lennar","LH":"LabCorp",
    "LHX":"L3Harris","LIN":"Linde","LDOS":"Leidos","LKQ":"LKQ Corp",
    "LLY":"Eli Lilly","LMT":"Lockheed Martin","LNT":"Alliant Energy","LOW":"Lowe's",
    "LRCX":"Lam Research","LULU":"Lululemon","LUV":"Southwest Airlines","LVS":"Las Vegas Sands",
    "LW":"Lamb Weston","LYB":"LyondellBasell","LYV":"Live Nation","MA":"Mastercard",
    "MAA":"Mid-America Apt","MAR":"Marriott","MAS":"Masco","MCD":"McDonald's",
    "MCK":"McKesson","MCO":"Moody's","MCHP":"Microchip Tech","MDLZ":"Mondelez",
    "MDT":"Medtronic","META":"Meta","MET":"MetLife","MGM":"MGM Resorts",
    "MHK":"Mohawk Industries","MKC":"McCormick","MKTX":"MarketAxess","MLM":"Martin Marietta",
    "MMC":"Marsh McLennan","MMM":"3M","MO":"Altria","MOH":"Molina Healthcare",
    "MOS":"Mosaic","MPWR":"Monolithic Power","MRK":"Merck","MRO":"Marathon Oil",
    "MS":"Morgan Stanley","MSCI":"MSCI Inc","MSFT":"Microsoft","MSI":"Motorola Solutions",
    "MTB":"M&T Bank","MTD":"Mettler-Toledo","MU":"Micron","MRNA":"Moderna",
    "MPC":"Marathon Petroleum","MTCH":"Match Group","TAP":"Molson Coors",
    "NDAQ":"Nasdaq","NEE":"NextEra Energy","NEM":"Newmont","NFLX":"Netflix",
    "NKE":"Nike","NOV":"NOV Inc","NRG":"NRG Energy","NTAP":"NetApp",
    "NUE":"Nucor","NVDA":"Nvidia","NVR":"NVR Inc","NWSA":"News Corp A",
    "NWS":"News Corp B","NXPI":"NXP Semi","O":"Realty Income","ODFL":"Old Dominion",
    "OKE":"ONEOK","OMC":"Omnicom","ON":"ON Semiconductor","OXY":"Occidental",
    "ORCL":"Oracle","OTIS":"Otis Worldwide","ORLY":"O'Reilly Auto",
    "PCAR":"Paccar","PAYC":"Paycom","PAYX":"Paychex","PCG":"PG&E",
    "PEG":"PSEG","PEP":"PepsiCo","PFE":"Pfizer","PFG":"Principal Financial",
    "PG":"Procter & Gamble","PGR":"Progressive","PH":"Parker Hannifin","PHM":"PulteGroup",
    "PKG":"Packaging Corp","PLD":"Prologis","PLTR":"Palantir","PM":"Philip Morris",
    "PNC":"PNC Financial","PNR":"Pentair","PNW":"Pinnacle West","POOL":"Pool Corp",
    "PPG":"PPG Industries","PPL":"PPL Corp","PRU":"Prudential","PSA":"Public Storage",
    "PSX":"Phillips 66","PTC":"PTC Inc","PWR":"Quanta Services","PYPL":"PayPal",
    "QCOM":"Qualcomm","QRVO":"Qorvo","RL":"Ralph Lauren","RCL":"Royal Caribbean",
    "REG":"Regency Centers","REGN":"Regeneron","RF":"Regions Financial","RJF":"Raymond James",
    "RMD":"ResMed","ROK":"Rockwell Automation","ROL":"Rollins","ROP":"Roper Tech",
    "ROST":"Ross Stores","RSG":"Republic Services","RTX":"RTX Corp","RVTY":"Revvity",
    "SBAC":"SBA Comm","SBUX":"Starbucks","SCHW":"Charles Schwab","SHW":"Sherwin-Williams",
    "SJM":"J.M. Smucker","SLB":"Schlumberger","SMCI":"Super Micro","SNA":"Snap-on",
    "SNPS":"Synopsys","SO":"Southern Co","SOLV":"Solventum","NOW":"ServiceNow",
    "SPG":"Simon Property","SPGI":"S&P Global","SRE":"Sempra","STT":"State Street",
    "STLD":"Steel Dynamics","STE":"Steris","STX":"Seagate","STZ":"Constellation Brands",
    "SW":"Smurfit WestRock","SWK":"Stanley Black & Decker","SWKS":"Skyworks",
    "SYF":"Synchrony","SYK":"Stryker","SYY":"Sysco","T":"AT&T",
    "TDG":"TransDigm","TDY":"Teledyne","TEL":"TE Connectivity","TER":"Teradyne",
    "TFC":"Truist Financial","TFX":"Teleflex","TGT":"Target","TMO":"Thermo Fisher",
    "TMUS":"T-Mobile","TPR":"Tapestry","TRGP":"Targa Resources","TJX":"TJX Companies",
    "TRV":"Travelers","TRMB":"Trimble","TROW":"T. Rowe Price","TSCO":"Tractor Supply",
    "TSLA":"Tesla","TSN":"Tyson Foods","TT":"Trane Technologies","TTWO":"Take-Two",
    "TXN":"Texas Instruments","TXT":"Textron","TYL":"Tyler Technologies",
    "UAL":"United Airlines","UDR":"UDR Inc","UHS":"Universal Health","UNH":"UnitedHealth",
    "UNP":"Union Pacific","UBER":"Uber","UPS":"UPS","URI":"United Rentals",
    "USB":"U.S. Bancorp","V":"Visa","VLO":"Valero","VICI":"VICI Properties",
    "VLTO":"Veralto","VMC":"Vulcan Materials","VTR":"Ventas","VRSN":"VeriSign",
    "VRSK":"Verisk","VTRS":"Viatris","VRTX":"Vertex Pharma","VZ":"Verizon",
    "WAB":"Wabtec","WAT":"Waters Corp","WBA":"Walgreens","WBD":"Warner Bros Discovery",
    "WDC":"Western Digital","WEC":"WEC Energy","WELL":"Welltower","WFC":"Wells Fargo",
    "WHR":"Whirlpool","WM":"Waste Management","WMB":"Williams Companies","WMT":"Walmart",
    "WRB":"W.R. Berkley","WRK":"WestRock","WST":"West Pharma","WTW":"WTW",
    "WY":"Weyerhaeuser","WYNN":"Wynn Resorts","XEL":"Xcel Energy","XYL":"Xylem",
    "YUM":"Yum! Brands","ZBRA":"Zebra Tech","ZBH":"Zimmer Biomet","ZTS":"Zoetis",
    "TECH":"Bio-Techne","GDDY":"GoDaddy","DOC":"Healthpeak","BCH":"Banco de Chile",
    "OMC":"Omnicom","CEG":"Constellation Energy","GEV":"GE Vernova",
}

# ─────────────────────────────────────────────────────────────
# INDICATOR FUNCTIES
# ─────────────────────────────────────────────────────────────
def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def calc_atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def add_indicators(df, spy_close, cfg):
    c = df["Close"].squeeze()
    h = df["High"].squeeze()
    l = df["Low"].squeeze()
    o = df["Open"].squeeze()
    v = df["Volume"].squeeze()

    df["ema21"]   = calc_ema(c, cfg["ema_fast"])
    df["ema50"]   = calc_ema(c, cfg["ema_slow"])
    df["ema200"]  = calc_ema(c, cfg["ema_trend"])
    df["rsi"]     = calc_rsi(c, cfg["rsi_period"])
    df["atr"]     = calc_atr(h, l, c, cfg["atr_period"])
    df["vol_ma"]  = v.rolling(cfg["vol_ma_period"]).mean()

    spy_aligned   = spy_close.reindex(df.index, method="ffill").squeeze()
    df["rs"]      = c.pct_change(cfg["rs_period"]) - spy_aligned.pct_change(cfg["rs_period"])
    df["rs_slope"]= df["rs"].diff(5)

    df["body_pct"]     = (c - o) / o
    df["higher_low"]   = (l > l.shift(5)).astype(int)
    df["atr_ma20"]     = df["atr"].rolling(20).mean()
    df["vcp_ratio"]    = df["atr"] / df["atr_ma20"]

    return df

# ─────────────────────────────────────────────────────────────
# SCORING — identiek aan backtester v1
# ─────────────────────────────────────────────────────────────
def score_setup(df, cfg):
    """
    Scoort de LAATSTE rij (vandaag).
    Geeft dict terug met per-component scores + totaal,
    of None als hard knockout faalt.
    """
    min_rows = max(cfg["ema_trend"], cfg["vol_ma_period"], cfg["rs_period"]) + 5
    if len(df) < min_rows:
        return None

    try:
        row  = df.iloc[-1]
        prev = df.iloc[-2]

        price    = float(row["Close"])
        o        = float(row["Open"])
        e50      = float(row["ema50"])
        e200     = float(row["ema200"])
        e21      = float(row["ema21"])
        rsi      = float(row["rsi"])
        vol      = float(row["Volume"])
        vol_ma   = float(row["vol_ma"])
        vol_prev = float(prev["Volume"])
        rs       = float(row["rs"])
        rs_slope = float(row["rs_slope"])
        vcp      = float(row["vcp_ratio"])
        hl       = float(row["higher_low"])
        atr      = float(row["atr"])

        if any(np.isnan(v) for v in [price, e50, e200, rsi, vol_ma, rs, atr]):
            return None

        # ── HARD KNOCKOUTS ──────────────────────────────────
        if not (e50 > e200 and price > e50):
            return None
        if price < e50 * (1 - cfg["pullback_max_pct"]):
            return None
        if rs <= 0:
            return None

        # ── SCORING ─────────────────────────────────────────
        components = {}

        # RSI (max 2)
        if cfg["rsi_min"] <= rsi <= cfg["rsi_max"]:
            components["RSI"] = 2.0
        elif 25 <= rsi <= 75:
            components["RSI"] = 1.0
        else:
            components["RSI"] = 0.0

        # Volume dry (max 2)
        if vol < vol_ma * cfg["vol_dry_threshold"]:
            components["Volume"] = 2.0
        elif vol < vol_ma * 0.95:
            components["Volume"] = 1.0
        else:
            components["Volume"] = 0.0

        # RS slope (max 2)
        if not np.isnan(rs_slope):
            if rs_slope > cfg["rs_slope_weak"]:
                components["RS"] = 2.0
            elif rs_slope > -0.001:
                components["RS"] = 1.0
            else:
                components["RS"] = 0.0
        else:
            components["RS"] = 0.0

        # Bullish body (max 1)
        body_pct = (price - o) / o if o > 0 else 0
        if body_pct > 0.002:
            components["Body"] = 1.0
        elif body_pct > 0.0:
            components["Body"] = 0.5
        else:
            components["Body"] = 0.0

        # Volume rising (max 1)
        components["VolRising"] = 1.0 if vol > vol_prev else 0.0

        # Higher low (max 1)
        components["HigherLow"] = 1.0 if (not np.isnan(hl) and hl == 1) else 0.0

        # VCP (max 1)
        if not np.isnan(vcp):
            if vcp < 0.80:
                components["VCP"] = 1.0
            elif vcp < 0.95:
                components["VCP"] = 0.5
            else:
                components["VCP"] = 0.0
        else:
            components["VCP"] = 0.0

        total = round(sum(components.values()), 2)

        if total < cfg["min_score"]:
            return None

        # ── ENTRY BEREKENING ─────────────────────────────────
        stop_price  = round(price - (atr * cfg["atr_multiplier"]), 2)
        stop_pct    = abs(price - stop_price) / price
        if stop_pct > cfg["max_stop_pct"]:
            return None

        target1 = round(price * (1 + cfg["target1_pct"]), 2)
        target2 = round(price * (1 + cfg["target2_pct"]), 2)
        rr      = round((target1 - price) / (price - stop_price), 2)

        return {
            "score":      total,
            "components": components,
            "price":      round(price, 2),
            "ema21":      round(e21, 2),
            "ema50":      round(e50, 2),
            "ema200":     round(e200, 2),
            "rsi":        round(rsi, 1),
            "rs":         round(rs * 100, 2),
            "stop":       stop_price,
            "stop_pct":   round(stop_pct * 100, 1),
            "target1":    target1,
            "target2":    target2,
            "rr":         rr,
            "atr":        round(atr, 2),
        }

    except Exception as e:
        return None

# ─────────────────────────────────────────────────────────────
# HISTORY PER TICKER (laatste N handelsdagen)
# ─────────────────────────────────────────────────────────────
def build_history(df, n=5):
    """Geeft lijst van laatste n handelsdagen met OHLCV + RSI + score-eligibility."""
    rows = []
    tail = df.tail(n)
    for date, row in tail.iterrows():
        try:
            rows.append({
                "date":   date.strftime("%Y-%m-%d"),
                "open":   round(float(row["Open"]), 2),
                "high":   round(float(row["High"]), 2),
                "low":    round(float(row["Low"]), 2),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
                "rsi":    round(float(row["rsi"]), 1) if not np.isnan(row["rsi"]) else None,
            })
        except Exception:
            continue
    return rows

# ─────────────────────────────────────────────────────────────
# MAIN SCANNER
# ─────────────────────────────────────────────────────────────
def run_scanner():
    today     = datetime.now().strftime("%Y-%m-%d")
    scan_time = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    print(f"\n{'='*60}")
    print(f"  VRSO SCANNER — {scan_time}")
    print(f"  Universe: {len(SP500_TICKERS)} tickers")
    print(f"{'='*60}\n")

    # ── Data ophalen ─────────────────────────────────────────
    start_date = (datetime.now() - timedelta(days=CONFIG["lookback_days"])).strftime("%Y-%m-%d")
    end_date   = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")  # morgen = zeker alles t/m vandaag

    print("📥 SPY ophalen...")
    spy_raw = yf.download("SPY", start=start_date, end=end_date, progress=False, auto_adjust=True)
    if spy_raw.empty:
        print("❌ SPY download mislukt")
        return
    spy_close = spy_raw["Close"].squeeze()
    print(f"✅ SPY: {len(spy_raw)} dagen\n")

    print(f"📥 S&P 500 data ophalen ({len(SP500_TICKERS)} tickers)...")
    # Splits in batches van 100 om timeouts te voorkomen
    batch_size = 100
    all_data   = {}

    for i in range(0, len(SP500_TICKERS), batch_size):
        batch = SP500_TICKERS[i:i+batch_size]
        print(f"  Batch {i//batch_size + 1}: tickers {i+1}–{min(i+batch_size, len(SP500_TICKERS))}")
        try:
            raw = yf.download(
                batch,
                start=start_date,
                end=end_date,
                progress=False,
                auto_adjust=True,
                group_by="ticker",
                threads=True,
            )
            for ticker in batch:
                try:
                    if len(batch) == 1:
                        df = raw.copy()
                    elif isinstance(raw.columns, pd.MultiIndex):
                        df = raw[ticker].copy()
                    else:
                        continue
                    df.dropna(subset=["Close", "High", "Low", "Open", "Volume"], inplace=True)
                    if len(df) >= 200:
                        all_data[ticker] = df
                except Exception:
                    continue
        except Exception as e:
            print(f"  ⚠️ Batch fout: {e}")
            continue

    print(f"\n✅ {len(all_data)} tickers succesvol geladen\n")

    # ── Indicatoren + scoring ────────────────────────────────
    print("🔍 Scanning...")
    signals   = []
    errors    = 0

    for ticker, df in all_data.items():
        try:
            df = add_indicators(df, spy_close, CONFIG)
            df.dropna(inplace=True)

            result = score_setup(df, CONFIG)
            if result is None:
                continue

            history = build_history(df, n=CONFIG["history_days"])

            signals.append({
                "ticker":     ticker,
                "name":       COMPANY_NAMES.get(ticker, ticker),
                "score":      result["score"],
                "components": result["components"],
                "price":      result["price"],
                "ema21":      result["ema21"],
                "ema50":      result["ema50"],
                "ema200":     result["ema200"],
                "rsi":        result["rsi"],
                "rs":         result["rs"],
                "stop":       result["stop"],
                "stop_pct":   result["stop_pct"],
                "target1":    result["target1"],
                "target2":    result["target2"],
                "rr":         result["rr"],
                "atr":        result["atr"],
                "history":    history,
                "scan_date":  today,
            })
        except Exception:
            errors += 1
            continue

    # Sorteer op score (hoog → laag)
    signals.sort(key=lambda x: x["score"], reverse=True)

    print(f"\n{'='*60}")
    print(f"  RESULTATEN")
    print(f"  Signals gevonden: {len(signals)}")
    print(f"  Errors: {errors}")
    print(f"{'='*60}")
    for s in signals[:10]:
        print(f"  {s['ticker']:6s}  score={s['score']:.1f}  ${s['price']:.2f}  stop=${s['stop']:.2f}  T1=${s['target1']:.2f}")
    if len(signals) > 10:
        print(f"  ... en {len(signals)-10} meer")
    print()

    # ── Vorige signals laden (voor nieuw/oud onderscheid) ────
    signals_path = os.path.join(os.path.dirname(__file__), "data", "signals.json")
    os.makedirs(os.path.dirname(signals_path), exist_ok=True)

    previous_tickers = set()
    if os.path.exists(signals_path):
        try:
            with open(signals_path, "r") as f:
                prev = json.load(f)
            # Alle tickers van gisteren
            if prev.get("signals"):
                previous_tickers = set(s["ticker"] for s in prev["signals"])
        except Exception:
            pass

    # Markeer nieuw vs. herhaling
    for s in signals:
        s["is_new"] = s["ticker"] not in previous_tickers

    # ── Opslaan ──────────────────────────────────────────────
    output = {
        "scan_time":      scan_time,
        "scan_date":      today,
        "total_scanned":  len(all_data),
        "total_signals":  len(signals),
        "new_signals":    sum(1 for s in signals if s["is_new"]),
        "signals":        signals,
    }

    with open(signals_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"✅ signals.json opgeslagen: {len(signals)} signals")

    # ── Email versturen ──────────────────────────────────────
    send_email(output)

    return output


# ─────────────────────────────────────────────────────────────
# EMAIL NOTIFICATIE
# ─────────────────────────────────────────────────────────────
def send_email(data):
    gmail_user  = os.environ.get("GMAIL_USER")
    gmail_pass  = os.environ.get("GMAIL_PASSWORD")
    notify_to   = os.environ.get("NOTIFY_EMAIL", gmail_user)
    pages_url   = os.environ.get("DASHBOARD_URL", "")

    if not gmail_user or not gmail_pass:
        print("⚠️  Geen email credentials — mail overgeslagen")
        print("   Stel GMAIL_USER en GMAIL_PASSWORD in als environment variable")
        return

    signals   = data["signals"]
    new_count = data["new_signals"]
    total     = data["total_signals"]
    date      = data["scan_date"]

    # Top 5 voor in de mail
    top5 = signals[:5]

    rows = ""
    for s in top5:
        badge = "🆕 NIEUW" if s["is_new"] else "🔁 Herhaling"
        rows += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #333;font-weight:bold;color:#e2e8f0">{s['ticker']}</td>
          <td style="padding:8px;border-bottom:1px solid #333;color:#f6c90e;font-weight:bold">{s['score']:.1f}</td>
          <td style="padding:8px;border-bottom:1px solid #333;color:#e2e8f0">${s['price']:.2f}</td>
          <td style="padding:8px;border-bottom:1px solid #333;color:#48bb78">${s['target1']:.2f}</td>
          <td style="padding:8px;border-bottom:1px solid #333;color:#fc8181">${s['stop']:.2f}</td>
          <td style="padding:8px;border-bottom:1px solid #333;color:#90cdf4">{badge}</td>
        </tr>"""

    dashboard_link = f'<p style="margin-top:20px"><a href="{pages_url}" style="color:#f6c90e;font-size:16px">→ Open dashboard voor volledige lijst</a></p>' if pages_url else ""

    html = f"""
    <html><body style="background:#1a1a2e;color:#e2e8f0;font-family:monospace;padding:20px">
      <h2 style="color:#f6c90e;margin-bottom:4px">VRSO Scanner — {date}</h2>
      <p style="color:#90cdf4;margin-top:0">{total} signals gevonden &nbsp;|&nbsp; {new_count} nieuw</p>
      <table style="border-collapse:collapse;width:100%;background:#16213e;border-radius:8px">
        <thead>
          <tr style="background:#0f3460">
            <th style="padding:10px;text-align:left;color:#f6c90e">Ticker</th>
            <th style="padding:10px;text-align:left;color:#f6c90e">Score</th>
            <th style="padding:10px;text-align:left;color:#f6c90e">Prijs</th>
            <th style="padding:10px;text-align:left;color:#f6c90e">Target 1</th>
            <th style="padding:10px;text-align:left;color:#f6c90e">Stop</th>
            <th style="padding:10px;text-align:left;color:#f6c90e">Status</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      {dashboard_link}
      <p style="color:#4a5568;font-size:11px;margin-top:30px">VRSO Scanner · automatisch gegenereerd · geen beleggingsadvies</p>
    </body></html>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"VRSO Scanner {date} — {total} signals ({new_count} nieuw)"
        msg["From"]    = gmail_user
        msg["To"]      = notify_to
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, notify_to, msg.as_string())

        print(f"✅ Email verstuurd naar {notify_to}")
    except Exception as e:
        print(f"❌ Email fout: {e}")


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run_scanner()
