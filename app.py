"""Equity Research Workbench: run with `streamlit run app.py`."""
import os
import time
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from research.core import read_document, analyse_financials, evaluate, savings, METRICS
from research.extraction import deterministic_extract, llm_extract, structured_summary
from research.sec import fetch_company_research, filing_linked_findings, llm_sec_summary
from research.valuation import Assumptions, dcf, scenarios, sensitivity
from research.market import quote, peer_table
from research.filings import recent_10k, filing_text, excerpts, analyse_filing_ai, benchmark_filing_findings


def env_or_secret(key):
    value=os.getenv(key)
    if value:return value
    try:return st.secrets.get(key,'')
    except Exception:return ''

st.set_page_config(page_title='Equity Research Workbench',page_icon='📊',layout='wide')
st.markdown('''<style>
.block-container {padding-top: 2rem; max-width: 1300px}
[data-testid="stMetric"] {border: 1px solid rgba(128,128,128,.2);border-radius:12px;padding:15px}
h1,h2,h3 {letter-spacing:-.02em}
</style>''',unsafe_allow_html=True)
st.title('Equity Research Workbench')
st.caption('Filing extraction · financial analysis · evidence-backed research · validation')

with st.sidebar:
    st.header('Data source')
    mode=st.radio('Filing source',['Ticker lookup (US SEC)','Illustrative demo','Upload company filings'],label_visibility='collapsed')
    if mode=='Ticker lookup (US SEC)':
        ticker_query=st.text_input('Company name or ticker',value='AAPL',help='US SEC registrants only, e.g. AAPL, MSFT, NVDA')
        sec_identity=st.text_input('SEC contact identity',value=env_or_secret('SEC_USER_AGENT'),placeholder='Your Name you@example.com',help='SEC requires a declared User-Agent with contact email. No account or SEC API key required.')
        sec_years=st.slider('Annual financial years',3,10,5)
    uploads=[]
    if mode=='Upload company filings':
        uploads=st.file_uploader('Annual reports or filings',type=['pdf','txt','md'],accept_multiple_files=True)
        st.caption('Use one company and a consistent currency/unit basis per analysis. Text PDFs only. Image-based scans need OCR first.')
    st.header('Extraction')
    if mode!='Ticker lookup (US SEC)':
        extraction_mode=st.radio('Method',['Rule-based demo parser','LLM structured extraction'])
        st.caption('Rule-based parser requires pipe-delimited demo lines. Use LLM for real narrative filings.')
    else:
        extraction_mode='SEC XBRL (automatic)'
        st.caption('Financial data comes from SEC XBRL. The LLM is optional for the written interpretation.')
    api_key=st.text_input('OpenAI API key (optional for demo)',type='password',value=env_or_secret('OPENAI_API_KEY'))
    model=st.text_input('Extraction and summary model',value='gpt-4.1-mini')
    do_extract=st.button('Generate company report' if mode=='Ticker lookup (US SEC)' else 'Run research',type='primary',use_container_width=True)
    st.divider()
    st.caption('Research outputs are provisional. Source checks verify textual numeric presence, not the accounting interpretation. Review before investment use.')

