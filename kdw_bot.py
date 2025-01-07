import ast
import base64
import json
import pathlib
import sys
import os
import io
import time
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters, CallbackQueryHandler
)
from configparser import ConfigParser
from ast import literal_eval
from urllib.parse import urlparse
import html
from functools import wraps

import sys
import logging
import traceback

default_config_file = "kdw.cfg"


class CustomFormatter(logging.Formatter):
    grey = '\x1b[38;21m'
    green = '\x1b[32m'
    blue = '\x1b[38;5;39m'
    yellow = '\x1b[38;5;226m'
    red = '\x1b[31m'
    bold_red = '\x1b[38;5;196m'
    reset = '\x1b[0m'

    # format =

    def __init__(self, fmt):
        super().__init__()
        self.fmt = fmt
        self.FORMATS = {
            logging.DEBUG: self.green + self.fmt + self.reset,
            logging.INFO: self.blue + self.fmt + self.reset,
            logging.WARNING: self.yellow + self.fmt + self.reset,
            logging.ERROR: self.red + self.fmt + self.reset,
            logging.CRITICAL: self.bold_red + self.fmt + self.reset
        }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class Log:
    def __init__(self, debug=False):
        if debug:
            self.log_level = logging.DEBUG
        else:
            self.log_level = logging.INFO

        global_format = ("[%(asctime)s] - PID:%(process)s - %(name)s - %(filename)s:%(lineno)d - %(levelname)s: %("
                         "message)s")
        self.log = logging.getLogger(None if debug else __name__)
        self.log.setLevel(self.log_level)
        # logging.getLogger('sqlalchemy.engine').setLevel(self.log_level)
        # logging.getLogger('sqlalchemy.pool').setLevel(self.log_level)

        # self.uvicorn_logger = logging.getLogger('uvicorn')
        # self.uvicorn_logger.propagate = False

        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(self.log_level)
        stdout_handler.setFormatter(CustomFormatter(fmt=global_format))

        # current = os.path.dirname(os.path.realpath(__file__))
        # parent = os.path.dirname(current)
        # log_file = config.get('logging', 'log_file')

        # if not log_file:
        #     os.makedirs(os.path.join(parent, 'logs'), exist_ok=True)
        # file_handler = logging.FileHandler(filename=log_file if log_file else os.path.join(parent, 'logs', 'znt.log'),
        #                                    mode='a')
        # file_handler.setLevel(self.log_level)
        # file_handler_format = logging.Formatter(global_format)
        # file_handler.setFormatter(fmt=file_handler_format)

        self.log.addHandler(stdout_handler)
        # self.uvicorn_logger.addHandler(stdout_handler)

        # self.log.addHandler(file_handler)
        # self.uvicorn_logger.addHandler(file_handler)

    def close_file_handler(self):
        for handler in self.log.root.handlers[:]:
            handler.close()
            self.log.removeHandler(handler)

    def get_level_name(self):
        return logging.getLevelName(self.log.getEffectiveLevel())


if os.path.isfile(default_config_file):
    config = ConfigParser()
    config.read(default_config_file, encoding='utf-8')
else:
    raise FileNotFoundError(f"Config file ({default_config_file}) not found!")

logger = Log(debug=False).log

KDW, ROUTER, KDW_KEYS, ACTION, STATUS, SHADOWSOCKS_KEY, RESTART_SESSION, RELOAD_BROWSER, CREATE_SCREENSHOTE, SET_BACKLIGHT, SET_LOCK, SET_URLS = range(
    12)

start_keyboard = [["KDW", "Router"]]
kdw_keyboard = [["Keys", "Lists"], ["Setup"], ["Cancel"]]
kdw_keys_keyboard = [["Shadowsocks", "Trojan"], ["Vmess"], ["Cancel"]]

tools_keyboard = [['Incident prority', 'SLA'], ['Cancel']]

wall_keyboard = [['Top'], ['Bottom'], ['Cancel']]
display_keyboard = [['Top:0', 'Top:1', 'Top:2', 'Top:3', 'Top:4'],
                    ['Bottom:0', 'Bottom:1', 'Bottom:2', 'Bottom:3', 'Bottom:4'], ['Cancel']]
backlight_keyboard = [['0.1', '0.5', '0.6', '0.7', '0.8', '0.9', '1.0'], ['Cancel']]
lock_keyboard = [['Lock', 'Unlock'], ['Cancel']]


def private_access(f):
    """Decorator: loads User model and passes it to the function or stops the request."""

    @wraps(f)
    async def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id in literal_eval(config.get("telegram", "access_ids")):
            return await f(update, context, *args, **kwargs)
        else:
            await update.message.reply_text('You do not have permission to use this bot! Bye!',
                                            reply_markup=ReplyKeyboardRemove())

    return wrapped


