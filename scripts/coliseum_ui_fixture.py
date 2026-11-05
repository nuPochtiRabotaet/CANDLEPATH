"""Standalone real saved-report page, isolated from financial startup."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import streamlit as st
from moex_intelligence.crypto.coliseum_ui import page
st.set_page_config(layout='wide')
page()
