import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import json

# --- Конфигурация ---
SPREADSHEET_ID = '10cBNkDQ3fOCajBIjeAsaCPsivEfVShGZ-BHmLcC6l5s/edit'  # ЗАМЕНИТЕ НА ВАШ ID

# Названия листов
SOURCE_SHEET_NAME = 'ЯндексФорм'
TARGET_SHEET_NAME_PREFIX = 'Офлайн регистрация'

# --- АУТЕНТИФИКАЦИЯ ЧЕРЕЗ SECRETS (ДЛЯ STREAMLIT CLOUD) ---
try:
    # Проверяем, есть ли секреты
    if 'gcp_service_account' not in st.secrets:
        st.error("❌ Секреты не настроены! Добавьте их в Streamlit Cloud.")
        st.info("📝 Зайдите в Manage app → Settings → Secrets")
        st.stop()
    
    # Загружаем credentials из секретов
    credentials_info = dict(st.secrets["gcp_service_account"])
    
    # Исправляем приватный ключ (заменяем \\n на реальные переносы)
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
except Exception as e:
    st.sidebar.error(f"❌ Не удалось открыть таблицу: {str(e)[:100]}...")
    st.stop()


# Открываем таблицу по ID
sh = client.open_by_key(SPREADSHEET_ID)

# --- Функции для работы с данными ---
@st.cache_data(ttl=10) # Кешируем данные на 10 секунд, чтобы при частых запросах не превысить лимиты API
def load_source_data():
    """Загружает данные из исходного листа и возвращает DataFrame."""
    try:
        worksheet = sh.worksheet(SOURCE_SHEET_NAME)
        data = worksheet.get_all_records()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        # Приводим названия колонок к удобному виду (уберите лишние пробелы)
        df.columns = df.columns.str.strip()
        return df
    except gspread.WorksheetNotFound:
        st.error(f"Лист '{SOURCE_SHEET_NAME}' не найден. Проверьте название.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Ошибка загрузки данных: {e}")
        return pd.DataFrame()

def save_to_target_sheet(participant_data):
    """Сохраняет данные участника в целевой лист (создает его, если нужно)."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    target_sheet_name = f"{TARGET_SHEET_NAME_PREFIX} {today_str}"

    try:
        # Пытаемся открыть лист, если нет - создаем
        try:
            target_worksheet = sh.worksheet(target_sheet_name)
        except gspread.WorksheetNotFound:
            target_worksheet = sh.add_worksheet(title=target_sheet_name, rows=100, cols=20)
            # Если лист только что создан, добавим заголовки
            headers = list(participant_data.keys())
            target_worksheet.append_row(headers)
            st.info(f"Создан новый лист: {target_sheet_name}")

        # Добавляем данные как новую строку
        target_worksheet.append_row(list(participant_data.values()))
        return True
    except Exception as e:
        st.error(f"Ошибка сохранения в лист '{target_sheet_name}': {e}")
        return False

def calculate_accommodation_cost(row, nights, tariff):
    """Пересчитывает стоимость проживания на основе ночей и тарифа."""
    # Здесь ваша логика расчета. Это просто пример.
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

# 1. Поиск по фамилии
# Предполагаем, что колонка с фамилией называется "ФИО". Возможно, потребуется парсинг.
# Для простоты будем искать по вхождению строки в колонку ФИО.
col1, col2 = st.columns([1, 2])
with col1:
    search_surname = st.text_input("🔍 Введите фамилию участника:")

if search_surname:
    # Фильтруем DataFrame по фамилии (простой поиск по подстроке в ФИО)
    mask = df['ФИО'].str.contains(search_surname, case=False, na=False)
    filtered_df = df[mask]

    if filtered_df.empty:
        st.warning(f"Участники с фамилией '{search_surname}' не найдены.")
    elif len(filtered_df) > 1:
        # 2. Если несколько однофамильцев, выбираем
        st.info(f"Найдено несколько участников. Уточните выбор:")
        # Создаем список для выбора: ФИО + уникальный идентификатор (например, дата рождения)
        options = filtered_df.apply(lambda row: f"{row['ФИО']} ({row.get('Дата рождения', 'Дата не указана')})", axis=1).tolist()
        selected_option = st.selectbox("Выберите участника:", options)

        # Находим выбранного участника в DataFrame
        selected_index = options.index(selected_option)
        participant = filtered_df.iloc[selected_index].to_dict()
    else:
        # Найден ровно один участник
        participant = filtered_df.iloc[0].to_dict()

    # 3. Отображаем и редактируем данные участника
    if 'participant' in locals():
        st.divider()
        st.subheader(f"Данные участника: {participant['ФИО']}")

        with st.form(key='edit_form'):
            # Разбиваем на колонки для компактности
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.text_input("ФИО", value=participant['ФИО'], disabled=True, key="display_fio")
                st.text_input("Дата рождения", value=participant.get('Дата рождения', ''), disabled=True)
                st.text_input("Оргвзнос (величина)", value=participant.get('Оргвзнос', ''), disabled=True)

            with col_b:
                # Редактируемые поля
                new_check_in = st.date_input("Дата заезда", value=pd.to_datetime(participant.get('Дата заезда', datetime.now())).date())
                new_check_out = st.date_input("Дата отъезда", value=pd.to_datetime(participant.get('Дата отъезда', datetime.now())).date())
                # Пересчет ночей
                calculated_nights = (new_check_out - new_check_in).days
                st.number_input("Количество ночей", value=calculated_nights, disabled=True)

            with col_c:
                new_tariff = st.number_input("Тариф проживания (₽/ночь)", value=float(participant.get('Тариф проживания', 0)))
                new_fee = st.text_input("Величина оргвзноса (новая)", value=participant.get('Оргвзнос', ''))

            # Кнопка сохранения
            submitted = st.form_submit_button("✅ Сохранить изменения в офлайн-регистрацию")

            if submitted:
                # Формируем данные для сохранения
                # Добавляем все поля из participant, но обновляем измененные
                data_to_save = participant.copy() # Копируем старые данные
                data_to_save['Дата заезда'] = str(new_check_in)
                data_to_save['Дата отъезда'] = str(new_check_out)
                data_to_save['Тариф проживания'] = new_tariff
                data_to_save['Оргвзнос'] = new_fee
                data_to_save['Количество ночей'] = calculated_nights
                # Пересчет стоимости проживания
                data_to_save['Стоимость проживания'] = calculate_accommodation_cost(participant, calculated_nights, new_tariff)
                data_to_save['Дата и время регистрации'] = str(datetime.now())

                # Сохраняем
                if save_to_target_sheet(data_to_save):
                    st.success("Данные успешно сохранены в офлайн-регистрацию!")
                    # Очищаем кеш, чтобы при следующем поиске данные были актуальны?
                    # st.cache_data.clear()
                else:
                    st.error("Не удалось сохранить данные.")


