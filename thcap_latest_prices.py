#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Collect most recent data from SetTrade.com web site on all stocks.
Save to JSON file. Thread program defined in optjar.live.priceCaptureThread and controlled in thcapd.
More Information: https://docs.google.com/presentation/d/16_o6492Quo8b3fJDorOjLAXnYPuHF1TpdyoC5B20Mjo/
"""

import requests
from bs4 import BeautifulSoup
import os, os.path, shutil
from datetime import datetime
import json
import tarfile

def capture():
    ts = datetime.now()
    
    archiveFolder = os.path.join(os.path.abspath("."),"""price-data""")
    dataFolder = os.path.join(os.path.abspath("."),"""market-data""") # this is cleared after each collection
    startPage = """http://www.settrade.com/C13_MarketSummary.jsp?detail=STOCK_TYPE&order=N&market=SET&type=S"""
    snapshotFile = os.path.join(dataFolder, "snapshot" + ts.strftime("%Y%m%d_%H%M") + ".dat")
    archiveFile = os.path.join(archiveFolder, "market" + ts.strftime("%Y%m%d") + ".tar")
    r = requests.get(startPage)
    # check content received OK
    # print r.status_code, r.content[:100]
    
    # Make sure data folder is reader.
    if os.path.exists(dataFolder):
        shutil.rmtree(dataFolder) # Remove existing folder and data if exists.
    # Creating folder
    os.mkdir(dataFolder)
    
    # Save the index page
    indexFile = os.path.join(dataFolder, "market" + ts.strftime("%Y%m%d_%H%M") + ".html")
    with open(indexFile, "w") as f:
        f.write(r.content)
    
    # load into BeautifulSoup
    soup = BeautifulSoup(r.content, 'html.parser')
    # print soup
    
    def get_quotes_links(soup):
        links = soup.find_all("a")
        for link in links:
            if link.has_attr('href'):
                if link.attrs['href'].startswith("/C13_FastQuote_Main.jsp"):
                    # print link.get_text()
                    # print link.attrs
                    yield link
    
    print datetime.now().strftime("%Y%m%d_%H%M")
    
    market_data = {}
    market_data['src'] = startPage
    market_data['ts'] = str(ts)
    market_data['data'] = {}
    market_data['stat'] = {}
    
    # stats: aggregrate over the information extracted
    market_data['stat']['symbols_count'] = 0
    market_data['stat']['average_price_thb'] = 0.0
    market_data['stat']['total_shares_value_thb'] = 0.0
    changes_obs = []
    
    for link in get_quotes_links(soup):
        # print link
        # print link.parent.parent.get_text()
        try:
            raw_data_cell = link.parent.parent.get_text().split('\n')
        except e:
            print str(e)
            break
        raw_data_cell.remove('') # realign cell. Remove empty element.
        symbol = raw_data_cell[0].encode('ascii',errors='ignore') # Remove non ascii chars
        if '<' in symbol: # for flaged stocks
            symbol = symbol[:symbol.find('<')]
            n = raw_data_cell[0].encode('ascii',errors='ignore')
            flag = n[n.find('<'):]
        price_open = raw_data_cell[1]
        price_high = raw_data_cell[2]
        price_low = raw_data_cell[3]
        price_latest = raw_data_cell[4]
        price_change = raw_data_cell[5]
        pct_change = raw_data_cell[6]
        price_bid = raw_data_cell[7]
        price_offer = raw_data_cell[8]
        shares_volume = raw_data_cell[9]
        shares_value_thb  = raw_data_cell[10]
    
        try:
            shares_volume = float(shares_volume.replace(',',''))
        except ValueError:
            shares_volume = 0
        try:
            shares_value_thb = float(shares_value_thb.replace(',','')) * 1000.0
        except ValueError:
            shares_value_thb = 0
    
        # aggregrate stats for data checking
        market_data['stat']['symbols_count'] += 1
        market_data['stat']['total_shares_value_thb'] += shares_value_thb
    
        # Observed price: 
        #  determine from this order:  price_latest > price_bid > price_offer
        try:
            observed_price = float(price_latest.replace(',',''))
        except ValueError:
            try:
                observed_price = float(price_bid.replace(',',''))
            except ValueError:
                try:
                    observed_price = float(price_offer.replace(',',''))
                except ValueError:
                    observed_price = None
    
        # add observed price to the average
        if observed_price:
            price0 = market_data['stat']['average_price_thb'] 
            price1 = (price0 + observed_price) / 2
            market_data['stat']['average_price_thb'] = price1
    
        # Pct Changes Observation
        try:
            chg1 = float(pct_change.replace(',',''))
            changes_obs.append(chg1)
        except ValueError:
            pass # don't include observation
    
        market_data['data'][symbol] = {}
        market_data['data'][symbol]['symbol'] = symbol
        market_data['data'][symbol]['price_open'] = price_open
        market_data['data'][symbol]['price_low'] = price_low
        market_data['data'][symbol]['price_high'] = price_high
        market_data['data'][symbol]['price_latest'] = price_latest
        market_data['data'][symbol]['price_change'] = price_change
        market_data['data'][symbol]['pct_change'] = pct_change
        market_data['data'][symbol]['price_bid'] = price_bid
        market_data['data'][symbol]['price_offer'] = price_offer
        market_data['data'][symbol]['shares_volume_qty'] = shares_volume
        market_data['data'][symbol]['shares_value_thb'] = shares_value_thb
    
    # Save the data file in json
    dataFile = os.path.join(dataFolder, "market" + ts.strftime("%Y%m%d_%H%M") + ".json")
    with open(dataFile, "w") as f:
        f.write(json.dumps(market_data, sort_keys=True, indent=4, separators=(',', ': ')))
    
    # Save to latest file overwriting previous data
    # Some checks perform:
    #  1. number of symbols in market_data dictionary more than 50
    #  2. average price computed returns a floating point number
    #  3. sum of shares values more than 500,000.00 THB
    
    print "Thai Market Data: %s" % ts
    print "Data Source: SetTrade.com, set.or.th (public data)"
    
    if market_data['stat']['symbols_count'] > 50:
        print "Number of securities observed OK. (%s > 50)" % market_data['stat']['symbols_count']
    
    if isinstance(market_data['stat']['average_price_thb'], float):
        print "Price average OK. (%0.4f THB)" % market_data['stat']['average_price_thb']
    
    if market_data['stat']['total_shares_value_thb'] > 500000:
        trade_value = "{:,}".format(market_data['stat']['total_shares_value_thb'])
        print "Total value of shares traded OK. (%s THB)" % trade_value
    
    # Harmonic mean of price changes
    # https://www.investopedia.com/terms/h/harmonicaverage.asp
    #
    # changes_obs is the list of pct_changes
    #
    
    print "Individual Percent Changes:"
    print changes_obs
    
    market_data['stat']['average_change_pct'] = sum([ x for x in changes_obs  ] ) / market_data['stat']['symbols_count'] 
    
    print "Stats:"
    print market_data['stat']
    
    outFile = os.path.join(dataFolder, "latest-price.json")
    with open(outFile, "w") as f:
        f.write(json.dumps(market_data, sort_keys=True, indent=4, separators=(',', ': ')))
        
    fileTimestamp = ts.strftime("%Y%m%d_%H%M%S")
    compressedOutFile = "market-%s.tar.gz" % fileTimestamp
    with tarfile.open(compressedOutFile, "w:gz") as t:
        t.add(outFile, arcname="market-%s.json" % fileTimestamp)
        print compressedOutFile, t.list()
    
    # Archive result
    with tarfile.open(archiveFile, "a:") as t:
        t.add(compressedOutFile)
        print archiveFile, t.list()
        
    print "Archive:", archiveFile
    
    # Cleanup:
    # 1. Move archive to permanent storage
    # 2. Cleanup working dir "market-data"
    # shutil.move(archiveFile, "price-data/") # archive append to price-data/market<DATE>.tar.gz
    # 3. Remove intermediate compressed file
    shutil.rmtree(dataFolder)
    os.remove(compressedOutFile)


if __name__ == '__main__':
    capture()  # do capture