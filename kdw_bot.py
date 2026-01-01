import sys
import os
import json
import html
import traceback
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
from core.key_manager import KeyManager

# --- Глобальные переменные и константы ---
script_dir = os.path.dirname(os.path.abspath(__file__))
default_config_file = os.path.join(script_dir, "kdw.cfg")
persistence_file = os.path.join(script_dir, "persitencebot")

# Состояния для ConversationHandler
(
    STATUS,
    BYPASS_MENU,
    KEYS_MENU,
    LISTS_MENU,
    SHOW_LIST,
    ADD_TO_LIST,
    REMOVE_FROM_LIST,
    AWAIT_SHADOWSOCKS_KEY,
    AWAIT_VMESS_KEY,
    AWAIT_TROJAN_KEY,
    SETTINGS_MENU,
) = range(11)

# --- Инициализация ---
if os.path.isfile(default_config_file):
    config = ConfigParser()
    config.read(default_config_file, encoding='utf-8')
else:
    log.error(f"Error: Config file ({default_config_file}) not found!")
    sys.exit(1)

installer = Installer()
service_manager = ServiceManager()
list_manager = ListManager()
key_manager = KeyManager()

# --- Клавиатуры ---
main_keyboard = [["Система обхода", "Роутер"], ["Настройки"]]
settings_keyboard = [
    ["🔄 Обновить", "🗑️ Удалить"],
    ["⚙️ Перезагрузить службы", "📝 Уровень логов"],
    ["📊 Статус служб"],
    ["🔙 Назад"]
]
bypass_keyboard = [["Ключи", "Списки"], ["🔙 Назад"]]
keys_keyboard = [["Shadowsocks", "Trojan"], ["Vmess"], ["🔙 Назад"]]
lists_action_keyboard = [["👁️ Показать", "➕ Добавить"], ["➖ Удалить"], ["🔙 Назад"]]
cancel_keyboard = [["Отмена"]]

# --- Декораторы ---
def private_access(f):
    @wraps(f)
    async def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id in literal_eval(config.get("telegram", "access_ids")):
            return await f(update, context, *args, **kwargs)
        else:
            # Обработка как для message, так и для callback_query
            if update.callback_query:
                await update.callback_query.answer("❌ У вас нет доступа к этому боту.", show_alert=True)
            else:
                await update.message.reply_text('❌ У вас нет доступа к этому боту.', reply_markup=ReplyKeyboardRemove())
    return wrapped

# --- Хелперы для подтверждения ---
async def remove_confirmation_keyboard(context: ContextTypes.DEFAULT_TYPE):
    """Удаляет inline-клавиатуру и сообщает о таймауте."""
    job = context.job
    await context.bot.edit_message_text(
        chat_id=job.chat_id,
        message_id=job.data['message_id'],
        text=f"{job.data['text']}\n\n_(Время на подтверждение истекло)_",
        reply_markup=None
    )

async def ask_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, text: str):
    """Отправляет сообщение с кнопками подтверждения и запускает таймер."""
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

# --- Основные обработчики ---
@private_access
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    log.info(f"Start session for {user.full_name}", extra={'user_id': user.id})
    await update.message.reply_text(f"👋 Привет, {user.full_name}!", reply_markup=ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True))
    return STATUS

@private_access
async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    log.debug("Возврат в главное меню", extra={'user_id': user_id})
    await update.message.reply_text("Главное меню", reply_markup=ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True))
    return STATUS

