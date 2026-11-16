"""Deterministic sample parser plus optional LLM extraction with page citations."""
from __future__ import annotations
import re
from pydantic import BaseModel
from .core import METRICS, Page, make_long

class ExtractedItem(BaseModel):
    metric: str
    year: int
    value: float
    source: str
    page: int
    unit: str
    evidence: str

class ExtractionBatch(BaseModel):
    items: list[ExtractedItem]

class SummaryResponse(BaseModel):
    findings: list[str]
    risks: list[str]

LINE = re.compile(r'^\s*([^|\n]+?)\s*\|\s*(20\d{2})\s*\|\s*([$(£)\d,.-]+)\s*\|\s*(USD millions|GBP millions|EUR millions)\s*$',re.I)


def deterministic_extract(pages: list[Page]):
    """For explicitly delimited demo/test data only. Real annual reports require LLM mode."""
    from .core import normalize_numeric
    records=[]
    aliases={v.lower():k for k,v in METRICS.items()}
    aliases.update({k.replace('_',' '):k for k in METRICS})
    aliases['depreciation and amortization']='depreciation_amortization'
    for page in pages:
        for line in page.text.splitlines():
            m = LINE.match(line)
            if not m: continue
            metric=aliases.get(m.group(1).strip().lower())
            value=normalize_numeric(m.group(3))
            if metric and value is not None:
                records.append({'metric':metric,'year':int(m.group(2)),'value':value,
                                'source':page.source,'page':page.page,'unit':m.group(4),
                                'evidence':line.strip(),'method':'rule-based'})
    return make_long(records,pages)


def llm_extract(pages: list[Page], api_key: str, model: str='gpt-4.1-mini', max_chars: int=14000):
    """Page-wise extraction. Returns only claims with a page; output carries source_check flag."""
    from openai import OpenAI
    client=OpenAI(api_key=api_key)
    records=[]
    for page in pages:
        if not page.text.strip(): continue
        chunks=[page.text[i:i+max_chars] for i in range(0,len(page.text),max_chars)]
        for chunk in chunks:
            response=client.responses.parse(
                model=model,
                input=[{'role':'system','content':(
                    'You are a careful financial statement extraction engine. Extract ONLY explicitly stated '
                    'financial amounts from the provided page. Allowed metrics: '+', '.join(METRICS.keys())+'. '
                    'Every item MUST use the exact provided source filename and page. '
                    'Do not infer numbers, calculate metrics, or fill missing fields. '
                    'Only USD millions, GBP millions or EUR millions are accepted. '
                    'Convert amounts stated in thousands or billions to millions. '
                    'Record the actual financial fiscal year associated with each figure, including comparable columns. '
                    'Cash flow and P&L fields are annual, not quarterly, unless explicitly stated annual. '
                    'Capital expenditure and interest expense should be positive magnitudes. '
                    'Evidence should contain a short direct quotation of the number and its label. '
                    'Never treat a number in the wrong unit/currency as an acceptable result.')},
                    {'role':'user','content':f'SOURCE: {page.source}\nPAGE: {page.page}\nTEXT:\n{chunk}'}],
                text_format=ExtractionBatch)
            parsed=response.output_parsed
            if parsed is None: continue
            for item in parsed.items:
                if item.source==page.source and item.page==page.page:
                    records.append({**item.model_dump(),'method':f'LLM ({model})'})
    return make_long(records,pages)


def structured_summary(financials, extracted, pages, api_key: str|None=None, model='gpt-4.1-mini'):
    """Narrative with exact citations from verified evidence, never generated arbitrary sources."""
    evidence=extracted[extracted['source_check']] if not extracted.empty else extracted
    lines=[]
    for r in evidence.head(100).itertuples():
        lines.append(f'{r.metric} {r.year} = {r.value:g} {r.unit} [{r.source}, p. {r.page}]')
    if not lines:
        return {'findings':['No source-checked numerical evidence available. Upload an extractable filing or use the demo.'], 'risks':['Evidence unavailable: do not rely on unsupported figures.']}
    if not api_key:
        findings=[]
        for r in evidence.head(12).itertuples():
            findings.append(f'{METRICS[r.metric]} ({r.year}): {r.value:,.1f} {r.unit} [{r.source}, p. {r.page}]')
        return {'findings':findings, 'risks':['Rule-based summary only. Supply an API key for synthesised analyst commentary.']}
    from openai import OpenAI
    client=OpenAI(api_key=api_key)
    response=client.responses.parse(model=model,
        input=[{'role':'system','content':(
            'Write concise, balanced equity research inferences based only on provided verified evidence. '
            'Every factual bullet MUST include at least one exact [filename, p. N] citation present in the evidence. '
            'No price targets or investment recommendations. Do not invent comparisons, trends or causes. '
            'Identify material missing data explicitly. Return 3-6 findings and 2-4 risks.')},
               {'role':'user','content':'Verified evidence:\n'+'\n'.join(lines)+'\nCalculated ratios (derived, not separate filing claims):\n'+financials.to_string()}],
        text_format=SummaryResponse)
    result=response.output_parsed
    if result is None: raise RuntimeError('Model returned no structured summary')
    citations=set(f'[{r.source}, p. {r.page}]' for r in evidence.itertuples())
    # Block unsupported narratives rather than display fake source references.
    def valid(s):
        found=re.findall(r'\[[^\[\]]+?, p\. \d+\]',s)
        return bool(found) and all(c in citations for c in found)
    findings=[f for f in result.findings if valid(f)]
    risks=[r for r in result.risks if valid(r)]
    return {'findings':findings or ['No model findings passed source-reference validation.'],
            'risks':risks or ['No model risk statements passed source-reference validation.']}
