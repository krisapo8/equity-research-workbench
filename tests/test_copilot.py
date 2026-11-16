import pandas as pd
from research.copilot import evidence_pack, validate_citations, health_screen
from research.reporting import make_html_report


def fixtures():
    company={'title':'Acme <script>bad()</script>','ticker':'TEST'}
    facts=pd.DataFrame([{'year':2024,'metric':'revenue','value':250.0,'tag':'Revenues',
                         'filed':'2025-03-01','source_url':'https://www.sec.gov/Archives/a'},
                        {'year':2024,'metric':'cash','value':10.0,'tag':'Cash','filed':'2025-03-01','source_url':'https://evil.example/a'}])
    fin=pd.DataFrame([{'year':2024,'Revenue':250.0,'Revenue growth %':10.0,'Operating margin %':12.0,
                       'FCF':20,'Net margin %':5,'EBITDA margin %':16}]).set_index('year')
    return company,facts,fin


def test_evidence_rejects_external_links():
    company,facts,fin=fixtures()
    pack=evidence_pack(company,facts,fin)
    assert len(pack['facts'])==1
    assert pack['facts'][0]['id']=='F1'
    assert len(pack['computed_ratios'])==1


def test_reject_unsupported_claims():
    company,facts,fin=fixtures()
    pack=evidence_pack(company,facts,fin)
    claims=validate_citations([{'claim':'valid','evidence_ids':['F1']},{'claim':'invented','evidence_ids':['F200']}],pack)
    assert len(claims)==1 and claims[0]['sources'][0]['id']=='F1'


def test_health_screen_is_transparent():
    _,_,fin=fixtures()
    flags=health_screen(fin)
    assert len(flags)==4
    assert all(i['status']=='Positive' for i in flags)
    assert all('test' in i for i in flags)


def test_html_export_escapes_company():
    company,facts,fin=fixtures()
    output=make_html_report(company,facts,fin,{'findings':[{'finding':'Revenue grew','url':'https://www.sec.gov/Archives/a'}]})
    assert '<script>' not in output
    assert '&lt;script&gt;' in output
    assert 'Revenue grew' in output
