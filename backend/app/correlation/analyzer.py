import pandas as pd

def compute_correlation_matrix(dfs: dict) -> pd.DataFrame:
    close_dfs = []
    for ticker, df in dfs.items():
        close_dfs.append(df['Close'].rename(ticker))
        
    aligned = pd.concat(close_dfs, axis=1, join='inner')
    returns = aligned.pct_change().dropna()
    return returns.corr()

def compute_rolling_correlation(df1: pd.DataFrame, df2: pd.DataFrame, window: int) -> pd.Series:
    aligned = pd.concat([df1['Close'], df2['Close']], axis=1, join='inner')
    returns = aligned.pct_change().dropna()
    if returns.empty:
        return pd.Series(dtype=float)
    return returns.iloc[:, 0].rolling(window).corr(returns.iloc[:, 1]).dropna()
