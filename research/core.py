"""Financial calculations, filing handling, evidence validation, and benchmarking."""
from __future__ import annotations
import io
import re
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import pandas as pd

METRICS = {
    'revenue': 'Revenue', 'cost_of_revenue': 'Cost of revenue',
    'operating_income': 'Operating income', 'net_income': 'Net income',
    'operating_cash_flow': 'Operating cash flow', 'capex': 'Capital expenditure',
    'total_assets': 'Total assets', 'total_liabilities': 'Total liabilities',
    'cash': 'Cash and equivalents', 'total_debt': 'Total debt',
    'equity': 'Total equity', 'interest_expense': 'Interest expense',
    'depreciation_amortization': 'D&A',
}
FLOW_METRICS = {'revenue','cost_of_revenue','operating_income','net_income','operating_cash_flow','capex','interest_expense','depreciation_amortization'}

@dataclass
class Page:
    source: str
    page: int
    text: str
    def reference(self) -> str:
        return f'{self.source}, p. {self.page}'


def read_document(filename: str, content: bytes) -> list[Page]:
    suffix = Path(filename).suffix.lower()
    if suffix == '.pdf':
        import fitz
        doc = fitz.open(stream=content, filetype='pdf')
        result = [Page(filename, i + 1, page.get_text(sort=True)) for i,page in enumerate(doc)]
        doc.close()
        return result
    if suffix in ('.txt','.md'):
        text = content.decode('utf-8-sig')
        # Form-feed is a page separator in text demo files.
        return [Page(filename, i+1, part) for i,part in enumerate(text.split('\f'))]
    raise ValueError('Supported formats are PDF, TXT and MD')


def normalize_numeric(value):
    """Return numeric value; parentheses indicate negatives. Units handled separately."""
    if value is None or str(value).strip().lower() in ('','n/a','none','null','-','—'):
        return None
    if isinstance(value, (float,int)):
        return float(value)
    s = str(value).strip().replace('$','').replace('£','').replace(',','').replace(' ','')
    negative = s.startswith('(') and s.endswith(')')
    if negative: s = s[1:-1]
    try: return (-1 if negative else 1)*float(s)
    except ValueError: return None


def evidence_supported(row: dict, pages: list[Page]) -> bool:
    """Conservative lexical evidence gate, not semantic proof of accounting correctness."""
    source, page = row.get('source'), row.get('page')
    candidates = [p for p in pages if p.source == source and p.page == page]
    if not candidates: return False
    number = normalize_numeric(row.get('value'))
    if number is None: return False
    raw = candidates[0].text.replace(',','')
    number_str = f'{abs(number):g}'
    return bool(re.search(r'(?<![\d.])'+re.escape(number_str)+r'(?![\d.])', raw))


def make_long(records: list[dict], pages: list[Page]) -> pd.DataFrame:
    clean=[]
    for r in records:
        metric = r.get('metric')
        value = normalize_numeric(r.get('value'))
        try: year = int(r.get('year'))
        except (TypeError,ValueError): continue
        if metric not in METRICS or value is None or year < 1990 or year > 2100: continue
        row = dict(metric=metric, year=year, value=value,
                   source=str(r.get('source','')),page=int(r.get('page',0)),
                   unit=str(r.get('unit','USD millions')),
                   evidence=str(r.get('evidence',''))[:500],
                   method=str(r.get('method','unknown')))
        row['source_check'] = evidence_supported(row,pages)
        clean.append(row)
    return pd.DataFrame(clean,columns=['metric','year','value','source','page','unit','evidence','method','source_check'])


def analyse_financials(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return pd.DataFrame()
    # Do not accidentally combine figures with incompatible currency/unit bases.
    work = df.sort_values(['year','source_check'],ascending=[True,False]).drop_duplicates(['year','metric'],keep='first')
    pivot = work.pivot(index='year',columns='metric',values='value').sort_index()
    def val(key): return pivot[key] if key in pivot.columns else pd.Series(float('nan'),index=pivot.index)
    def ratio(n,d):
        return n.div(d.where(d != 0)).mul(100)
    out = pd.DataFrame(index=pivot.index)
    out['Revenue'] = val('revenue')
    out['Revenue growth %'] = val('revenue').pct_change(fill_method=None).mul(100)
    out['Gross margin %'] = ratio(val('revenue')-val('cost_of_revenue'),val('revenue'))
    out['Operating margin %'] = ratio(val('operating_income'),val('revenue'))
    out['Net margin %'] = ratio(val('net_income'),val('revenue'))
    out['EBITDA'] = val('operating_income') + val('depreciation_amortization')
    out['EBITDA margin %'] = ratio(out['EBITDA'],val('revenue'))
    out['FCF'] = val('operating_cash_flow') - val('capex').abs()
    out['FCF margin %'] = ratio(out['FCF'],val('revenue'))
    out['Debt / equity'] = val('total_debt').div(val('equity').where(val('equity')!=0))
    out['Net debt'] = val('total_debt') - val('cash')
    out['Interest coverage'] = val('operating_income').div(val('interest_expense').abs().replace(0,float('nan')))
    return out.round(2)


def evaluate(predicted: pd.DataFrame, gold: pd.DataFrame, tolerance: float=0.005) -> dict:
    """Key-level recall/precision; accuracy within relative tolerance, or small abs tolerance near zero."""
    required={'metric','year','value','source'}
    if not required.issubset(gold.columns): raise ValueError('Gold data needs metric, year, value, source')
    if gold.duplicated(['source','year','metric']).any(): raise ValueError('Gold contains duplicate keys')
    pk = {} if predicted.empty else { (r.source,int(r.year),r.metric): float(r.value) for r in predicted.itertuples() }
    gk = {(r.source,int(r.year),r.metric):float(r.value) for r in gold.itertuples()}
    matches = set(pk)&set(gk)
    correct = sum(abs(pk[k]-gk[k]) <= max(0.01,abs(gk[k])*tolerance) for k in matches)
    accuracy = correct/len(matches) if matches else 0.0
    precision = correct/len(pk) if pk else 0.0
    recall = correct/len(gk) if gk else 0.0
    f1 = (2*precision*recall/(precision+recall)) if precision+recall else 0.0
    return {'expected_fields':len(gk),'extracted_fields':len(pk),'matched_keys':len(matches),
            'correct_values':correct,'value_accuracy_on_matched':accuracy,
            'field_precision':precision,'field_recall':recall,'field_f1':f1,
            'source_check_rate':float(predicted['source_check'].mean()) if not predicted.empty and 'source_check' in predicted else 0.0}


def savings(manual_minutes: float, automation_seconds: float, review_minutes: float, filings: int) -> dict:
    if manual_minutes <= 0 or automation_seconds < 0 or review_minutes < 0 or filings <= 0:
        raise ValueError('Manual time and number of filings must be positive. Other times cannot be negative.')
    auto_per = automation_seconds/60/filings + review_minutes
    saved = manual_minutes-auto_per
    return {'manual_minutes_per_filing':manual_minutes,'automated_plus_review_minutes_per_filing':round(auto_per,2),
            'minutes_saved_per_filing':round(saved,2),'time_reduction_pct':round(100*saved/manual_minutes,1),
            'total_hours_saved':round(saved*filings/60,2)}
