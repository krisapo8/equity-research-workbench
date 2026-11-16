"""US SEC EDGAR ticker lookup and XBRL-based annual company research.

SEC facts are machine-readable filing data, not full-document interpretation.
Amounts normalized to USD millions. URLs point to SEC filing archive indices.
"""
from __future__ import annotations
from datetime import date
from typing import Any
import re
import requests
import pandas as pd
from .core import analyse_financials

TICKERS_URL = 'https://www.sec.gov/files/company_tickers.json'
BASE = 'https://data.sec.gov'
# Ordered aliases. Only published US-GAAP facts are used.
TAGS = {
 'revenue': ['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','RevenueFromContractWithCustomerIncludingAssessedTax','SalesRevenueGoodsNet'],
 'cost_of_revenue': ['CostOfRevenue','CostOfGoodsAndServicesSold','CostOfGoodsSold'],
 'operating_income': ['OperatingIncomeLoss'],
 'net_income': ['NetIncomeLoss'],
 'operating_cash_flow': ['NetCashProvidedByUsedInOperatingActivities'],
 'capex': ['PaymentsToAcquirePropertyPlantAndEquipment'],
 'total_assets': ['Assets'],
 'total_liabilities': ['Liabilities'],
 'cash': ['CashAndCashEquivalentsAtCarryingValue'],
 'total_debt': ['LongTermDebtAndFinanceLeaseObligationsIncludingCurrentMaturities','LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities','LongTermDebt'],
 'equity': ['StockholdersEquity','StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'],
 'interest_expense': ['InterestExpenseNonOperating','InterestExpense'],
 'depreciation_amortization': ['DepreciationDepletionAndAmortization','DepreciationDepletionAndAmortizationPropertyPlantAndEquipment','DepreciationAmortizationAndAccretionNet'],
}
FLOW = {'revenue','cost_of_revenue','operating_income','net_income','operating_cash_flow','capex','interest_expense','depreciation_amortization'}


def fetch_json(url: str, identity: str) -> dict:
    if not identity or not re.search(r'[^\s@]+@[^\s@]+\.[^\s@]+',identity):
        raise ValueError('Enter a contact email for the SEC User-Agent, such as Your Name you@example.com.')
    response = requests.get(url, headers={'User-Agent': f'EquityResearchWorkbench {identity}', 'Accept-Encoding':'gzip, deflate', 'Accept':'application/json'}, timeout=25)
    if response.status_code in (403,429):
        raise RuntimeError('SEC access was blocked or rate-limited. Check your contact identity, then retry later.')
    response.raise_for_status()
    return response.json()


def lookup_company(query: str, identity: str) -> dict:
    q=query.strip().upper()
    if not q: raise ValueError('Enter a US-listed ticker or a company name.')
    data=fetch_json(TICKERS_URL,identity)
    companies=list(data.values()) if isinstance(data,dict) else data
    exact=[c for c in companies if c['ticker'].upper()==q]
    if exact: return exact[0]
    by_name=[c for c in companies if c['title'].upper()==q]
    if len(by_name)==1: return by_name[0]
    starts=[c for c in companies if c['title'].upper().startswith(q)]
    if len(starts)==1: return starts[0]
    matches=[c for c in companies if q in c['title'].upper()]
    if len(matches)==1: return matches[0]
    if matches or starts:
        choices=starts or matches
        raise ValueError('Company name is ambiguous. Use its ticker instead. Matches: '+', '.join(f"{c['ticker']} ({c['title']})" for c in choices[:7]))
    raise ValueError('No SEC-listed company found. Check the ticker or company name. Non-US companies are not yet supported.')


def _annual_options(facts: dict, metric: str, years: int) -> list[dict]:
    usgaap=facts.get('facts',{}).get('us-gaap',{})
    options=[]
    for alias_rank,tag in enumerate(TAGS[metric]):
        concept=usgaap.get(tag, {})
        for unit,observations in concept.get('units',{}).items():
            if unit!='USD': continue
            for f in observations:
                if f.get('form') not in ('10-K','10-K/A'): continue
                if f.get('fp')!='FY': continue
                if f.get('val') is None or not f.get('end'): continue
                end_year=int(f['end'][:4]); fy=f.get('fy')
                if fy is not None and abs(int(fy)-end_year)>1: continue
                if metric in FLOW:
                    if not f.get('start'): continue
                    duration=(date.fromisoformat(f['end'])-date.fromisoformat(f['start'])).days
                    if duration<330 or duration>380: continue
                else:
                    if f.get('start'): continue
                options.append({**f,'metric':metric,'tag':tag,'alias_rank':alias_rank,'year':end_year})
    return options


