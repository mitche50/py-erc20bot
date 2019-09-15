import modules.aliases as aliases
from celery import Celery
import configparser
import modules.db as db
from decimal import Decimal, InvalidOperation
import eth_keyfile
import json
import requests
import tasks
import modules.util as util

config = configparser.ConfigParser()
config.read('config.ini')

# Set Log File
logger = util.get_logger('db')

queue = Celery('tasks', broker='redis://localhost//')

ENV = config.get('main', 'env')

CONTRACT_ADDRESS = config.get('main', 'contract')
MASTER = config.get('main', 'master')
FEE = config.get('main', 'fee')
TOKEN = config.get('main', 'token')
ETHERSCAN_ROUTE = config.get(ENV, 'etherscan_route')
ETHERSCAN_KEY = config.get('main', 'etherscan_key')
INFURA = config.get('main', 'infura')
INFURA_ROUTE = config.get(ENV, 'infura_route')
BOT_ID = config.get('main', 'bot_id')

with open('static/abi.json', 'r') as abi_file:
    ABI = json.load(abi_file)
    

async def get_all_txs(address):
    get_blockno_call = "SELECT block_number FROM users WHERE address = %s"
    get_blockno_values = [address, ]
    blockno_return = db.get_db_data(get_blockno_call, get_blockno_values)
    if blockno_return is not ():
        blockno = blockno_return[0][0]
        route = "{}api?module=account&action=tokentx&contractaddress={}" \
                "&address={}&startblock={}&sort=asc&apikey={}".format(ETHERSCAN_ROUTE, CONTRACT_ADDRESS, address[0][0],
                                                                      blockno + 1, ETHERSCAN_KEY)
        r = requests.get(route)
        rx = r.json()

        return rx, blockno
    return {'result': {}}, None


async def set_tip_list(message, bot):
    """
    Find the list of users to tip and add it to a dictionary.
    """
    message['msg_list'] = message['content'].lower().split(' ')
    message['starting_point'] = -1

    for alias in aliases.TIP['TRIGGER']:
        if ("!" + alias) in message['msg_list']:
            message['starting_point'] = message['msg_list'].index("!" + alias)

    if message['starting_point'] == -1:
        return None

    first_user_flag = False
    users_to_tip = []

    for t_index in range(message['starting_point'] + 1, len(message['msg_list'])):
        if (first_user_flag
                and len(message['msg_list'][t_index]) > 0
                and str(message['msg_list'][t_index][0:2]) != "<@"):
            # non-user found in tipping, break the loop
            message['last_user'] = t_index
            break
        if (len(message['msg_list'][t_index]) > 0
                and str(message['msg_list'][t_index][0:2]) == "<@"
                and message['msg_list'][t_index] != ("<@" + str(message['author']) + ">")
                and message['msg_list'][t_index] != ("<@" + str(BOT_ID) + ">")):
            if not first_user_flag:
                first_user_flag = True
            user = message['msg_list'][t_index][2:-1]
            username = bot.get_user(int(user))
            user_dict = {'user': user, 'username': username.name}
            if user_dict not in users_to_tip:
                users_to_tip.append(user_dict)

    return users_to_tip


async def get_account(user_id):
    """
    Retrieves the user's account from the DB.
    """
    get_account_sql = "SELECT address FROM users WHERE user_id = %s"
    get_account_values = [str(user_id), ]
    account_return = db.get_db_data(get_account_sql, get_account_values)

    return account_return


async def get_user_id(address):
    """
    Get the user_id who owns the provided address
    """
    address = address.lower()
    user_sql = "SELECT user_id FROM users WHERE address = %s"
    user_values = [address, ]

    user_return = db.get_db_data(user_sql, user_values)

    if user_return is ():
        return None

    return user_return[0][0]


