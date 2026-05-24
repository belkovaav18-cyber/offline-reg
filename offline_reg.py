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

def save_to_target_sheets(participant_data, full_name, is_residing=True):
    """Сохраняет данные участника в целевые листы (основной и бухгалтерский)."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    registration_sheet_name = f"{TARGET_SHEET_NAME_PREFIX} {today_str}"
    accounting_sheet_name = f"{ACCOUNTING_SHEET_PREFIX} {today_str}"
    
    success = True
    registration_success = False
    accounting_success = False

    try:
        # --- СОХРАНЕНИЕ В ОСНОВНОЙ ЛИСТ РЕГИСТРАЦИИ (всегда) ---
        try:
            try:
                registration_worksheet = sh.worksheet(registration_sheet_name)
            except gspread.WorksheetNotFound:
                registration_worksheet = sh.add_worksheet(title=registration_sheet_name, rows=100, cols=20)
                headers = ['Дата регистрации', 'ФИО', 'Статус проживания', 'Комната', 'Дата заезда', 'Дата отъезда', 
                          'Количество ночей', 'Тариф (₽/ночь)', 'Стоимость (₽)', 'Оргвзнос']
                registration_worksheet.append_row(headers)
                st.info(f"📋 Создан новый лист регистрации: {registration_sheet_name}")

            # Подготовка данных для регистрации
            if is_residing:
                status = "Проживает"
                room = participant_data.get('Комната', '')
                check_in = str(participant_data.get('Дата заезда', ''))
                check_out = str(participant_data.get('Дата отъезда', ''))
                nights = participant_data.get('Количество ночей', 0)
                tariff = participant_data.get('Тариф', 0)
                cost = participant_data.get('Стоимость', 0)
                fee = participant_data.get('Оргвзнос', 0)
            else:
                status = "Не проживает"
                room = "Не проживает"
                check_in = ""
                check_out = ""
                nights = 0
                tariff = 0
                cost = 0
                fee = participant_data.get('Оргвзнос', 0)
            
            row_data = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                full_name,
                status,
                room,
                check_in,
                check_out,
                nights,
                tariff,
                cost,
                fee
            ]
            
            registration_worksheet.append_row(row_data)
            st.success(f"✅ Данные сохранены в лист регистрации '{registration_sheet_name}'")
            registration_success = True
            
        except Exception as e:
            st.error(f"❌ Ошибка сохранения в лист регистрации: {e}")
            success = False

        # --- СОХРАНЕНИЕ В БУХГАЛТЕРСКИЙ ЛИСТ (только для проживающих) ---
        if is_residing:
            try:
                try:
                    accounting_worksheet = sh.worksheet(accounting_sheet_name)
                except gspread.WorksheetNotFound:
                    accounting_worksheet = sh.add_worksheet(title=accounting_sheet_name, rows=100, cols=20)
                    accounting_headers = [
                        'Дата регистрации',
                        'ФИО',
                        'Фамилия',
                        'Комната',
                        'Дата заезда',
                        'Дата отъезда',
                        'Количество ночей',
                        'Тариф (₽/ночь)',
                        'Стоимость проживания (₽)',
                        'Оргвзнос (₽)'
                    ]
                    accounting_worksheet.append_row(accounting_headers)
                    st.info(f"📊 Создан новый бухгалтерский лист: '{accounting_sheet_name}'")

                # Извлекаем фамилию для бухгалтерии
                surname = extract_surname(full_name)
                
                accounting_data = [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    full_name,
                    surname,
                    participant_data.get('Комната', ''),
                    str(participant_data.get('Дата заезда', '')),
                    str(participant_data.get('Дата отъезда', '')),
                    participant_data.get('Количество ночей', 0),
                    participant_data.get('Тариф', 0),
                    participant_data.get('Стоимость', 0),
                    participant_data.get('Оргвзнос', 0)
                ]
                
                accounting_worksheet.append_row(accounting_data)
                st.success(f"✅ Данные сохранены в бухгалтерский лист '{accounting_sheet_name}'")
                accounting_success = True
                
            except Exception as e:
                st.error(f"❌ Ошибка сохранения в бухгалтерский лист: {e}")
                success = False
        else:
            st.info("ℹ️ Участник не проживает, данные в бухгалтерию не добавлены")
            accounting_success = True  # Считаем успехом, т.к. это ожидаемое поведение

        if registration_success and (accounting_success or not is_residing):
            st.success("🎉 Данные успешно сохранены!")
        elif registration_success:
            st.warning("⚠️ Данные сохранены только в лист регистрации")
        
        return success
        
    except Exception as e:
        st.error(f"❌ Критическая ошибка сохранения: {e}")
        return False

def add_new_participant(fio, org_fee, is_residing, room=None, check_in=None, check_out=None, tariff=None):
    """Добавляет нового участника в исходный лист и регистрирует его"""
    try:
        worksheet = sh.worksheet(SOURCE_SHEET_NAME)
        
        # Подготовка данных для добавления
        new_row = [fio, room if is_residing else "не проживает", 
                  check_in.strftime("%Y-%m-%d") if check_in and is_residing else "",
                  check_out.strftime("%Y-%m-%d") if check_out and is_residing else "",
                  tariff if is_residing else 0]
        
        # Добавляем строку
        worksheet.append_row(new_row)
        
        # Сохраняем данные для регистрации
        if is_residing and room and check_in and check_out and tariff:
            nights = (check_out - check_in).days if check_out > check_in else 0
            cost = nights * tariff
            participant_data = {
                'Комната': room,
                'Дата заезда': check_in.strftime("%d.%m.%Y"),
                'Дата отъезда': check_out.strftime("%d.%m.%Y"),
                'Количество ночей': nights,
                'Тариф': tariff,
                'Стоимость': cost,
                'Оргвзнос': org_fee
            }
        else:
            participant_data = {
                'Оргвзнос': org_fee
            }
        
        # Сохраняем в целевые листы
        return save_to_target_sheets(participant_data, fio, is_residing)
        
    except Exception as e:
        st.error(f"❌ Ошибка добавления участника: {e}")
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
st.markdown("Найдите участника по фамилии или добавьте нового")

# Создаем вкладки
tab1, tab2 = st.tabs(["🔍 Поиск существующего участника", "➕ Добавить нового участника"])

st.sidebar.info(f"📅 Сегодня: {datetime.now().strftime('%d.%m.%Y')}")

# Загружаем данные
df = load_source_data()

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

# Вкладка 1: Поиск существующего участника
with tab1:
    if not df.empty:
        # Поиск по фамилии
        search_surname = st.text_input("🔍 Введите фамилию участника:", placeholder="Например: Иванов", key="search_surname")
        
        if search_surname:
            filtered_df = search_by_surname(df, search_surname)
            
            if filtered_df.empty:
                st.warning(f"❌ Участники с фамилией '{search_surname}' не найдены. Перейдите на вкладку 'Добавить нового участника'")
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
                    room_id = str(participant.get('room_id', ''))
                    is_residing = room_id != "не проживает"
                    st.session_state.new_room = room_id if is_residing else ""
                    
                    check_in_value = parse_date_safe(participant.get('Дата заезда', None)) if is_residing else datetime.now().date()
                    check_out_value = parse_date_safe(participant.get('Дата отъезда', None)) if is_residing else datetime.now().date()
                    st.session_state.new_check_in = check_in_value
                    st.session_state.new_check_out = check_out_value
                    
                    try:
                        st.session_state.new_tariff = float(participant.get('тариф', 0)) if participant.get('тариф', 0) else 0.0
                    except:
                        st.session_state.new_tariff = 0.0
                    
                    # Оргвзнос (если есть)
                    try:
                        st.session_state.new_fee = float(participant.get('оргвзнос', 0)) if participant.get('оргвзнос', 0) else 0.0
                    except:
                        st.session_state.new_fee = 0.0
                
                if st.session_state.participant is not None:
                    # Определяем, проживает ли участник
                    room_id_value = str(st.session_state.participant.get('room_id', ''))
                    is_residing = room_id_value != "не проживает" and room_id_value != "" and not pd.isna(room_id_value)
                    
                    st.divider()
                    st.subheader(f"📝 Редактирование данных: {st.session_state.selected_fio}")
                    
                    if not is_residing:
                        st.info("ℹ️ Этот участник не проживает в гостинице. Будут сохранены только данные регистрации (без бухгалтерии)")
                    
                    # Расчет стоимости только для проживающих
                    if is_residing:
                        nights, cost = calculate_cost(
                            st.session_state.new_check_in, 
                            st.session_state.new_check_out, 
                            st.session_state.new_tariff
                        )
                    else:
                        nights, cost = 0, 0
                    
                    # Форма редактирования
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # ФИО (только для информации)
                        st.text_input("ФИО", value=st.session_state.selected_fio, disabled=True)
                        
                        # Комната (только для проживающих)
                        if is_residing:
                            st.session_state.new_room = st.text_input(
                                "Номер комнаты", 
                                value=st.session_state.new_room,
                                key="room_input"
                            )
                        else:
                            st.text_input("Статус", value="Не проживает", disabled=True)
                        
                        # Оргвзнос (всегда)
                        st.session_state.new_fee = st.number_input(
                            "Оргвзнос (₽)", 
                            value=st.session_state.new_fee, 
                            step=100.0, 
                            format="%.0f",
                            key="fee_input"
                        )
                    
                    with col2:
                        if is_residing:
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
                        else:
                            st.info("Для непроживающих участников данные о проживании не требуются")
                    
                    # Отображение рассчитанных значений для проживающих
                    if is_residing:
                        col3, col4 = st.columns(2)
                        with col3:
                            st.metric("Количество ночей", f"{nights}")
                        with col4:
                            st.metric("💰 Итого к оплате за проживание", f"{cost:,.0f} ₽")
                    
                    st.divider()
                    
                    # Кнопка сохранения
                    if st.button("✅ Сохранить изменения", type="primary", use_container_width=True, key="save_existing"):
                        # Формируем данные для сохранения
                        if is_residing:
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
                        else:
                            data_to_save = {
                                'Оргвзнос': st.session_state.new_fee
                            }
                        
                        # Сохраняем
                        if save_to_target_sheets(data_to_save, st.session_state.selected_fio, is_residing):
                            st.balloons()
                            st.success("🎉 Данные успешно сохранены!")
                            st.cache_data.clear()
                        else:
                            st.error("❌ Ошибка при сохранении данных")
    else:
        st.warning("Нет данных для поиска. Пожалуйста, добавьте участников через вкладку 'Добавить нового'")

# Вкладка 2: Добавление нового участника
with tab2:
    st.subheader("➕ Добавление нового участника")
    
    with st.form(key="add_participant_form"):
        new_fio = st.text_input("ФИО участника *", placeholder="Иванов Иван Иванович")
        
        is_residing_new = st.radio(
            "Статус проживания",
            ["Проживает в гостинице", "Не проживает"],
            horizontal=True
        )
        
        org_fee_new = st.number_input("Оргвзнос (₽)", min_value=0.0, step=100.0, format="%.0f", value=0.0)
        
        room_new = None
        check_in_new = None
        check_out_new = None
        tariff_new = None
        
        if is_residing_new == "Проживает в гостинице":
            col1, col2 = st.columns(2)
            with col1:
                room_new = st.text_input("Номер комнаты *")
            with col2:
                tariff_new = st.number_input("Тариф (₽/ночь) *", min_value=0.0, step=500.0, format="%.0f")
            
            col3, col4 = st.columns(2)
            with col3:
                check_in_new = st.date_input("Дата заезда *", value=datetime.now().date())
            with col4:
                check_out_new = st.date_input("Дата отъезда *", value=datetime.now().date())
        
        submitted = st.form_submit_button("Добавить и зарегистрировать", type="primary", use_container_width=True)
        
        if submitted:
            if not new_fio:
                st.error("❌ Пожалуйста, введите ФИО участника")
            elif is_residing_new == "Проживает в гостинице" and (not room_new or not tariff_new):
                st.error("❌ Для проживающих участников необходимо указать номер комнаты и тариф")
            else:
                if add_new_participant(
                    new_fio,
                    org_fee_new,
                    is_residing_new == "Проживает в гостинице",
                    room_new,
                    check_in_new,
                    check_out_new,
                    tariff_new
                ):
                    st.balloons()
                    st.success(f"✅ Участник {new_fio} успешно добавлен и зарегистрирован!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("❌ Ошибка при добавлении участника")
                    st.error("❌ Ошибка при сохранении данных")

else:
    st.info("👆 Введите фамилию участника для поиска")
