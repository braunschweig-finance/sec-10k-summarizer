"""
Broad sector for a company from its SEC Standard Industrial Classification (SIC) code, the industry code SEC assigns
each filer (shown on every EDGAR company page). The SIC ranges are grouped into eleven sectors named like the GICS
sectors investors know. It's this site's own grouping of SEC's codes, so a few companies land differently from GICS
(Alphabet and Meta file under SIC 7370, computer services, so they count as Information Technology here, not
Communication Services).
"""

# (first SIC, last SIC, sector), checked in order, so narrower ranges come before the broad ones that contain them
RANGES = [
    (100, 999, "Consumer Staples"),             # agriculture
    (1000, 1099, "Materials"),                  # metal mining
    (1200, 1299, "Energy"),                     # coal
    (1300, 1399, "Energy"),                     # oil and gas extraction and services
    (1400, 1499, "Materials"),                  # nonmetallic minerals
    (1500, 1799, "Industrials"),                # construction
    (2000, 2199, "Consumer Staples"),           # food, beverages, tobacco
    (2200, 2399, "Consumer Discretionary"),     # textiles, apparel
    (2400, 2499, "Materials"),                  # lumber and wood
    (2500, 2599, "Consumer Discretionary"),     # furniture
    (2600, 2699, "Materials"),                  # paper
    (2700, 2799, "Communication Services"),     # printing and publishing
    (2830, 2836, "Health Care"),                # drugs, biologics
    (2840, 2844, "Consumer Staples"),           # soap, cleaners, cosmetics
    (2800, 2899, "Materials"),                  # other chemicals
    (2900, 2999, "Energy"),                     # petroleum refining
    (3020, 3021, "Consumer Discretionary"),     # footwear
    (3000, 3099, "Materials"),                  # rubber and plastics
    (3100, 3199, "Consumer Discretionary"),     # leather
    (3200, 3399, "Materials"),                  # stone, glass, primary metals
    (3400, 3499, "Industrials"),                # fabricated metal products
    (3570, 3579, "Information Technology"),     # computers and office equipment
    (3500, 3599, "Industrials"),                # other machinery
    (3630, 3639, "Consumer Discretionary"),     # household appliances
    (3640, 3649, "Industrials"),                # lighting and wiring
    (3650, 3652, "Consumer Discretionary"),     # household audio and video
    (3690, 3699, "Industrials"),                # other electrical equipment
    (3600, 3699, "Information Technology"),     # electronic components, semiconductors, communications equipment
    (3710, 3716, "Consumer Discretionary"),     # motor vehicles and parts
    (3790, 3799, "Consumer Discretionary"),     # motorcycles, trailers, RVs
    (3700, 3799, "Industrials"),                # aircraft, ships, railroad equipment, defense
    (3812, 3812, "Industrials"),                # defense electronics and navigation
    (3840, 3851, "Health Care"),                # medical instruments and supplies
    (3870, 3873, "Consumer Discretionary"),     # watches
    (3800, 3899, "Information Technology"),     # measuring and analytical instruments
    (3900, 3999, "Consumer Discretionary"),     # jewelry, toys, sporting goods
    (4950, 4959, "Industrials"),                # waste management
    (4900, 4999, "Utilities"),                  # electric, gas, water
    (4800, 4899, "Communication Services"),     # telecom, broadcasting, cable
    (4000, 4799, "Industrials"),                # transportation
    (5120, 5122, "Health Care"),                # drug wholesale
    (5140, 5149, "Consumer Staples"),           # grocery wholesale
    (5170, 5172, "Energy"),                     # petroleum wholesale
    (5000, 5199, "Industrials"),                # other wholesale
    (5400, 5499, "Consumer Staples"),           # grocery stores
    (5910, 5912, "Consumer Staples"),           # drug stores
    (5200, 5999, "Consumer Discretionary"),     # other retail and restaurants
    (6500, 6599, "Real Estate"),                # real estate operators and developers
    (6798, 6798, "Real Estate"),                # REITs
    (6000, 6799, "Financials"),                 # banks, brokers, insurance, holding companies
    (7000, 7099, "Consumer Discretionary"),     # hotels
    (7200, 7299, "Consumer Discretionary"),     # personal services
    (7370, 7379, "Information Technology"),     # software and computer services
    (7300, 7399, "Industrials"),                # other business services
    (7500, 7599, "Consumer Discretionary"),     # auto services
    (7990, 7999, "Consumer Discretionary"),     # amusement and recreation (casinos, theme parks)
    (7800, 7899, "Communication Services"),     # movies and entertainment
    (8000, 8099, "Health Care"),                # health services
    (8200, 8299, "Consumer Discretionary"),     # education
    (8000, 8999, "Industrials"),                # engineering, consulting and other services
]


def sector(sic):
    """The sector for a SIC code (int or string), or None if there's no code."""
    try:
        code = int(str(sic).strip())
    except (TypeError, ValueError):
        return None
    return next((name for lo, hi, name in RANGES if lo <= code <= hi), None)