if 'research_df' not in st.session_state: st.session_state.research_df=None
if 'source_pages' not in st.session_state: st.session_state.source_pages=[]
if 'run_time' not in st.session_state: st.session_state.run_time=None
if mode=='Ticker lookup (US SEC)':
    st.subheader('Ticker-driven company research')
    st.caption('Free SEC EDGAR financial fundamentals, five-year trends, linked reported facts and optional AI commentary. US reporting companies only.')
    if do_extract:
        try:
            start=time.perf_counter()
            with st.spinner('Retrieving SEC financial facts and calculating financial ratios...'):
                company, facts, financials=fetch_company_research(ticker_query,sec_identity,sec_years)
            st.session_state['ticker_report']={'company':company,'facts':facts,'financials':financials,'seconds':time.perf_counter()-start}
            st.session_state['ticker_ai_note']=None
        except Exception as exc:
            st.error(f'Could not generate ticker report: {exc}')
    report=st.session_state.get('ticker_report')
    if not report:
        st.info('Enter AAPL, MSFT, NVDA or another US-listed ticker, add your contact email for SEC access, and select Generate company report.')
        st.stop()
    company=report['company']; facts=report['facts']; fin=report['financials']
    if ticker_query.strip().upper() not in (company['ticker'].upper(),company['title'].upper()):
        st.info('The displayed report belongs to the previous search. Click Generate company report to update it.')
    st.markdown(f"### {company['title']} ({company['ticker']})")
    st.caption(f"SEC CIK {int(company['cik_str']):010d} | {len(fin)} annual periods | USD millions | SEC XBRL filing data | Automated in {report['seconds']:.1f} seconds")
    latest=fin.iloc[-1]
    metrics=st.columns(4)
    for col,key,suffix in zip(metrics,['Revenue','Revenue growth %','Operating margin %','FCF'],[' USD m','%','%',' USD m']):
        val=latest[key]
        col.metric(key,('N/A' if pd.isna(val) else f'{val:,.1f}{suffix}'))
    summary,history,valuation,peers,filings,evidence=st.tabs(['Company report','Historical financials','DCF valuation','Comparable companies','AI filing analysis','SEC evidence'])
    with summary:
        note=filing_linked_findings(company,facts,fin)
        st.markdown('#### Financial highlights')
        for item in note['findings']:
            if item['url']:
                st.markdown(f"- {item['finding']} [SEC filing]({item['url']})")
            else:
                st.markdown(f"- {item['finding']}")
        st.markdown('#### Key limitations and analyst questions')
        for risk in note['risks']: st.markdown(f'- {risk}')
        st.divider()
        st.markdown('#### AI research commentary (optional)')
        if not api_key:
            st.info('Enter your OpenAI API key in the sidebar to generate a written AI analyst commentary. Financial highlights and ratios above work without an API key.')
        if st.button('Generate AI commentary',disabled=not bool(api_key)):
            try:
                with st.spinner('Writing the source-linked overview...'):
                    st.session_state['ticker_ai_note']=llm_sec_summary(company,facts,fin,api_key,model)
            except Exception as exc: st.error(f'AI commentary failed: {exc}')
        if st.session_state.get('ticker_ai_note'):
            st.markdown(st.session_state['ticker_ai_note'])
        body=f"# {company['title']} ({company['ticker']})\n\n## SEC financial highlights\n"
        body+='\n'.join(f"- {it['finding']} {it['url']}" for it in note['findings'])
        body+='\n\n## Limitations\n'+'\n'.join(f'- {x}' for x in note['risks'])
        if st.session_state.get('ticker_ai_note'): body+='\n\n## AI commentary\n'+st.session_state['ticker_ai_note']
        st.download_button('Download research report (Markdown)',body,f"{company['ticker']}_research.md",'text/markdown')
    with history:
        columns=[c for c in ['Revenue','EBITDA','FCF','Net debt'] if fin[c].notna().any()]
        if columns:
            fig=px.line(fin.reset_index(),x='year',y=columns,markers=True)
            fig.update_layout(yaxis_title='USD millions',xaxis=dict(dtick=1))
            st.plotly_chart(fig,use_container_width=True)
        st.dataframe(fin.style.format(precision=2,na_rep='N/A'),use_container_width=True)
        st.download_button('Download financial ratios (CSV)',fin.to_csv().encode(),f"{company['ticker']}_ratios.csv",'text/csv')

    with valuation:
        st.subheader('Five-year discounted cash flow')
        st.caption('Analyst scenario assumptions, not broker consensus estimates. All monetary amounts USD millions. This FCFF model uses an EBIT-based tax calculation and a terminal perpetuity growth method.')
        last_year=int(fin.index[-1]); current=facts[facts.year==last_year].set_index('metric')['value'].to_dict()
        rev=latest['Revenue']; net_debt=latest['Net debt']
        if pd.isna(rev) or pd.isna(net_debt):
            st.error('DCF requires annual revenue, debt and cash figures. Missing fields must be resolved before valuation.')
        else:
            c1,c2,c3=st.columns(3)
            with c1:
                growth=st.number_input('Base annual revenue growth (%)',-40.0,100.0,8.0,0.5)/100
                margin_default=float(latest['Operating margin %']) if pd.notna(latest['Operating margin %']) else 23.0
                margin=st.number_input('EBIT margin (%)',0.0,90.0,max(0.0,min(margin_default,90.0)),0.5)/100
                tax=st.number_input('Cash tax assumption (%)',0.0,60.0,21.0,0.5)/100
            with c2:
                da=st.number_input('D&A as % of revenue',0.0,40.0,3.5,0.5)/100
                capex=st.number_input('Capex as % of revenue',0.0,60.0,4.5,0.5)/100
                nwc=st.number_input('Change in NWC / revenue increase (%)',-50.0,50.0,2.0,0.5)/100
            with c3:
                wacc=st.number_input('WACC (%)',1.0,40.0,10.0,0.5)/100
                terminal_growth=st.number_input('Terminal growth (%)',-5.0,10.0,2.5,0.5)/100
                shares=st.number_input('Diluted shares outstanding (millions)',min_value=0.001,value=1000.0,step=1.0,help='Required share count. Obtain from the latest filing or quote provider and review dilution. Not auto-filled from annual XBRL.')
            if st.button('Load indicative share count from market quote',key='load_share'):
                try:
                    q=quote(company['ticker'])
                    if q['shares_m']:
                        st.session_state['suggested_shares']=q['shares_m']
                        st.success(f"Indicative diluted-share proxy: {q['shares_m']:,.2f} million outstanding shares. Yahoo Finance, retrieved {q['retrieved_utc']}. Enter this figure into the diluted shares field after verifying its basis.")
                    else: st.warning('Quote provider did not return shares outstanding.')
                except Exception as exc:st.error(f'Could not retrieve market quote: {exc}')
            try:
                a=Assumptions(growth,margin,tax,da,capex,nwc,wacc,terminal_growth)
                results,assumptions=scenarios(float(rev),float(net_debt),float(shares),last_year,a)
                summary_table=pd.DataFrame([{'Scenario':name,'Annual growth':assumptions[name].revenue_growth,'EBIT margin':assumptions[name].ebit_margin,'WACC':assumptions[name].wacc,'Terminal growth':assumptions[name].terminal_growth,'EV (USD m)':r['enterprise_value'],'Equity (USD m)':r['equity_value'],'Value/share (USD)':r['value_per_share'],'Terminal EV weight (%)':r['terminal_weight_pct']} for name,r in results.items()]).set_index('Scenario')
                st.dataframe(summary_table.style.format({'Annual growth':'{:.1%}','EBIT margin':'{:.1%}','WACC':'{:.1%}','Terminal growth':'{:.1%}','EV (USD m)':'{:,.1f}','Equity (USD m)':'{:,.1f}','Value/share (USD)':'${:,.2f}','Terminal EV weight (%)':'{:.1f}'}),use_container_width=True)
                st.plotly_chart(px.bar(summary_table.reset_index(),x='Scenario',y='Value/share (USD)',title='Illustrative per-share intrinsic value'),use_container_width=True)
                st.markdown('#### Base-case forecast')
                st.dataframe(results['Base']['forecast'].style.format(precision=1),use_container_width=True)
                st.markdown('#### WACC / terminal growth sensitivity, USD per share')
                sens=sensitivity(float(rev),float(net_debt),float(shares),last_year,a)
                sens.index=sens.index.map(lambda x:f'{x:.1%}')
                st.dataframe(sens.style.format('${:,.2f}',na_rep='N/A'),use_container_width=True)
                st.download_button('Download DCF scenarios (CSV)',summary_table.to_csv(),f"{company['ticker']}_dcf.csv",'text/csv')
                st.download_button('Download base DCF forecast (CSV)',results['Base']['forecast'].to_csv(index=False),f"{company['ticker']}_dcf_forecast.csv",'text/csv')
                st.caption('Terminal value relies heavily on WACC and growth. Taxes, working capital, leases and share dilution require analyst validation. EBITDA can be tracked in financial history; FCFF is projected from EBIT, D&A, capex and working capital.')
            except Exception as exc: st.error(f'DCF input issue: {exc}')
    with peers:
        st.subheader('Comparable company multiples')
        st.caption('Quotes come from Yahoo Finance via yfinance and may be delayed, stale or unavailable. Fundamental denominators come from the latest available annual SEC XBRL filing. Figures are not automatically date-aligned or peer-normalised.')
        peer_input=st.text_input('Peer tickers, comma-separated',value='MSFT,GOOGL,AMZN',key='peer_tickers')
        st.caption('All quotes must be USD; non-USD securities are excluded until FX conversion is implemented.')
        if st.button('Fetch market data and calculate peer multiples',key='peers_run'):
            with st.spinner('Retrieving quotes and SEC financial statements...'):
                df_peers=peer_table([company['ticker']]+peer_input.split(','),fetch_company_research,sec_identity)
            st.session_state['peer_results']=df_peers
        if 'peer_results' in st.session_state:
            ptab=st.session_state['peer_results']
            st.dataframe(ptab,hide_index=True,use_container_width=True)
            st.download_button('Download peer multiples (CSV)',ptab.to_csv(index=False),f"{company['ticker']}_peers.csv",'text/csv')
            st.caption('Use fiscal-year and market-date columns to assess comparability. EV depends on SEC debt/cash coverage; missing components prevent calculating multiples.')
    with filings:
        st.subheader('AI analysis of latest annual filing')
        st.caption('Retrieves SEC 10-K HTML and extracts candidate passages for business model, risks, management discussion and competition. Generated observations cite source-excerpt IDs and the filing URL. SEC HTML does not have stable PDF page numbers.')
        if st.button('Fetch latest 10-K and identify evidence',key='fetch_filing'):
            try:
                with st.spinner('Retrieving filing and extracting passages...'):
                    filing=recent_10k(int(company['cik_str']),sec_identity)
                    raw=filing_text(filing['url'],sec_identity)
                    segments=excerpts(raw,filing['url'])
                st.session_state['filing_data']={'ticker':company['ticker'],'filing':filing,'segments':segments,'raw_len':len(raw)}
                st.session_state.pop('filing_analysis',None)
            except Exception as exc: st.error(f'Filing retrieval error: {exc}')
        stored=st.session_state.get('filing_data')
        if stored and stored['ticker']==company['ticker']:
            fd=stored['filing']; segments=stored['segments']
            st.markdown(f"Filing: [{fd['form']} filed {fd['filed']}]({fd['url']}) | {len(segments)} candidate excerpts")
            with st.expander('Review actual source excerpts'):
                for seg in segments:
                    st.markdown(f"**{seg['id']} | {seg['topic']}** | [Original SEC document]({seg['source_url']})")
                    st.text(seg['quote'][:850])
            if st.button('Generate sourced AI filing briefing',disabled=not bool(api_key),key='filing_ai'):
                try:
                    with st.spinner('Analysing retrieved evidence...'):
                        st.session_state['filing_analysis']=analyse_filing_ai(company['title'],segments,api_key,model)
                except Exception as exc: st.error(f'AI analysis error: {exc}')
            if not api_key: st.info('Enter an OpenAI API key to generate commentary from these retrieved passages.')
            analysis=st.session_state.get('filing_analysis')
            if analysis:
                for finding in analysis['findings']:
                    st.markdown(f"#### {finding['topic']}")
                    st.write(finding['finding'])
                    for source in finding['sources']:
                        st.caption(f"[{source['id']} | {source['topic']}, view original 10-K]({source['source_url']}) | excerpt starts at text offset {source['start_char']:,}")
                    if finding['caveat']:st.caption('Caveat: '+finding['caveat'])
                if analysis['unanswered_questions']:
                    st.markdown('#### Open questions')
                    for question in analysis['unanswered_questions']:st.write('- '+question)
                st.markdown('#### Human accuracy and citation audit')
                st.caption('Independent reviewers should label each generated finding: correct 1/0, source_support 1/0. Upload a CSV with those two columns to calculate reliability.')
                labels_template=pd.DataFrame([{'finding':f['finding'],'correct':'','source_support':''} for f in analysis['findings']])
                st.download_button('Download review template',labels_template.to_csv(index=False),'filing_review_template.csv','text/csv')
                review_file=st.file_uploader('Upload reviewed finding labels',type='csv',key='filing_review')
                if review_file:
                    try: st.json(benchmark_filing_findings(analysis,pd.read_csv(review_file)))
                    except Exception as exc:st.error(f'Invalid review file: {exc}')
                st.caption('Full-document completeness is not established by matching candidate excerpts. Source IDs confirm the cited snippet exists, not that its interpretation is correct.')

    with evidence:
        st.caption('Each observation links to an SEC filing archive and identifies the US-GAAP XBRL concept, accession and filing date. These are filing-level citations, not verified page citations.')
        st.dataframe(facts[['year','metric','value','tag','filing','filed','accession','source_url']],hide_index=True,use_container_width=True,
                     column_config={'source_url':st.column_config.LinkColumn('SEC filing')})
        st.download_button('Download source evidence (CSV)',facts.to_csv(index=False).encode(),f"{company['ticker']}_evidence.csv",'text/csv')
        st.warning('Data quality: taxonomy tags, fiscal-year alignment, restatements, and missing fields require human review. Debt and D&A may be incomplete. Source URLs reference SEC filing directories, not exact PDF pages. Do not treat these values as audited calculations by this app.')
    st.stop()

