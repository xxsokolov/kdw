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

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
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
script_dir = os.path.dirname(os.path.abspath(__file__))
default_config_file = os.path.join(script_dir, "kdw.cfg")
persistence_file = os.path.join(script_dir, "persitencebot")

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
) = range(11)

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
    ["📊 Статус служб", "📝 Уровень логов"],
    ["⚙️ Перезагрузить службы", "🤖 Перезагрузить бота"],
    ["🔄 Обновить", "🗑️ Удалить"],
    ["🔙 Назад"]
]
bypass_keyboard = [["Ключи", "Списки"], ["🔙 Назад"]]
key_types_keyboard = [["Shadowsocks"], ["Trojan", "Vmess"], ["🔙 Назад"]]
key_list_keyboard = [["➕ Добавить"], ["🔙 Назад"]]
cancel_keyboard = [["Отмена"]]
lists_action_keyboard = [["👁️ Показать", "➕ Добавить"], ["➖ Удалить"], ["🔙 Назад"]]


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
    Вызывается через `JobQueue`.
    """
    job = context.job
    if not (job and isinstance(job.data, dict) and 'message_id' in job.data and 'text' in job.data):
        return

    await context.bot.edit_message_text(
        chat_id=job.chat_id,
        message_id=job.data['message_id'],
        text=f"{job.data['text']}\n\n🚫 Отменено по таймауту",
        reply_markup=None
    )

async def ask_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, text: str):
    """
    Отправляет сообщение с инлайн-кнопками "Подтвердить" и "Отмена".
    Запускает задачу на удаление этих кнопок через 30 секунд.

    Args:
        update: Объект Update от Telegram.
        context: Контекст бота.
        action (str): Строка действия для `callback_data` (например, "update").
        text (str): Текст сообщения, запрашивающего подтверждение.
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

    context.job_queue.run_once(
        remove_confirmation_keyboard,
        30,
        chat_id=update.effective_chat.id,
        data={'message_id': message.message_id, 'text': text},
        name=f"confirm_{update.effective_chat.id}"
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

# --- Обработчики главного меню ---
@private_access
async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начальная точка диалога. Вызывается по команде /start.
    Приветствует пользователя и показывает главное меню.
    """
    user = update.message.from_user
    log.info(f"Start session for {user.full_name}", extra={'user_id': user.id})
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
    user_id = update.effective_user.id
    key_type = update.message.text.lower()
    
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
    context.user_data['key_config_messages'].append(msg_list_header.message_id)

    for config_path in configs:
        is_active = (config_path == active_config)
        filename = os.path.basename(config_path)
        
        config_data = manager.read_config(config_path)
        server_host = config_data.get("remote_addr") if key_type == 'trojan' else config_data.get("server", "N/A")
        ping_result = await service_manager.get_direct_ping(server_host)

        text = f"📄 `{filename}` (Пинг: {ping_result})"
        
        buttons_row1 = [
            InlineKeyboardButton("🚀 Применить", callback_data=f"key_activate_{key_type}_{filename}"),
            InlineKeyboardButton("👁️ Показать", callback_data=f"key_view_{key_type}_{filename}"),
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"key_delete_{key_type}_{filename}"),
        ]
        if is_active:
            buttons_row1.pop(0)
            buttons_row1.insert(0, InlineKeyboardButton("✅ Активен", callback_data="noop"))
        
        buttons_row2 = [InlineKeyboardButton("🚦 Тест", callback_data=f"key_diagnose_{key_type}_{filename}")]

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

    log.info(f"Действие с ключом: '{action}' для '{filename}' (тип: {key_type})", extra={'user_id': user_id})

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

    elif action == 'diagnose':
        if key_type == 'trojan':
            keyboard = [[InlineKeyboardButton("✅ Да, продолжить", callback_data=f"confirm_diag_trojan_{filename}")], [InlineKeyboardButton("❌ Нет, отмена", callback_data="confirm_cancel")]]
            await query.message.reply_text(
                "Для полного теста Trojan требуется временная остановка службы. "
                "Это может привести к кратковременному разрыву соединения.\n\nПродолжить?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else: # Для Shadowsocks и других
            await run_full_diagnose(query, context, key_type, config_path)


async def run_full_diagnose(query: Update, context: ContextTypes.DEFAULT_TYPE, key_type: str, config_path: str):
    """Запускает полный тест и отправляет отчет."""
    await query.message.edit_text(f"🚦 Выполняю полный тест для *{os.path.basename(config_path)}*...", parse_mode=ParseMode.MARKDOWN)
    
    res = await service_manager.diagnose_full_proxy(key_type, config_path)
    
    if "error" in res:
        await query.message.edit_text(f"❌ Ошибка теста: {res['error']}")
        return

    ping = res.get("ping", "❌")
    latency = res.get("latency", "❌")
    speed = res.get("speed", "❌")
    
    report = f"🚦 Тест *{res.get('server')}*:\n"
    report += f"   Пинг: {ping}\n"
    
    if latency == "❌":
        report += f"   Прокси: ❌ ({res.get('details', 'ошибка')})"
    else:
        report += f"   Прокси: Задержка: {latency} | Скорость: {speed}"

    await query.message.edit_text(report, parse_mode=ParseMode.MARKDOWN)


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

    log.info(f"Найдено {len(urls)} URL для создания ключей типа '{key_type}'", extra={'user_id': user_id})
    
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
    if not lists:
        await update.message.reply_text("Не найдено ни одного файла списков.", reply_markup=ReplyKeyboardMarkup(bypass_keyboard, resize_keyboard=True))
        return BYPASS_MENU
    keyboard = [[l] for l in lists] + [["🔙 Назад"]]
    await update.message.reply_text("Выберите список для управления:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return LISTS_MENU

@private_access
async def select_list_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор конкретного списка и показывает меню действий с ним.
    """
    user_id = update.effective_user.id
    list_name = update.message.text
    context.user_data['current_list'] = list_name
    log.debug(f"Выбран список '{list_name}' для управления", extra={'user_id': user_id})
    await update.message.reply_text(f"Выбран список: *{list_name}*\n\nЧто вы хотите сделать?", reply_markup=ReplyKeyboardMarkup(lists_action_keyboard, resize_keyboard=True), parse_mode=ParseMode.MARKDOWN)
    return SHOW_LIST

@private_access
async def show_list_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показывает содержимое выбранного списка доменов.
    """
    user_id = update.effective_user.id
    list_name = context.user_data.get('current_list')
    log.info(f"Запрошено содержимое списка '{list_name}'", extra={'user_id': user_id})
    content = list_manager.read_list(list_name)
    if len(content) > 4096:
        for x in range(0, len(content), 4096):
            await update.message.reply_text(content[x:x + 4096])
    else:
        await update.message.reply_text(content)
    return SHOW_LIST

@private_access
async def ask_for_domains_to_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запрашивает у пользователя домены для добавления в список.
    """
    user_id = update.effective_user.id
    list_name = context.user_data.get('current_list')
    log.debug(f"Запрошено добавление в список '{list_name}'", extra={'user_id': user_id})
    await update.message.reply_text("Отправьте один или несколько доменов для добавления.", reply_markup=ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True))
    return ADD_TO_LIST

