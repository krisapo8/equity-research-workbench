"""Transparent 5-year FCFF valuation. All monetary amounts USD millions.
Assumptions are analyst-editable, never inferred as consensus estimates.
"""
from dataclasses import dataclass
from math import isfinite
import pandas as pd

@dataclass(frozen=True)
class Assumptions:
    revenue_growth: float = 0.08
    ebit_margin: float = 0.23
    tax_rate: float = 0.21
    da_pct_sales: float = 0.035
    capex_pct_sales: float = 0.045
    nwc_pct_incremental_sales: float = 0.02
    wacc: float = 0.10
    terminal_growth: float = 0.025


def dcf(revenue: float, net_debt: float, shares_m: float, start_year: int, a: Assumptions, horizon: int = 5) -> dict:
    if not all(isfinite(float(v)) for v in (revenue, net_debt, shares_m)) or revenue <= 0 or shares_m <= 0:
        raise ValueError('Revenue and diluted shares must be positive, and all inputs finite.')
    if not 0 <= a.tax_rate <= 1 or not -0.5 < a.revenue_growth < 2 or not 0 <= a.ebit_margin <= 1:
        raise ValueError('Invalid operating assumptions.')
    if a.wacc <= a.terminal_growth or a.wacc <= 0 or a.terminal_growth < -0.1:
        raise ValueError('WACC must exceed terminal growth and be positive.')
    if not 1 <= horizon <= 20: raise ValueError('Invalid forecast horizon')
    rows=[]; prev=revenue; pv=0.0
    for t in range(1,horizon+1):
        sales=prev*(1+a.revenue_growth)
        ebit=sales*a.ebit_margin
        tax=max(ebit,0)*a.tax_rate
        da=sales*a.da_pct_sales
        capex=sales*a.capex_pct_sales
        delta_nwc=(sales-prev)*a.nwc_pct_incremental_sales
        fcff=ebit-tax+da-capex-delta_nwc
        discount=1/(1+a.wacc)**t
        pv+=fcff*discount
        rows.append({'Year':start_year+t,'Revenue':sales,'EBIT':ebit,'NOPAT':ebit-tax,'D&A':da,'Capex':capex,'Change in NWC':delta_nwc,'FCFF':fcff,'PV FCFF':fcff*discount})
        prev=sales
    terminal=rows[-1]['FCFF']*(1+a.terminal_growth)/(a.wacc-a.terminal_growth)
    pv_terminal=terminal/(1+a.wacc)**horizon
    ev=pv+pv_terminal
    equity=ev-net_debt
    return {'forecast':pd.DataFrame(rows),'pv_fcff':pv,'terminal_value':terminal,'pv_terminal_value':pv_terminal,'enterprise_value':ev,'equity_value':equity,'value_per_share':equity/shares_m,'terminal_weight_pct':100*pv_terminal/ev if ev else float('nan')}


def scenarios(revenue, net_debt, shares_m, start_year, base: Assumptions):
    configs={
        'Bear': Assumptions(**{**vars(base),'revenue_growth':max(-0.40,base.revenue_growth-0.05),'ebit_margin':max(0,base.ebit_margin-0.04),'wacc':base.wacc+0.015,'terminal_growth':max(-0.05,base.terminal_growth-0.005)}),
        'Base':base,
        'Bull': Assumptions(**{**vars(base),'revenue_growth':min(1.5,base.revenue_growth+0.05),'ebit_margin':min(1,base.ebit_margin+0.04),'wacc':max(0.001,base.wacc-0.01),'terminal_growth':base.terminal_growth+0.005}),
    }
    return {k:dcf(revenue,net_debt,shares_m,start_year,a) for k,a in configs.items()},configs


def sensitivity(revenue,net_debt,shares_m,start_year,base:Assumptions,wacc_step=0.01,g_step=0.005):
    records=[]
    for dw in [-2,-1,0,1,2]:
        row={'WACC':base.wacc+dw*wacc_step}
        for dg in [-2,-1,0,1,2]:
            g=base.terminal_growth+dg*g_step
            key=f'{g:.1%}'
            if row['WACC']<=g or row['WACC']<=0: row[key]=None
            else: row[key]=dcf(revenue,net_debt,shares_m,start_year,Assumptions(**{**vars(base),'wacc':row['WACC'],'terminal_growth':g}))['value_per_share']
        records.append(row)
    return pd.DataFrame(records).set_index('WACC')


def peer_multiples(market_cap_m, total_debt_m, cash_m, revenue_m, ebitda_m, net_income_m):
    """No fabricated multiples for zero/missing values. Input amounts in same currency millions."""
    def valid(v): return v is not None and pd.notna(v) and isfinite(float(v))
    cap=float(market_cap_m) if valid(market_cap_m) else None
    debt=float(total_debt_m) if valid(total_debt_m) else None
    cash=float(cash_m) if valid(cash_m) else None
    ev=cap+debt-cash if cap is not None and debt is not None and cash is not None else None
    def mult(num,den): return num/float(den) if num is not None and valid(den) and float(den)>0 else None
    return {'Market cap':cap,'Enterprise value':ev,'EV / Revenue':mult(ev,revenue_m),'EV / EBITDA':mult(ev,ebitda_m),'P / E':mult(cap,net_income_m)}