@private_access
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    await update.message.reply_text(
        'Hi, {full_name} ({user_id})!\nI am Botgod!'.format(full_name=user.full_name, user_id=user.id),
        reply_markup=ReplyKeyboardMarkup(start_keyboard, resize_keyboard=True))
    logger.info("Start session {full_name} ({user_id})".format(full_name=user.full_name, user_id=user.id))
    return await status(update, context)


@private_access
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(text='Awaiting your instructions...',
                                    reply_markup=ReplyKeyboardMarkup(start_keyboard, resize_keyboard=True))
    return STATUS


@private_access
def cancel(update, context):
    update.message.reply_text(text='Waiting for your instructions',
                              reply_markup=ReplyKeyboardMarkup(start_keyboard, resize_keyboard=True))
    return status(update, context)


@private_access
async def handle_text(update, context):
    await update.message.reply_text(text='Your session is out of date or this menu does not exist, use /start',
                                    reply_markup=ReplyKeyboardRemove())


@private_access
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error("Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        "An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    # Finally, send the message
    await context.bot.send_message(
        chat_id=59552110, text=message, parse_mode=ParseMode.HTML
    )


@private_access
async def test():
    pass


@private_access
async def kdw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info("{full_name} ({user_id}) entered to the 'KDW' menu.".format(full_name=user.full_name, user_id=user.id))
    await update.message.reply_text(text="You are in the menu 'KDW'",
                                    reply_markup=ReplyKeyboardMarkup(kdw_keyboard, resize_keyboard=True))
    return KDW


@private_access
async def kdw_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info("{full_name} ({user_id}) entered to the 'Keys' menu.".format(full_name=user.full_name, user_id=user.id))
    await update.message.reply_text(text="You are in the menu 'Keys'",
                                    reply_markup=ReplyKeyboardMarkup(kdw_keys_keyboard, resize_keyboard=True))
    return KDW_KEYS


@private_access
async def callback_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query
    if query.data == "null":
        await query.answer("no action")
        return
    callback_data: str = query.data

    if 'menu_shadowsocks_configs' in context.user_data and context.user_data['menu_shadowsocks_configs']:
        if callback_data == 'view':
            await update.effective_chat.send_message(f"view json config {callback_data}",
                                                     reply_to_message_id=update.effective_message.message_id)
            await query.answer()
        elif callback_data == 'change':
            # await update.effective_chat.send_message(f"change json config {callback_data[0]}",
            #                                          reply_to_message_id=update.effective_message.message_id)
            await update.effective_chat.send_message(text="Send me url 'Shadowsocks'.",
                                                     reply_to_message_id=update.effective_message.message_id,
                                                     reply_markup=ReplyKeyboardMarkup([['Cancel']],
                                                                                      resize_keyboard=True))
            await update.effective_message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="⏳",
                        callback_data="null")]
                ]))
            context.user_data['effective_callback_message'] = update.effective_message.id
            await query.answer()
            return SHADOWSOCKS_KEY
        elif callback_data == 'delete':
            await update.effective_message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="❌",
                        callback_data="null")]
                ]))
            await query.answer("DELETE OK!")
        elif callback_data == 'add':
            await query.answer("add")

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery

    #yyy = ast.literal_eval(query.data)

    #await query.edit_message_text(text=f"Selected option: \n{query.data}")


@private_access
async def callback_none(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer("no menu")
    #yyy = ast.literal_eval(query.data)

    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([]))


@private_access
async def kdw_keys_shadowsocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    files = [f for f in pathlib.Path().glob(config.get('shadowsocks', 'path') + "/*.json")]
    context.user_data['shadowsocks']: list = []
    for file in files:
        msg = await update.effective_chat.send_message(text=f"{file}",
                                                       reply_markup=InlineKeyboardMarkup(
                                                           inline_keyboard=[
                                                               [InlineKeyboardButton(
                                                                   text="👀 view",
                                                                   callback_data="view"),
                                                                   InlineKeyboardButton(
                                                                       text="📝 change",
                                                                       callback_data="change"),
                                                                   InlineKeyboardButton(
                                                                       text="🗑️ delete",
                                                                       callback_data="delete")]
                                                           ]), disable_notification=True)
        context.user_data['shadowsocks'].append(dict(filename=file, message_id=msg.message_id))

    await update.effective_chat.send_message(text="Add new config?",
                                             reply_markup=InlineKeyboardMarkup(
                                                 inline_keyboard=[
                                                     [InlineKeyboardButton(text="yes", callback_data='null:add')]]),
                                             disable_notification=True)
    context.user_data['menu_shadowsocks_configs'] = True

    #return KDW_KEYS


