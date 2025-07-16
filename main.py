import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from dotenv import load_dotenv
import pandas as pd
from datetime import datetime
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from pandas.tseries.offsets import DateOffset

# Загрузка токена
load_dotenv()
BOT_TOKEN = os.getenv('TOKEN')

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
print("BOT_TOKEN:", BOT_TOKEN)
dp = Dispatcher()

EXCEL_FILE = 'nalet.xlsx'

# Функция для получения индивидуального файла пользователя
def get_user_excel_file(user_id):
    return f'nalet_{user_id}.xlsx'

# Создание Excel-файла пользователя, если не существует
def init_user_excel(user_id):
    user_file = get_user_excel_file(user_id)
    if not os.path.exists(user_file):
        df = pd.DataFrame(columns=[
            'Дата', 'Упражнение', 'Часы', 'Минуты', 'Тип полёта', 'Время суток', 'Боевой/Тренировочный'
        ])
        df.to_excel(user_file, index=False)

# FSM для пошагового ввода налёта
class NalotStates(StatesGroup):
    waiting_for_exercise = State()
    waiting_for_hours = State()
    waiting_for_minutes = State()
    waiting_for_date = State()

# Классификация упражнения
def classify_exercise(ex_num: int):
    if 128 <= ex_num <= 137:
        return 'Боевой', 'День'
    elif 228 <= ex_num <= 237:
        return 'Боевой', 'Ночь'
    elif 100 <= ex_num < 200:
        return 'Тренировочный', 'День'
    elif 200 <= ex_num < 300:
        return 'Тренировочный', 'Ночь'
    else:
        return 'Тренировочный', 'День'

