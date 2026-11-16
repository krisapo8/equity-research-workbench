import pytest
from research.valuation import Assumptions,dcf,scenarios,sensitivity,peer_multiples
from research.filings import excerpts,benchmark_filing_findings
import pandas as pd

def test_dcf_consistency():
    r=dcf(1000,100,100,2024,Assumptions())
    assert len(r['forecast'])==5
    assert r['enterprise_value']==pytest.approx(r['pv_fcff']+r['pv_terminal_value'])
    assert r['equity_value']==pytest.approx(r['enterprise_value']-100)
    assert r['value_per_share']==pytest.approx(r['equity_value']/100)

def test_scenarios_ordered():
    results,_=scenarios(1000,100,100,2024,Assumptions())
    assert results['Bear']['value_per_share']<results['Base']['value_per_share']<results['Bull']['value_per_share']

def test_invalid_wacc():
    with pytest.raises(ValueError): dcf(1000,100,100,2024,Assumptions(wacc=0.02,terminal_growth=0.03))

def test_sensitivity_shape():
    assert sensitivity(1000,100,100,2024,Assumptions()).shape==(5,5)

def test_peer_missing():
    r=peer_multiples(1000,None,50,200,10,30)
    assert r['Enterprise value'] is None and r['P / E']==pytest.approx(1000/30)

def test_filing_excerpts_cited():
    text=('Item 1. Business We manufacture specialised semiconductors and sell internationally. '*12+'Item 1A. Risk Factors demand can vary widely. '*10)
    out=excerpts(text,'https://www.sec.gov/a',span=500)
    assert out and all(e['source_url']=='https://www.sec.gov/a' for e in out)

def test_review_benchmark():
    result=benchmark_filing_findings({},pd.DataFrame({'correct':[1,0],'source_support':[1,1]}))
    assert result['factual_accuracy']==.5 and result['citation_support_rate']==1
