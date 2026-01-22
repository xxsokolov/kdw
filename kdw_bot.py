"""
Основной файл телеграм-бота для управления KDW.

Этот файл содержит всю логику работы бота, включая:
- Определение состояний диалога (ConversationHandler).
- Обработчики команд и сообщений.
- Функции для взаимодействия с модулями ядра (установщик, менеджеры сервисов, списков, конфигов).
- Настройку и запуск приложения `python-telegram-bot`.
"""
import sys
import os
import json
import html
import traceback
import re
from configparser import ConfigParser
from ast import literal_eval
from functools import wraps
import asyncio
import logging
import httpx
from packaging.version import parse as parse_version

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    JobQueue,
    PicklePersistence,
)

from core.log_utils import log, set_level as set_log_level
from core.installer import Installer
from core.service_manager import ServiceManager
from core.list_manager import ListManager
from core.config_manager import ConfigManager
from core.shell_utils import run_shell_command

# --- Глобальные переменные и константы ---
__version__ = "1.0.0"
script_dir = os.path.dirname(os.path.abspath(__file__))
default_config_file = os.path.join(script_dir, "kdw.cfg")
persistence_file = os.path.join(script_dir, "kdw_persistence.pickle")
UPDATE_STATE_FILE = "/tmp/kdw_update_state.json"
FIREWALL_STATE_FILE = "/opt/etc/kdw/firewall_mode.state"

# Порты для прокси
PROXY_PORTS = {
    "shadowsocks": 1080,
    "trojan": 10829,
    "vmess": 10810,
}

# Состояния для ConversationHandler. Определяют шаги диалога с пользователем.
(
    STATUS,
    BYPASS_MENU,
    KEYS_MENU,
    LISTS_MENU,
    SHOW_LIST,
    ADD_TO_LIST,
    REMOVE_FROM_LIST,
    SETTINGS_MENU,
    KEY_TYPE_MENU,
    KEY_LIST_MENU,
    AWAIT_KEY_URL,
    AWAIT_MOVE_CONFIRMATION,
    SYSTEM_MANAGEMENT_MENU,
    BOT_SETTINGS_MENU,
    FIREWALL_MENU,
) = range(15)

# --- Инициализация ---
# Загрузка конфигурации и инициализация основных модулей ядра.
if os.path.isfile(default_config_file):
    config = ConfigParser()
    config.read(default_config_file, encoding='utf-8')
else:
    log.error(f"Error: Config file ({default_config_file}) not found!")
    sys.exit(1)

installer = Installer()
service_manager = ServiceManager()
list_manager = ListManager()

# --- Клавиатуры ---
# Определение раскладок кнопок для различных меню.
main_keyboard = [["Система обхода", "Роутер"], ["Настройки"]]
settings_keyboard = [
    ["Управление системой", "Настройки бота"],
    ["Правила Firewall"],
    ["🔙 Назад"]
]
system_management_keyboard = [
    ["📊 Статус служб", "⚙️ Перезагрузить службы"],
    ["🤖 Перезагрузить бота", "🔄 Обновить"],
    ["🗑️ Удалить", "🔙 Назад"]
]
bot_settings_keyboard = [
    ["📝 Уровень логов", "Пинг в списке"],
    ["Прокси для всего трафика"],
    ["🔙 Назад"]
]
firewall_keyboard = [
    ["🔙 Назад"]
]
bypass_keyboard = [["Ключи", "Списки"], ["🔙 Назад"]]
key_types_keyboard = [["Shadowsocks"], ["Trojan", "Vmess"], ["🔙 Назад"]]
key_list_keyboard = [["➕ Добавить"], ["🔙 Назад"]]
cancel_keyboard = [["Отмена"]]
lists_action_keyboard = [["👁️ Показать", "➕ Добавить"], ["➖ Удалить", "Поиск домена"], ["🔙 Назад"]]


# --- Декораторы ---
def private_access(f):
    """
    Декоратор для ограничения доступа к функциям только для авторизованных пользователей.
    ID авторизованных пользователей берутся из конфиг-файла.
    """
    @wraps(f)
    async def wrapped(update, context, *args, **kwargs):
        user = update.effective_user
        if not user and update.callback_query:
            user = update.callback_query.from_user

        if user and user.id in literal_eval(config.get("telegram", "access_ids")):
            return await f(update, context, *args, **kwargs)
        else:
            if update.callback_query:
                await update.callback_query.answer("❌ У вас нет доступа к этому боту.", show_alert=True)
                return
            else:
                await update.message.reply_text('❌ У вас нет доступа к этому боту.', reply_markup=ReplyKeyboardRemove())
                return ConversationHandler.END
    return wrapped

# --- Вспомогательные функции (хелперы) ---
async def remove_confirmation_keyboard(context: ContextTypes.DEFAULT_TYPE):
    """
    Удаляет инлайн-клавиатуру подтверждения по истечении времени.
    Вызывается через `JobQueue`. Стала более устойчивой к ошибкам.
    """
    job = context.job
    if not (job and isinstance(job.data, dict) and 'message_id' in job.data and 'text' in job.data):
        return

    try:
        await context.bot.edit_message_text(
            chat_id=job.chat_id,
            message_id=job.data['message_id'],
            text=f"{job.data['text']}\n\n🚫 Отменено по таймауту",
            reply_markup=None
        )
    except BadRequest as e:
        if "Message to edit not found" in str(e):
            log.debug(f"Job to remove confirmation keyboard for message {job.data['message_id']} ran, but message was already deleted.")
        else:
            raise e # Перебрасываем другие ошибки BadRequest

async def ask_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, text: str):
    """
    Отправляет сообщение с инлайн-кнопками "Подтвердить" и "Отмена".
    Запускает задачу на удаление этих кнопок через 30 секунд.
    Использует уникальное имя для задачи.
    """
    user_id = update.effective_user.id
    log.debug(f"Запрос подтверждения '{action}'", extra={'user_id': user_id})
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{action}"),
            InlineKeyboardButton("❌ Отмена", callback_data="confirm_cancel"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = await update.message.reply_text(text, reply_markup=reply_markup)

    # Создаем уникальное имя для задачи, чтобы ее можно было отменить
    job_name = f"confirm_timeout_{message.message_id}"
    context.job_queue.run_once(
        remove_confirmation_keyboard,
        30,
        chat_id=update.effective_chat.id,
        data={'message_id': message.message_id, 'text': text},
        name=job_name
    )

async def clear_key_config_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """
    Удаляет ранее отправленные сообщения со списком конфигураций ключей.
    ID сообщений хранятся в `context.user_data['key_config_messages']`.

    Args:
        context: Контекст бота.
        chat_id (int): ID чата, в котором нужно удалить сообщения.
    """
    if 'key_config_messages' in context.user_data:
        for msg_id in context.user_data['key_config_messages']:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception as e:
                log.debug(f"Could not delete message {msg_id}: {e}")
        context.user_data['key_config_messages'] = []

# --- Новые функции для проверки обновлений ---
async def get_latest_version() -> str | None:
    """Получает последнюю версию с GitHub."""
    url = "https://api.github.com/repos/xxsokolov/KDW/releases/latest"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("tag_name", "").lstrip('v')
    except (httpx.RequestError, json.JSONDecodeError) as e:
        log.warning(f"Не удалось проверить обновления: {e}")
        return None

async def check_for_updates(context: ContextTypes.DEFAULT_TYPE):
    """Периодическая задача для проверки обновлений."""
    latest_version_str = await get_latest_version()
    if not latest_version_str:
        return

    current_version = parse_version(__version__)
    latest_version = parse_version(latest_version_str)

    if latest_version > current_version:
        last_notified_version = context.bot_data.get("last_notified_version")
        if str(latest_version) != last_notified_version:
            text = (
                f"📢 Доступно обновление!\n\n"
                f"Текущая версия: `{__version__}`\n"
                f"Новая версия: `{latest_version_str}`\n\n"
                "Нажмите '🔄 Обновить' в меню 'Управление системой', чтобы обновиться."
            )
            for user_id in literal_eval(config.get("telegram", "access_ids")):
                try:
                    await context.bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.MARKDOWN)
                except Exception as e:
                    log.error(f"Не удалось отправить уведомление об обновлении пользователю {user_id}: {e}")
            context.bot_data["last_notified_version"] = str(latest_version)

