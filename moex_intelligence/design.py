"""MOEX Intelligence Design System v2: one token source for Python/CSS/JS."""
from html import escape
from pathlib import Path

TOKENS={
 'bg':'#20211f','panel':'#282a27','raised':'#30332f','line':'#454a43','grid':'#363b35',
 'text':'#f1f2ec','muted':'#b9c0b5','accent':'#8ac8ba','accent_strong':'#397b69','warn':'#ebc57e',
 'accent_fill':'rgba(138,200,186,.16)','loss':'#f0aba2','gain':'#b5d3a2','fund':'#c5b98c','bond':'#b6bbd4','cash':'#737d70',
 'radius':'10px','control':'40px','font':'14px','small':'12px','space':'12px'
}


def css_vars(selector=':root'):
    return selector+'{'+''.join('--'+k+':'+v+';' for k,v in TOKENS.items())+'}'


def chart_style(fig,height=320,ytitle=None):
    fig.update_layout(template='plotly_dark',height=height,paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',
      colorway=[TOKENS[k] for k in ['accent','fund','bond','gain','loss']],font=dict(family='system-ui',size=12,color=TOKENS['muted']),
      margin=dict(l=12,r=12,t=28,b=20),legend=dict(orientation='h',y=1.02),hovermode='x unified')
    fig.update_xaxes(showgrid=False,zerolinecolor=TOKENS['line'])
    fig.update_yaxes(gridcolor=TOKENS['grid'],title=ytitle,zerolinecolor=TOKENS['line'])
    return fig


def apply_theme():
    import streamlit as st
    st.html('<style>'+css_vars()+Path(__file__).with_name('components').joinpath('workspace.css').read_text()+'</style>')


def metrics_html(items,*,capital=False):
    """Escaped presentation. Unknowns are text, never giant numeric KPI values."""
    pieces=[]
    for item in items:
        label,value,*rest=item;note=rest[0] if rest else ''
        pieces.append('<div class="financial-item"><div class="financial-label">'+escape(label)+'</div><div class="financial-value">'+escape(str(value))+'</div>'+(('<div class="financial-note">'+escape(note)+'</div>') if note else '')+'</div>')
    return '<div class="financial-summary'+(' with-capital' if capital else '')+'">'+''.join(pieces)+'</div>'


def source_badge(status):
    return '<span class="data-badge '+('attention' if status.get('critical') else '')+'">'+escape(status['label'])+'</span>'
