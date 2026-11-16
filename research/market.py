"""Indicative delayed market quotes. Yahoo Finance is not an institutional licensed feed."""
from datetime import datetime,timezone
import pandas as pd

def quote(ticker: str) -> dict:
    import yfinance as yf
    item=yf.Ticker(ticker)
    info=item.info or {}
    price=info.get('currentPrice') or info.get('regularMarketPrice')
    shares=info.get('sharesOutstanding')
    cap=info.get('marketCap')
    currency=info.get('currency')
    return {'ticker':ticker.upper(),'price':float(price) if price else None,
            'shares_m':float(shares)/1e6 if shares else None,
            'market_cap_m':float(cap)/1e6 if cap else None,
            'currency':currency,'retrieved_utc':datetime.now(timezone.utc).isoformat(),
            'source':'Yahoo Finance via yfinance (indicative; may be delayed)'}

def peer_table(tickers, fetch_fundamentals, identity):
    from .valuation import peer_multiples
    rows=[]
    for ticker in dict.fromkeys(t.strip().upper() for t in tickers if t.strip()):
        try:
            company,facts,fin=fetch_fundamentals(ticker,identity,2)
            q=quote(ticker)
            if q['currency']!='USD':
                rows.append({'Ticker':ticker,'Error':'Non-USD quote; FX conversion not implemented'})
                continue
            latest=fin.iloc[-1]; year=int(fin.index[-1]); current=facts[facts.year==year].set_index('metric')['value'].to_dict()
            multiple=peer_multiples(q['market_cap_m'],current.get('total_debt'),current.get('cash'),latest['Revenue'],latest['EBITDA'],current.get('net_income'))
            rows.append({'Ticker':ticker,'Company':company['title'],'Fiscal year':year,'Quote UTC':q['retrieved_utc'],**multiple,'Error':''})
        except Exception as exc:
            rows.append({'Ticker':ticker,'Error':str(exc)[:150]})
    return pd.DataFrame(rows)