@private_access
async def menu_bypass_system(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    log.debug("Переход в меню 'Система обхода'", extra={'user_id': user_id})
    await update.message.reply_text("Меню управления системой обхода.", reply_markup=ReplyKeyboardMarkup(bypass_keyboard, resize_keyboard=True))
    return BYPASS_MENU

# --- Меню служб ---
@private_access
async def menu_services_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    log.debug("Запрошен статус служб", extra={'user_id': user_id})
    await update.message.reply_text("⏳ Проверяю статус служб...")
    status_report = await service_manager.get_all_statuses()
    await update.message.reply_text(f"Статус служб:\n\n{status_report}")
    return SETTINGS_MENU

# --- Меню списков ---
@private_access
async def menu_lists(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
    user_id = update.effective_user.id
    list_name = update.message.text
    context.user_data['current_list'] = list_name
    log.debug(f"Выбран список '{list_name}' для управления", extra={'user_id': user_id})
    await update.message.reply_text(f"Выбран список: *{list_name}*\n\nЧто вы хотите сделать?", reply_markup=ReplyKeyboardMarkup(lists_action_keyboard, resize_keyboard=True), parse_mode=ParseMode.MARKDOWN)
    return SHOW_LIST

@private_access
async def show_list_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    list_name = context.user_data.get('current_list')
    log.debug(f"Запрошено содержимое списка '{list_name}'", extra={'user_id': user_id})
    content = list_manager.read_list(list_name)
    if len(content) > 4096:
        for x in range(0, len(content), 4096):
            await update.message.reply_text(content[x:x + 4096])
    else:
        await update.message.reply_text(content)
    return SHOW_LIST

@private_access
async def ask_for_domains_to_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    list_name = context.user_data.get('current_list')
    log.debug(f"Запрошено добавление в список '{list_name}'", extra={'user_id': user_id})
    await update.message.reply_text("Отправьте один или несколько доменов для добавления.", reply_markup=ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True))
    return ADD_TO_LIST

@private_access
async def add_domains_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    list_name = context.user_data.get('current_list')
    domains = update.message.text.splitlines()
    log.debug(f"Попытка добавить {len(domains)} домен(ов) в список '{list_name}'", extra={'user_id': user_id})
    added = await list_manager.add_to_list(list_name, domains)
    if added:
        await update.message.reply_text("✅ Домены добавлены. Применяю изменения...")
        success, message = await list_manager.apply_changes()
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("ℹ️ Эти домены уже были в списке.")
    await update.message.reply_text(f"Выбран список: *{list_name}*", reply_markup=ReplyKeyboardMarkup(lists_action_keyboard, resize_keyboard=True), parse_mode=ParseMode.MARKDOWN)
    return SHOW_LIST

@private_access
async def ask_for_domains_to_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    list_name = context.user_data.get('current_list')
    log.debug(f"Запрошено удаление из списка '{list_name}'", extra={'user_id': user_id})
    await update.message.reply_text("Отправьте один или несколько доменов для удаления.", reply_markup=ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True))
    return REMOVE_FROM_LIST

@private_access
async def remove_domains_from_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    list_name = context.user_data.get('current_list')
    domains = update.message.text.splitlines()
    log.debug(f"Попытка удалить {len(domains)} домен(ов) из списка '{list_name}'", extra={'user_id': user_id})
    removed = await list_manager.remove_from_list(list_name, domains)
    if removed:
        await update.message.reply_text("✅ Домены удалены. Применяю изменения...")
        success, message = await list_manager.apply_changes()
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("ℹ️ Этих доменов не было в списке.")
    await update.message.reply_text(f"Выбран список: *{list_name}*", reply_markup=ReplyKeyboardMarkup(lists_action_keyboard, resize_keyboard=True), parse_mode=ParseMode.MARKDOWN)
    return SHOW_LIST

# --- Меню ключей ---
@private_access
async def menu_keys(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    log.debug("Переход в меню 'Ключи'", extra={'user_id': user_id})
    await update.message.reply_text("Меню управления ключами.", reply_markup=ReplyKeyboardMarkup(keys_keyboard, resize_keyboard=True))
    return KEYS_MENU

@private_access
async def ask_for_shadowsocks_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    log.debug("Запрошено добавление ключа Shadowsocks", extra={'user_id': user_id})
    await update.message.reply_text("Пожалуйста, отправьте ключ в формате ss://...", reply_markup=ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True))
    return AWAIT_SHADOWSOCKS_KEY