@private_access
async def add_domains_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Добавляет полученные домены в список и применяет изменения.
    """
    user_id = update.effective_user.id
    list_name = context.user_data.get('current_list')
    domains = update.message.text.splitlines()
    log.info(f"Попытка добавить {len(domains)} домен(ов) в список '{list_name}'", extra={'user_id': user_id})
    added = await list_manager.add_to_list(list_name, domains)
    if added:
        await update.message.reply_text("✅ Домены добавлены. Применяю изменения...")
        _success, message = await list_manager.apply_changes()
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("ℹ️ Эти домены уже были в списке.")
    await update.message.reply_text(f"Выбран список: *{list_name}*", reply_markup=ReplyKeyboardMarkup(lists_action_keyboard, resize_keyboard=True), parse_mode=ParseMode.MARKDOWN)
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
    log.info(f"Попытка удалить {len(domains)} домен(ов) из списка '{list_name}'", extra={'user_id': user_id})
    removed = await list_manager.remove_from_list(list_name, domains)
    if removed:
        await update.message.reply_text("✅ Домены удалены. Применяю изменения...")
        _success, message = await list_manager.apply_changes()
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("ℹ️ Этих доменов не было в списке.")
    await update.message.reply_text(f"Выбран список: *{list_name}*", reply_markup=ReplyKeyboardMarkup(lists_action_keyboard, resize_keyboard=True), parse_mode=ParseMode.MARKDOWN)
    return SHOW_LIST

# --- Обработчики меню настроек ---
@private_access
async def menu_settings(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает меню настроек.
    """
    user_id = update.effective_user.id
    log.debug("Переход в меню 'Настройки'", extra={'user_id': user_id})
    await update.message.reply_text("Меню настроек.", reply_markup=ReplyKeyboardMarkup(settings_keyboard, resize_keyboard=True))
    return SETTINGS_MENU