# --- Обработчики главного меню ---
@private_access
async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начальная точка диалога. Вызывается по команде /start.
    Приветствует пользователя и показывает главное меню.
    """
    user = update.message.from_user
    log.debug(f"Start session for {user.full_name}", extra={'user_id': user.id})
    await update.message.reply_text(f"👋 Привет, {user.full_name}!", reply_markup=ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True))
    return STATUS

@private_access
async def back_to_main_menu(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Возвращает пользователя в главное меню из других разделов.
    """
    user_id = update.effective_user.id
    log.debug("Возврат в главное меню", extra={'user_id': user_id})
    await update.message.reply_text("Главное меню", reply_markup=ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True))
    return STATUS

@private_access
async def menu_bypass_system(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Переводит пользователя в меню управления системой обхода.
    """
    user_id = update.effective_user.id
    log.debug("Переход в меню 'Система обхода'", extra={'user_id': user_id})
    await update.message.reply_text("Меню управления системой обхода.", reply_markup=ReplyKeyboardMarkup(bypass_keyboard, resize_keyboard=True))
    return BYPASS_MENU

# --- Обработчики меню управления ключами ---
@private_access
async def menu_keys(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Переводит в меню выбора типа ключа ('Shadowsocks', 'Trojan' и т.д.).
    Очищает предыдущие сообщения со списками ключей.
    """
    user_id = update.effective_user.id
    log.debug("Переход в меню 'Ключи'", extra={'user_id': user_id})
    await clear_key_config_messages(context, update.effective_chat.id)
    await update.message.reply_text("Выберите тип ключа:", reply_markup=ReplyKeyboardMarkup(key_types_keyboard, resize_keyboard=True))
    return KEY_TYPE_MENU

@private_access
async def menu_key_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор типа ключа, сохраняет его в `user_data` и
    переходит к отображению списка ключей этого типа.
    """
    user_id = update.message.from_user.id
    key_type = update.message.text.lower() # Определение key_type здесь
    
    if key_type not in ['shadowsocks', 'trojan', 'vmess']:
        await update.message.reply_text("Пожалуйста, используйте кнопки.")
        return KEY_TYPE_MENU

    log.debug(f"Выбран тип ключа: {key_type}", extra={'user_id': user_id})
    context.user_data['key_type'] = key_type
    
    await menu_key_list(update, context)
    return KEY_LIST_MENU

async def menu_key_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает список конфигураций для выбранного типа ключа.
    Для каждой конфигурации выводит инлайн-кнопки для действий.
    """
    key_type = context.user_data['key_type']
    manager = ConfigManager(key_type)
    
    configs = manager.get_configs()
    active_config = manager.get_active_config()
    
    await clear_key_config_messages(context, update.effective_chat.id)

    if not configs:
        await update.effective_chat.send_message(f"Не найдено ни одного конфига для {key_type}.", reply_markup=ReplyKeyboardMarkup(key_list_keyboard, resize_keyboard=True))
        return KEY_LIST_MENU

    msg_list_header = await update.effective_chat.send_message(f"Список конфигураций для *{key_type}*:", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardMarkup(key_list_keyboard, resize_keyboard=True))
    context.user_data['key_config_messages'] = [] # Очищаем перед заполнением
    context.user_data['key_config_messages'].append(msg_list_header.message_id)

    show_ping = config.getboolean('general', 'show_ping_on_list', fallback=True)

    for config_path in configs:
        is_active = (config_path == active_config)
        filename = os.path.basename(config_path)
        
        text = f"📄 `{filename}`"
        if show_ping:
            config_data = manager.read_config(config_path)
            server_host = config_data.get("remote_addr") if key_type == 'trojan' else config_data.get("server", "N/A")
            ping_result = await service_manager.get_direct_ping(server_host)
            text += f" (Пинг: {ping_result})"
        
        buttons_row1 = [
            InlineKeyboardButton("🚀 Применить", callback_data=f"key_activate_{key_type}_{filename}"),
            InlineKeyboardButton("👁️ Показать", callback_data=f"key_view_{key_type}_{filename}"),
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"key_delete_{key_type}_{filename}"),
        ]
        if is_active:
            buttons_row1.pop(0)
            buttons_row1.insert(0, InlineKeyboardButton("✅ Активен", callback_data="noop"))
        
        buttons_row2 = [InlineKeyboardButton("🚦 Тест", callback_data=f"key_test_{key_type}_{filename}")]

        msg = await update.effective_chat.send_message(
            text=text,
            reply_markup=InlineKeyboardMarkup([buttons_row1, buttons_row2]),
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data['key_config_messages'].append(msg.message_id)
        
    return KEY_LIST_MENU

@private_access
async def handle_key_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает нажатия на инлайн-кнопки для действий с ключами.
    """
    query = update.callback_query
    
    if query.data == "noop":
        await query.answer("Этот конфиг уже активен.")
        return

    await query.answer()

    if not query.message:
        log.warning("query.message is None in handle_key_action")
        return

    user_id = query.from_user.id
    try:
        action_parts = query.data.split('_')
        action = action_parts[1]
        key_type = action_parts[2]
        filename = "_".join(action_parts[3:])
    except IndexError:
        log.error(f"Invalid callback_data format in handle_key_action: {query.data}")
        await query.answer("Произошла ошибка, попробуйте снова.", show_alert=True)
        return

    context.user_data['key_type'] = key_type
    manager = ConfigManager(key_type)
    config_path = os.path.join(manager.path, filename)

    log.debug(f"Действие с ключом: '{action}' для '{filename}' (тип: {key_type})", extra={'user_id': user_id})

    if action == 'view':
        config_data = manager.read_config(config_path)
        if config_data:
            await query.message.reply_text(f"```json\n{json.dumps(config_data, indent=2)}\n```", parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await query.message.reply_text("Не удалось прочитать конфиг.")
    
    elif action == 'delete':
        if manager.delete_config(config_path):
            await query.edit_message_text(f"🗑️ Конфиг `{filename}` удален.", parse_mode=ParseMode.MARKDOWN)
        else:
            await query.answer("❌ Ошибка удаления", show_alert=True)

    elif action == 'activate':
        await query.answer("Применение...")
        target_link = manager.active_config_link
        
        success, output = await run_shell_command(f"ln -sf {config_path} {target_link}")
        if not success:
            log.error(f"Ошибка создания symlink: {output}")
            await query.message.reply_text(f"❌ Ошибка применения: не удалось создать символическую ссылку.\n`{output}`", parse_mode=ParseMode.MARKDOWN)
            return

        restart_success, restart_output = await service_manager.restart_service(key_type)
        if not restart_success:
            log.error(f"Ошибка перезапуска {key_type}: {restart_output}")
            await query.message.reply_text(f"⚠️ Конфиг `{filename}` применен, но службу перезапустить не удалось. Попробуйте вручную.\n`{restart_output}`", parse_mode=ParseMode.MARKDOWN)
        else:
            await query.message.reply_text(f"🚀 Конфиг `{filename}` применен и служба перезапущена.", parse_mode=ParseMode.MARKDOWN)
        
        await menu_key_list(update, context)

    elif action == 'test':
        base_text = query.message.text
        if key_type == 'trojan':
            context.user_data['test_message_id'] = query.message.message_id
            context.user_data['test_chat_id'] = query.message.chat_id
            context.user_data['test_base_text'] = base_text
            context.user_data['test_reply_markup_json'] = query.message.reply_markup.to_json()
            keyboard = [[InlineKeyboardButton("✅ Да, продолжить", callback_data=f"confirm_test_trojan_{filename}")], [InlineKeyboardButton("❌ Нет, отмена", callback_data="confirm_cancel")]]
            await query.message.reply_text(
                "Для полного теста Trojan требуется временная остановка службы. "
                "Это может привести к кратковременному разрыву соединения.\n\nПродолжить?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await run_full_test(context, key_type, config_path, query.message.message_id, query.message.chat_id, base_text, query.message.reply_markup)


async def run_full_test(context: ContextTypes.DEFAULT_TYPE, key_type: str, config_path: str, message_id: int, chat_id: int, base_text: str, reply_markup):
    """Запускает полный тест и обновляет исходное сообщение с результатами."""
    
    # Убираем старые результаты теста, если они есть
    clean_base_text = base_text.split('\n')[0]

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=f"{clean_base_text}\n🚦 Выполняю полный тест...",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    res = await service_manager.test_full_proxy(key_type, config_path)
    
    if "error" in res:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"{clean_base_text}\n   ↳ Тест: ❌ ({res['error']})",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        return

    latency = res.get("latency", "❌")
    speed = res.get("speed", "❌")
    
    if latency == "❌":
        report_line = f"\n   ↳ Тест: ❌ ({res.get('details', 'ошибка')})"
    else:
        report_line = f"\n   ↳ Тест: ⏱️{latency} | ⚡️{speed}"

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=f"{clean_base_text}{report_line}",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )


@private_access
async def ask_for_key_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запрашивает у пользователя URL ключа для добавления.
    """
    user_id = update.effective_user.id
    key_type = context.user_data['key_type']
    log.debug(f"Запрошено добавление ключа типа '{key_type}'", extra={'user_id': user_id})
    
    url_example = f"`{key_type}://...`"
    
    await update.message.reply_text(
        f"Отправьте сообщение с одним или несколькими ключами.\n"
        f"Поддерживаемый формат: {url_example}",
        reply_markup=ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return AWAIT_KEY_URL

@private_access
async def handle_new_key_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Находит в тексте все URL ключей, создает из них файлы конфигурации
    и обновляет список ключей.
    """
    user_id = update.effective_user.id
    text = update.message.text
    key_type = context.user_data['key_type']
    manager = ConfigManager(key_type)

    url_pattern = rf'{key_type}://[^\s]+'
    urls = re.findall(url_pattern, text)
    
    if not urls:
        await update.message.reply_text(f"Не найдено ни одной ссылки формата `{key_type}://...` в вашем сообщении.", parse_mode=ParseMode.MARKDOWN)
        return AWAIT_KEY_URL

    log.debug(f"Найдено {len(urls)} URL для создания ключей типа '{key_type}'", extra={'user_id': user_id})
    
    results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}
    
    for url in urls:
        status = manager.create_from_url(url)
        if status in results:
            results[status] += 1
        else:
            results["failed"] += 1
            log.warning(f"Не удалось создать конфиг из URL: {url}")

    report = []
    if results["created"] > 0:
        report.append(f"✅ Создано: {results['created']} шт.")
    if results["updated"] > 0:
        report.append(f"🔄 Обновлено: {results['updated']} шт.")
    if results["skipped"] > 0:
        report.append(f"🤷 Пропущено (без изменений): {results['skipped']} шт.")
    if results["failed"] > 0:
        report.append(f"❌ Не удалось добавить: {results['failed']} шт. (проверьте формат ссылок)")
        
    await update.message.reply_text("\n".join(report) if report else "Не найдено новых или измененных ключей.")
        
    await menu_key_list(update, context)
    return KEY_LIST_MENU

# --- Обработчики меню управления списками ---
@private_access
async def menu_lists(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает меню для управления списками доменов.
    """
    user_id = update.effective_user.id
    log.debug("Переход в меню 'Списки'", extra={'user_id': user_id})
    
    lists = list_manager.get_list_files()
    
    # Создаем клавиатуру с 2 кнопками в ряду
    keyboard = []
    row = []
    for l in lists:
        row.append(l.capitalize())
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    keyboard.append(["🔙 Назад"])
    
    await update.message.reply_text("Выберите список для управления:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return LISTS_MENU

@private_access
async def select_list_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор конкретного списка и показывает меню действий с ним.
    """
    user_id = update.effective_user.id
    list_name = update.message.text.lower()
    
    # Проверка, что нажата одна из кнопок
    if list_name not in list_manager.get_list_files():
        await update.message.reply_text("Пожалуйста, используйте кнопки.")
        return LISTS_MENU
        
    context.user_data['current_list'] = list_name
    log.debug(f"Выбран список '{list_name}' для управления", extra={'user_id': user_id})
    await update.message.reply_text(f"Выбран список: *{list_name.capitalize()}*\n\nЧто вы хотите сделать?", reply_markup=ReplyKeyboardMarkup(lists_action_keyboard, resize_keyboard=True), parse_mode=ParseMode.MARKDOWN)
    return SHOW_LIST

@private_access
async def show_list_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показывает содержимое выбранного списка доменов.
    """
    user_id = update.effective_user.id
    list_name = context.user_data.get('current_list')
    log.debug(f"Запрошено содержимое списка '{list_name}'", extra={'user_id': user_id})
    
    content = list_manager.read_list(list_name)
    
    if len(content) > 4000: # Оставляем запас
        await update.message.reply_text(f"Содержимое списка *{list_name.capitalize()}*:", parse_mode=ParseMode.MARKDOWN)
        # Отправляем содержимое в виде файла, если оно слишком большое
        file_path = os.path.join(script_dir, f"{list_name}_content.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        await update.message.reply_document(document=open(file_path, 'rb'))
        os.remove(file_path)
    else:
        await update.message.reply_text(f"Содержимое списка *{list_name.capitalize()}*:\n\n<pre>{html.escape(content)}</pre>", parse_mode=ParseMode.HTML)
        
    return SHOW_LIST

@private_access
async def ask_for_domains_to_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запрашивает у пользователя домены для добавления в список.
    """
    user_id = update.effective_user.id
    list_name = context.user_data.get('current_list')
    log.debug(f"Запрошено добавление в список '{list_name}'", extra={'user_id': user_id})
    await update.message.reply_text("Отправьте один или несколько доменов для добавления. Каждый домен с новой строки.", reply_markup=ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True))
    return ADD_TO_LIST

@private_access
async def add_domains_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Добавляет полученные домены в список, проверяя на уникальность.
    """
    user_id = update.effective_user.id
    target_list = context.user_data.get('current_list')
    domains_to_process = [d.strip() for d in update.message.text.splitlines() if d.strip()]
    
    log.debug(f"Попытка добавить {len(domains_to_process)} домен(ов) в список '{target_list}'", extra={'user_id': user_id})

    domains_to_add = []
    domains_to_move = {} # { 'source_list': ['domain1', 'domain2'] }
    domains_skipped = []

    for domain in domains_to_process:
        source_list = list_manager.find_domain(domain)
        if source_list:
            if source_list == target_list:
                domains_skipped.append(domain)
            else:
                if source_list not in domains_to_move:
                    domains_to_move[source_list] = []
                domains_to_move[source_list].append(domain)
        else:
            domains_to_add.append(domain)

    # --- Обработка доменов, которые нужно переместить ---
    if domains_to_move:
        context.user_data['domains_to_move_data'] = {
            'target_list': target_list,
            'domains_to_move': domains_to_move
        }
        
        move_report = []
        for src, dmns in domains_to_move.items():
            move_report.append(f"Из списка *{src.capitalize()}*: `{', '.join(dmns)}`")
        
        # Исправленная, более простая сборка строки
        text_parts = [
            "⚠️ Некоторые домены уже находятся в других списках.\n",
            "\n".join(move_report),
            f"\nХотите переместить их в список *{target_list.capitalize()}*?"
        ]
        text = "\n".join(text_parts)

        keyboard = [[
            InlineKeyboardButton("✅ Да, переместить", callback_data="move_domain_confirm"),
            InlineKeyboardButton("❌ Нет, пропустить", callback_data="move_domain_cancel"),
        ]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
        
        # Сохраняем "чистые" домены для добавления после подтверждения
        context.user_data['domains_to_add_after_move'] = domains_to_add
        return AWAIT_MOVE_CONFIRMATION

    # --- Если перемещать нечего, просто добавляем "чистые" домены ---
    final_report = []
    changes_made = False
    
    if domains_to_add:
        added = await list_manager.add_to_list(target_list, domains_to_add)
        if added:
            final_report.append(f"✅ Добавлено: {len(domains_to_add)} шт.")
            changes_made = True
        else:
            # Это может случиться, если домены были добавлены в skipped и add
            final_report.append(f"ℹ️ Новых доменов для добавления нет.")

    if domains_skipped:
        final_report.append(f"🤷 Пропущено (уже в списке): {len(domains_skipped)} шт.")

    if not final_report:
        await update.message.reply_text("Вы не отправили ни одного домена.", reply_markup=ReplyKeyboardMarkup(lists_action_keyboard, resize_keyboard=True))
        return SHOW_LIST

    await update.message.reply_text("\n".join(final_report))
    
    if changes_made:
        await update.message.reply_text("Применяю изменения...")
        _success, message = await list_manager.apply_changes()
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

    await update.message.reply_text(f"Выбран список: *{target_list.capitalize()}*", reply_markup=ReplyKeyboardMarkup(lists_action_keyboard, resize_keyboard=True), parse_mode=ParseMode.MARKDOWN)
    return SHOW_LIST

@private_access
async def handle_move_domain_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает подтверждение перемещения доменов.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    action = query.data
    
    move_data = context.user_data.get('domains_to_move_data', {})
    target_list = move_data.get('target_list')
    domains_to_move = move_data.get('domains_to_move')
    domains_to_add_after_move = context.user_data.get('domains_to_add_after_move', [])

    changes_made = False
    report = []

    if action == 'move_domain_confirm':
        log.debug(f"Пользователь {user_id} подтвердил перемещение доменов.", extra={'user_id': user_id})
        moved_count = 0
        if domains_to_move and target_list:
            for source_list, domains in domains_to_move.items():
                for domain in domains:
                    await list_manager.move_domain(domain, source_list, target_list)
                    moved_count += len(domains)
            report.append(f"🔄 Перемещено: {moved_count} шт.")
            changes_made = True
    else:
        log.debug(f"Пользователь {user_id} отменил перемещение доменов.", extra={'user_id': user_id})
        skipped_count = sum(len(d) for d in domains_to_move.values())
        report.append(f"🚫 Перемещение отменено. Пропущено: {skipped_count} шт.")

    # Добавляем домены, которые не требовали перемещения
    if domains_to_add_after_move:
        added = await list_manager.add_to_list(target_list, domains_to_add_after_move)
        if added:
            report.append(f"✅ Добавлено новых: {len(domains_to_add_after_move)} шт.")
            changes_made = True

    await query.edit_message_text("\n".join(report))

    if changes_made:
        await context.bot.send_message(chat_id=query.message.chat_id, text="Применяю изменения...")
        _success, message = await list_manager.apply_changes()
        await context.bot.send_message(chat_id=query.message.chat_id, text=message, parse_mode=ParseMode.MARKDOWN)

    # Очистка user_data
    context.user_data.pop('domains_to_move_data', None)
    context.user_data.pop('domains_to_add_after_move', None)

    await context.bot.send_message(chat_id=query.message.chat_id, text=f"Выбран список: *{target_list.capitalize()}*", reply_markup=ReplyKeyboardMarkup(lists_action_keyboard, resize_keyboard=True), parse_mode=ParseMode.MARKDOWN)
    return SHOW_LIST


@private_access
async def ask_for_domains_to_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запрашивает у пользователя домены для удаления из списка.
    """
    user_id = update.effective_user.id
    list_name = context.user_data.get('current_list')
    log.debug(f"Запрошено удаление из списка '{list_name}'", extra={'user_id': user_id})
    await update.message.reply_text("Отправьте один или несколько доменов для удаления.", reply_markup=ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True))
    return REMOVE_FROM_LIST

@private_access
async def remove_domains_from_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Удаляет полученные домены из списка и применяет изменения.
    """
    user_id = update.effective_user.id
    list_name = context.user_data.get('current_list')
    domains = update.message.text.splitlines()
    log.debug(f"Попытка удалить {len(domains)} домен(ов) из списка '{list_name}'", extra={'user_id': user_id})
    removed = await list_manager.remove_from_list(list_name, domains)
    if removed:
        await update.message.reply_text("✅ Домены удалены. Применяю изменения...")
        _success, message = await list_manager.apply_changes()
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("ℹ️ Этих доменов не было в списке.")
    await update.message.reply_text(f"Выбран список: *{list_name.capitalize()}*", reply_markup=ReplyKeyboardMarkup(lists_action_keyboard, resize_keyboard=True), parse_mode=ParseMode.MARKDOWN)
    return SHOW_LIST

# --- Обработчики меню настроек ---
@private_access
async def menu_settings(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает новое, реорганизованное меню настроек.
    """
    user_id = update.effective_user.id
    log.debug("Переход в меню 'Настройки'", extra={'user_id': user_id})
    await update.message.reply_text("Выберите категорию настроек:", reply_markup=ReplyKeyboardMarkup(settings_keyboard, resize_keyboard=True))
    return SETTINGS_MENU

@private_access
async def menu_system_management(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает меню управления системой.
    """
    user_id = update.effective_user.id
    log.debug("Переход в меню 'Управление системой'", extra={'user_id': user_id})
    await update.message.reply_text("Меню управления системой.", reply_markup=ReplyKeyboardMarkup(system_management_keyboard, resize_keyboard=True))
    return SYSTEM_MANAGEMENT_MENU

@private_access
async def menu_bot_settings(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает меню настроек бота.
    """
    user_id = update.effective_user.id
    log.debug("Переход в меню 'Настройки бота'", extra={'user_id': user_id})
    await update.message.reply_text("Меню настроек бота.", reply_markup=ReplyKeyboardMarkup(bot_settings_keyboard, resize_keyboard=True))
    return BOT_SETTINGS_MENU

@private_access
async def menu_firewall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает меню управления правилами Firewall.
    """
    user_id = update.effective_user.id
    log.debug("Переход в меню 'Правила Firewall'", extra={'user_id': user_id})
    
    # Получаем текущее состояние
    script_path = os.path.join(script_dir, "scripts", "kdw_get_firewall_state.sh")
    success, current_state = await run_shell_command(f"sh {script_path}")
    current_state = current_state.strip() if success else "unknown"

    # Маркируем активную кнопку
    def get_button_text(mode, text):
        return f"✅ {text}" if mode == current_state else text

    keyboard = [
        [InlineKeyboardButton(get_button_text("lists_only", "Применить правила для списков"), callback_data="firewall_apply_lists")],
        [InlineKeyboardButton(get_button_text("all_traffic", "Применить правила для всего трафика"), callback_data="firewall_apply_all")],
        [InlineKeyboardButton(get_button_text("flushed", "Сбросить все правила"), callback_data="firewall_flush")],
    ]
    
    await update.message.reply_text(
        "Здесь вы можете управлять правилами `iptables` для прокси.\n\n"
        "Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("Меню Firewall.", reply_markup=ReplyKeyboardMarkup(firewall_keyboard, resize_keyboard=True))
    return FIREWALL_MENU

@private_access
async def handle_firewall_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает нажатия на инлайн-кнопки для управления правилами Firewall.
    """
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    action = query.data.split("firewall_")[-1]
    
    log.debug(f"Запрошено действие с Firewall: {action}", extra={'user_id': user_id})

    command = ""
    new_state = ""
    
    if action == "apply_lists":
        script_path = os.path.join(script_dir, "scripts", "kdw_apply_proxy_lists.sh")
        command = f"sh {script_path}"
        new_state = "lists_only"
        await query.message.edit_text("⏳ Применяю правила для списков...", reply_markup=None)

    elif action == "flush":
        script_path = os.path.join(script_dir, "scripts", "kdw_flush_proxy_rules.sh")
        command = f"sh {script_path}"
        new_state = "flushed"
        await query.message.edit_text("⏳ Сбрасываю правила...", reply_markup=None)

    elif action == "apply_all":
        default_proxy = config.get('firewall', 'default_proxy_type', fallback='trojan')
        manager = ConfigManager(default_proxy)
        
        if not manager.get_active_config():
            await query.message.edit_text(
                f"❌ Ошибка: не найден активный ключ для прокси типа '{default_proxy}', "
                f"установленного по умолчанию в kdw.cfg.",
                reply_markup=None
            )
            return FIREWALL_MENU
            
        port = PROXY_PORTS.get(default_proxy)
        if not port:
            await query.message.edit_text(f"❌ Ошибка: не определен порт для прокси типа '{default_proxy}'.", reply_markup=None)
            return FIREWALL_MENU

        script_path = os.path.join(script_dir, "scripts", "kdw_apply_all_traffic_proxy.sh")
        command = f"sh {script_path} {default_proxy} {port}"
        new_state = "all_traffic"
        await query.message.edit_text(f"⏳ Применяю правила для всего трафика через {default_proxy}...", reply_markup=None)

    else:
        return FIREWALL_MENU

    # Записываем новое состояние для сохранения после перезагрузки
    with open(FIREWALL_STATE_FILE, "w") as f:
        f.write(new_state)

    success, output = await run_shell_command(command)
    
    if success:
        await query.message.edit_text(f"✅ Готово!\n\n<pre>{html.escape(output)}</pre>", parse_mode=ParseMode.HTML)
    else:
        await query.message.edit_text(f"❌ Ошибка выполнения скрипта!\n\n<pre>{html.escape(output)}</pre>", parse_mode=ParseMode.HTML)
        
    return FIREWALL_MENU

@private_access
async def menu_services_status(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показывает статус системных служб.
    """
    user_id = update.effective_user.id
    log.debug("Запрошен статус служб", extra={'user_id': user_id})
    await update.message.reply_text("⏳ Проверяю статус служб...")
    status_report = await service_manager.get_all_statuses()
    await update.message.reply_text(f"Статус служб:\n\n{status_report}")
    return SYSTEM_MANAGEMENT_MENU

@private_access
async def ask_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрашивает подтверждение на обновление бота."""
    user_id = update.effective_user.id
    log.debug("Запрошено обновление", extra={'user_id': user_id})

    latest_version_str = await get_latest_version()
    version_info = f"Текущая версия: `{__version__}`\n"
    if latest_version_str:
        version_info += f"Последняя доступная версия: `{latest_version_str}`\n\n"
    else:
        version_info += "Не удалось проверить последнюю версию.\n\n"

    text = (
        f"{version_info}"
        "Вы уверены, что хотите запустить обновление?\n\n"
        "Будут загружены и установлены последние версии файлов бота. "
        "Это приведет к временной остановке всех сервисов и перезапуску бота. "
        "Ваши настройки, ключи и списки затронуты не будут."
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Начать обновление", callback_data="update_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="update_cancel"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return SYSTEM_MANAGEMENT_MENU

@private_access
async def ask_uninstall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запрашивает подтверждение на полное удаление бота.
    """
    await ask_confirmation(update, context, "uninstall", "Вы уверены, что хотите **полностью** удалить бота?")
    return SYSTEM_MANAGEMENT_MENU

@private_access
async def ask_restart_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запрашивает подтверждение на перезапуск служб.
    """
    await ask_confirmation(update, context, "restart_services", "Вы уверены, что хотите перезагрузить все службы обхода?")
    return SYSTEM_MANAGEMENT_MENU

@private_access
async def ask_restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запрашивает подтверждение на перезапуск самого бота.
    """
    await ask_confirmation(update, context, "restart_bot", "Вы уверены, что хотите перезагрузить бота?")
    return SYSTEM_MANAGEMENT_MENU

@private_access
async def handle_update_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает подтверждение и запуск процесса обновления.
    """
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "update_confirm":
        log.debug("Пользователь подтвердил обновление.", extra={'user_id': user_id})
        
        # Сохраняем chat_id для хука после обновления
        update_state = {'chat_id': query.message.chat_id}
        with open(UPDATE_STATE_FILE, 'w') as f:
            json.dump(update_state, f)
            
        message = await query.message.edit_text("🚀 Обновление началось...", reply_markup=None)
        
        # Запускаем обновление в фоне
        asyncio.create_task(installer.run_update(update, context, message))

    elif query.data == "update_cancel":
        log.debug("Пользователь отменил обновление.", extra={'user_id': user_id})
        await query.message.edit_text("Обновление отменено.", reply_markup=None)

@private_access
async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает нажатия на инлайн-кнопки подтверждения действий.
    Теперь также отменяет задачу авто-отмены.
    """
    query = update.callback_query
    await query.answer()

    if not query.message:
        log.warning("query.message is None in handle_confirmation")
        return

    # --- NEW: Отменяем задачу авто-отмены ---
    job_name = f"confirm_timeout_{query.message.message_id}"
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    if current_jobs:
        for job in current_jobs:
            job.schedule_removal()
        log.debug(f"Отменена задача авто-отмены подтверждения: {job_name}")
    # --- END NEW ---

    user_id = query.from_user.id
    
    try:
        await query.message.delete()
    except Exception:
        pass

    action_string = query.data.replace("confirm_", "")
    log.debug(f"Подтверждено действие: '{action_string}'", extra={'user_id': user_id})

    if action_string == "cancel":
        test_message_id = context.user_data.get('test_message_id')
        if test_message_id:
            base_text = context.user_data.get('test_base_text', 'Действие отменено.')
            reply_markup_json = context.user_data.get('test_reply_markup_json')
            if reply_markup_json:
                reply_markup = InlineKeyboardMarkup.de_json(json.loads(reply_markup_json), context.bot)
            else:
                reply_markup = None
            await context.bot.edit_message_text(chat_id=query.message.chat_id, message_id=test_message_id, text=base_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    
    elif action_string == "uninstall":
        await query.message.reply_text("Начинаю полное удаление...")
        asyncio.create_task(installer.run_uninstallation(update, context))
    
    elif action_string == "restart_services":
        await query.message.reply_text("⏳ Перезапускаю службы...")
        report = await service_manager.restart_all_services()
        await query.message.reply_text(f"Отчет о перезапуске:\n\n{report}")
    
    elif action_string == "restart_bot":
        await query.message.reply_text("⏳ Перезагружаюсь...")
        python_executable = os.path.join(sys.prefix, 'bin', 'python')
        os.execv(python_executable, [python_executable] + sys.argv)
    
    elif action_string.startswith("test_trojan_"):
        filename = action_string.replace("test_trojan_", "")
        key_type = 'trojan'
        manager = ConfigManager(key_type)
        config_path = os.path.join(manager.path, filename)
        
        message_id = context.user_data.get('test_message_id')
        chat_id = context.user_data.get('test_chat_id')
        base_text_from_data = context.user_data.get('test_base_text')
        reply_markup_json = context.user_data.get('test_reply_markup_json')

        if message_id and chat_id and base_text_from_data and reply_markup_json:
            # Восстанавливаем Markdown-разметку для имени файла, чтобы избежать ошибки парсинга
            ping_match = re.search(r'\(Пинг: .*\)', base_text_from_data)
            ping_text = ping_match.group(0) if ping_match else ""
            
            # Создаем правильный base_text с Markdown
            base_text = f"📄 `{filename}` {ping_text}".strip()

            reply_markup = InlineKeyboardMarkup.de_json(json.loads(reply_markup_json), context.bot)
            await run_full_test(context, key_type, config_path, message_id, chat_id, base_text, reply_markup)
        else:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ Ошибка: не удалось найти исходное сообщение для теста.")


@private_access
async def handle_log_level_selection(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает нажатия на инлайн-кнопки для смены уровня логирования.
    """
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    new_level = query.data.split('_', 1)[1]

    if new_level == 'cancel':
        log.debug("Отмена смены уровня логирования", extra={'user_id': user_id})
        await query.edit_message_text("Действие отменено.", reply_markup=None)
    else:
        if not config.has_section('logging'):
            config.add_section('logging')
        config.set('logging', 'level', new_level)
        with open(default_config_file, 'w', encoding='utf-8') as configfile:
            config.write(configfile)
        set_log_level(new_level, user_id=user_id)
        await query.edit_message_text(f"✅ Уровень логирования изменен на *{new_level}*.", parse_mode=ParseMode.MARKDOWN, reply_markup=None)

@private_access
async def menu_logging(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает меню выбора уровня логирования.
    """
    user_id = update.effective_user.id
    log.debug("Переход в меню 'Уровень логов'", extra={'user_id': user_id})
    current_level = logging.getLevelName(log.level)
    
    levels = ['INFO', 'WARNING', 'ERROR', 'DEBUG']
    keyboard = [
        [InlineKeyboardButton(f"• {level} •" if level == current_level else level, callback_data=f"log_{level}")]
        for level in levels
    ]
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="log_cancel")])
    
    await update.message.reply_text(
        f"Текущий уровень логирования: *{current_level}*.\n\nВыберите новый уровень:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return BOT_SETTINGS_MENU

@private_access
async def menu_ping_toggle(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает меню для включения/отключения пинга в списке ключей.
    """
    user_id = update.effective_user.id
    log.debug("Переход в меню 'Пинг в списке'", extra={'user_id': user_id})
    
    show_ping = config.getboolean('general', 'show_ping_on_list', fallback=True)
    
    status_text = "включен" if show_ping else "отключен"
    
    keyboard = [
        [
            InlineKeyboardButton("Включить", callback_data="ping_toggle_on"),
            InlineKeyboardButton("Выключить", callback_data="ping_toggle_off"),
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data="ping_toggle_cancel")]
    ]
    
    await update.message.reply_text(
        f"Пинг в списке ключей сейчас *{status_text}*.\n\nХотите изменить?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return BOT_SETTINGS_MENU

@private_access
async def handle_ping_toggle(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает включение/отключение пинга.
    """
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    action = query.data.split('_')[-1]

    if action == 'cancel':
        log.debug("Отмена изменения настройки пинга", extra={'user_id': user_id})
        await query.edit_message_text("Действие отменено.", reply_markup=None)
        return

    new_value = (action == 'on')
    
    if not config.has_section('general'):
        config.add_section('general')
    config.set('general', 'show_ping_on_list', str(new_value).lower())
    
    with open(default_config_file, 'w', encoding='utf-8') as configfile:
        config.write(configfile)
        
    # Перечитываем конфиг, чтобы изменения вступили в силу немедленно
    config.read(default_config_file, encoding='utf-8')
    
    status_text = "включен" if new_value else "отключен"
    log.debug(f"Пинг в списке ключей {status_text}", extra={'user_id': user_id})
    await query.edit_message_text(f"✅ Пинг в списке ключей *{status_text}*.", parse_mode=ParseMode.MARKDOWN, reply_markup=None)

@private_access
async def menu_default_proxy_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает меню выбора типа прокси по умолчанию для режима "весь трафик".
    """
    user_id = update.effective_user.id
    log.debug("Переход в меню 'Прокси для всего трафика'", extra={'user_id': user_id})
    
    current_default = config.get('firewall', 'default_proxy_type', fallback='trojan')
    
    keyboard = []
    for proxy_type in PROXY_PORTS.keys():
        button_text = f"• {proxy_type.capitalize()} •" if proxy_type == current_default else proxy_type.capitalize()
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"set_default_proxy_{proxy_type}")])
    
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="set_default_proxy_cancel")])
    
    await update.message.reply_text(
        f"Текущий прокси по умолчанию для режима 'весь трафик': *{current_default}*.\n\n"
        "Выберите новый тип прокси:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return BOT_SETTINGS_MENU

@private_access
async def handle_default_proxy_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает выбор нового типа прокси по умолчанию.
    """
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    action = query.data.split("set_default_proxy_")[-1]

    if action == 'cancel':
        log.debug("Отмена смены прокси по умолчанию.", extra={'user_id': user_id})
        await query.edit_message_text("Действие отменено.", reply_markup=None)
        return

    new_default_proxy = action
    
    if not config.has_section('firewall'):
        config.add_section('firewall')
    config.set('firewall', 'default_proxy_type', new_default_proxy)
    
    with open(default_config_file, 'w', encoding='utf-8') as configfile:
        config.write(configfile)
        
    # Перечитываем конфиг
    config.read(default_config_file, encoding='utf-8')
    
    log.debug(f"Прокси по умолчанию изменен на '{new_default_proxy}'", extra={'user_id': user_id})
    await query.edit_message_text(f"✅ Прокси по умолчанию для режима 'весь трафик' изменен на *{new_default_proxy}*.", parse_mode=ParseMode.MARKDOWN, reply_markup=None)


# --- Системные обработчики ---

async def _send_long_technical_message(bot, chat_id, text, prefix):
    """
    Вспомогательная функция для отправки длинных технических сообщений по частям.
    Каждая часть оборачивается в спойлер и тег <pre>.
    """
    CHUNK_SIZE = 4000  # Макс. размер части, чтобы не превысить лимит Telegram
    
    try:
        await bot.send_message(chat_id=chat_id, text=prefix, parse_mode=ParseMode.HTML)
    except Exception as e:
        log.error(f"Не удалось отправить префикс для сообщения об ошибке: {e}")
        return

    escaped_text = html.escape(text)
    if not escaped_text.strip():
        escaped_text = "(пусто)"

    for i in range(0, len(escaped_text), CHUNK_SIZE):
        chunk = escaped_text[i:i + CHUNK_SIZE]
        message_chunk = f"<tg-spoiler><pre>{chunk}</pre></tg-spoiler>"
        try:
            await bot.send_message(chat_id=chat_id, text=message_chunk, parse_mode=ParseMode.HTML)
        except Exception as e:
            log.error(f"Не удалось отправить часть сообщения об ошибке в чат {chat_id}: {e}")
            try:
                await bot.send_message(chat_id=chat_id, text="<i>[Не удалось отправить часть технической информации]</i>", parse_mode=ParseMode.HTML)
            except Exception:
                pass


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Глобальный обработчик ошибок. Логирует ошибку и отправляет
    сообщение с трассировкой в чат, где произошла ошибка, или администратору.
    Техническая информация разбивается на логические блоки (update, user_data и т.д.)
    и отправляется отдельными сообщениями, чтобы избежать разрыва данных.
    """
    log.error("Exception while handling an update:", exc_info=context.error)

    # Определяем chat_id для отправки отчета
    chat_id = None
    if isinstance(update, Update) and update.effective_chat:
        chat_id = update.effective_chat.id
    if not chat_id:
        try:
            chat_id = literal_eval(config.get("telegram", "access_ids"))[0]
            log.debug(f"Не удалось определить чат ошибки, отправка администратору {chat_id}")
        except Exception:
            log.error("Не удалось определить чат ошибки и не найден ID администратора.")
            return

    # 1. Отправляем основное, нетехническое сообщение
    message = (
        "<b>🤖 Ой, что-то пошло не так...</b>\n\n"
        "Произошла внутренняя ошибка. Лог записан. "
        "Ниже будет отправлена техническая информация для отладки."
    )
    try:
        await context.bot.send_message(chat_id=chat_id, text=message, parse_mode=ParseMode.HTML)
    except Exception as e:
        log.error(f"Не удалось отправить основное сообщение об ошибке в чат {chat_id}: {e}")
        return

    # 2. Готовим и отправляем техническую информацию по частям
    try:
        # 2.1. Контекст вызова (Update)
        update_str = update.to_dict() if isinstance(update, Update) else str(update)
        update_json_str = json.dumps(update_str, indent=2, ensure_ascii=False)
        await _send_long_technical_message(context.bot, chat_id, update_json_str, "<b>Контекст вызова (Update):</b>")

        # 2.2. Данные чата (context.chat_data)
        chat_data_str = str(context.chat_data)
        await _send_long_technical_message(context.bot, chat_id, chat_data_str, "<b>Данные чата (context.chat_data):</b>")

        # 2.3. Данные пользователя (context.user_data)
        user_data_str = str(context.user_data)
        await _send_long_technical_message(context.bot, chat_id, user_data_str, "<b>Данные пользователя (context.user_data):</b>")

        # 2.4. Трассировка ошибки (Traceback)
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = "".join(tb_list)
        await _send_long_technical_message(context.bot, chat_id, tb_string, "<b>Трассировка ошибки:</b>")
    except Exception as e:
        log.error(f"Произошла критическая ошибка внутри error_handler при отправке деталей: {e}")
        try:
            await context.bot.send_message(chat_id=chat_id, text="<i>[Произошла ошибка при формировании отчета об ошибке.]</i>", parse_mode=ParseMode.HTML)
        except Exception:
            pass


async def post_restart_hook(application: Application):
    """
    Функция, выполняемая после перезапуска бота.
    Отправляет сообщение о успешном перезапуске в чат, из которого он был инициирован.
    """
    restarted_chat_id = os.environ.get('KDW_RESTART_CHAT_ID')
    if restarted_chat_id:
        log.debug(f"Бот был перезапущен. Отправка подтверждения в чат {restarted_chat_id}.")
        try:
            await application.bot.send_message(chat_id=restarted_chat_id, text="✅ Бот успешно перезагружен!")
        except Exception as e:
            log.error(f"Не удалось отправить подтверждение о перезапуске: {e}")
        finally:
            del os.environ['KDW_RESTART_CHAT_ID']


async def post_update_hook(application: Application):
    """
    Проверяет, был ли бот обновлен, и отправляет уведомление.
    """
    if os.path.exists(UPDATE_STATE_FILE):
        log.debug("Обнаружен файл состояния обновления. Отправка уведомления.")
        try:
            with open(UPDATE_STATE_FILE, 'r') as f:
                state = json.load(f)
            chat_id = state.get('chat_id')
            if chat_id:
                await application.bot.send_message(chat_id=chat_id, text="✅ Обновление успешно завершено!")
        except Exception as e:
            log.error(f"Не удалось отправить уведомление о завершении обновления: {e}")
        finally:
            os.remove(UPDATE_STATE_FILE)


def main() -> None:
    """
    Основная функция.
    Настраивает и запускает бота, определяет логику диалогов.
    """
    # Настройка персистентности для сохранения состояний между перезапусками
    persistence = PicklePersistence(filepath=persistence_file)
    job_queue = JobQueue()
    
    application = (Application.builder()
                   .token(config.get("telegram", "token"))
                   .persistence(persistence)
                   .job_queue(job_queue)
                   .post_init(post_restart_hook)
                   .post_init(post_update_hook)
                   .build())

    # Запускаем периодическую проверку обновлений (раз в 24 часа)
    application.job_queue.run_repeating(check_for_updates, interval=86400, first=10)

    # Основной обработчик диалогов, управляющий навигацией по меню
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            # Главное меню
            STATUS: [
                MessageHandler(filters.Regex('^Система обхода$'), menu_bypass_system),
                MessageHandler(filters.Regex('^Настройки$'), menu_settings),
            ],
            # Меню настроек (теперь это хаб)
            SETTINGS_MENU: [
                MessageHandler(filters.Regex('^Управление системой$'), menu_system_management),
                MessageHandler(filters.Regex('^Настройки бота$'), menu_bot_settings),
                MessageHandler(filters.Regex('^Правила Firewall$'), menu_firewall),
                MessageHandler(filters.Regex('^🔙 Назад$'), back_to_main_menu),
            ],
            # Новое подменю "Управление системой"
            SYSTEM_MANAGEMENT_MENU: [
                MessageHandler(filters.Regex('^📊 Статус служб$'), menu_services_status),
                MessageHandler(filters.Regex('^⚙️ Перезагрузить службы$'), ask_restart_services),
                MessageHandler(filters.Regex('^🤖 Перезагрузить бота$'), ask_restart_bot),
                MessageHandler(filters.Regex('^🔄 Обновить$'), ask_update),
                MessageHandler(filters.Regex('^🗑️ Удалить$'), ask_uninstall),
                MessageHandler(filters.Regex('^🔙 Назад$'), menu_settings),
            ],
            # Новое подменю "Настройки бота"
            BOT_SETTINGS_MENU: [
                MessageHandler(filters.Regex('^📝 Уровень логов$'), menu_logging),
                MessageHandler(filters.Regex('^Пинг в списке$'), menu_ping_toggle),
                MessageHandler(filters.Regex('^Прокси для всего трафика$'), menu_default_proxy_type),
                MessageHandler(filters.Regex('^🔙 Назад$'), menu_settings),
            ],
            # Новое подменю "Правила Firewall"
            FIREWALL_MENU: [
                MessageHandler(filters.Regex('^🔙 Назад$'), menu_settings),
            ],
            # Меню системы обхода
            BYPASS_MENU: [
                MessageHandler(filters.Regex('^Ключи$'), menu_keys),
                MessageHandler(filters.Regex('^Списки$'), menu_lists),
                MessageHandler(filters.Regex('^🔙 Назад$'), back_to_main_menu),
            ],
            # Меню выбора типа ключа
            KEY_TYPE_MENU: [
                MessageHandler(filters.Regex('^(Shadowsocks|Trojan|Vmess)$'), menu_key_type),
                MessageHandler(filters.Regex('^🔙 Назад$'), menu_bypass_system),
            ],
            # Меню списка ключей
            KEY_LIST_MENU: [
                MessageHandler(filters.Regex('^➕ Добавить$'), ask_for_key_url),
                MessageHandler(filters.Regex('^🔙 Назад$'), menu_keys),
            ],
            # Ожидание URL ключа
            AWAIT_KEY_URL: [
                MessageHandler(filters.Regex('^Отмена$'), menu_key_list),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_key_url),
            ],
            # Меню выбора списка доменов
            LISTS_MENU: [
                MessageHandler(filters.Regex('^🔙 Назад$'), menu_bypass_system),
                MessageHandler(filters.Regex('^Отмена$'), menu_bypass_system),
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_list_action),
            ],
            # Меню действий со списком
            SHOW_LIST: [
                MessageHandler(filters.Regex('^👁️ Показать$'), show_list_content),
                MessageHandler(filters.Regex('^➕ Добавить$'), ask_for_domains_to_add),
                MessageHandler(filters.Regex('^➖ Удалить$'), ask_for_domains_to_remove),
                MessageHandler(filters.Regex('^🔙 Назад$'), menu_lists),
            ],
            # Ожидание доменов для добавления
            ADD_TO_LIST: [
                MessageHandler(filters.Regex('^Отмена$'), select_list_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_domains_to_list),
            ],
            # Ожидание доменов для удаления
            REMOVE_FROM_LIST: [
                MessageHandler(filters.Regex('^Отмена$'), select_list_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, remove_domains_from_list),
            ],
            # Ожидание подтверждения перемещения домена
            AWAIT_MOVE_CONFIRMATION: [
                CallbackQueryHandler(handle_move_domain_confirmation, pattern='^move_domain_')
            ],
        },
        fallbacks=[CommandHandler('start', start)],
        persistent=True,
        name="main_conversation",
        per_chat=False,
        per_user=True,
        per_message=False,
    )

    application.add_handler(conv_handler)
    
    # Добавляем обработчики колбэков отдельно от ConversationHandler, чтобы избежать конфликтов состояний
    application.add_handler(CallbackQueryHandler(handle_key_action, pattern='^key_'))
    application.add_handler(CallbackQueryHandler(handle_confirmation, pattern='^confirm_'))
    application.add_handler(CallbackQueryHandler(handle_update_confirmation, pattern='^update_'))
    application.add_handler(CallbackQueryHandler(handle_log_level_selection, pattern='^log_'))
    application.add_handler(CallbackQueryHandler(handle_ping_toggle, pattern='^ping_toggle_'))
    application.add_handler(CallbackQueryHandler(handle_firewall_action, pattern='^firewall_'))
    application.add_handler(CallbackQueryHandler(handle_default_proxy_type_selection, pattern='^set_default_proxy_'))
    application.add_handler(CallbackQueryHandler(handle_key_action, pattern='^noop$'))


    # Регистрируем глобальный обработчик ошибок
    application.add_error_handler(error_handler)

    log.info("KDW Bot запущен")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
