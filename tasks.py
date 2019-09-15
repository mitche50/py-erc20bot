from celery import Celery
import configparser
import modules.db as db
from decimal import Decimal
import discord
import eth_keyfile
from time import sleep
import json
import modules.util as util
from web3 import Web3, HTTPProvider

config = configparser.ConfigParser()
config.read('config.ini')
ENV = config.get('main', 'env')

CONTRACT_ADDRESS = config.get('main', 'contract')
MASTER = config.get('main', 'master')
FEE = config.get('main', 'fee')
TOKEN = config.get('main', 'token')
ETHERSCAN_KEY = config.get('main', 'etherscan_key')
INFURA = config.get('main', 'infura')
INFURA_ROUTE = config.get(ENV, 'infura_route')
BOT_TOKEN = config.get('main', 'bot_token')
CHAIN_ID = config.get(ENV, 'chain_id')

queue = Celery('tasks', broker='redis://localhost//')
bot = discord.Client()

logger = util.get_logger("task")

with open('static/abi.json', 'r') as abi_file:
    ABI = json.load(abi_file)


def set_balance(user_id, amount):
    """
    Set the balance to the provided amount.
    """
    set_balance_sql = "UPDATE users SET balance = %s WHERE user_id = %s"
    set_balance_values = [amount, user_id]
    db.set_db_data(set_balance_sql, set_balance_values)


def set_pending(user_id, amount):
    """
    Set the user's pending balance to the provided amount.
    """
    set_pending_sql = "UPDATE users SET pending_withdraw = %s WHERE user_id = %s"
    set_pending_values = [amount, user_id]
    db.set_db_data(set_pending_sql, set_pending_values)


def add_pending(user_id, amount):
    """
    Add the provided amount to the user's pending balance
    """
    _, pending = get_balance(user_id)
    new_pending = pending + Decimal(amount)
    set_pending(user_id, new_pending)


def remove_pending(user_id, amount):
    """
    Add the provided amount to the user's pending balance
    """
    _, pending = get_balance(user_id)
    new_pending = pending - Decimal(amount)
    set_pending(user_id, new_pending)


def get_balance(user_id):
    """
    Retrieve user's balance from DB.
    """
    get_balance_sql = "SELECT balance, pending_withdraw FROM users WHERE user_id = %s"
    get_balance_values = [user_id, ]
    balance_return = db.get_db_data(get_balance_sql, get_balance_values)
    balance = Decimal(balance_return[0][0])
    pending = Decimal(balance_return[0][1])
    try:
        return balance, pending
    except Exception as e:
        return None


def remove_balance(user_id, amount):
    """
    Remove the provided amount from the user's balance.
    """
    current_balance_sql = "SELECT balance FROM users WHERE user_id = %s"
    current_balance_values = [user_id, ]
    current_balance_return = db.get_db_data(current_balance_sql, current_balance_values)

    new_balance = Decimal(current_balance_return[0][0]) - Decimal(amount)

    set_balance(user_id, new_balance)


def own_account(address):
    """
    Check if the provided withdraw account is owned by the bot.  If it is, do not allow withdraws.
    """
    address = address.lower()
    db_return = db.get_db_data("SELECT user_id FROM users WHERE address = %s",
                               [address, ])

    if db_return is ():
        return False
    else:
        return True


def get_master_key():
    """
    Retrieve the private key for the master account from the keystore file
    """
    try:
        master_keyfile = json.load(open('keyfiles/master.json', 'rb'))
        master_key = eth_keyfile.decode_keyfile_json(master_keyfile, b'')
        return master_key
    except Exception as e:
        logger.error("Error retrieving master key: {}".format(e))
        return False


def get_priv_key(address):
    """
    Retrieve the private key from the keystore file
    """
    try:
        read_keyfile = json.load(open('keyfiles/{}.json'.format(address), 'rb'))
        key = eth_keyfile.decode_keyfile_json(read_keyfile, b'')
        return key
    except Exception as e:
        logger.error("Error retrieving private key for address {}: {}".format(address, e))
        return False


@queue.task()
def send_tokens(to, amount, author_id):
    """
    Transfer the provided amount of tokens to the provided account
    """
    try:
        w3 = Web3(HTTPProvider("{}{}".format(INFURA_ROUTE, INFURA)))

        contract = w3.eth.contract(w3.toChecksumAddress(CONTRACT_ADDRESS), abi=ABI)
        master = w3.toChecksumAddress(MASTER)
        master_key = w3.toHex(get_master_key())
        to = w3.toChecksumAddress(to)
        if not (own_account(to)) and to.lower() != master.lower():
            send_amount = float(amount) * (10**18)

            send_tx = contract.functions.transfer(to, int(send_amount)).buildTransaction(dict(
                    chainId=int(CHAIN_ID),
                    gas=140000,
                    gasPrice=w3.eth.gasPrice,
                    nonce=w3.eth.getTransactionCount(master)
            ))
            sent = w3.eth.account.signTransaction(send_tx, master_key)
            send_hash = w3.eth.sendRawTransaction(sent.rawTransaction)
            logger.info("Generated transaction {} - waiting for confirmations.".format(w3.toHex(send_hash)))

            try:
                w3.eth.waitForTransactionReceipt(w3.toHex(send_hash), timeout=18000)
                remove_pending(author_id, amount)
                return True
            except Exception as e:
                return False
        else:
            return False
    except Exception as e:
        logger.debug("error: {}".format(e))


