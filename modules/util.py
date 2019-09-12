import modules.db as db
import discord
import logging
import logging.handlers
import configparser

config = configparser.ConfigParser()
config.read('config.ini')

TOKEN = config.get('main', 'token')


def get_logger(name, log_file='debug.log'):
    """
    Create a logging instance and return it
    """
    formatter = logging.Formatter('%(asctime)s [%(name)s] -%(levelname)s- %(message)s')
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    file_handler = logging.handlers.TimedRotatingFileHandler(log_file, when='midnight', backupCount=0)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.handlers = []
    logger.addHandler(file_handler)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logger.propagate = False
    return logger


def get_aliases(dict, exclude=''):
    """
    Returns list of command triggers excluding `exclude`
    """
    cmds = dict["TRIGGER"]
    ret_cmds = []
    for cmd in cmds:
        if cmd != exclude:
            ret_cmds.append(cmd)
    return ret_cmds


def is_private(channel):
    """
    Check if a discord channel is private
    """
    return isinstance(channel, discord.abc.PrivateChannel)


async def check_user_notify(message):
    """
    Checks to see if the user was notified of liability waiver.
    """
    if not await is_notified(message.author.id):
        await message.author.send("By continuing to use this bot, you agree to release the creator, owners, all "
                                  "maintainers of the bot, and the {} Team from any legal liability.\n\n"
                                  "Please run your previous command again.".format(TOKEN))
        await mark_notified(message.author.id, message.author)
        return False

    return True


async def is_notified(user_id):
    """
    Checks to see if the user was notified of liability waiver.
    """
    check_user_sql = "SELECT notify FROM users WHERE user_id = %s"
    check_user_values = [user_id, ]
    check_user_return = db.get_db_data(check_user_sql, check_user_values)

    if check_user_return == () or check_user_return[0][0] == 0 or check_user_return[0][0] is None:
        return False

    return True




async def mark_notified(user_id, user_name):
    """
    Update DB to mark the user as notified of liability waiver.
    """
    insert_user_sql = ("INSERT INTO users (user_id, username, balance, notify) "
                       "VALUES (%s, %s, '0', 1) "
                       "ON DUPLICATE KEY UPDATE notify = 1")
    insert_user_values = [user_id, user_name]
    db.set_db_data(insert_user_sql, insert_user_values)