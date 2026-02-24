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
SPREADSHEET_ID = '10cBNkDQ3fOCajBIjeAsaCPsivEfVShGZ-BHmLcC6l5s'  # ЗАМЕНИТЕ НА ВАШ ID

# Названия листов
SOURCE_SHEET_NAME = 'Лист1'  # ЗАМЕНИТЕ НА НАЗВАНИЕ ВАШЕГО ЛИСТА
TARGET_SHEET_NAME_PREFIX = 'Офлайн регистрация'
ACCOUNTING_SHEET_PREFIX = 'Бухгалтерия'  # Новый лист для бухгалтерии

# --- АУТЕНТИФИКАЦИЯ ---
try:
    # Проверяем, есть ли секреты
    if 'gcp_service_account' not in st.secrets:
        st.error("❌ Секреты не настроены! Добавьте их в Streamlit Cloud.")
        st.info("📝 Зайдите в Manage app → Settings → Secrets")
        st.stop()
    
    # Загружаем credentials из секретов
    credentials_info = dict(st.secrets["gcp_service_account"])
    
    # Исправляем приватный ключ
    if 'private_key' in credentials_info:
        credentials_info['private_key'] = credentials_info['private_key'].replace('\\n', '\n')
    
    # Создаем credentials
    creds = Credentials.from_service_account_info(
        credentials_info,
        scopes=['https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive']
    )
    
    # Авторизуемся
    client = gspread.authorize(creds)
    st.sidebar.success("✅ Подключено к Google Sheets")
    
except Exception as e:
    st.sidebar.error(f"❌ Ошибка аутентификации: {str(e)[:100]}...")
    st.stop()

# Открываем таблицу
try:
    sh = client.open_by_key(SPREADSHEET_ID)
    st.sidebar.success("✅ Таблица открыта")
    
    # Показываем все доступные листы
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
        # Если это уже datetime
        if isinstance(date_value, (datetime, pd.Timestamp)):
            return date_value.date()
        
        # Если это строка
        if isinstance(date_value, str):
            # Пробуем разные форматы
            for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d', '%d/%m/%Y']:
                try:
                    return datetime.strptime(date_value.strip(), fmt).date()
                except:
                    continue
        
        # Если ничего не подошло
        return datetime.now().date()
    except:
        return datetime.now().date()

# --- Функции для работы с данными ---
@st.cache_data(ttl=10)
def load_source_data():
    """Загружает данные из исходного листа и возвращает DataFrame."""
    try:
        # Проверяем, есть ли нужный лист
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
        
        # Показываем колонки для отладки
        st.sidebar.write("📊 Колонки в таблице:")
        for col in df.columns:
            st.sidebar.write(f"  - '{col}'")
        
        st.sidebar.success(f"✅ Загружено {len(df)} записей")
        return df
        
    except Exception as e:
        st.sidebar.error(f"❌ Ошибка загрузки данных: {e}")
        return pd.DataFrame()

