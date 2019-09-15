import modules.aliases as aliases
from celery import Celery
import configparser
import modules.currency as currency
from modules.db import db_init
from decimal import Decimal, InvalidOperation
import discord
from discord.ext import commands
import tasks
import modules.util as util
from web3 import Web3, HTTPProvider

# Read config and parse constants
config = configparser.ConfigParser()
config.read('config.ini')
ENV = config.get('main', 'env')

INFURA = config.get('main', 'infura')
INFURA_ROUTE = config.get(ENV, 'infura_route')
CONTRACT_ADDRESS = config.get('main', 'contract')
MASTER = config.get('main', 'master')
ETHERSCAN_ROUTE = config.get(ENV, 'etherscan_route')


logger = util.get_logger("main")

# Initialize discord bot
bot = commands.Bot(command_prefix='!')
bot.remove_command("help")

TOKEN = config.get('main', 'token')
FEE = int(config.get('main', 'fee'))
DECIMALS = int(config.get('main', 'decimals'))
MIN_TIP = int(config.get('main', 'min_tip'))
BOT_OWNER = config.get('main', 'bot_owner')
BOT_ID = config.get('main', 'bot_id')
BOT_TOKEN = config.get('main', 'bot_token')

w3 = Web3(HTTPProvider("{}{}".format(INFURA_ROUTE, INFURA)))


@bot.event
async def on_message(message):
    """
    Bot received message from discord user.
    """
    # disregard messages sent by our own bot
    if message.author.id == bot.user.id:
        return

    # if the user was not notified of liability, send the notification
    notified = await util.check_user_notify(message)
    if not notified:
        return

    await bot.process_commands(message)


@bot.command(aliases=util.get_aliases(aliases.HELP, exclude='help'))
async def help(ctx):
    """
    Generate the help message and send to the user.
    """
    message = ctx.message
    embed = discord.Embed(colour=discord.Colour.dark_gold())
    embed.title = 'REN Tip Bot Help'
    help_t = ('To run a command, preface it with "!" ("!deposit", "!tip")\n\n'
              'This bot does use decimals, and has {2} decimals of accuracy. You can also use "all" instead of any '
              'AMOUNT to tip/withdraw your entire balance.\n\n'
              '-- **!balance or !b**\n'
              '*DM ONLY*\n'
              'Prints your balance.\n\n'
              '-- **!tip or !t <@PERSON> <AMOUNT>**\n'
              '*IN CHAT ONLY*\n'
              'Tips the person the provided amount of {0}.  The minimum tip amount is {3}\n\n'
              '-- **!withdraw or !w <ADDRESS> <OPTIONAL:AMOUNT>**\n'
              '*DM ONLY*\n'
              'Withdraws AMOUNT to ADDRESS, charging a {1} {0} fee.  If no amount is provided, withdraw '
              'your entire balance, less the 5 {0} fee.\n\n'
              '-- **!address or !account or !deposit or !a or !d**\n'
              '*DM ONLY*\n'
              'Prints your personal deposit address.\n\n'
              'If you have any questions, feel free to ask <@{4}>.\n\n'
              'This bot is fully open source and available at https://github.com/mitche50/rentipbot').format(TOKEN,
                                                                                                             FEE,
                                                                                                             DECIMALS,
                                                                                                             MIN_TIP,
                                                                                                             BOT_OWNER)
    embed.description = help_t

    await message.author.send(embed=embed)


@bot.command(aliases=util.get_aliases(aliases.ACCOUNT, exclude='account'))
async def account(ctx):
    """
    Retrieve the user's account from the DB.  If it doesn't exist, create a new one and store it.
    """
    message = ctx.message

    # Retrieve the user's account from the DB
    account_return = await currency.get_account(message.author.id)
    if account_return == () or account_return[0][0] is None:
        await currency.generate_new_account(message, w3)

    elif account_return[0][0] == 'GENERATING':
        await message.author.send("Your account is still generating, check back in a few minutes.")

    elif account_return[0][0] == 'ERROR':
        await message.author.send("There was an error generating your account, please reach out to bot admin.")

    else:
        address = w3.toChecksumAddress(account_return[0][0])
        await message.author.send("Your reusable deposit address is: {}".format(address))


@bot.command(aliases=util.get_aliases(aliases.BALANCE, exclude='balance'))
async def balance(ctx):
    """
    Check for unseen transactions and then retrieve user balance from database and respond.
    """
    message = ctx.message

    account_return = await currency.get_account(message.author.id)
    address = account_return[0][0]
    if address == 'GENERATING':
        await message.author.send("Your account is still generating.  Check back in a few minutes.")
        return
    elif address == 'ERROR':
        await message.author.send("There was an error generating your account, please reach out to bot admin.")
        return

    new_balance = await currency.check_pending(message)
    user_balance, pending = tasks.get_balance(message.author.id)

    if user_balance == () or user_balance is None:
        await message.author.send("There was an error retrieving your account balance.  Please reach out to the "
                                  "administrator of this bot.  ERROR: Balance was empty for "
                                  "user {}".format(message.author.id))
    else:
        await message.author.send("Your balance is {0} {1}.  You have {2} {1} pending withdraw".format(user_balance,
                                                                                                       TOKEN,
                                                                                                       pending))

    if new_balance > 0:
        tasks.forward_to_master.delay(address, new_balance)


