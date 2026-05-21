import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import os
import base64
from PIL import Image
import io
import streamlit.components.v1 as components

# --- Конфигурация ---
SPREADSHEET_ID = '10cBNkDQ3fOCajBIjeAsaCPsivEfVShGZ-BHmLcC6l5s'

# Названия листов
SOURCE_SHEET_NAME = 'Лист1'
TARGET_SHEET_NAME_PREFIX = 'Офлайн регистрация'
ACCOUNTING_SHEET_PREFIX = 'Бухгалтерия'

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

# --- Функция для безопасного парсинга дат ---
def parse_date_safe(date_value):
    """Безопасно парсит дату из разных форматов"""
    if date_value is None or pd.isna(date_value):
        return datetime.now().date()
    
    try:
        if isinstance(date_value, (datetime, pd.Timestamp)):
            return date_value.date()
        
        if isinstance(date_value, str):
            for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d', '%d/%m/%Y']:
                try:
                    return datetime.strptime(date_value.strip(), fmt).date()
                except:
                    continue
        
        return datetime.now().date()
    except:
        return datetime.now().date()

# --- Функции для работы с данными ---
@st.cache_data(ttl=10)
def load_source_data():
    """Загружает данные из исходного листа и возвращает DataFrame."""
    try:
        all_sheets = [w.title for w in sh.worksheets()]
        if SOURCE_SHEET_NAME not in all_sheets:
            st.sidebar.error(f"❌ Лист '{SOURCE_SHEET_NAME}' не найден!")
            st.sidebar.info(f"💡 Доступные листы: {', '.join(all_sheets)}")
            return pd.DataFrame()
        
        worksheet = sh.worksheet(SOURCE_SHEET_NAME)
        data = worksheet.get_all_records()
        
        if not data:
            st.sidebar.warning(f"⚠️ Лист '{SOURCE_SHEET_NAME}' пуст")
            return pd.DataFrame()
            
        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip()
        
        st.sidebar.success(f"✅ Загружено {len(df)} записей")
        return df
        
    except Exception as e:
        st.sidebar.error(f"❌ Ошибка загрузки данных: {e}")
        return pd.DataFrame()