@private_access
async def handle_shadowsocks_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    key_string = update.message.text
    log.debug("Получен ключ Shadowsocks для обработки", extra={'user_id': user_id})
    await update.message.reply_text("⏳ Обрабатываю ключ...", reply_markup=ReplyKeyboardRemove())
    success, message = await key_manager.update_shadowsocks_config(key_string)
    await update.message.reply_text(message, reply_markup=ReplyKeyboardMarkup(keys_keyboard, resize_keyboard=True))
    return KEYS_MENU

# --- Заглушки для других ключей ---
@private_access
async def ask_for_vmess_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    log.warning("Вызвана нереализованная функция 'Vmess'", extra={'user_id': user_id})
    await update.message.reply_text("Эта функция еще не реализована.", reply_markup=ReplyKeyboardMarkup(keys_keyboard, resize_keyboard=True))
    return KEYS_MENU

@private_access
async def ask_for_trojan_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    log.warning("Вызвана нереализованная функция 'Trojan'", extra={'user_id': user_id})
    await update.message.reply_text("Эта функция еще не реализована.", reply_markup=ReplyKeyboardMarkup(keys_keyboard, resize_keyboard=True))
    return KEYS_MENU

# --- Меню настроек ---
@private_access
async def menu_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    log.debug("Переход в меню 'Настройки'", extra={'user_id': user_id})
    await update.message.reply_text("Меню настроек.", reply_markup=ReplyKeyboardMarkup(settings_keyboard, resize_keyboard=True))
    return SETTINGS_MENU

@private_access
async def ask_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ask_confirmation(update, context, "update", "Вы уверены, что хотите обновить бота до последней версии?")
    return SETTINGS_MENU

@private_access
async def ask_uninstall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ask_confirmation(update, context, "uninstall", "Вы уверены, что хотите **полностью** удалить бота?")
    return SETTINGS_MENU

@private_access
async def ask_restart_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await ask_confirmation(update, context, "restart_services", "Вы уверены, что хотите перезагрузить все службы обхода?")
    return SETTINGS_MENU

# --- Обработчики Inline кнопок ---
@private_access
async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    jobs = context.job_queue.get_jobs_by_name(f"confirm_{query.message.chat_id}")
    for job in jobs:
        job.schedule_removal()

    action = query.data.split('_', 1)[1]
    log.debug(f"Подтверждено действие: '{action}'", extra={'user_id': user_id})

    if action == "cancel":
        await query.edit_message_text("Действие отменено.", reply_markup=None)
        return

    if action == "update":
        await query.edit_message_text("Начинаю обновление...", reply_markup=None)
        asyncio.create_task(installer.run_update(update, context))

    elif action == "uninstall":
        await query.edit_message_text("Начинаю полное удаление...", reply_markup=None)
        asyncio.create_task(installer.run_uninstallation(update, context))

    elif action == "restart_services":
        await query.edit_message_text("⏳ Перезапускаю службы...", reply_markup=None)
        report = await service_manager.restart_all_services()
        await query.edit_message_text(f"Отчет о перезапуске:\n\n{report}", reply_markup=None)

@private_access
async def handle_log_level_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    new_level = query.data.split('_', 1)[1]

    if new_level == 'cancel':
        log.debug("Отмена смены уровня логирования", extra={'user_id': user_id})
        await query.edit_message_text("Действие отменено.", reply_markup=None)
        return

    # Обновляем конфиг
    if not config.has_section('logging'):
        config.add_section('logging')
    config.set('logging', 'level', new_level)
    with open(default_config_file, 'w', encoding='utf-8') as configfile:
        config.write(configfile)

    # Применяем на лету
    set_log_level(new_level, user_id=user_id)
    
    await query.edit_message_text(
        f"✅ Уровень логирования изменен на *{new_level}*.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=None
    )