@queue.task()
def forward_to_master(address, amount):
    """
    Forward tokens to master account after receipt
    """
    w3 = Web3(HTTPProvider("{}{}".format(INFURA_ROUTE, INFURA)))
    contract = w3.eth.contract(w3.toChecksumAddress(CONTRACT_ADDRESS), abi=ABI)
    master = w3.toChecksumAddress(MASTER)
    address = w3.toChecksumAddress(address)
    master_key = w3.toHex(get_master_key())
    try:
        send_amount = float(amount) * (10**18)

        send_tx = contract.functions.transferFrom(address, master, int(send_amount)).buildTransaction(dict(
            chainId=int(CHAIN_ID),
            gas=140000,
            gasPrice=w3.eth.gasPrice,
            nonce=w3.eth.getTransactionCount(master)
        ))
        sent = w3.eth.account.signTransaction(send_tx, master_key)
        send_hash = w3.eth.sendRawTransaction(sent.rawTransaction)

        w3.eth.waitForTransactionReceipt(w3.toHex(send_hash), timeout=18000)
    except Exception as e:
        logger.error("Error forwarding {} {} to master from address {}: {}".format(amount, TOKEN, address, e))
    finally:
        return


@queue.task()
def set_account(user_id, address):
    """
    Sets the user's account in the DB and returns True if it was set successfully.
    """
    try:
        allowed = allow_master(address)
        if allowed:
            address = address.lower()
            update_account_sql = "UPDATE users SET address = %s WHERE user_id = %s"
            update_account_values = [address, user_id]
            db.set_db_data(update_account_sql, update_account_values)
            return True
        else:
            mark_error(user_id)
        return False

    except Exception as e:
        mark_error(user_id)
        return False


def mark_error(user_id):
    """
    Mark that there was an error in the DB.
    """
    update_account_sql = "UPDATE users SET address = 'ERROR' WHERE user_id = %s"
    update_account_values = [user_id, ]
    db.set_db_data(update_account_sql, update_account_values)


def allow_master(address):
    """
    Allow the master address to spend on behalf of the provided address
    """
    # It is necessary to fund the slave account with 0.01 ETH so they can sign the approve transaction to allow control
    w3 = Web3(HTTPProvider("{}{}".format(INFURA_ROUTE, INFURA)))
    contract_address = w3.toChecksumAddress(CONTRACT_ADDRESS)
    contract = w3.eth.contract(contract_address, abi=ABI)
    master = w3.toChecksumAddress(MASTER)
    address = w3.toChecksumAddress(address)
    master_key = w3.toHex(get_master_key())
    private_key = w3.toHex(get_priv_key(address))
    master_nonce = w3.eth.getTransactionCount(master)

    try:
        fund = w3.eth.account.signTransaction(dict(
            chainId=int(CHAIN_ID),
            nonce=master_nonce,
            gasPrice=w3.eth.gasPrice,
            gas=21000,
            to=address,
            value=w3.toWei(0.001, 'ether')
        ), master_key
        )
        w3.eth.sendRawTransaction(fund.rawTransaction)
        fund_hash = fund.hash

        funded = w3.eth.waitForTransactionReceipt(fund_hash, timeout=18000)

        if not funded.status:
            logger.error("Error funding account from master on hash {}".format(w3.toHex(fund_hash)))
            return False

        # Once funded, allow the master to sign transactions for all accounts
        approve_tx = contract.functions.approve(master, (1000 * 10**18)).buildTransaction(dict(
            chainId=int(CHAIN_ID),
            gas=140000,
            gasPrice=w3.eth.gasPrice,
            nonce=w3.eth.getTransactionCount(address)
        ))
        sleep(1)

        approve = w3.eth.account.signTransaction(approve_tx, private_key)
        approve_hash = w3.eth.sendRawTransaction(approve.rawTransaction)

        receipt = w3.eth.waitForTransactionReceipt(w3.toHex(approve_hash), timeout=18000)
        if not receipt.status:
            logger.error("Error approving the master to move funds on hash {}".format(w3.toHex(approve_hash)))
            return False

        return True
    except Exception as e:
        logger.error("Error setting address: {}".format(e))
        return False


if __name__ == '__main__':
    queue.start()