def save_to_target_sheets(participant_data, full_name):
    """Сохраняет данные участника в целевые листы (основной и бухгалтерский) с разделением по датам."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    registration_sheet_name = f"{TARGET_SHEET_NAME_PREFIX} {today_str}"
    accounting_sheet_name = f"{ACCOUNTING_SHEET_PREFIX} {today_str}"
    
    success = True
    registration_success = False
    accounting_success = False

    try:
        # --- СОХРАНЕНИЕ В ОСНОВНОЙ ЛИСТ РЕГИСТРАЦИИ ---
        try:
            try:
                registration_worksheet = sh.worksheet(registration_sheet_name)
            except gspread.WorksheetNotFound:
                registration_worksheet = sh.add_worksheet(title=registration_sheet_name, rows=100, cols=20)
                headers = list(participant_data.keys())
                registration_worksheet.append_row(headers)
                st.info(f"📋 Создан новый лист регистрации: {registration_sheet_name}")

            registration_worksheet.append_row(list(participant_data.values()))
            st.success(f"✅ Данные сохранены в лист регистрации '{registration_sheet_name}'")
            registration_success = True
            
        except Exception as e:
            st.error(f"❌ Ошибка сохранения в лист регистрации: {e}")
            success = False

        # --- СОХРАНЕНИЕ В БУХГАЛТЕРСКИЙ ЛИСТ ---
        try:
            try:
                accounting_worksheet = sh.worksheet(accounting_sheet_name)
            except gspread.WorksheetNotFound:
                accounting_worksheet = sh.add_worksheet(title=accounting_sheet_name, rows=100, cols=20)
                accounting_headers = [
                    'Дата регистрации',
                    'ФИО',
                    'Дата заезда',
                    'Дата отъезда',
                    'Количество ночей',
                    'Тариф (₽/ночь)',
                    'Стоимость проживания (₽)',
                    'Оргвзнос',
                    'Возраст',
                    'Пол',
                    'Должность',
                    'Город',
                    'Организация',
                    'Примечание'
                ]
                accounting_worksheet.append_row(accounting_headers)
                st.info(f"📊 Создан новый бухгалтерский лист: '{accounting_sheet_name}'")

            accounting_data = [
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                full_name,
                str(participant_data.get('Дата заезда (новая)', '')),
                str(participant_data.get('Дата отъезда (новая)', '')),
                str(participant_data.get('Количество ночей', '')),
                str(participant_data.get('Тариф проживания', '')),
                str(participant_data.get('Стоимость проживания', '')),
                str(participant_data.get('Оргвзнос', '')),
                str(participant_data.get('возраст', '')),
                str(participant_data.get('пол', '')),
                str(participant_data.get('должность', '')),
                str(participant_data.get('город', '')),
                str(participant_data.get('организация', '')),
                f"Изменения внесены: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            ]
            
            accounting_worksheet.append_row(accounting_data)
            st.success(f"✅ Данные сохранены в бухгалтерский лист '{accounting_sheet_name}'")
            accounting_success = True
            
        except Exception as e:
            st.error(f"❌ Ошибка сохранения в бухгалтерский лист: {e}")
            success = False

        if registration_success and accounting_success:
            st.success("🎉 Данные успешно сохранены в оба листа!")
        elif registration_success:
            st.warning("⚠️ Данные сохранены только в лист регистрации")
        elif accounting_success:
            st.warning("⚠️ Данные сохранены только в бухгалтерский лист")
        
        return success
        
    except Exception as e:
        st.error(f"❌ Критическая ошибка сохранения: {e}")
        return False

def calculate_accommodation_cost(nights, tariff):
    """Пересчитывает стоимость проживания."""
    try:
        tariff = float(tariff) if tariff else 0
        nights = int(nights) if nights else 0
        return nights * tariff
    except (ValueError, TypeError):
        return 0

def get_full_name(row):
    """Возвращает ФИО из колонки 'ФИО'"""
    fio = row.get('ФИО', '')
    return str(fio) if pd.notna(fio) else ''

# --- Интерфейс приложения ---
st.set_page_config(layout="wide")

st.title("Офлайн-регистрация на конференцию ВОЛНЫ-2026")
st.markdown("Найдите участника по фамилии и скорректируйте его данные.")

st.markdown("<br>", unsafe_allow_html=True)

st.sidebar.info(f"📅 Сегодня: {datetime.now().strftime('%d.%m.%Y')}")

# Загружаем данные
df = load_source_data()

if df.empty:
    st.warning("Исходная таблица пуста или не удалось загрузить данные.")
    st.stop()

# 1. Поиск по ФИО
col1, col2 = st.columns([1, 2])
with col1:
    search_name = st.text_input("🔍 Введите ФИО участника:")

if search_name:
    # Поиск по колонке ФИО
    mask = df['ФИО'].str.contains(search_name, case=False, na=False)
    filtered_df = df[mask].copy()

    if filtered_df.empty:
        st.warning(f"Участники с ФИО '{search_name}' не найдены.")
    elif len(filtered_df) > 1:
        st.info(f"Найдено несколько участников. Уточните выбор:")
        selected_name = st.selectbox("Выберите участника:", filtered_df['ФИО'].tolist())
        participant = filtered_df[filtered_df['ФИО'] == selected_name].iloc[0].to_dict()
        full_name = selected_name
    else:
        participant = filtered_df.iloc[0].to_dict()
        full_name = participant.get('ФИО', '')
    
    # Отображаем и редактируем данные участника
    if 'participant' in locals():
        st.divider()
        st.subheader(f"Данные участника: {full_name}")

        with st.form(key='edit_form'):
            col_a, col_b, col_c = st.columns(3)
            
            with col_a:
                st.text_input("ФИО", value=full_name, disabled=True)
                
                # Возраст
                age = participant.get('возраст', '')
                st.text_input("Возраст", value=str(age), disabled=True)
                
                # Пол
                gender = participant.get('пол', '')
                st.text_input("Пол", value=str(gender), disabled=True)
                
                # Должность
                position = participant.get('должность', '')
                st.text_input("Должность", value=str(position), disabled=True)

            with col_b:
                # Город
                city = participant.get('город', '')
                st.text_input("Город", value=str(city), disabled=True)
                
                # Организация
                organization = participant.get('организация', '')
                st.text_input("Организация", value=str(organization), disabled=True)
                
                # Оргвзнос (оригинальный)
                fee = participant.get('оргвзнос', '')
                new_fee = st.text_input("Новый оргвзнос (если меняется)", value=str(fee) if fee else "")

            with col_c:
                # room_id (номер комнаты)
                room_id = participant.get('room_id', '')
                room_capacity = participant.get('room_capacity', '')
                st.text_input("ID комнаты", value=str(room_id), disabled=True)
                st.text_input("Вместимость комнаты", value=str(room_capacity), disabled=True)
                
                # Комментарий
                comment = participant.get('comment', '')
                st.text_area("Комментарий", value=str(comment), disabled=True, height=100)

            st.divider()
            
            # Даты и тарифы - новая секция
            col_d, col_e = st.columns(2)
            
            with col_d:
                # Даты заезда/отъезда
                check_in_value = parse_date_safe(participant.get('Дата заезда', None))
                check_out_value = parse_date_safe(participant.get('Дата отъезда', None))
                
                new_check_in = st.date_input("Дата заезда", value=check_in_value)
                new_check_out = st.date_input("Дата отъезда", value=check_out_value)
                
                # Пересчет ночей
                calculated_nights = (new_check_out - new_check_in).days
                if calculated_nights < 0:
                    st.warning("⚠️ Дата отъезда раньше даты заезда!")
                    calculated_nights = 0
                
                nights = st.number_input("Количество ночей", value=calculated_nights, disabled=True)

            with col_e:
                # Тариф и стоимость
                try:
                    tariff_value = float(participant.get('тариф', 0))
                except:
                    tariff_value = 0
                
                old_cost = participant.get('стоимость', 0)
                st.text_input("Исходная стоимость", value=f"{old_cost} ₽", disabled=True)
                
                new_tariff = st.number_input("Новый тариф проживания (₽/ночь)", value=float(tariff_value))
                
                # Расчет новой стоимости
                accommodation_cost = calculate_accommodation_cost(calculated_nights, new_tariff)
                st.metric("Новая стоимость проживания", f"{accommodation_cost} ₽")

            # Кнопка сохранения
            submitted = st.form_submit_button("✅ Сохранить изменения")
        
        # Обработка сохранения
        if submitted:
            # Формируем данные для сохранения
            data_to_save = {
                'ФИО': full_name,
                'room_id': participant.get('room_id', ''),
                'room_capacity': participant.get('room_capacity', ''),
                'Дата заезда (оригинал)': participant.get('Дата заезда', ''),
                'Дата отъезда (оригинал)': participant.get('Дата отъезда', ''),
                'Дата заезда (новая)': str(new_check_in),
                'Дата отъезда (новая)': str(new_check_out),
                'Количество ночей': calculated_nights,
                'Тариф проживания (оригинал)': participant.get('тариф', ''),
                'Тариф проживания (новый)': new_tariff,
                'Стоимость проживания (оригинал)': participant.get('стоимость', ''),
                'Стоимость проживания (новая)': accommodation_cost,
                'Оргвзнос (оригинал)': participant.get('оргвзнос', ''),
                'Оргвзнос (новый)': new_fee if new_fee else participant.get('оргвзнос', ''),
                'возраст': participant.get('возраст', ''),
                'пол': participant.get('пол', ''),
                'должность': participant.get('должность', ''),
                'город': participant.get('город', ''),
                'организация': participant.get('организация', ''),
                'comment': participant.get('comment', ''),
                'Дата и время регистрации': str(datetime.now()),
                'Регистратор': 'Офлайн'
            }
            
            # Сохраняем в оба листа
            if save_to_target_sheets(data_to_save, full_name):
                st.cache_data.clear()
                st.balloons()
            else:
                st.error("❌ Произошли ошибки при сохранении. Проверьте логи выше.")
