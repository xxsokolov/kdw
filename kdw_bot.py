import sys
import os
import json
import html
import traceback
from configparser import ConfigParser
from ast import literal_eval
from functools import wraps

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.installer import Installer
from core.log_utils import Log
from core.service_manager import ServiceManager
from core.list_manager import ListManager
from core.key_manager import KeyManager

# --- Глобальные переменные и константы ---
# Определяем путь к конфиг-файлу относительно расположения самого скрипта
script_dir = os.path.dirname(os.path.abspath(__file__))
default_config_file = os.path.join(script_dir, "kdw.cfg")

# Состояния для ConversationHandler
(
    STATUS,
    INSTALL,
    CONFIGURE_IPTABLES,
    AWAIT_SS_PORT,
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
    DANGER_ZONE,
    AWAIT_UNINSTALL_CONFIRMATION,
) = range(16)

# --- Инициализация ---
if os.path.isfile(default_config_file):
    config = ConfigParser()
    config.read(default_config_file, encoding='utf-8')
else:
    print(f"Error: Config file ({default_config_file}) not found!")
    sys.exit(1)

logger = Log(debug=False).log
installer = Installer(default_config_file)
service_manager = ServiceManager()
list_manager = ListManager()
key_manager = KeyManager()

# --- Клавиатуры ---
install_keyboard = [["🚀 Установить систему обхода"]]
configure_keyboard = [["⚙️ Настроить iptables"]]
main_keyboard = [["Система обхода", "Роутер"], ["Настройки"]]
settings_keyboard = [["☢️ Зона риска"], ["🔙 Назад"]]
danger_zone_keyboard = [["🔄 Переустановить"], ["🗑️ Удалить"], ["🔙 Назад"]]
bypass_keyboard = [["Ключи", "Списки"], ["Статус служб"], ["🔙 Назад"]]
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
            await update.message.reply_text('❌ У вас нет доступа к этому боту.', reply_markup=ReplyKeyboardRemove())
    return wrapped

# --- Основные обработчики ---
@private_access
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    logger.info(f"Start session for {user.full_name} ({user.id})")
    if await installer.is_configured():
        await update.message.reply_text(f"👋 Привет, {user.full_name}!", reply_markup=ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True))
        return STATUS
    elif await installer.is_installed():
        await update.message.reply_text("Базовая установка завершена, но система еще не настроена.", reply_markup=ReplyKeyboardMarkup(configure_keyboard, resize_keyboard=True))
        return CONFIGURE_IPTABLES
    else:
        await update.message.reply_text(f"👋 Привет, {user.full_name}!\nСистема обхода еще не установлена.", reply_markup=ReplyKeyboardMarkup(install_keyboard, resize_keyboard=True))
        return INSTALL

