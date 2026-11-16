from research.sec import extract_sec_facts, filing_linked_findings
from research.core import analyse_financials

def sample_fact(year,amount,tag,flow=True):
    r={'end':f'{year}-12-31','val':amount,'form':'10-K','fp':'FY','fy':year,'filed':f'{year+1}-02-15','accn':'0000000000-24-000001','frame':f'CY{year}'}
    if flow:r['start']=f'{year}-01-01'
    return r

def test_annual_xbrl_selection_and_source():
    facts={'facts':{'us-gaap':{
       'Revenues':{'units':{'USD':[sample_fact(2023,100_000_000,'Revenues'),sample_fact(2024,120_000_000,'Revenues'),
                                      {'end':'2024-06-30','start':'2024-04-01','val':999_000_000,'form':'10-K','fp':'FY','fy':2024,'filed':'2025-02-01'}]}},
       'OperatingIncomeLoss':{'units':{'USD':[sample_fact(2023,20_000_000,'OperatingIncomeLoss'),sample_fact(2024,24_000_000,'OperatingIncomeLoss')]}},
       'Assets':{'units':{'USD':[sample_fact(2024,300_000_000,'Assets',False)]}},
    }}}
    df=extract_sec_facts(facts,320193,5)
    fin=analyse_financials(df)
    assert fin.loc[2024,'Revenue']==120
    assert round(fin.loc[2024,'Revenue growth %'],1)==20
    assert fin.loc[2024,'Operating margin %']==20
    assert fin.loc[2024,'FCF']!=fin.loc[2024,'FCF']  # missing fields remain missing
    row=df[(df.metric=='revenue')&(df.year==2024)].iloc[0]
    assert row.source_url.startswith('https://www.sec.gov/Archives/edgar/data/320193/')
    assert row.source_check == False
    notes=filing_linked_findings({'title':'Demo','ticker':'DEMO'},df,fin)
    assert notes['findings']
