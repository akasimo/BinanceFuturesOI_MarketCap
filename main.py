from binance.client import Client
from binance.exceptions import BinanceAPIException

import pandas as pd
import requests
import matplotlib.pyplot as plt

BINANCE_TO_COINGECKO_MAP = {
    "1000SHIBUSDT": "shib",
    # Add more mappings if needed
}

api_key = "YOUR_API_KEY"
api_secret = "YOUR_API_SECRET"

client = Client(api_key, api_secret)
from binance.exceptions import BinanceAPIException

def get_futures_open_interest():
    try:
        futures_volume_data = client.futures_ticker()
    except BinanceAPIException as e:
        print(f"Error fetching 24-hour ticker for all symbols: {e.message}")
        return pd.DataFrame()

    volume_df = pd.DataFrame(futures_volume_data)
    volume_df = volume_df[volume_df.symbol.str.contains("USDT")]
    volume_df["quoteVolume"] = volume_df["quoteVolume"].astype(float)
    top_20_volume_symbols = volume_df.sort_values(by="quoteVolume", ascending=False).head(20)
    top_20_volume_symbols["lastPrice"] = top_20_volume_symbols["lastPrice"].astype(float)

    futures_data = []
    for symbol in top_20_volume_symbols["symbol"]:
        try:
            open_interest = client.futures_open_interest(symbol=symbol)
            open_interest["openInterest"] = float(open_interest["openInterest"])
            last_price = top_20_volume_symbols.loc[top_20_volume_symbols["symbol"] == symbol, "lastPrice"].values[0]
            open_interest["openInterestUSD"] = open_interest["openInterest"] * last_price
            futures_data.append(open_interest)
        except BinanceAPIException as e:
            if e.code == -4108:
                print(f"Skipping symbol {symbol}: {e.message}")
            else:
                raise e

    open_interest_df = pd.DataFrame(futures_data)
    return open_interest_df

def binance_symbol_to_coingecko_id(symbol):
    if symbol in BINANCE_TO_COINGECKO_MAP:
        return BINANCE_TO_COINGECKO_MAP[symbol]

    symbol = symbol.replace("USDT", "").replace("BUSD", "")
    if symbol.startswith("1000"):
        symbol = symbol[4:]
    return symbol.lower()

def get_coingecko_market_caps(symbols):
    coingecko_ids = [binance_symbol_to_coingecko_id(symbol) for symbol in symbols]
    # url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd"
    # response = requests.get(url)
    # market_data = response.json()
    # market_data_df = pd.DataFrame(market_data)

    per_page = 1000
    market_data = []
    for page in range(1, 3 + 1):
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&per_page={per_page}&page={page}"
        response = requests.get(url)
        page_market_data = response.json()
        market_data.extend(page_market_data)
    market_data_df = pd.DataFrame(market_data)

    market_caps = {}
    for symbol, coingecko_id in zip(symbols, coingecko_ids):
        row = market_data_df.loc[market_data_df['symbol'] == coingecko_id]
        if not row.empty:
            market_caps[symbol] = row.iloc[0]['market_cap']
        else:
            pass
    return market_caps

# def get_coingecko_market_data(symbols):
#     coingecko_ids = [binance_symbol_to_coingecko_id(symbol) for symbol in symbols]
#     market_data = []
#     for coingecko_id in coingecko_ids:
#         try:
#             data = cg.get_coin_by_id(coingecko_id)
#             market_data.append({
#                 "id": data["id"],
#                 "symbol": data["symbol"].upper(),
#                 "market_cap": data["market_data"]["market_cap"]["usd"]
#             })
#         except Exception as e:
#             print(f"Error fetching market data for {coingecko_id}: {e}")
#     market_data_df = pd.DataFrame(market_data)
#     return market_data_df


def calculate_oi_market_cap_ratio(open_interest_df, market_caps):
    open_interest_df['market_cap'] = open_interest_df['symbol'].map(market_caps)
    open_interest_df['oi_market_cap_ratio'] = open_interest_df['openInterest'] / open_interest_df['market_cap']
    return open_interest_df

def get_futures_hourly_changes(open_interest_df):
    klines = {}
    for symbol in open_interest_df['symbol']:
        kline_data = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_1HOUR, "2 hours ago UTC")
        close_prices = [float(x[4]) for x in kline_data]
        hourly_change = (close_prices[1] - close_prices[0]) / close_prices[0]
        klines[symbol] = hourly_change
    return klines

def plot_scatter(oi_market_cap_ratios, hourly_changes):
    fig, ax = plt.subplots()
    ax.scatter(oi_market_cap_ratios, hourly_changes)
    ax.set_xlabel('OI/Market Cap')
    ax.set_ylabel('Hourly Change')
    plt.show()

def main():
    open_interest_df = get_futures_open_interest()
    symbols = open_interest_df['symbol'].unique()
    
    market_caps = get_coingecko_market_caps(symbols)
    open_interest_df = calculate_oi_market_cap_ratio(open_interest_df, market_caps)
    
    hourly_changes = get_futures_hourly_changes(open_interest_df)
    open_interest_df['hourly_change'] = open_interest_df['symbol'].map(hourly_changes)
    
    plot_scatter(open_interest_df['oi_market_cap_ratio'], open_interest_df['hourly_change'])
    a = 1

if __name__ == "__main__":
    main()
