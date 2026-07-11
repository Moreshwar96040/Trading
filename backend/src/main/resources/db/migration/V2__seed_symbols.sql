-- V2: Seed the 20-stock NSE symbol master (matches nse_dataset/).
-- Idempotent: ON CONFLICT DO NOTHING.

INSERT INTO symbols (ticker, yahoo_symbol, name, sector) VALUES
    ('RELIANCE',   'RELIANCE.NS',   'Reliance Industries Ltd',        'Oil & Gas'),
    ('TCS',        'TCS.NS',        'Tata Consultancy Services Ltd',  'IT'),
    ('HDFCBANK',   'HDFCBANK.NS',   'HDFC Bank Ltd',                  'Banking'),
    ('SUNPHARMA',  'SUNPHARMA.NS',  'Sun Pharmaceutical Industries',  'Pharma'),
    ('MARUTI',     'MARUTI.NS',     'Maruti Suzuki India Ltd',        'Auto'),
    ('HINDUNILVR', 'HINDUNILVR.NS', 'Hindustan Unilever Ltd',         'FMCG'),
    ('TATASTEEL',  'TATASTEEL.NS',  'Tata Steel Ltd',                 'Steel'),
    ('BHARTIARTL', 'BHARTIARTL.NS', 'Bharti Airtel Ltd',              'Telecom'),
    ('LT',         'LT.NS',         'Larsen & Toubro Ltd',            'Construction'),
    ('ULTRACEMCO', 'ULTRACEMCO.NS', 'UltraTech Cement Ltd',           'Cement'),
    ('ASIANPAINT', 'ASIANPAINT.NS', 'Asian Paints Ltd',               'Paints'),
    ('NTPC',       'NTPC.NS',       'NTPC Ltd',                       'Power'),
    ('TITAN',      'TITAN.NS',      'Titan Company Ltd',              'Jewellery/Retail'),
    ('DMART',      'DMART.NS',      'Avenue Supermarts Ltd',          'Retail'),
    ('BAJFINANCE', 'BAJFINANCE.NS', 'Bajaj Finance Ltd',              'NBFC'),
    ('COALINDIA',  'COALINDIA.NS',  'Coal India Ltd',                 'Mining'),
    ('INDIGO',     'INDIGO.NS',     'InterGlobe Aviation Ltd',        'Aviation'),
    ('ADANIPORTS', 'ADANIPORTS.NS', 'Adani Ports & SEZ Ltd',          'Logistics'),
    ('UPL',        'UPL.NS',        'UPL Ltd',                        'Agrochem'),
    ('APOLLOHOSP', 'APOLLOHOSP.NS', 'Apollo Hospitals Enterprise',    'Healthcare')
ON CONFLICT (ticker, exchange) DO NOTHING;
