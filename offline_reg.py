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

def save_to_target_sheets(participant_data, full_name):
    """Сохраняет данные участника в целевые листы (основной и бухгалтерский)."""
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
                headers = ['Дата регистрации', 'ФИО', 'Комната', 'Дата заезда', 'Дата отъезда', 
                          'Количество ночей', 'Тариф (₽/ночь)', 'Стоимость (₽)', 'Оргвзнос']
                registration_worksheet.append_row(headers)
                st.info(f"📋 Создан новый лист регистрации: {registration_sheet_name}")

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
            
            registration_worksheet.append_row(row_data)
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
                    'Фамилия',
                    'Дата заезда',
                    'Дата отъезда',
                    'Количество ночей',
                    'Тариф (₽/ночь)',
                    'Стоимость проживания (₽)',
                    'Оргвзнос'
                ]
                accounting_worksheet.append_row(accounting_headers)
                st.info(f"📊 Создан новый бухгалтерский лист: '{accounting_sheet_name}'")

            # Извлекаем фамилию для бухгалтерии
            surname = extract_surname(full_name)
            
            accounting_data = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                full_name,
                surname,
                str(participant_data['Дата заезда']),
                str(participant_data['Дата отъезда']),
                participant_data['Количество ночей'],
                participant_data['Тариф'],
                participant_data['Стоимость'],
                participant_data['Оргвзнос']
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

# Инициализация session state для хранения текущих значений
if 'selected_fio' not in st.session_state:
    st.session_state.selected_fio = None
if 'new_room' not in st.session_state:
    st.session_state.new_room = ""
if 'new_check_in' not in st.session_state:
    st.session_state.new_check_in = datetime.now().date()
if 'new_check_out' not in st.session_state:
    st.session_state.new_check_out = datetime.now().date()
if 'new_tariff' not in st.session_state:
    st.session_state.new_tariff = 0.0
if 'new_fee' not in st.session_state:
    st.session_state.new_fee = 0.0
if 'participant' not in st.session_state:
    st.session_state.participant = None

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
        
        # Если выбран новый участник, обновляем session state
        if selected_fio != st.session_state.selected_fio:
            st.session_state.selected_fio = selected_fio
            participant = df[df['ФИО'] == selected_fio].iloc[0].to_dict()
            st.session_state.participant = participant
            
            # Загружаем текущие значения
            st.session_state.new_room = str(participant.get('room_id', ''))
            
            check_in_value = parse_date_safe(participant.get('Дата заезда', None))
            check_out_value = parse_date_safe(participant.get('Дата отъезда', None))
            st.session_state.new_check_in = check_in_value
            st.session_state.new_check_out = check_out_value
            
            try:
                st.session_state.new_tariff = float(participant.get('тариф', 0)) if participant.get('тариф', 0) else 0.0
            except:
                st.session_state.new_tariff = 0.0
                
            try:
                st.session_state.new_fee = float(participant.get('оргвзнос', 0)) if participant.get('оргвзнос', 0) else 0.0
            except:
                st.session_state.new_fee = 0.0
        
        if st.session_state.participant is not None:
            st.divider()
            st.subheader(f"📝 Редактирование данных: {st.session_state.selected_fio}")
            
            # Расчет стоимости при каждом изменении
            nights, cost = calculate_cost(
                st.session_state.new_check_in, 
                st.session_state.new_check_out, 
                st.session_state.new_tariff
            )
            
            # Форма редактирования с авто-обновлением
            col1, col2 = st.columns(2)
            
            with col1:
                # ФИО (только для информации)
                st.text_input("ФИО", value=st.session_state.selected_fio, disabled=True)
                
                # Комната (редактируемая)
                st.session_state.new_room = st.text_input(
                    "Номер комнаты", 
                    value=st.session_state.new_room,
                    key="room_input"
                )
                
                # Оргвзнос (редактируемый)
                st.session_state.new_fee = st.number_input(
                    "Оргвзнос (₽)", 
                    value=st.session_state.new_fee, 
                    step=100.0, 
                    format="%.0f",
                    key="fee_input"
                )
            
            with col2:
                # Даты
                st.session_state.new_check_in = st.date_input(
                    "📅 Дата заезда", 
                    value=st.session_state.new_check_in,
                    key="check_in_input"
                )
                
                st.session_state.new_check_out = st.date_input(
                    "📅 Дата отъезда", 
                    value=st.session_state.new_check_out,
                    key="check_out_input"
                )
                
                # Тариф
                st.session_state.new_tariff = st.number_input(
                    "💰 Тариф (₽/ночь)", 
                    value=st.session_state.new_tariff, 
                    step=500.0, 
                    format="%.0f",
                    key="tariff_input"
                )
            
            # Отображение рассчитанных значений (авто-обновляются)
            col3, col4 = st.columns(2)
            with col3:
                st.metric("Количество ночей", f"{nights}")
            with col4:
                st.metric("💰 Итого к оплате", f"{cost:,.0f} ₽")
            
            st.divider()
            
            # Кнопка сохранения
            if st.button("✅ Сохранить изменения", type="primary", use_container_width=True):
                # Формируем данные для сохранения
                data_to_save = {
                    'ФИО': st.session_state.selected_fio,
                    'Комната': st.session_state.new_room,
                    'Дата заезда': st.session_state.new_check_in.strftime("%d.%m.%Y"),
                    'Дата отъезда': st.session_state.new_check_out.strftime("%d.%m.%Y"),
                    'Количество ночей': nights,
                    'Тариф': st.session_state.new_tariff,
                    'Стоимость': cost,
                    'Оргвзнос': st.session_state.new_fee
                }
                
                # Сохраняем в оба листа
                if save_to_target_sheets(data_to_save, st.session_state.selected_fio):
                    st.balloons()
                    st.success("🎉 Данные успешно сохранены!")
                    st.cache_data.clear()
                else:
                    st.error("❌ Ошибка при сохранении данных")

else:
    st.info("👆 Введите фамилию участника для поиска")