@private_access
async def menu_services_status(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показывает статус системных служб.
    """
    user_id = update.effective_user.id
    log.info("Запрошен статус служб", extra={'user_id': user_id})
    await update.message.reply_text("⏳ Проверяю статус служб...")
    status_report = await service_manager.get_all_statuses()
    await update.message.reply_text(f"Статус служб:\n\n{status_report}")
    return SETTINGS_MENU

@private_access
async def ask_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запрашивает подтверждение на обновление бота.
    """
    await ask_confirmation(update, context, "update", "Вы уверены, что хотите обновить бота до последней версии?")
    return SETTINGS_MENU

@private_access
async def ask_uninstall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запрашивает подтверждение на полное удаление бота.
    """
    await ask_confirmation(update, context, "uninstall", "Вы уверены, что хотите **полностью** удалить бота?")
    return SETTINGS_MENU

@private_access
async def ask_restart_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запрашивает подтверждение на перезапуск служб.
    """
    await ask_confirmation(update, context, "restart_services", "Вы уверены, что хотите перезагрузить все службы обхода?")
    return SETTINGS_MENU

@private_access
async def ask_restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запрашивает подтверждение на перезапуск самого бота.
    """
    await ask_confirmation(update, context, "restart_bot", "Вы уверены, что хотите перезагрузить бота?")
    return SETTINGS_MENU

@private_access
async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает нажатия на инлайн-кнопки подтверждения действий.
    """
    query = update.callback_query
    await query.answer()

    if not query.message:
        log.warning("query.message is None in handle_confirmation")
        return

    user_id = query.from_user.id
    
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    action_parts = query.data.split('_')
    action = action_parts[1]
    
    log.info(f"Подтверждено действие: '{action}'", extra={'user_id': user_id})

    if action == "cancel":
        await query.edit_message_text("Действие отменено.")
    elif action == "update":
        await query.edit_message_text("Начинаю обновление...")
        asyncio.create_task(installer.run_update(update, context))
    elif action == "uninstall":
        await query.edit_message_text("Начинаю полное удаление...")
        asyncio.create_task(installer.run_uninstallation(update, context))
    elif action == "restart_services":
        await query.edit_message_text("⏳ Перезапускаю службы...")
        report = await service_manager.restart_all_services()
        await query.edit_message_text(f"Отчет о перезапуске:\n\n{report}")
    elif action == "restart_bot":
        await query.edit_message_text("⏳ Перезагружаюсь...")
        python_executable = os.path.join(sys.prefix, 'bin', 'python')
        os.execv(python_executable, [python_executable] + sys.argv)
    elif action == "diag" and action_parts[2] == "trojan":
        filename = "_".join(action_parts[3:])
        key_type = 'trojan'
        manager = ConfigManager(key_type)
        config_path = os.path.join(manager.path, filename)
        await run_full_diagnose(query, context, key_type, config_path)


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
    return SETTINGS_MENU

# --- Системные обработчики ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Глобальный обработчик ошибок. Логирует ошибку и отправляет
    сообщение с трассировкой администратору.
    """
    log.error("Exception while handling an update:", exc_info=context.error)
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    
    try:
        admin_id = literal_eval(config.get("telegram", "access_ids"))[0]
    except Exception:
        log.error("Could not parse access_ids or it is empty.")
        return

    message = (f"An exception was raised while handling an update\n"
               f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}</pre>\n\n"
               f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
               f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
               f"<pre>{html.escape(tb_string)}</pre>")
    await context.bot.send_message(chat_id=admin_id, text=message, parse_mode=ParseMode.HTML)

async def post_restart_hook(application: Application):
    """
    Функция, выполняемая после перезапуска бота.
    Отправляет сообщение о успешном перезапуске в чат, из которого он был инициирован.
    """
    restarted_chat_id = os.environ.get('KDW_RESTART_CHAT_ID')
    if restarted_chat_id:
        log.info(f"Бот был перезапущен. Отправка подтверждения в чат {restarted_chat_id}.")
        try:
            await application.bot.send_message(chat_id=restarted_chat_id, text="✅ Бот успешно перезагружен!")
        except Exception as e:
            log.error(f"Не удалось отправить подтверждение о перезапуске: {e}")
        finally:
            del os.environ['KDW_RESTART_CHAT_ID']

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
                   .build())

    # Основной обработчик диалогов, управляющий навигацией по меню
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            # Главное меню
            STATUS: [
                MessageHandler(filters.Regex('^Система обхода$'), menu_bypass_system),
                MessageHandler(filters.Regex('^Настройки$'), menu_settings),
            ],
            # Меню настроек
            SETTINGS_MENU: [
                MessageHandler(filters.Regex('^📊 Статус служб$'), menu_services_status),
                MessageHandler(filters.Regex('^📝 Уровень логов$'), menu_logging),
                MessageHandler(filters.Regex('^⚙️ Перезагрузить службы$'), ask_restart_services),
                MessageHandler(filters.Regex('^🤖 Перезагрузить бота$'), ask_restart_bot),
                MessageHandler(filters.Regex('^🔄 Обновить$'), ask_update),
                MessageHandler(filters.Regex('^🗑️ Удалить$'), ask_uninstall),
                MessageHandler(filters.Regex('^🔙 Назад$'), back_to_main_menu),
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
    application.add_handler(CallbackQueryHandler(handle_log_level_selection, pattern='^log_'))
    application.add_handler(CallbackQueryHandler(handle_key_action, pattern='^noop$'))


    # Регистрируем глобальный обработчик ошибок
    application.add_error_handler(error_handler)

    log.info("KDW Bot запущен")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
