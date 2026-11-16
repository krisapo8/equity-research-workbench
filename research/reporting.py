"""Self-contained, escape-safe research report export."""
import html
from datetime import datetime,timezone
import pandas as pd


def make_html_report(company, facts, financials, findings, ai_note='', copilot=None):
    name=html.escape(str(company['title']))
    ticker=html.escape(str(company['ticker']))
    generated=datetime.now(timezone.utc).strftime('%d %B %Y %H:%M UTC')
    rows=[]
    metrics=['Revenue','Revenue growth %','EBITDA','Operating margin %','Net margin %','FCF','Net debt']
    for yr, rec in financials.iterrows():
        cells=''.join('<td>'+ ('N/A' if pd.isna(rec.get(k)) else f'{float(rec[k]):,.2f}')+'</td>' for k in metrics)
        rows.append(f'<tr><td>{int(yr)}</td>{cells}</tr>')
    evidence=''.join('<li>'+html.escape(str(f['finding']))+' '+
                     ('<a href="'+html.escape(str(f['url']),quote=True)+'">SEC filing</a>' if str(f.get('url','')).startswith('https://www.sec.gov/') else '')+'</li>'
                     for f in findings.get('findings',[]))
    headers=''.join('<th>'+html.escape(x)+'</th>' for x in ['Year']+metrics)
    ai='<section><h2>AI commentary</h2><pre>'+html.escape(str(ai_note))+'</pre></section>' if ai_note else ''
    notes=''
    if copilot:
        notes='<section><h2>AI copilot research</h2>'
        for item in copilot.get('claims',[]):
            notes+='<p>'+html.escape(item['claim'])+'</p><ul>'
            for source in item['sources']:
                notes+='<li><a href="'+html.escape(source['source_url'],quote=True)+'">'+html.escape(source['id'])+'</a></li>'
            notes+='</ul>'
        notes+='</section>'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{ticker} | Equity Research</title><style>
body{{font:15px/1.65 system-ui,-apple-system,sans-serif;max-width:1080px;margin:48px auto;padding:0 28px;color:#14243c}}
h1{{font-size:38px;margin:0}}h2{{margin-top:35px;border-bottom:1px solid #ddd;padding-bottom:7px}}
.subtitle{{color:#64748b}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:10px;border-bottom:1px solid #dde3eb;text-align:right}}
:first-child:is(th,td){{text-align:left}}th{{background:#edf3fa}}a{{color:#1456ab}}pre{{white-space:pre-wrap;font:inherit}}
.warning{{padding:16px;background:#f4f6fa;border-radius:8px;margin-top:30px}}@media print{{body{{margin:12mm auto}}}}
</style></head><body><p class="subtitle">EQUITY INTELLIGENCE / COMPANY RESEARCH</p><h1>{name} ({ticker})</h1>
<p class="subtitle">Generated {generated} · USD millions unless otherwise stated</p>
<section><h2>Historical financial performance</h2><table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table></section>
<section><h2>Source-linked observations</h2><ul>{evidence}</ul></section>{ai}{notes}
<div class="warning">Research aid only. SEC-reported figures and calculated ratios may be incomplete or differently defined.
AI findings, excerpts, and valuations require human verification before investment decisions.</div></body></html>'''
