import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import json
import sys

st.set_page_config(layout="wide")
st.title("🔧 Тестовый режим")

# Информация о системе
st.write("### Информация о системе")
st.write(f"Python: {sys.version}")
st.write(f"Streamlit: {st.__version__}")

# Проверка импортов
st.write("### Проверка импортов")
try:
    import gspread
    st.success("✅ gspread - OK")
except Exception as e:
    st.error(f"❌ gspread: {e}")

try:
    import pandas as pd
    st.success(f"✅ pandas - OK (версия {pd.__version__})")
except Exception as e:
    st.error(f"❌ pandas: {e}")

try:
    from google.oauth2.service_account import Credentials
    st.success("✅ google-auth - OK")
except Exception as e:
    st.error(f"❌ google-auth: {e}")

# Проверка секретов
st.write("### Проверка секретов")
if st.secrets:
    st.success("✅ Секреты найдены")
    if 'gcp_service_account' in st.secrets:
        st.success("✅ gcp_service_account в секретах")
        st.write("Email:", st.secrets['gcp_service_account'].get('client_email', 'не найден'))
    else:
        st.error("❌ gcp_service_account не найден в секретах")
else:
    st.error("❌ Секреты не настроены")

# Если всё хорошо, покажем основной интерфейс
if all([gspread, pd, Credentials]) and 'gcp_service_account' in st.secrets:
    st.success("✅ Все проверки пройдены! Можно разворачивать полную версию.")