@private_access
async def start_install(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await installer.run_installation(update, context)
    return ConversationHandler.END

@private_access
async def ask_for_ss_port(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Пожалуйста, введите порт, на котором будет работать ss-redir (обычно 1080).", reply_markup=ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True))
    return AWAIT_SS_PORT

@private_access
async def configure_iptables(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        port = int(update.message.text)
        success, message = await installer.configure_iptables(port)
        await update.message.reply_text(message)
        if success:
            await update.message.reply_text("Настройка завершена! Пожалуйста, перезапустите бота командой /start.", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        else:
            return AWAIT_SS_PORT
    except ValueError:
        await update.message.reply_text("❌ Неверный формат порта. Пожалуйста, введите число.", reply_markup=ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True))
        return AWAIT_SS_PORT

@private_access
async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Главное меню", reply_markup=ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True))
    return STATUS

@private_access
async def menu_bypass_system(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Меню управления системой обхода.", reply_markup=ReplyKeyboardMarkup(bypass_keyboard, resize_keyboard=True))
    return BYPASS_MENU

# --- Меню служб ---
@private_access
async def menu_services_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("⏳ Проверяю статус служб...")
    status_report = await service_manager.get_all_statuses()
    await update.message.reply_text(f"Статус служб:\n\n{status_report}")
    return BYPASS_MENU

# --- Меню списков ---
@private_access
async def menu_lists(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lists = list_manager.get_list_files()
    if not lists:
        await update.message.reply_text("Не найдено ни одного файла списков.", reply_markup=ReplyKeyboardMarkup(bypass_keyboard, resize_keyboard=True))
        return BYPASS_MENU
    keyboard = [[l] for l in lists] + [["🔙 Назад"]]
    await update.message.reply_text("Выберите список для управления:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return LISTS_MENU

@private_access
async def select_list_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    list_name = update.message.text
    context.user_data['current_list'] = list_name
    await update.message.reply_text(f"Выбран список: *{list_name}*\n\nЧто вы хотите сделать?", reply_markup=ReplyKeyboardMarkup(lists_action_keyboard, resize_keyboard=True), parse_mode=ParseMode.MARKDOWN)
    return SHOW_LIST

@private_access
async def show_list_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    list_name = context.user_data.get('current_list')
    content = list_manager.read_list(list_name)
    if len(content) > 4096:
        for x in range(0, len(content), 4096):
            await update.message.reply_text(content[x:x + 4096])
    else:
        await update.message.reply_text(content)
    return SHOW_LIST

@private_access
async def ask_for_domains_to_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отправьте один или несколько доменов для добавления.", reply_markup=ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True))
    return ADD_TO_LIST

@private_access
async def add_domains_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    list_name = context.user_data.get('current_list')
    domains = update.message.text.splitlines()
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
    await update.message.reply_text("Отправьте один или несколько доменов для удаления.", reply_markup=ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True))
    return REMOVE_FROM_LIST

@private_access
async def remove_domains_from_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    list_name = context.user_data.get('current_list')
    domains = update.message.text.splitlines()
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
    await update.message.reply_text("Меню управления ключами.", reply_markup=ReplyKeyboardMarkup(keys_keyboard, resize_keyboard=True))
    return KEYS_MENU

@private_access
async def ask_for_shadowsocks_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Пожалуйста, отправьте ключ в формате ss://...", reply_markup=ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True))
    return AWAIT_SHADOWSOCKS_KEY

@private_access
async def handle_shadowsocks_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    key_string = update.message.text
    await update.message.reply_text("⏳ Обрабатываю ключ...", reply_markup=ReplyKeyboardRemove())
    success, message = await key_manager.update_shadowsocks_config(key_string)
    await update.message.reply_text(message, reply_markup=ReplyKeyboardMarkup(keys_keyboard, resize_keyboard=True))
    return KEYS_MENU

# --- Заглушки для других ключей ---
@private_access
async def ask_for_vmess_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Эта функция еще не реализована.", reply_markup=ReplyKeyboardMarkup(keys_keyboard, resize_keyboard=True))
    return KEYS_MENU

@private_access
async def ask_for_trojan_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Эта функция еще не реализована.", reply_markup=ReplyKeyboardMarkup(keys_keyboard, resize_keyboard=True))
    return KEYS_MENU

# --- Новые обработчики для меню настроек ---
@private_access
async def menu_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Меню настроек.", reply_markup=ReplyKeyboardMarkup(settings_keyboard, resize_keyboard=True))
    return SETTINGS_MENU

@private_access
async def menu_danger_zone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Вы вошли в зону риска. Эти действия могут нарушить работу системы.", reply_markup=ReplyKeyboardMarkup(danger_zone_keyboard, resize_keyboard=True))
    return DANGER_ZONE

@private_access
async def start_reinstall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await installer.run_reinstallation(update, context)
    return ConversationHandler.END

@private_access
async def ask_for_uninstall_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = """⚠️ **ВНИМАНИЕ!**
Это действие **полностью удалит** бота, все его настройки, созданные файлы и установленные пакеты (`shadowsocks`, `dnsmasq` и т.д.).

**Это действие необратимо.**

Для подтверждения, пожалуйста, отправьте в ответ фразу:
`да, удалить все`"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True))
    return AWAIT_UNINSTALL_CONFIRMATION

@private_access
async def handle_uninstall_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "да, удалить все":
        await installer.run_uninstallation(update, context)
        return ConversationHandler.END
    else:
        await update.message.reply_text("Неверная фраза подтверждения. Удаление отменено.", reply_markup=ReplyKeyboardMarkup(danger_zone_keyboard, resize_keyboard=True))
        return DANGER_ZONE

# --- Обработчик ошибок ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    
    try:
        admin_id = literal_eval(config.get("telegram", "access_ids"))[0]
    except:
        logger.error("Could not parse access_ids or it is empty.")
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
    application = Application.builder().token(config.get('telegram', 'token')).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            INSTALL: [MessageHandler(filters.Regex('^🚀 Установить систему обхода$'), start_install)],
            CONFIGURE_IPTABLES: [MessageHandler(filters.Regex('^⚙️ Настроить iptables$'), ask_for_ss_port)],
            AWAIT_SS_PORT: [
                MessageHandler(filters.Regex('^Отмена$'), start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, configure_iptables),
            ],
            STATUS: [
                MessageHandler(filters.Regex('^Система обхода$'), menu_bypass_system),
                MessageHandler(filters.Regex('^Настройки$'), menu_settings),
            ],
            SETTINGS_MENU: [
                MessageHandler(filters.Regex('^☢️ Зона риска$'), menu_danger_zone),
                MessageHandler(filters.Regex('^🔙 Назад$'), back_to_main_menu),
            ],
            DANGER_ZONE: [
                MessageHandler(filters.Regex('^🔄 Переустановить$'), start_reinstall),
                MessageHandler(filters.Regex('^🗑️ Удалить$'), ask_for_uninstall_confirmation),
                MessageHandler(filters.Regex('^🔙 Назад$'), menu_settings),
            ],
            AWAIT_UNINSTALL_CONFIRMATION: [
                MessageHandler(filters.Regex('^Отмена$'), menu_danger_zone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_uninstall_confirmation),
            ],
            BYPASS_MENU: [
                MessageHandler(filters.Regex('^Ключи$'), menu_keys),
                MessageHandler(filters.Regex('^Списки$'), menu_lists),
                MessageHandler(filters.Regex('^Статус служб$'), menu_services_status),
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
    )

    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    logger.info("KDW Bot запущен")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
