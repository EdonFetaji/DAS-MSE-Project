import os
import time
import aiohttp
import asyncio
import requests
import pandas as pd
import numpy as np
from io import StringIO
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import re


def create_directory(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)


async def get_one_year_stock_data(session, stockname, from_date, until_date):
    data = {
        "FromDate": from_date.strftime("%m/%d/%Y"),
        "ToDate": until_date.strftime("%m/%d/%Y"),
        "Code": stockname
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Referer": f"https://www.mse.mk/en/stats/symbolhistory/{stockname}"
    }
    try:
        async with session.post("https://www.mse.mk/en/stats/symbolhistory/" + stockname, data=data,
                                headers=headers) as response:
            if response.status == 200:
                html_content = await response.text()

                tables = pd.read_html(StringIO(html_content))
                if tables:
                    print(f"Data for {stockname} in {from_date.year} collected.")

                    return tables[0]
                else:
                    print(f"No tables found for {stockname} in {from_date.year}.")

            else:
                print(
                    f"HTTP RESPONSE ERROR: Failed to retrieve data for {stockname} in {from_date.year}, Status: {response.status}")

    except Exception as e:
        print(f"Error fetching data for {stockname} in {from_date.year}: {e}")


async def get_all_data_for_one_stock(session, stock, last_date, directory):
    data_array = []

    from_date = datetime.now().date()
    until_date = from_date
    while until_date > last_date:

        if until_date - last_date >= timedelta(days=365):
            data_array.append(
                await get_one_year_stock_data(session, stock, until_date - timedelta(days=365), until_date))
            until_date -= timedelta(days=365)
        else:
            data_array.append(await get_one_year_stock_data(session, stock, last_date, until_date))
            break

    data_array = list(filter(lambda x: x is not None, data_array))
    if len(data_array) == 0:
        print(f"No data found for {stock} in {last_date.year}.")
        return None

    new_data = pd.concat(data_array, ignore_index=True)
    file_path = os.path.join(directory, f"{stock}.csv")

    # If file already exists, read its existing data and append new data
    if os.path.exists(file_path):
        existing_data = pd.read_csv(file_path)
        combined_data = pd.concat([new_data, existing_data], ignore_index=True)
        combined_data.to_csv(file_path, index=False)
        print(f"Data for {stock} updated and saved to {file_path}")
    else:
        # If file doesn't exist, just save the new data
        new_data.to_csv(file_path, index=False)
        print(f"Data for {stock} saved to {file_path}")

    return file_path


async def get_all_stocks_data(stocks):
    directory = os.path.join(os.getcwd(), 'All_Stock_Data')
    create_directory(directory)
    connector = aiohttp.TCPConnector(limit=21)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [get_all_data_for_one_stock(session, stock['Code'], stock['Date'], directory) for stock in stocks]
        results = await asyncio.gather(*tasks)
        return results


def get_stock_names():
    response = requests.get("https://www.mse.mk/en/stats/symbolhistory/ALK")
    soup = BeautifulSoup(response.text, 'html.parser')
    codes = map(lambda x: x.text.strip(), soup.select("#Code option"))
    stocks = [
        s for s in codes
        if not (s.startswith('E') or any(char.isdigit() for char in s))
    ]

    return check_last_date_available(stocks)


def check_last_date_available(stocks):
    stocks_objects = []
    for s in stocks:
        stock_object = {"Code": s}
        file = os.path.join(os.getcwd(), 'All_Stock_Data', f"{s}.csv")
        if os.path.exists(file):
            df = pd.read_csv(file)
            date_str = df.loc[1, 'Date']
            date = datetime.strptime(date_str, '%d.%m.%Y').date()
            stock_object["Date"] = date
        else:
            stock_object["Date"] = datetime.now().date() - timedelta(days=3650)

        stocks_objects.append(stock_object)

    return stocks_objects


def process_data(files):
    def format_date_to_european(date_str):
        try:
            date_obj = datetime.strptime(date_str, '%m/%d/%Y')
            return date_obj.strftime('%d.%m.%Y')
            # return date_obj.strftime('%m/%d/%Y')

        except (ValueError, TypeError):
            return date_str

    def format_price(value):
        if isinstance(value, str):
            parts = re.split(r'\D', value)
            if len(parts[-1]) <= 2:
                decimal_part = parts.pop()
                integer_part = ''.join(parts)
                cleaned_value = f"{integer_part}.{decimal_part}"
            else:
                cleaned_value = ''.join(parts)

            try:
                cleaned_float = float(cleaned_value)
                return f"{cleaned_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            except ValueError:
                return "Invalid input format"

        elif isinstance(value, (int, float)):
            return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        return "Invalid input format"

    for filename in files:
        if filename:
            df = pd.read_csv(filename)

            if "Date" in df.columns:
                df["Date"] = df["Date"].apply(format_date_to_european)
            for col in df.columns:
                if col != 'Date':
                    df[col] = df[col].apply(format_price)
            df.to_csv(filename, index=False)
            print(f"Formatted price and date in {filename}.")


async def main():
    stocks = get_stock_names()

    start_time = time.time()
    files = await get_all_stocks_data(stocks)
    end_time = time.time()

    elapsed_time = end_time - start_time
    process_data(files)
    print(f"Program elapsed time: {elapsed_time} seconds")


if __name__ == "__main__":
    asyncio.run(main())
