"""Consistent Plotly figures on presentation copies of frozen values."""
import plotly.express as px
import plotly.graph_objects as go
from dashboard.metrics import policy_label, spec

COLORS={'SLA-aware':'#55b7ec','JointSLA-v1':'#e5ad63','JointSLA-v2':'#ba9af0','MJO':'#9cc7ae','Static':'#8793a8','Reactive':'#a3b8ca','Periodic':'#ce9eae'}

def finish(fig, title, unit='', presentation=False):
    fig.update_layout(title=dict(text=title,font_size=23 if presentation else 19),
        template='plotly_dark',paper_bgcolor='#111d2d',plot_bgcolor='#111d2d',
        font=dict(family='Segoe UI, Arial',size=19 if presentation else 15,color='#e9eff8'),
        margin=dict(l=65,r=25,t=70,b=65),height=450 if presentation else 395,
        legend=dict(orientation='h',y=1.12,x=0),hovermode='closest')
    fig.update_yaxes(title=unit,gridcolor='#28374b',rangemode='tozero')
    fig.update_xaxes(gridcolor='#28374b')
    return fig

def metric_chart(summary, metric, x='policy', presentation=False):
    label,unit,factor,_=spec(metric)
    data=summary[summary.metric==metric].copy()
    if data.empty:
        return None
    data['value']=data['mean']*factor
    if 'policy' in data:data['Policy']=data.policy.map(policy_label)
    if {'ci95_lower','ci95_upper'}.issubset(data.columns):
        data['err_plus']=(data.ci95_upper-data['mean'])*factor
        data['err_minus']=(data['mean']-data.ci95_lower)*factor
        errors=dict(error_y='err_plus',error_y_minus='err_minus')
    else:errors={}
    if x=='policy':
        fig=px.bar(data,x='Policy',y='value',color='Policy',color_discrete_map=COLORS,**errors)
        fig.update_layout(showlegend=False)
    else:
        fig=px.line(data,x=x,y='value',color='Policy',markers=True,color_discrete_map=COLORS,**errors)
        if x=='scale':fig.update_xaxes(categoryorder='array',categoryarray=['SMALL','MEDIUM','LARGE'])
    return finish(fig,label+(' · frozen 95% CI' if errors else ' · CI unavailable'),unit,presentation)

def paired_chart(paired, metric, x='load_multiplier', presentation=False):
    data=paired[paired.metric==metric].copy()
    if data.empty or 'delta' not in data:return None
    _,unit,factor,_=spec(metric)
    data['value']=data.delta*factor
    data['plus']=(data.upper-data.delta)*factor;data['minus']=(data.delta-data.lower)*factor
    if x not in data: x='comparison'
    fig=px.scatter(data,x=x,y='value',color='comparison',error_y='plus',error_y_minus='minus')
    fig.add_hline(y=0,line_color='#d7e2ed',line_dash='dash')
    return finish(fig,'Paired difference · frozen 95% CI','percentage points' if unit=='%' else unit,presentation)

def distribution(raw, metric, presentation=False):
    if metric not in raw:return None
    label,unit,factor,_=spec(metric)
    data=raw.copy();data['Policy']=data.policy.map(policy_label);data['value']=data[metric]*factor
    fig=px.box(data,x='Policy',y='value',color='Policy',points='all',hover_data=['seed'],color_discrete_map=COLORS)
    fig.update_layout(showlegend=False)
    return finish(fig,label+' · seed-level distribution',unit,presentation)

def operating_points(data, x, y, presentation=False):
    if not {x,y,'policy'}.issubset(data):return None
    data=data.copy();data['Policy']=data.policy.map(policy_label)
    data['x_value']=data[x]*spec(x)[2];data['y_value']=data[y]*spec(y)[2]
    fig=px.scatter(data,x='x_value',y='y_value',color='Policy',text='Policy',color_discrete_map=COLORS)
    fig.update_traces(marker_size=16,textposition='top center')
    fig=finish(fig,'Observed performance–resource operating points',spec(y)[0]+' ('+spec(y)[1]+')',presentation)
    fig.update_xaxes(title=spec(x)[0]+' ('+spec(x)[1]+')',rangemode='tozero')
    return fig