@bot.command(aliases=util.get_aliases(aliases.TIP, exclude='tip'))
async def tip(ctx):
    """
    Send tips to provided user list.
    """
    message = {'content': ctx.message.content,
               'author': ctx.message.author.id,
               'author_name': ctx.message.author}
    # Ignore private message tips
    if util.is_private(ctx.message.channel):
        await ctx.message.add_reaction('❌')
        await ctx.message.author.send("Tips can only be made in public channels.")
        return

    # Set the list of users to tip
    users_to_tip = await currency.set_tip_list(message, bot)
    if users_to_tip is None:
        await ctx.message.add_reaction('❌')
        await ctx.message.author.send("We couldn't find anyone in your message to tip.  Please review and resend.")
        return

    message = await currency.validate_tip_amount(message, users_to_tip)
    if message['tip_amount'] is None:
        await ctx.message.add_reaction('❌')
        await ctx.message.author.send("There was an error with the format of your tip amount.  "
                                      "Please review and resend.")
        return
    if Decimal(message['total_tip_amount']) < Decimal(MIN_TIP):
        await ctx.message.add_reaction('❌')
        await ctx.message.author.send("The minimum tip amount is {} {} and you tried "
                                      "to send {}.  Nice try!".format(MIN_TIP, TOKEN, message['total_tip_amount']))
        return

    if not await currency.validate_user(message):
        await ctx.message.add_reaction('❌')
        await ctx.message.author.send("You don't have enough {0} to cover this "
                                      "{1} {0} tip.".format(TOKEN, message['total_tip_amount']))
        return

    await currency.send_tip(message, users_to_tip, ctx, bot)


@bot.command(aliases=util.get_aliases(aliases.WITHDRAW, exclude='withdraw'))
async def withdraw(ctx):
    """
    Withdraw the provided amount to the provided address.
    """
    message = ctx.message
    incorrect_withdraw = ("Your withdraw request has an incorrect syntax.  Please resend with the format "
                          "!withdraw <address> <optional: amount>")

    msg_list = message.content.split(' ')

    if len(msg_list) < 2:
        await message.author.send(incorrect_withdraw)
        return
    try:
        to = w3.toChecksumAddress(msg_list[1])
        user_balance, _ = tasks.get_balance(message.author.id)
        user_balance = Decimal(user_balance)
        if user_balance <= 0:
            await message.author.send("You have 0 {} balance.  Please fund your account "
                                      "before trying to withdraw!".format(TOKEN))
            return
        elif len(msg_list) > 2:
            # User provided an amount, send the whole amount.
            print(msg_list)
            amount = Decimal(msg_list[2])
            total_amount = amount
            remove_amount = amount + FEE
            tasks.add_pending(message.author.id, amount)
            tasks.remove_balance(message.author.id, remove_amount)

        else:
            # User didn't provide an amount, send their whole balance - FEE
            amount, _ = tasks.get_balance(message.author.id)
            amount = Decimal(amount)
            total_amount = amount - FEE
            remove_amount = amount
            tasks.add_pending(message.author.id, remove_amount)
            tasks.remove_balance(message.author.id, amount)

        if user_balance < total_amount or user_balance < FEE:
            await message.author.send("You were trying to withdraw {1} {0} + a fee of {3} {0} and you "
                                      "only have {2} {0}.  Please review the your "
                                      "balance before withdrawing.".format(TOKEN, total_amount, user_balance, FEE))
            return

        tasks.send_tokens.delay(to, total_amount, message.author.id)

        await message.author.send("Your withdraw request for {2} {3} + {4} {3} fee has been queued.  You can check "
                                  "https://{0}/address/{1}#tokentxns for your transaction hash.  Please give a minute "
                                  "or 2 for the block to show on the explorer.".format(ETHERSCAN_ROUTE,
                                                                                       to,
                                                                                       total_amount,
                                                                                       TOKEN,
                                                                                       FEE))

    except ValueError as e:
        logger.error("Error converting decimal value on withdraw: {}".format(e))
        await message.author.send(incorrect_withdraw)
    except InvalidOperation as e:
        logger.error("Error while performing withdraw: {}".format(e))
        await message.author.send(incorrect_withdraw)


if __name__ == '__main__':
    queue = Celery('tasks', broker='redis://localhost//')
    db_init()
    bot.run(BOT_TOKEN)
