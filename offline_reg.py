import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

# --- Конфигурация ---
SPREADSHEET_ID = '10cBNkDQ3fOCajBIjeAsaCPsivEfVShGZ-BHmLcC6l5s'

# Названия листов
SOURCE_SHEET_NAME = 'Лист1'
TARGET_SHEET_NAME_PREFIX = 'Офлайн регистрация'

# --- АУТЕНТИФИКАЦИЯ ---
try:
    if 'gcp_service_account' not in st.secrets:
        st.error("❌ Секреты не настроены! Добавьте их в Streamlit Cloud.")
        st.info("📝 Зайдите в Manage app → Settings → Secrets")
        st.stop()
    
    credentials_info = dict(st.secrets["gcp_service_account"])
    
    if 'private_key' in credentials_info:
        credentials_info['private_key'] = credentials_info['private_key'].replace('\\n', '\n')
    
    creds = Credentials.from_service_account_info(
        credentials_info,
        scopes=['https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive']
    )
    
    client = gspread.authorize(creds)
    st.sidebar.success("✅ Подключено к Google Sheets")
    
except Exception as e:
    st.sidebar.error(f"❌ Ошибка аутентификации: {str(e)[:100]}...")
    st.stop()

# Открываем таблицу
try:
    sh = client.open_by_key(SPREADSHEET_ID)
    st.sidebar.success("✅ Таблица открыта")
    
    all_sheets = [w.title for w in sh.worksheets()]
    st.sidebar.write("📋 Доступные листы:", all_sheets)
    
except Exception as e:
    st.sidebar.error(f"❌ Не удалось открыть таблицу: {str(e)[:100]}...")
    st.stop()

# --- Функция для извлечения фамилии из ФИО ---
def extract_surname(full_name):
    """Извлекает фамилию из полного ФИО"""
    if pd.isna(full_name) or not full_name:
        return ""
    full_name = str(full_name).strip()
    parts = full_name.split()
    return parts[0] if parts else ""

def search_by_surname(df, search_surname):
    """Ищет участников по фамилии (независимо от регистра)"""
    if not search_surname:
        return pd.DataFrame()
    
    search_surname = search_surname.strip().lower()
    df_copy = df.copy()
    df_copy['_surname'] = df_copy['ФИО'].apply(extract_surname)
    df_copy['_surname_lower'] = df_copy['_surname'].str.lower()
    mask = df_copy['_surname_lower'].str.contains(search_surname, na=False)
    
    return df_copy[mask]

# --- Функции для работы с данными ---
@st.cache_data(ttl=10)
def load_source_data():
    """Загружает данные из исходного листа."""
    try:
        all_sheets = [w.title for w in sh.worksheets()]
        if SOURCE_SHEET_NAME not in all_sheets:
            st.sidebar.error(f"❌ Лист '{SOURCE_SHEET_NAME}' не найден!")
            return pd.DataFrame()
        
        worksheet = sh.worksheet(SOURCE_SHEET_NAME)
        data = worksheet.get_all_records()
        
        if not data:
            st.sidebar.warning(f"⚠️ Лист '{SOURCE_SHEET_NAME}' пуст")
            return pd.DataFrame()
            
        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip()
        
        # Проверяем наличие обязательных колонок
        required_cols = ['ФИО', 'room_id', 'Дата заезда', 'Дата отъезда', 'тариф']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            st.sidebar.error(f"❌ Отсутствуют колонки: {missing_cols}")
            return pd.DataFrame()
        
        st.sidebar.success(f"✅ Загружено {len(df)} записей")
        return df
        
    except Exception as e:
        st.sidebar.error(f"❌ Ошибка загрузки данных: {e}")
        return pd.DataFrame()

