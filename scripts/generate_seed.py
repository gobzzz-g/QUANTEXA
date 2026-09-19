import yfinance as yf
import pandas as pd
import os
import hashlib
from datetime import datetime

seed_dir = "data/seed"
os.makedirs(seed_dir, exist_ok=True)

tickers = ["BTC-USD", "GC=F", "NVDA"]

manifest = []

for t in tickers:
    print(f"Downloading {t}...")
    df = yf.download(t, period="5y")
    if not df.empty:
        # Multi-index fix for yfinance > 0.2.30 if needed, but assuming standard here
        csv_path = os.path.join(seed_dir, f"{t}.csv")
        df.to_csv(csv_path)
        
        with open(csv_path, 'rb') as f:
            checksum = hashlib.md5(f.read()).hexdigest()
            
        manifest.append({
            "ticker": t,
            "download_date": datetime.utcnow().isoformat(),
            "row_count": len(df),
            "checksum": checksum
        })

pd.DataFrame(manifest).to_csv(os.path.join(seed_dir, "manifest.csv"), index=False)
print("Seed data generated.")