async def check_pending(message):
    """
    Check to see if the current nonce is the same as the tracked nonce.  If not, update the balance and nonce
    """
    address = await get_account(message.author.id)

    if (address[0][0] is not None and address != ()
            and address[0][0] != 'GENERATING' and address[0][0] != 'ERROR'):

        transactions, blockno = await get_all_txs(address)
        new_balance = 0
        new_blockno = 0

        for block in transactions['result']:
            if block['to'].lower() == address[0][0].lower() and Decimal(block['blockNumber']) > Decimal(blockno):
                decimals = Decimal(10**18)
                new_balance += Decimal(Decimal(block['value']) / decimals)
                new_blockno = block['blockNumber']

        if Decimal(new_balance) > 0 and Decimal(new_blockno) > 0:
            balance, _ = tasks.get_balance(message.author.id)
            balance = Decimal(balance) + new_balance

            update_balance_sql = "UPDATE users SET block_number = %s, balance = %s WHERE user_id = %s"
            update_balance_values = [new_blockno, balance, message.author.id]
            success = db.set_db_data(update_balance_sql, update_balance_values)
            if success is not None:
                logger.error("Error in setting DB data: {}".format(success))
                await message.author.send("There was an error setting your new balance, please reach "
                                          "out to bot admin: {}".format(success))

        return new_balance
    return 0


async def add_balance(user, username, amount):
    """
    Add the balance to the provided user.
    """
    current_balance, _ = tasks.get_balance(user)
    if current_balance is not None and current_balance is not ():
        new_balance = Decimal(current_balance) + Decimal(amount)
        await tasks.set_balance(user, new_balance)
    else:
        new_user_sql = "INSERT INTO users (balance, user_id, username) VALUES (%s, %s, %s)"
        new_user_values = [amount, user, username]
        db.set_db_data(new_user_sql, new_user_values)


async def validate_tip_amount(message, users_to_tip):
    """
    Tip amount indexes are only valid after the tip command, or after the list of users.  If neither is a number,
    return None.
    """
    try:
        # First check to see if the value after the tip command is a number.
        message['tip_amount'] = Decimal(message['msg_list'][message['starting_point'] + 1])
    except InvalidOperation:
        try:
            # If it isn't, check to see if the value after the last identified user is a number
            message['tip_amount'] = Decimal(message['msg_list'][message['last_user']])
        except InvalidOperation:
            # If neither, return None
            message['tip_amount'] = None
            return message

    # The total tip amount will be the number of users being tipped * the tip amount
    message['total_tip_amount'] = message['tip_amount']
    message['total_tip_amount'] *= len(users_to_tip)

    return message


async def send_tip(message, users_to_tip, ctx, bot):
    """
    Update the database with new balances and respond with emojis.
    """
    sender_new_balance = message['sender_balance'] - message['total_tip_amount']

    for receiver in users_to_tip:
        await add_balance(receiver['user'], receiver['username'], message['tip_amount'])
        dm_user = bot.get_user(int(receiver['user']))
        await dm_user.send("You just received a {} {} tip from <@{}>".format(message['tip_amount'],
                                                                             TOKEN,
                                                                             message['author']))

    await tasks.set_balance(message['author'], sender_new_balance)

    await ctx.message.add_reaction('☑')
    # Note, these have unicode that does not show in IDE.  Do not modify
    await ctx.message.add_reaction('🇸')
    await ctx.message.add_reaction('🇪')
    await ctx.message.add_reaction('🇳')
    await ctx.message.add_reaction('🇹')


async def validate_user(message):
    """
    Validate the user has enough tokens to send the tip.
    """
    message['sender_balance'], _ = Decimal(tasks.get_balance(message['author']))

    if (message['sender_balance'] is None
            or message['sender_balance'] is ()
            or message['total_tip_amount'] > message['sender_balance']):
        return False

    return True


async def generate_new_account(message, w3):
    """
    Generates a new account and gives privileges to the master account.
    """
    # Inform the user their account is being generated
    await message.author.send("No account, generating one.  Please check back in a few minutes by sending the "
                              "!account command again.")

    db.set_db_data("UPDATE users SET address = 'GENERATING' WHERE user_id = %s", [message.author.id, ])

    new_account = w3.eth.account.create('')

    # Store the user's address in a keyfile
    keyfile_return = eth_keyfile.create_keyfile_json(new_account.key, b'')
    address = w3.toChecksumAddress(new_account.address)
    with open('keyfiles/{}.json'.format(address), 'w') as local_keyfile:
        json.dump(keyfile_return, local_keyfile)

    # Update user's account
    tasks.set_account.delay(message.author.id, address)
    return


if __name__ == '__main__':
    queue.start()