if do_extract:
    try:
        if mode=='Illustrative demo':
            p=Path(__file__).parent/'demo'/'Orion_Systems_FY2024.txt'
            documents=[(p.name,p.read_bytes())]
        else:
            documents=[(f.name,f.getvalue()) for f in uploads]
        if not documents: st.error('Upload at least one filing.')
        elif extraction_mode.startswith('LLM') and not api_key: st.error('An API key is required for LLM extraction.')
        else:
            pages=[]
            for filename,data in documents: pages.extend(read_document(filename,data))
            if len(pages)>120: st.warning('Large document set: LLM calls will process each page and may incur substantial API usage.')
            t0=time.perf_counter()
            with st.spinner('Extracting financial figures and testing source references...'):
                df=(llm_extract(pages,api_key,model) if extraction_mode.startswith('LLM') else deterministic_extract(pages))
            st.session_state.research_df=df
            st.session_state.source_pages=pages
            st.session_state.run_time=time.perf_counter()-t0
            st.session_state.summary=None
            st.success(f'Processed {len(pages)} pages, extracted {len(df)} figures.')
    except Exception as exc: st.error(f'Extraction failed: {exc}')

df=st.session_state.research_df
if df is None:
    st.info('Choose the illustrative demo, then click Run research. The demo uses fictional financials and runs without an API key.')
    st.stop()
