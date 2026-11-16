from pathlib import Path
import pandas as pd
import pytest
from research.core import read_document, analyse_financials, evaluate, savings, normalize_numeric
from research.extraction import deterministic_extract, structured_summary

DEMO=Path(__file__).resolve().parents[1]/'demo'/'Orion_Systems_FY2024.txt'

def data():
    pages=read_document(DEMO.name,DEMO.read_bytes())
    return pages, deterministic_extract(pages)

def test_parse_and_source():
    pages,df=data()
    assert len(pages)==3
    assert len(df)==39
    assert df.source_check.all()

def test_ratios():
    _,df=data()
    fin=analyse_financials(df)
    assert fin.loc[2024,'Revenue']==1540
    assert fin.loc[2024,'EBITDA']==317
    assert fin.loc[2024,'FCF']==148
    assert fin.loc[2024,'Revenue growth %']==round((1540/1320-1)*100,2)
    assert fin.loc[2024,'Operating margin %']==round(255/1540*100,2)

def test_gold():
    _,df=data()
    gold=pd.read_csv(DEMO.parent/'gold_labels.csv')
    r=evaluate(df,gold)
    assert r['correct_values']==39
    assert r['field_precision']==r['field_recall']==1.0

def test_failure_reduces_precision():
    _,df=data()
    gold=pd.read_csv(DEMO.parent/'gold_labels.csv')
    df.loc[0,'value']=9999
    assert evaluate(df,gold)['field_precision'] < 1

def test_reference_validation():
    pages,df=data()
    summary=structured_summary(analyse_financials(df),df,pages)
    assert '[Orion_Systems_FY2024.txt, p.' in summary['findings'][0]

def test_time_savings():
    r=savings(45,120,10,2)
    assert r['minutes_saved_per_filing']==34
    with pytest.raises(ValueError): savings(0,3,5,1)

def test_numeric():
    assert normalize_numeric('(1,250)')==-1250
    assert normalize_numeric('—') is None