# --- Меню логирования ---
@private_access
async def menu_logging(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    log.debug("Переход в меню 'Уровень логов'", extra={'user_id': user_id})
    current_level = logging.getLevelName(log.level)
    
    levels = ['INFO', 'WARNING', 'ERROR', 'DEBUG']
    keyboard = []
    row = []
    for level in levels:
        button_text = f"• {level} •" if level == current_level else level
        row.append(InlineKeyboardButton(button_text, callback_data=f"log_{level}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="log_cancel")])
    
    await update.message.reply_text(
        f"Текущий уровень логирования: *{current_level}*.\n\n"
        "Выберите новый уровень:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return SETTINGS_MENU

# --- Обработчик ошибок ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Exception while handling an update:", exc_info=context.error)
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    
    try:
        admin_id = literal_eval(config.get("telegram", "access_ids"))[0]
    except Exception:
        log.error("Could not parse access_ids or it is empty.")
        return

    message = (
        "An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )
    await context.bot.send_message(chat_id=admin_id, text=message, parse_mode=ParseMode.HTML)


def main() -> None:
    # Создаем объект для сохранения состояния
    persistence = PicklePersistence(filepath=persistence_file)
    
    job_queue = JobQueue()
    application = (
        Application.builder()
        .token(config.get("telegram", "token"))
        .job_queue(job_queue)
        .persistence(persistence)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            STATUS: [
                MessageHandler(filters.Regex('^Система обхода$'), menu_bypass_system),
                MessageHandler(filters.Regex('^Настройки$'), menu_settings),
            ],
            SETTINGS_MENU: [
                MessageHandler(filters.Regex('^🔄 Обновить$'), ask_update),
                MessageHandler(filters.Regex('^🗑️ Удалить$'), ask_uninstall),
                MessageHandler(filters.Regex('^⚙️ Перезагрузить службы$'), ask_restart_services),
                MessageHandler(filters.Regex('^📝 Уровень логов$'), menu_logging),
                MessageHandler(filters.Regex('^📊 Статус служб$'), menu_services_status),
                MessageHandler(filters.Regex('^🔙 Назад$'), back_to_main_menu),
            ],
            BYPASS_MENU: [
                MessageHandler(filters.Regex('^Ключи$'), menu_keys),
                MessageHandler(filters.Regex('^Списки$'), menu_lists),
                MessageHandler(filters.Regex('^🔙 Назад$'), back_to_main_menu),
            ],
            LISTS_MENU: [
                MessageHandler(filters.Regex('^🔙 Назад$'), menu_bypass_system),
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_list_action),
            ],
            SHOW_LIST: [
                MessageHandler(filters.Regex('^👁️ Показать$'), show_list_content),
                MessageHandler(filters.Regex('^➕ Добавить$'), ask_for_domains_to_add),
                MessageHandler(filters.Regex('^➖ Удалить$'), ask_for_domains_to_remove),
                MessageHandler(filters.Regex('^🔙 Назад$'), menu_lists),
            ],
            ADD_TO_LIST: [
                MessageHandler(filters.Regex('^Отмена$'), select_list_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_domains_to_list),
            ],
            REMOVE_FROM_LIST: [
                MessageHandler(filters.Regex('^Отмена$'), select_list_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, remove_domains_from_list),
            ],
            KEYS_MENU: [
                 MessageHandler(filters.Regex('^Shadowsocks$'), ask_for_shadowsocks_key),
                 MessageHandler(filters.Regex('^Vmess$'), ask_for_vmess_key),
                 MessageHandler(filters.Regex('^Trojan$'), ask_for_trojan_key),
                 MessageHandler(filters.Regex('^🔙 Назад$'), menu_bypass_system),
            ],
            AWAIT_SHADOWSOCKS_KEY: [
                MessageHandler(filters.Regex('^Отмена$'), menu_keys),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_shadowsocks_key),
            ],
        },
        fallbacks=[CommandHandler('start', start)],
        persistent=True,
        name="main_conversation"
    )

    application.add_handler(conv_handler)
    # Добавляем обработчики для inline-кнопок
    application.add_handler(CallbackQueryHandler(handle_confirmation, pattern='^confirm_'))
    application.add_handler(CallbackQueryHandler(handle_log_level_selection, pattern='^log_'))

    application.add_error_handler(error_handler)
    log.info("KDW Bot запущен")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