@private_access
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    await update.message.reply_text(
        "Bye! I hope we can talk again some day.", reply_markup=ReplyKeyboardRemove()
    )

    return ConversationHandler.END


@private_access
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, I didn't understand that command.")


@private_access
async def decode_shadowsocks_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = update.message.text
    user = update.message.from_user
    pattern = config.get("shadowsocks", "pattern")
    import re
    if not re.match(pattern, url):
        await update.message.reply_text(text=f"Error! Shadowsocks URL doesn't match the pattern!",
                                        reply_markup=ReplyKeyboardMarkup([['Cancel']], resize_keyboard=True))
        return SHADOWSOCKS_KEY

    parts = urlparse(url)
    sh_config = dict(server=[parts.hostname],
                     mode=config.get('shadowsocks', 'mode'),
                     server_port=int(parts.port),
                     password=base64.b64decode(parts.username).decode("utf-8").split(':')[1],
                     timeout=config.getint('shadowsocks', 'timeout'),
                     method=base64.b64decode(parts.username).decode("utf-8").split(':')[0],
                     local_address=config.get('shadowsocks', 'local_address'),
                     local_port=config.getint('shadowsocks', 'local_port'),
                     fast_open=config.getboolean('shadowsocks', 'fast_open'),
                     ipv6_first=config.getboolean('shadowsocks', 'ipv6_first'))

    # await update.message.reply_text(text=f'Your parsing data \n{json.dumps(sh_config, indent=2)}',
    #                                 reply_markup=ReplyKeyboardMarkup(kdw_keys_keyboard, resize_keyboard=True))

    filename = next((item.get("filename") for item in context.user_data['shadowsocks'] if
                     item.get("message_id") and item["message_id"] == context.user_data['effective_callback_message']),
                    None)

    with open(filename, 'w') as f:
        json.dump(sh_config, f, indent=2)

    logger.info("User %s add new shadowsocks config.", user.first_name)

    await context.bot.edit_message_reply_markup(chat_id=update.effective_chat.id,
                                                message_id=context.user_data['effective_callback_message'],
                                                reply_markup=InlineKeyboardMarkup(
                                                    inline_keyboard=[
                                                        [InlineKeyboardButton(
                                                            text="✅",
                                                            callback_data="null")]
                                                    ]))
    await update.message.reply_text(text="ok", reply_markup=ReplyKeyboardMarkup(kdw_keys_keyboard, resize_keyboard=True))
    #await update.callback_query.answer("OK")
    return KDW_KEYS


if __name__ == '__main__':
    application = Application.builder().token(config.get('telegram', 'token')).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            STATUS:
                [MessageHandler(filters.Regex('KDW'), kdw),
                 MessageHandler(filters.Regex('ROUTER'), test)
                 ],
            KDW:
                [MessageHandler(filters.Regex('Cancel'), status),
                 MessageHandler(filters.Regex('Keys'), kdw_keys),
                 MessageHandler(filters.Regex('Lists'), test),
                 MessageHandler(filters.Regex('Setup'), test)
                 ],
            ROUTER:
                [MessageHandler(filters.Regex('Cancel'), status),
                 ],
            KDW_KEYS:
                [MessageHandler(filters.Regex('Cancel'), kdw),
                 MessageHandler(filters.Regex('Shadowsocks'), kdw_keys_shadowsocks),
                 MessageHandler(filters.Regex('Trojan'), test),
                 MessageHandler(filters.Regex('Vmess'), test),
                 CallbackQueryHandler(callback_buttons),
                 ],
            SHADOWSOCKS_KEY:
                [MessageHandler(filters.Regex('Cancel'), kdw),
                 MessageHandler(filters.Text(), decode_shadowsocks_key),
                 CallbackQueryHandler(callback_buttons)
                 ],
        },
        fallbacks=[CommandHandler('cancel', callback=cancel)]
    )

    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.Text(), handle_text))
    application.add_handler(MessageHandler(filters.Command(), unknown))
    application.add_handler(CallbackQueryHandler(callback_none))
    application.add_error_handler(error_handler)

    logger.info("Telegram Bot God botgod.service active (running)")

    application.run_polling(allowed_updates=Update.ALL_TYPES)

    logger.info("Telegram Bot God botgod.service stoping")

# pattern_shadowsocks = r"(?<![\w-])(ss://[^\s<>#|]+)"
# pattern_vmess = r"(?<![\w-])(vmess://[^\s<>#|]+)"
# pattern_vless = r"(?<![\w-])(vless://(?:(?!=reality)[^\s<>#|])+(?=[\s<>#|]))"
# pattern_reality = r"(?<![\w-])(vless://[^\s<>#|]+?security=reality[^\s<>#|]*)"
