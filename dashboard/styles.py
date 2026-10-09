"""Presentation-friendly local styling, without external assets."""
import streamlit as st

def apply(presentation=False):
    size=20 if presentation else 16
    st.markdown(f'''<style>
    .stApp {{background:#0b1422;color:#e9eff8;}}
    [data-testid="stSidebar"] {{background:#111d2d;border-right:1px solid #29384d;}}
    .block-container {{max-width:1700px;padding-top:2rem;padding-bottom:5rem;}}
    h1 {{font-size:{38 if presentation else 34}px!important;letter-spacing:-.8px;}}
    h2 {{font-size:26px!important;}}
    p,li,[data-testid="stMarkdownContainer"] {{font-size:{size}px;}}
    [data-testid="stMetric"] {{background:#152338;border:1px solid #293b52;border-radius:10px;padding:18px;}}
    [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p {{color:#b7c6da!important;}}
    [data-testid="stMetricValue"] {{color:#e9eff8!important;}}
    [data-testid="stForm"] [data-testid="stWidgetLabel"] p,
    [data-testid="stForm"] label p {{color:#e9eff8!important;}}
    .notice {{padding:14px 20px;border-left:3px solid #55b7ec;background:#13243a;border-radius:5px;margin:16px 0;}}
    .story {{border:1px solid #34465d;border-radius:9px;padding:19px;background:#111d2d;height:160px;}}
    .story b {{color:#79c8f4;font-size:19px;}}
    .flow {{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0;align-items:center;}}
    .step {{padding:14px 17px;background:#172940;border:1px solid #3b5572;border-radius:8px;}}
    .boundary {{border:1px dashed #7a889b;background:#202634;}}
    footer {{visibility:hidden;}}
    </style>''',unsafe_allow_html=True)