@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    init_user_excel(message.from_user.id)
    builder = ReplyKeyboardBuilder()
    builder.button(text='Записать новый налёт')
    builder.button(text='Показать статистику')
    builder.button(text='Выгрузить Excel')
    builder.button(text='Удалить последнюю запись')
    builder.button(text='Удалить весь налёт')
    await message.answer(
        'Привет! Я бот учёта налёта. Выберите действие:',
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

# Обработка кнопки "Записать новый налёт"
async def start_nalot(message: types.Message, state: FSMContext):
    await message.answer('Введите номер упражнения:')
    await state.set_state(NalotStates.waiting_for_exercise)

@dp.message(NalotStates.waiting_for_exercise)
async def process_exercise(message: types.Message, state: FSMContext):
    try:
        ex_num = int(message.text)
        await state.update_data(ex_num=ex_num)
        await message.answer('Введите часы налёта:')
        await state.set_state(NalotStates.waiting_for_hours)
    except ValueError:
        await message.answer('Пожалуйста, введите корректный номер упражнения (число).')

@dp.message(NalotStates.waiting_for_hours)
async def process_hours(message: types.Message, state: FSMContext):
    try:
        hours = int(message.text)
        await state.update_data(hours=hours)
        await message.answer('Введите минуты налёта:')
        await state.set_state(NalotStates.waiting_for_minutes)
    except ValueError:
        await message.answer('Пожалуйста, введите часы налёта (целое число).')

@dp.message(NalotStates.waiting_for_minutes)
async def process_minutes(message: types.Message, state: FSMContext):
    try:
        minutes = int(message.text)
        await state.update_data(minutes=minutes)
        await message.answer('Введите дату (ГГГГ-ММ-ДД) или отправьте "-" для сегодняшней даты:')
        await state.set_state(NalotStates.waiting_for_date)
    except ValueError:
        await message.answer('Пожалуйста, введите минуты налёта (целое число).')

@dp.message(NalotStates.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    date_str = message.text.strip()
    if date_str == '-' or date_str == '' or date_str.lower() == 'сегодня':
        date = datetime.now().strftime('%Y-%m-%d')
    else:
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
        except ValueError:
            await message.answer('Пожалуйста, введите дату в формате ГГГГ-ММ-ДД или "-".')
            return
    ex_num = user_data['ex_num']
    hours = user_data['hours']
    minutes = user_data['minutes']
    boevoy, daynight = classify_exercise(ex_num)
    tip_poleta = f'{boevoy} применение' if boevoy == 'Боевой' else 'Тренировочный'
    # Сохраняем в индивидуальный Excel
    user_file = get_user_excel_file(message.from_user.id)
    if not os.path.exists(user_file):
        df = pd.DataFrame(columns=[
            'Дата', 'Упражнение', 'Часы', 'Минуты', 'Тип полёта', 'Время суток', 'Боевой/Тренировочный'
        ])
    else:
        df = pd.read_excel(user_file)
    df.loc[len(df)] = [date, ex_num, hours, minutes, tip_poleta, daynight, boevoy]
    df.to_excel(user_file, index=False)
    await message.answer(f'Запись добавлена!\nДата: {date}\nУпражнение: {ex_num}\nЧасы: {hours}\nМинуты: {minutes}\nТип: {tip_poleta}\nВремя суток: {daynight}')
    await state.clear()

# Заглушки для остальных кнопок
async def show_stats(message: types.Message):
    user_file = get_user_excel_file(message.from_user.id)
    if not os.path.exists(user_file):
        await message.answer('Нет данных для статистики.')
        return
    df = pd.read_excel(user_file)
    if df.empty:
        await message.answer('Нет данных для статистики.')
        return
    # Преобразуем дату
    df['Дата'] = pd.to_datetime(df['Дата'], errors='coerce')
    now = pd.Timestamp.now()
    # Фильтры
    year = now.year
    month = now.month
    three_months_ago = now - DateOffset(months=3)

    def nalet_sum(subdf):
        total_minutes = subdf['Часы'].fillna(0).astype(int) * 60 + subdf['Минуты'].fillna(0).astype(int)
        total = total_minutes.sum()
        return f"{total // 60} ч {total % 60} мин" if total > 0 else "0 ч 0 мин"

    # Общий налёт за всё время
    total_all = nalet_sum(df)
    total_day = nalet_sum(df[df['Время суток'] == 'День'])
    total_night = nalet_sum(df[df['Время суток'] == 'Ночь'])

    # За год
    df_year = df[df['Дата'].dt.year == year]
    year_all = nalet_sum(df_year)
    year_day = nalet_sum(df_year[df_year['Время суток'] == 'День'])
    year_night = nalet_sum(df_year[df_year['Время суток'] == 'Ночь'])
    # За месяц
    df_month = df[(df['Дата'].dt.year == year) & (df['Дата'].dt.month == month)]
    month_all = nalet_sum(df_month)
    month_day = nalet_sum(df_month[df_month['Время суток'] == 'День'])
    month_night = nalet_sum(df_month[df_month['Время суток'] == 'Ночь'])
    # За 3 месяца
    df_3m = df[df['Дата'] >= three_months_ago]
    three_all = nalet_sum(df_3m)
    three_day = nalet_sum(df_3m[df_3m['Время суток'] == 'День'])
    three_night = nalet_sum(df_3m[df_3m['Время суток'] == 'Ночь'])
    # Боевой налёт
    boevoy_all = nalet_sum(df[df['Боевой/Тренировочный'] == 'Боевой'])
    boevoy_day = nalet_sum(df[(df['Боевой/Тренировочный'] == 'Боевой') & (df['Время суток'] == 'День')])
    boevoy_night = nalet_sum(df[(df['Боевой/Тренировочный'] == 'Боевой') & (df['Время суток'] == 'Ночь')])
    # Тренировочный налёт
    tren_all = nalet_sum(df[df['Боевой/Тренировочный'] == 'Тренировочный'])
    tren_day = nalet_sum(df[(df['Боевой/Тренировочный'] == 'Тренировочный') & (df['Время суток'] == 'День')])
    tren_night = nalet_sum(df[(df['Боевой/Тренировочный'] == 'Тренировочный') & (df['Время суток'] == 'Ночь')])

    text = (
        f"\U0001F4C8 <b>Общий налёт за всё время</b>\n"
        f"Всего: <b>{total_all}</b>\nДнём: <b>{total_day}</b>\nНочью: <b>{total_night}</b>\n\n"
        f"<b>За текущий год</b>\nВсего: <b>{year_all}</b>\nДнём: <b>{year_day}</b>\nНочью: <b>{year_night}</b>\n\n"
        f"<b>За текущий месяц</b>\nВсего: <b>{month_all}</b>\nДнём: <b>{month_day}</b>\nНочью: <b>{month_night}</b>\n\n"
        f"<b>За последние 3 месяца</b>\nВсего: <b>{three_all}</b>\nДнём: <b>{three_day}</b>\nНочью: <b>{three_night}</b>\n\n"
        f"<b>Боевой налёт</b>\nВсего: <b>{boevoy_all}</b>\nДнём: <b>{boevoy_day}</b>\nНочью: <b>{boevoy_night}</b>\n\n"
        f"<b>Тренировочный налёт</b>\nВсего: <b>{tren_all}</b>\nДнём: <b>{tren_day}</b>\nНочью: <b>{tren_night}</b>"
    )
    await message.answer(text, parse_mode='HTML')

async def send_excel(message: types.Message):
    user_file = get_user_excel_file(message.from_user.id)
    if os.path.exists(user_file):
        await message.answer_document(FSInputFile(user_file))
    else:
        await message.answer('Файл не найден.')

async def delete_last(message: types.Message):
    user_file = get_user_excel_file(message.from_user.id)
    if os.path.exists(user_file):
        df = pd.read_excel(user_file)
        if len(df) > 0:
            df = df.iloc[:-1]
            df.to_excel(user_file, index=False)
            await message.answer('Последняя запись удалена.')
        else:
            await message.answer('Нет записей для удаления.')
    else:
        await message.answer('Файл не найден.')

async def delete_all(message: types.Message):
    user_file = get_user_excel_file(message.from_user.id)
    if os.path.exists(user_file):
        df = pd.DataFrame(columns=[
            'Дата', 'Упражнение', 'Часы', 'Минуты', 'Тип полёта', 'Время суток', 'Боевой/Тренировочный'
        ])
        df.to_excel(user_file, index=False)
        await message.answer('Весь налёт удалён.')
    else:
        await message.answer('Файл не найден.')

# Универсальный обработчик для кнопок и FSM состояний:
@dp.message()
async def handle_buttons(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    
    # Если мы в состоянии FSM, обрабатываем по состояниям
    if current_state == NalotStates.waiting_for_exercise.state:
        await process_exercise(message, state)
    elif current_state == NalotStates.waiting_for_hours.state:
        await process_hours(message, state)
    elif current_state == NalotStates.waiting_for_minutes.state:
        await process_minutes(message, state)
    elif current_state == NalotStates.waiting_for_date.state:
        await process_date(message, state)
    else:
        # Если не в состоянии FSM, обрабатываем кнопки
        text = message.text
        if text == 'Записать новый налёт':
            await start_nalot(message, state)
        elif text == 'Показать статистику':
            await show_stats(message)
        elif text == 'Выгрузить Excel':
            await send_excel(message)
        elif text == 'Удалить последнюю запись':
            await delete_last(message)
        elif text == 'Удалить весь налёт':
            await delete_all(message)

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main()) 