def save_to_target_sheets(participant_data, full_name):
    """Сохраняет данные участника в целевые листы (основной и бухгалтерский) с разделением по датам."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Названия листов для сегодняшней даты
    registration_sheet_name = f"{TARGET_SHEET_NAME_PREFIX} {today_str}"
    accounting_sheet_name = f"{ACCOUNTING_SHEET_PREFIX} {today_str}"
    
    success = True
    registration_success = False
    accounting_success = False

    try:
        # --- СОХРАНЕНИЕ В ОСНОВНОЙ ЛИСТ РЕГИСТРАЦИИ (все данные) ---
        try:
            # Пытаемся открыть лист регистрации, если нет - создаем
            try:
                registration_worksheet = sh.worksheet(registration_sheet_name)
            except gspread.WorksheetNotFound:
                registration_worksheet = sh.add_worksheet(title=registration_sheet_name, rows=100, cols=20)
                # Добавляем заголовки
                headers = list(participant_data.keys())
                registration_worksheet.append_row(headers)
                st.info(f"📋 Создан новый лист регистрации: {registration_sheet_name}")

            # Добавляем данные как новую строку
            registration_worksheet.append_row(list(participant_data.values()))
            st.success(f"✅ Данные сохранены в лист регистрации '{registration_sheet_name}'")
            registration_success = True
            
        except Exception as e:
            st.error(f"❌ Ошибка сохранения в лист регистрации: {e}")
            success = False

        # --- СОХРАНЕНИЕ В БУХГАЛТЕРСКИЙ ЛИСТ (только финансовые данные) - ТОЖЕ ПО ДАТАМ ---
        try:
            # Пытаемся открыть бухгалтерский лист за сегодня, если нет - создаем
            try:
                accounting_worksheet = sh.worksheet(accounting_sheet_name)
            except gspread.WorksheetNotFound:
                accounting_worksheet = sh.add_worksheet(title=accounting_sheet_name, rows=100, cols=20)
                # Заголовки для бухгалтерии
                accounting_headers = [
                    'Дата регистрации',
                    'ФИО',
                    'Дата заезда',
                    'Дата отъезда',
                    'Количество ночей',
                    'Тариф (₽/ночь)',
                    'Стоимость проживания (₽)',
                    'Оргвзнос (новый)',
                    'Примечание'
                ]
                accounting_worksheet.append_row(accounting_headers)
                st.info(f"📊 Создан новый бухгалтерский лист: '{accounting_sheet_name}'")

            # Формируем данные для бухгалтерии
            accounting_data = [
                datetime.now().strftime("%Y-%m-%d %H:%M"),  # Дата регистрации
                full_name,                                   # ФИО
                str(participant_data.get('Дата заезда (новая)', '')),
                str(participant_data.get('Дата отъезда (новая)', '')),
                str(participant_data.get('Количество ночей', '')),
                str(participant_data.get('Тариф проживания', '')),
                str(participant_data.get('Стоимость проживания', '')),
                str(participant_data.get('Оргвзнос (новый)', '')),  # Новый оргвзнос
                f"Изменения внесены: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            ]
            
            # Добавляем строку в бухгалтерский лист
            accounting_worksheet.append_row(accounting_data)
            st.success(f"✅ Данные сохранены в бухгалтерский лист '{accounting_sheet_name}'")
            accounting_success = True
            
        except Exception as e:
            st.error(f"❌ Ошибка сохранения в бухгалтерский лист: {e}")
            success = False

        # Итоговое сообщение
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

def get_full_name(row, df):
    """Собирает ФИО из колонок фамилия, имя, отчество"""
    parts = []
    for name_part in ['фамилия', 'имя', 'отчество']:
        for col in df.columns:
            if col.lower() == name_part:
                value = row.get(col, '')
                if pd.notna(value):
                    parts.append(str(value))
                break
    return ' '.join(parts).strip()

# --- Интерфейс приложения ---
st.set_page_config(layout="wide")


st.title("Офлайн-регистрация на конференцию ВОЛНЫ-2026")
st.markdown("Найдите участника по фамилии и скорректируйте его данные.")

# Добавляем еще волн внизу (опционально)
st.markdown("<br>", unsafe_allow_html=True)

# Отображаем текущую дату
st.sidebar.info(f"📅 Сегодня: {datetime.now().strftime('%d.%m.%Y')}")

# Загружаем данные
df = load_source_data()

if df.empty:
    st.warning("Исходная таблица пуста или не удалось загрузить данные.")
    st.stop()

# Проверяем, какие колонки есть в таблице
available_columns = df.columns.tolist()
st.sidebar.write("🔍 Доступные для поиска колонки:", available_columns)

# 1. Поиск по фамилии
col1, col2 = st.columns([1, 2])
with col1:
    search_surname = st.text_input("🔍 Введите фамилию участника:")

if search_surname:
    # Проверяем, есть ли колонка 'фамилия'
    surname_column = None
    possible_names = ['фамилия', 'Фамилия', 'ФАМИЛИЯ']
    
    for col_name in possible_names:
        if col_name in df.columns:
            surname_column = col_name
            break
    
    if surname_column is None:
        st.error(f"❌ Не найдена колонка с фамилией. Доступные колонки: {', '.join(df.columns)}")
        st.stop()
    
    # Фильтруем по фамилии
    mask = df[surname_column].str.contains(search_surname, case=False, na=False)
    filtered_df = df[mask].copy()

    if filtered_df.empty:
        st.warning(f"Участники с фамилией '{search_surname}' не найдены.")
    elif len(filtered_df) > 1:
        # Если несколько однофамильцев, показываем для выбора
        st.info(f"Найдено несколько участников. Уточните выбор:")
        
        # Создаем ФИО для отображения
        filtered_df['display_name'] = filtered_df.apply(lambda row: get_full_name(row, df), axis=1)
        
        selected_name = st.selectbox("Выберите участника:", filtered_df['display_name'].tolist())
        participant = filtered_df[filtered_df['display_name'] == selected_name].iloc[0].to_dict()
        full_name = selected_name
    else:
        # Найден ровно один участник
        participant = filtered_df.iloc[0].to_dict()
        full_name = get_full_name(participant, df)
    
    # 3. Отображаем и редактируем данные участника
    if 'participant' in locals():
        st.divider()
        st.subheader(f"Данные участника: {full_name}")

        # Ищем нужные колонки
        birth_col = None
        fee_col = None
        checkin_col = None
        checkout_col = None
        tariff_col = None
        
        for col in df.columns:
            col_lower = col.lower()
            if 'рожден' in col_lower or ('дата' in col_lower and 'рож' in col_lower):
                birth_col = col
            elif 'оргвзнос' in col_lower or 'взнос' in col_lower:
                fee_col = col
            elif 'заезд' in col_lower or 'приезд' in col_lower:
                checkin_col = col
            elif 'отъезд' in col_lower or 'выезд' in col_lower:
                checkout_col = col
            elif 'тариф' in col_lower or 'стоимость' in col_lower:
                tariff_col = col
        
        with st.form(key='edit_form'):
            # Разбиваем на колонки
            col_a, col_b, col_c = st.columns(3)
            
            with col_a:
                st.text_input("ФИО", value=full_name, disabled=True)
                
                # Дата рождения
                birth_date = participant.get(birth_col, '') if birth_col else ''
                st.text_input("Дата рождения", value=str(birth_date), disabled=True)
                
                # Оргвзнос
                fee = participant.get(fee_col, '') if fee_col else ''
                st.text_input("Оргвзнос (текущий)", value=str(fee), disabled=True)

            with col_b:
                # Даты заезда/отъезда
                check_in_value = parse_date_safe(participant.get(checkin_col, None)) if checkin_col else datetime.now().date()
                check_out_value = parse_date_safe(participant.get(checkout_col, None)) if checkout_col else datetime.now().date()
                
                new_check_in = st.date_input("Дата заезда", value=check_in_value)
                new_check_out = st.date_input("Дата отъезда", value=check_out_value)
                
                # Пересчет ночей
                calculated_nights = (new_check_out - new_check_in).days
                if calculated_nights < 0:
                    st.warning("⚠️ Дата отъезда раньше даты заезда!")
                    calculated_nights = 0
                
                nights = st.number_input("Количество ночей", value=calculated_nights, disabled=True)

            with col_c:
                # Тариф
                try:
                    tariff_value = float(participant.get(tariff_col, 0)) if tariff_col else 0
                except:
                    tariff_value = 0
                
                new_tariff = st.number_input("Тариф проживания (₽/ночь)", value=float(tariff_value))
                
                # Новый оргвзнос
                new_fee = st.text_input("Новый оргвзнос (если меняется)", value="")
                
                # Расчет стоимости проживания
                accommodation_cost = calculate_accommodation_cost(calculated_nights, new_tariff)
                st.metric("Стоимость проживания", f"{accommodation_cost} ₽")

            # Кнопка сохранения
            submitted = st.form_submit_button("✅ Сохранить изменения")
        
        # Обработка сохранения (вне формы)
        if submitted:
            # Формируем данные для сохранения
            data_to_save = participant.copy()
            
            # Обновляем измененные поля
            data_to_save['Дата заезда (новая)'] = str(new_check_in)
            data_to_save['Дата отъезда (новая)'] = str(new_check_out)
            data_to_save['Количество ночей'] = calculated_nights
            data_to_save['Тариф проживания'] = new_tariff
            data_to_save['Стоимость проживания'] = accommodation_cost
            
            if new_fee:
                data_to_save['Оргвзнос (новый)'] = new_fee
            
            data_to_save['Дата и время регистрации'] = str(datetime.now())
            data_to_save['Регистратор'] = 'Офлайн'
            
            # Сохраняем в оба листа (теперь оба создаются по датам)
            if save_to_target_sheets(data_to_save, full_name):
    
                # Очищаем кеш после сохранения
                st.cache_data.clear()
            else:
                st.error("❌ Произошли ошибки при сохранении. Проверьте логи выше.")