def save_to_target_sheet(participant_data):
    """Сохраняет данные участника в целевой лист."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    sheet_name = f"{TARGET_SHEET_NAME_PREFIX} {today_str}"
    
    try:
        # Открываем или создаем лист
        try:
            worksheet = sh.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            worksheet = sh.add_worksheet(title=sheet_name, rows=100, cols=20)
            # Заголовки: только нужные поля
            headers = ['Дата регистрации', 'ФИО', 'Комната', 'Дата заезда', 'Дата отъезда', 
                      'Количество ночей', 'Тариф (₽/ночь)', 'Стоимость (₽)', 'Оргвзнос']
            worksheet.append_row(headers)
            st.info(f"📋 Создан новый лист: {sheet_name}")

        # Добавляем данные
        row_data = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            participant_data['ФИО'],
            participant_data['Комната'],
            str(participant_data['Дата заезда']),
            str(participant_data['Дата отъезда']),
            participant_data['Количество ночей'],
            participant_data['Тариф'],
            participant_data['Стоимость'],
            participant_data['Оргвзнос']
        ]
        
        worksheet.append_row(row_data)
        st.success(f"✅ Данные сохранены в лист '{sheet_name}'")
        return True
        
    except Exception as e:
        st.error(f"❌ Ошибка сохранения: {e}")
        return False

def calculate_cost(check_in, check_out, tariff):
    """Рассчитывает количество ночей и стоимость."""
    if check_in and check_out:
        nights = (check_out - check_in).days
        if nights < 0:
            nights = 0
        cost = nights * tariff if tariff else 0
        return nights, cost
    return 0, 0

# --- Интерфейс приложения ---
st.set_page_config(layout="wide")

st.title("🏨 Офлайн-регистрация на конференцию ВОЛНЫ-2026")
st.markdown("Найдите участника по фамилии и скорректируйте данные")

st.sidebar.info(f"📅 Сегодня: {datetime.now().strftime('%d.%m.%Y')}")

# Загружаем данные
df = load_source_data()

if df.empty:
    st.warning("Исходная таблица пуста или не удалось загрузить данные.")
    st.stop()

# Поиск по фамилии
search_surname = st.text_input("🔍 Введите фамилию участника:", placeholder="Например: Иванов")

if search_surname:
    filtered_df = search_by_surname(df, search_surname)
    
    if filtered_df.empty:
        st.warning(f"❌ Участники с фамилией '{search_surname}' не найдены.")
    else:
        # Показываем список найденных
        st.info(f"✅ Найдено участников: {len(filtered_df)}")
        
        # Выбор участника
        selected_fio = st.selectbox(
            "Выберите участника:", 
            filtered_df['ФИО'].tolist(),
            key="participant_select"
        )
        
        if selected_fio:
            participant = df[df['ФИО'] == selected_fio].iloc[0].to_dict()
            
            st.divider()
            st.subheader(f"📝 Редактирование данных: {selected_fio}")
            
            # Форма редактирования
            with st.form(key='edit_form'):
                col1, col2 = st.columns(2)
                
                with col1:
                    # ФИО (только для информации)
                    st.text_input("ФИО", value=selected_fio, disabled=True)
                    
                    # Комната (редактируемая)
                    current_room = participant.get('room_id', '')
                    new_room = st.text_input("Номер комнаты", value=str(current_room))
                    
                    # Оргвзнос (можно отредактировать)
                    current_fee = participant.get('оргвзнос', 0)
                    new_fee = st.number_input("Оргвзнос (₽)", value=float(current_fee) if current_fee else 0, step=100)
                
                with col2:
                    # Даты
                    check_in_value = parse_date_safe(participant.get('Дата заезда', None))
                    check_out_value = parse_date_safe(participant.get('Дата отъезда', None))
                    
                    new_check_in = st.date_input("📅 Дата заезда", value=check_in_value)
                    new_check_out = st.date_input("📅 Дата отъезда", value=check_out_value)
                    
                    # Тариф
                    current_tariff = participant.get('тариф', 0)
                    new_tariff = st.number_input("💰 Тариф (₽/ночь)", value=float(current_tariff) if current_tariff else 0, step=500)
                
                # Расчет стоимости
                nights, cost = calculate_cost(new_check_in, new_check_out, new_tariff)
                
                # Отображение рассчитанных значений
                col3, col4 = st.columns(2)
                with col3:
                    st.metric("Количество ночей", f"{nights}")
                with col4:
                    st.metric("💰 Итого к оплате", f"{cost:,.0f} ₽")
                
                st.divider()
                
                # Кнопка сохранения
                submitted = st.form_submit_button("✅ Сохранить изменения", type="primary", use_container_width=True)
            
            # Обработка сохранения
            if submitted:
                # Формируем данные для сохранения
                data_to_save = {
                    'ФИО': selected_fio,
                    'Комната': new_room,
                    'Дата заезда': new_check_in.strftime("%d.%m.%Y"),
                    'Дата отъезда': new_check_out.strftime("%d.%m.%Y"),
                    'Количество ночей': nights,
                    'Тариф': new_tariff,
                    'Стоимость': cost,
                    'Оргвзнос': new_fee
                }
                
                # Сохраняем
                if save_to_target_sheet(data_to_save):
                    st.balloons()
                    st.success("🎉 Данные успешно сохранены!")
                    # Очищаем кеш
                    st.cache_data.clear()
                else:
                    st.error("❌ Ошибка при сохранении данных")

else:
    st.info("👆 Введите фамилию участника для поиска")