if df.empty:
    st.warning('No matching financial data was extracted. Use LLM mode for normal annual reports or a pipe-delimited sample for the rule-based parser.')
    st.stop()

pages=st.session_state.source_pages
unique_units=df['unit'].unique().tolist()
if len(unique_units)>1:
    st.error('Multiple reporting currencies/units detected. Do not combine these values. Upload a consistent reporting basis.')
    st.stop()
if df.duplicated(['year','metric']).any():
    st.warning('Multiple values appear for the same year and metric. Check for duplicate comparative periods or multiple companies. Ratios use one value per year/metric.')
fin=analyse_financials(df)
st.caption('Amounts: '+unique_units[0]+' | Extracted fields: '+str(len(df))+' | Source-checked: '+str(int(df.source_check.sum()))+'/'+str(len(df)))
latest_year=int(fin.index.max())
latest=fin.loc[latest_year]
c1,c2,c3,c4=st.columns(4)
c1.metric('Revenue',f'{latest["Revenue"]:,.1f}' if pd.notna(latest['Revenue']) else 'N/A',help=unique_units[0])
c2.metric('Revenue YoY',f'{latest["Revenue growth %"]:.1f}%' if pd.notna(latest['Revenue growth %']) else 'N/A')
c3.metric('Operating margin',f'{latest["Operating margin %"]:.1f}%' if pd.notna(latest['Operating margin %']) else 'N/A')
c4.metric('Free cash flow',f'{latest["FCF"]:,.1f}' if pd.notna(latest['FCF']) else 'N/A')

