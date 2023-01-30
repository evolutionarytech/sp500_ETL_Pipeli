from typing import Dict

import pandas as pd

import numpy as np

from datetime import datetime

import boto3
import io
import logging

import pandas_datareader as pdr

start = "2023-01-23"
# setting today date as End Date
end = datetime.today().strftime("%Y-%m-%d")


def extract_sp500_data() -> pd.DataFrame:
    sp500_tickers = pd.read_html(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    )[0]["Symbol"].tolist()

    api_key = "b8048079af04b7e50218c15f24286df5b4c51164"
    data = []
    failed_tickers = []

    for ticker in sp500_tickers:
        try:
            df = pdr.DataReader(ticker, "tiingo", api_key=api_key, start=start, end=end)
            data.append(df)
        except Exception as e:
            print(f"Error while extracting data for {ticker}: {e}")
            failed_tickers.append(ticker)
    if failed_tickers:
        print(f"Failed to retrieve data for the following tickers: {failed_tickers}")
    df = pd.concat(data)

    df.reset_index(drop=False, inplace=True)
    # df = df.to_json(orient="columns")
    print("extraction function complete")
    return df


def transform_stock_data(df: pd.DataFrame) -> pd.DataFrame:
    # df = pd.read_json(df, orient="columns")
    min_periods = 75
    TRADING_DAYS = 252
    try:
        if df.empty:
            print("Dataframe is empty, nothing to transform")
            return
        df.date = pd.to_datetime(df.date)
        df.set_index("date", inplace=True)
        df["daily_pct_change"] = df["adjClose"].pct_change()
        df["20_day"] = df["adjClose"].rolling(20).mean()
        df["200_day"] = df["adjClose"].rolling(200).mean()
        df["std"] = df["adjClose"].rolling(20).std()
        df["bollinger_up"] = df["20_day"] + df["std"] * 2  # Calculate top band
        df["bollinger_down"] = df["20_day"] - df["std"] * 2  # Calculate bottom band
        df["cum_daily_returns"] = (1 + df["daily_pct_change"]).cumprod()
        df["cum_monthly_returns"] = df["cum_daily_returns"].resample("M").mean()
        df["daily_log_returns"] = np.log(df["daily_pct_change"] + 1)
        df["volaltility"] = df["adjClose"].rolling(min_periods).std() * np.sqrt(
            min_periods
        )
        df["returns"] = np.log(df["adjClose"] / df["adjClose"].shift(1))
        df["sharpe_ratio"] = (
            df["returns"].rolling(window=TRADING_DAYS).std()
            * np.sqrt(TRADING_DAYS).mean()
            / df["returns"].rolling(window=TRADING_DAYS).std()
            * np.sqrt(TRADING_DAYS)
        )
        df.reset_index(drop=False, inplace=True)

        print("transformation function complete")
        return df
    except:
        print("error within transformation step")


def load_data_to_s3(
    data: pd.DataFrame,
    bucket_name: str,
    file_name: str,
    access_key: str,
    secret_key: str,
):
    data = data.to_json()
    try:
        s3 = boto3.client(
            "s3", aws_access_key_id=access_key, aws_secret_access_key=secret_key
        )
        if not bucket_exists(s3, bucket_name):
            create_bucket(s3, bucket_name)
        encoded_data = data.encode("utf-8")
        file_stream = io.BytesIO(encoded_data)
        s3.upload_fileobj(file_stream, bucket_name, file_name)
        logging.info(f"Data stored successfully in S3 bucket: {bucket_name}")
    except Exception as e:
        logging.error(f"Error while storing data in S3 bucket: {e}")
        raise


def bucket_exists(s3, bucket_name: str) -> bool:
    response = s3.list_buckets()
    for bucket in response["Buckets"]:
        if bucket["Name"] == bucket_name:
            return True
    return False


def create_bucket(s3, bucket_name: str):
    s3.create_bucket(Bucket=bucket_name)
