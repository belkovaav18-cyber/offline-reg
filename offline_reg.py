import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import os

# --- Конфигурация ---
SPREADSHEET_ID = '10cBNkDQ3fOCajBIjeAsaCPsivEfVShGZ-BHmLcC6l5s'  # ЗАМЕНИТЕ НА ВАШ ID

# Названия листов
SOURCE_SHEET_NAME = 'Лист1'  # ЗАМЕНИТЕ НА НАЗВАНИЕ ВАШЕГО ЛИСТА
TARGET_SHEET_NAME_PREFIX = 'Офлайн регистрация'

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

def save_to_target_sheet(participant_data):
    """Сохраняет данные участника в целевой лист."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    target_sheet_name = f"{TARGET_SHEET_NAME_PREFIX} {today_str}"

    try:
        # Пытаемся открыть лист, если нет - создаем
        try:
            target_worksheet = sh.worksheet(target_sheet_name)
        except gspread.WorksheetNotFound:
            target_worksheet = sh.add_worksheet(title=target_sheet_name, rows=100, cols=20)
            # Добавляем заголовки
            headers = list(participant_data.keys())
            target_worksheet.append_row(headers)
            st.info(f"Создан новый лист: {target_sheet_name}")

        # Добавляем данные как новую строку
        target_worksheet.append_row(list(participant_data.values()))
        return True
    except Exception as e:
        st.error(f"Ошибка сохранения: {e}")
        return False

def calculate_accommodation_cost(nights, tariff):
    """Пересчитывает стоимость проживания."""
    try:
        tariff = float(tariff) if tariff else 0
        nights = int(nights) if nights else 0
        return nights * tariff
    except (ValueError, TypeError):
        return 0

# --- Интерфейс приложения ---
st.set_page_config(layout="wide")
st.title("🏨 Офлайн-регистрация на конференцию")
st.markdown("Найдите участника по фамилии и скорректируйте его данные.")

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
    # Проверяем, есть ли колонка 'фамилия' (с маленькой буквы)
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
    filtered_df = df[mask]

    if filtered_df.empty:
        st.warning(f"Участники с фамилией '{search_surname}' не найдены.")
    elif len(filtered_df) > 1:
        # Если несколько однофамильцев, показываем для выбора
        st.info(f"Найдено несколько участников. Уточните выбор:")
        
        # Создаем ФИО для отображения
        def get_full_name(row):
            parts = []
            for name_part in ['фамилия', 'имя', 'отчество']:
                for col in df.columns:
                    if col.lower() == name_part:
                        parts.append(str(row[col]) if pd.notna(row[col]) else '')
                        break
            return ' '.join(parts).strip()
        
        filtered_df['display_name'] = filtered_df.apply(get_full_name, axis=1)
        
        selected_name = st.selectbox("Выберите участника:", filtered_df['display_name'].tolist())
        participant = filtered_df[filtered_df['display_name'] == selected_name].iloc[0].to_dict()
    else:
        # Найден ровно один участник
        participant = filtered_df.iloc[0].to_dict()
        # Создаем ФИО для отображения
        name_parts = []
        for name_part in ['фамилия', 'имя', 'отчество']:
            for col in df.columns:
                if col.lower() == name_part:
                    name_parts.append(str(participant[col]) if pd.notna(participant[col]) else '')
                    break
        full_name = ' '.join(name_parts).strip()
    # 3. Отображаем и редактируем данные участника
    if 'participant' in locals():
        # Формируем ФИО для отображения
        name_parts = []
        for name_part in ['фамилия', 'имя', 'отчество']:
            for col in df.columns:
                if col.lower() == name_part:
                    name_parts.append(str(participant[col]) if pd.notna(participant[col]) else '')
                    break
        full_name = ' '.join(name_parts).strip()
        
        st.divider()
        st.subheader(f"Данные участника: {full_name}")

        with st.form(key='edit_form'):
            # Разбиваем на колонки
            col_a, col_b, col_c = st.columns(3)
            
            with col_a:
                st.text_input("ФИО", value=full_name, disabled=True)
                
                # Ищем дату рождения
                birth_date = ''
                for col in df.columns:
                    if 'рожден' in col.lower() or 'birth' in col.lower() or 'дата' in col.lower() and 'рож' in col.lower():
                        birth_date = participant.get(col, '')
                        break
                st.text_input("Дата рождения", value=birth_date, disabled=True)
                
                # Ищем оргвзнос
                fee = ''
                for col in df.columns:
                    if 'оргвзнос' in col.lower() or 'взнос' in col.lower() or 'fee' in col.lower():
                        fee = participant.get(col, '')
                        break
                st.text_input("Оргвзнос (текущий)", value=fee, disabled=True)

            with col_b:
                # Редактируемые поля - даты
                check_in_value = None
                check_out_value = None
                
                # Ищем колонки с датами
                for col in df.columns:
                    if 'заезд' in col.lower() or 'приезд' in col.lower() or 'check-in' in col.lower():
                        try:
                            check_in_value = pd.to_datetime(participant.get(col, datetime.now())).date()
                        except:
                            check_in_value = datetime.now().date()
                    
                    if 'отъезд' in col.lower() or 'выезд' in col.lower() or 'check-out' in col.lower() or 'от\'езд' in col.lower():
                        try:
                            check_out_value = pd.to_datetime(participant.get(col, datetime.now())).date()
                        except:
                            check_out_value = datetime.now().date()
                
                # Если не нашли, используем текущую дату
                if check_in_value is None:
                    check_in_value = datetime.now().date()
                if check_out_value is None:
                    check_out_value = datetime.now().date()
                
                new_check_in = st.date_input("Дата заезда", value=check_in_value)
                new_check_out = st.date_input("Дата отъезда", value=check_out_value)
                
                # Пересчет ночей
                calculated_nights = (new_check_out - new_check_in).days
                nights = st.number_input("Количество ночей", value=calculated_nights, disabled=True)

            with col_c:
                # Ищем тариф
                tariff_value = 0
                for col in df.columns:
                    if 'тариф' in col.lower() or 'стоимость' in col.lower() or 'tariff' in col.lower():
                        try:
                            tariff_value = float(participant.get(col, 0))
                        except:
                            tariff_value = 0
                        break
                
                new_tariff = st.number_input("Тариф проживания (₽/ночь)", value=tariff_value)
                
                # Новый оргвзнос
                new_fee = st.text_input("Новый оргвзнос (если меняется)", value="")
                
                # Расчет стоимости проживания
                accommodation_cost = calculate_accommodation_cost(calculated_nights, new_tariff)
                st.metric("Стоимость проживания", f"{accommodation_cost} ₽")

            # Кнопка сохранения
            submitted = st.form_submit_button("✅ Сохранить изменения в офлайн-регистрацию")

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
                
                # Сохраняем
                if save_to_target_sheet(data_to_save):
                    st.success("✅ Данные успешно сохранены в офлайн-регистрацию!")
                else:
                    st.error("❌ Не удалось сохранить данные.")