t1,t2,t3,t4=st.tabs(['Financial performance','Evidence ledger','Research notes','Benchmarking'])
with t1:
    st.subheader('Historical performance')
    a,b=st.columns([1.5,1])
    with a:
        chart_data=fin.reset_index()
        fig=px.line(chart_data,x='year',y=[c for c in ['Revenue','EBITDA','FCF'] if fin[c].notna().any()],markers=True)
        fig.update_layout(legend_title_text='',xaxis=dict(dtick=1),yaxis_title=unique_units[0],margin=dict(l=0,r=10,t=20,b=0))
        st.plotly_chart(fig,use_container_width=True)
    with b:
        margin_cols=[c for c in ['Gross margin %','Operating margin %','Net margin %','EBITDA margin %'] if fin[c].notna().any()]
        if margin_cols:
            fig2=px.line(chart_data,x='year',y=margin_cols,markers=True)
            fig2.update_layout(legend_title_text='',xaxis=dict(dtick=1),yaxis_title='%',margin=dict(l=0,r=10,t=20,b=0))
            st.plotly_chart(fig2,use_container_width=True)
    st.dataframe(fin.style.format(precision=2,na_rep='N/A'),use_container_width=True)
    st.download_button('Download calculated ratios (CSV)',fin.to_csv().encode(),'financial_ratios.csv','text/csv')
    st.caption('Ratios are derived. EBITDA = operating income + D&A. FCF = CFO minus absolute capex. Revenue growth is YoY. Debt/equity uses year-end balances. No averaging of assets or capital employed.')