def extract_sec_facts(facts: dict, cik: int, years: int=5) -> pd.DataFrame:
    """One annual value per metric/year. Prefer taxonomy specificity and most recently filed FY facts.

    We deliberately leave missing tags blank rather than reconstructing them with unsafe assumptions.
    """
    rows=[]
    all_options={m:_annual_options(facts,m,years) for m in TAGS}
    available=sorted({r['year'] for opts in all_options.values() for r in opts if r['metric']=='revenue'},reverse=True)[:years]
    if not available:
        available=sorted({r['year'] for opts in all_options.values() for r in opts},reverse=True)[:years]
    for metric,opts in all_options.items():
        for year in available:
            candidates=[r for r in opts if r['year']==year]
            if not candidates: continue
            # Prioritise annual frames when supplied, then original statement tags, then filing date.
            candidates.sort(key=lambda r:(r['frame']==f'CY{year}' if r.get('frame') else False,-r['alias_rank'],r.get('filed',''),r.get('accn','')),reverse=True)
            r=candidates[0]
            accession=r.get('accn','')
            archive=(f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/' if accession else '')
            rows.append({'year':year,'metric':metric,'value':abs(r['val'])/1e6 if metric in ('capex','interest_expense') else r['val']/1e6,
                         'unit':'USD millions','tag':r['tag'],'filing':r.get('form',''), 'filed':r.get('filed',''),
                         'accession':accession,'source_url':archive,'source':'SEC EDGAR XBRL',
                         'page':None,'evidence':f"{r['tag']} = {r['val']:,} USD, period ended {r['end']}",
                         'method':'SEC XBRL','source_check':False})
    return pd.DataFrame(rows,columns=['metric','year','value','unit','tag','filing','filed','accession','source_url','source','page','evidence','method','source_check'])


def fetch_company_research(query: str, identity: str, years: int=5):
    company=lookup_company(query,identity)
    cik=int(company['cik_str'])
    facts=fetch_json(f'{BASE}/api/xbrl/companyfacts/CIK{cik:010d}.json',identity)
    values=extract_sec_facts(facts,cik,years=years)
    if values.empty: raise ValueError('No comparable annual USD XBRL financial values were found for this company.')
    return company, values, analyse_financials(values)


def filing_linked_findings(company: dict, values: pd.DataFrame, financials: pd.DataFrame) -> dict:
    """Grounded deterministic summary, suitable without an LLM key."""
    latest=financials.index.max()
    prior=financials.index[financials.index<latest]
    conclusions=[]
    risks=[]
    def src(metric,year):
        r=values[(values.metric==metric)&(values.year==year)]
        if len(r): return r.iloc[0]['source_url']
        return ''
    def f(v): return pd.notna(v)
    revenue=financials.loc[latest,'Revenue']
    if f(revenue):
        line=f"FY{latest} revenue was ${revenue:,.1f}m"
        growth=financials.loc[latest,'Revenue growth %']
        if f(growth): line+=f', up {growth:.1f}% year on year' if growth>=0 else f', down {abs(growth):.1f}% year on year'
        conclusions.append({'finding':line+'.','metric':'revenue','url':src('revenue',latest)})
    for key,metric,label,unit in [('Operating margin %','operating_income','Operating margin','%'),('Net margin %','net_income','Net margin','%'),('FCF','operating_cash_flow','Free cash flow','$m'),('Debt / equity','total_debt','Debt/equity','x')]:
        v=financials.loc[latest,key]
        if f(v):
            fmt=f'${v:,.1f}m' if unit=='$m' else f'{v:.1f}{unit}' if unit=='%' else f'{v:.2f}x'
            conclusions.append({'finding':f'FY{latest} {label.lower()} was {fmt}.','metric':metric,'url':src(metric,latest)})
    if len(prior)==0: risks.append('Insufficient historical observations to assess financial trends.')
    absent=[m for m in ('revenue','net_income','operating_cash_flow','total_debt') if not len(values[(values.metric==m)&(values.year==latest)])]
    if absent: risks.append('Missing latest-year values: '+', '.join(absent)+'. The analysis does not fill gaps with estimates.')
    risks.append('XBRL tags can differ across issuers. Annual SEC facts alone cannot establish competitive positioning, valuation or the causes of reported performance.')
    return {'findings':conclusions,'risks':risks}


def llm_sec_summary(company: dict, values: pd.DataFrame, financials: pd.DataFrame, api_key: str, model: str='gpt-4.1-mini') -> str:
    from openai import OpenAI
    evidence=values.sort_values(['year','metric']).tail(65)[['metric','year','value','tag','source_url']].to_dict('records')
    prompt=f'''Company: {company['title']} ({company['ticker']}).\nSEC-reported US-GAAP annual XBRL evidence (USD millions): {evidence}\nDerived ratios: {financials.round(2).to_string()}\nWrite a concise analyst overview, historical trends, cash generation, balance sheet and limitations. Use only supplied numbers. Link every material numerical claim to its matching source_url using Markdown inline links. For computed ratios, cite the source figures and identify the ratio as calculated. Do not invent management commentary, catalysts, valuation or recommendations. Mention any material missing values. Treat this as a preliminary financial screen, not a complete annual-report review.'''
    client=OpenAI(api_key=api_key)
    resp=client.responses.create(model=model,input=[{'role':'system','content':'You are a cautious equity research assistant. Never fabricate figures or sources.'},{'role':'user','content':prompt}])
    return resp.output_text
