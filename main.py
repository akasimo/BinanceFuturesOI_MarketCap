
import pickle 
import os
import datetime
import requests
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

from binance.client import Client
from binance.exceptions import BinanceAPIException

TOP_N_VOLUME_SYMBOLS = 10

BINANCE_TO_COINGECKO_MAP = {
    "1000SHIBUSDT": "shib",
    # Add more mappings if needed
}

client = Client("api_key", "api_secret")

def get_futures_open_interest():
    futures_volume_data = client.futures_ticker()
    volume_df = pd.DataFrame(futures_volume_data)
    volume_df = volume_df[volume_df.symbol.str.contains("USDT")]
    for col in ["quoteVolume", "lastPrice", "priceChangePercent"]:
        volume_df[col] = volume_df[col].astype(float)

    top_volume_symbols = volume_df.sort_values(by="quoteVolume", ascending=False).head(TOP_N_VOLUME_SYMBOLS)
    top_volume_symbols["lastPrice"] = top_volume_symbols["lastPrice"].astype(float)

    futures_data = []
    for symbol in top_volume_symbols["symbol"]:
        try:
            open_interest = client.futures_open_interest(symbol=symbol)
            open_interest["openInterest"] = float(open_interest["openInterest"])
            last_price = top_volume_symbols.loc[top_volume_symbols["symbol"] == symbol, "lastPrice"].values[0]
            open_interest["openInterestUSD"] = open_interest["openInterest"] * last_price

            for col in ["quoteVolume", "lastPrice", "priceChangePercent"]:
                open_interest[col] = top_volume_symbols.loc[top_volume_symbols["symbol"] == symbol, col].values[0]

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
    
    if "_" in symbol:
        symbol = symbol.split("_")[0]

    symbol = symbol.replace("USDT", "").replace("BUSD", "")
    if symbol.startswith("1000"):
        symbol = symbol[4:]
    return symbol.lower()

def get_coingecko_market_caps(symbols):
    coingecko_ids = [binance_symbol_to_coingecko_id(symbol) for symbol in symbols]
    file_name = "coingecko_market_data.pkl"

    # Check if the file exists and was modified within the last 24 hours
    if os.path.exists(file_name) and datetime.datetime.fromtimestamp(os.path.getmtime(file_name)) > datetime.datetime.now() - datetime.timedelta(hours=24):
        with open(file_name, "rb") as file:
            market_data_df = pickle.load(file)
    else:
        per_page = 250
        market_data = []
        for page in range(1, 6 + 1):
            url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&per_page={per_page}&page={page}"
            response = requests.get(url)
            page_market_data = response.json()
            market_data.extend(page_market_data)
        market_data_df = pd.DataFrame(market_data)

        # Save the fetched market data to a file
        with open(file_name, "wb") as file:
            pickle.dump(market_data_df, file)

    market_caps = {}
    for symbol, coingecko_id in zip(symbols, coingecko_ids):
        row = market_data_df.loc[market_data_df['symbol'] == coingecko_id]
        if not row.empty:
            market_caps[symbol] = row.iloc[0]['market_cap']
        else:
            print(f"Missing market cap for {symbol} ({coingecko_id})")

    return market_caps

def calculate_oi_market_cap_ratio(open_interest_df, market_caps):
    open_interest_df['market_cap'] = open_interest_df['symbol'].map(market_caps)
    open_interest_df['oi_market_cap_ratio'] = open_interest_df['openInterestUSD'] / open_interest_df['market_cap']
    return open_interest_df.dropna()

def get_futures_hourly_changes(open_interest_df):
    klines = {}
    for symbol in open_interest_df['symbol']:
        kline_data = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_1HOUR, "2 hours ago UTC")
        close_prices = [float(x[4]) for x in kline_data]
        hourly_change = (close_prices[1] - close_prices[0]) / close_prices[0]
        klines[symbol] = hourly_change
    return klines

def plot_scatter(x, y, labels):
    _, ax = plt.subplots(figsize=(12, 8))  # Increase the size of the chart

    ax.scatter(x, y)

    # Add symbol names as annotations to each point
    for i, label in enumerate(labels):
        ax.annotate(label, (x.values[i], y.values[i]), fontsize=8, ha='right', va='bottom')

    ax.set_xlabel('OI/Market Cap')
    ax.set_ylabel('Daily Change')

    ax.grid(True)  # Introduce grid lines
    ax.set_title('OI/Market Cap vs Hourly Change for Top N Volume Symbols')  # Add title

    plt.show()

def plot_joint_scatter_chart(x, y, labels):
    data = {
        'OI/Market Cap': x,
        'Daily Change': y,
        'Symbol': labels
    }

    df = pd.DataFrame(data)

    g = sns.jointplot(data=df,
                      x='OI/Market Cap',
                      y='Daily Change',
                      kind="scatter",
                      marginal_kws=dict(bins=25, fill=False),
                      height=8,
                      alpha=0.6)

    g.set_axis_labels('OI/Market Cap', 'Daily Change', fontsize=12)
    g.fig.suptitle('OI/Market Cap vs Daily Change for Top N Volume Symbols', fontsize=16, y=1.03)

    plt.show()


def create_heatmap(df):
    # Normalize data to a range between 0 and 1
    normalized_df = (df - df.min()) / (df.max() - df.min())

    # Create a pivot table from the DataFrame
    pivot_table = normalized_df.pivot_table(
        values='priceChangePercent',
        index='symbol',
        columns='oi_market_cap_ratio'
    )

    # Generate the heatmap
    fig, ax = plt.subplots(figsize=(12, 8))
    sns.heatmap(pivot_table, annot=True, cmap='coolwarm', ax=ax)
    ax.set_title('Heatmap of OI/Market Cap vs Daily Change for Top N Volume Symbols')
    plt.show()

def main():
    open_interest_df = get_futures_open_interest()
    symbols = open_interest_df['symbol'].unique()
    market_caps = get_coingecko_market_caps(symbols)
    open_interest_df = calculate_oi_market_cap_ratio(open_interest_df, market_caps)
    
    plot_scatter(open_interest_df['oi_market_cap_ratio'], open_interest_df['priceChangePercent'], open_interest_df['symbol'])
    # plot_joint_scatter_chart(open_interest_df['oi_market_cap_ratio'], open_interest_df['priceChangePercent'], open_interest_df['symbol'])
    # create_heatmap(open_interest_df)

if __name__ == "__main__":
    main()