with t2:
    st.subheader('Filing evidence and review queue')
    bad=df.loc[~df.source_check]
    if len(bad): st.warning(f'{len(bad)} rows need review because numeric source checks failed.')
    filtered=st.dataframe(df,hide_index=True,use_container_width=True,on_select='rerun',selection_mode='single-row')
    st.download_button('Download extraction evidence (CSV)',df.to_csv(index=False).encode(),'extraction_evidence.csv','text/csv')
    selected=filtered.selection.rows
    if selected:
        r=df.iloc[selected[0]]
        page=next((p for p in pages if p.source==r.source and p.page==r.page),None)
        if page:
            st.markdown(f'#### Source preview: {page.reference()}')
            st.code(page.text[:16000],language=None)

with t3:
    st.subheader('Source-linked research notes')
    if st.button('Generate research summary'):
        try:
            with st.spinner('Preparing source-referenced notes...'):
                st.session_state.summary=structured_summary(fin,df,pages,api_key or None,model)
        except Exception as exc: st.error(f'Summary failed: {exc}')
    result=st.session_state.get('summary')
    if result:
        st.markdown('#### Findings')
        for item in result['findings']: st.write('• '+item)
        st.markdown('#### Risks and limitations')
        for item in result['risks']: st.write('• '+item)
        st.caption('Summary references must match extracted pages, but factual interpretations still require analyst review.')

with t4:
    st.subheader('Extraction reliability')
    demo_gold=Path(__file__).parent/'demo'/'gold_labels.csv'
    uploaded_gold=st.file_uploader('Upload analyst-verified ground truth CSV (source, year, metric, value)',type='csv',key='gold')
    gold=None
    if uploaded_gold:
        try: gold=pd.read_csv(uploaded_gold)
        except Exception as exc: st.error(f'Could not read CSV: {exc}')
    elif mode=='Illustrative demo':
        gold=pd.read_csv(demo_gold)
        st.caption('Using the supplied fictional-company ground truth. This is a test fixture, not evidence of real-world accuracy.')
    if gold is not None:
        try:
            result=evaluate(df,gold)
            x,y,z=st.columns(3)
            x.metric('Field precision',f'{result["field_precision"]:.1%}')
            y.metric('Field recall',f'{result["field_recall"]:.1%}')
            z.metric('Value accuracy on matched keys',f'{result["value_accuracy_on_matched"]:.1%}')
            st.json(result)
        except Exception as exc: st.error(f'Evaluation error: {exc}')
    else:
        st.info('Upload human-verified labels for real filings. The platform will not claim accuracy without ground truth.')
    st.subheader('Analyst time study')
    st.caption('Enter independently observed manual extraction time and human quality-control time. Processing time is measured by the app. Do not report estimates as observed outcomes.')
    manual=st.number_input('Manual work per filing (minutes)',min_value=0.1,value=45.0,step=5.0)
    review=st.number_input('Human review per filing (minutes)',min_value=0.0,value=10.0,step=2.0)
    filing_count=st.number_input('Number of filings in this processing run',min_value=1,value=len({p.source for p in pages}),step=1)
    report=savings(manual,st.session_state.run_time or 0,review,filing_count)
    q,w,e=st.columns(3)
    q.metric('Time reduction (scenario)',f'{report["time_reduction_pct"]:.1f}%')
    w.metric('Minutes saved per filing',f'{report["minutes_saved_per_filing"]:.1f}')
    e.metric('Measured machine processing',f'{st.session_state.run_time or 0:.2f} s')
    st.json(report)
    st.download_button('Download time-study scenario (CSV)',pd.DataFrame([report]).to_csv(index=False),'time_study.csv','text/csv')
