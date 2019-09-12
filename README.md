# ERC20 Tip Bot
The ERC20 tip bot allows you to send and receive ERC20 tokens on Discord.  Running this bot does not imply any liability to the bot creator or any ERC20 token teams.

Prerequisites:
- Existing ERC20 Token contract on the ETH or Ropsten network
- MySQL Server running
- Redis Server running

Steps to run:
1. Create master key and store in a keystore JSON file under file name "keyfiles/master.json" with a blank password
2. Move exampleconfig.ini to config.ini: `mv exampleconfig.ini config.ini`
3. Update the values of config.ini to reflect your keys / passwords
4. Create virtual environment: `pip install virtualenv && python3 -m venv /path/to/app/venv`
5. Activate venv: `source /path/to/app/venv/bin/activate`
6. Install requirements: `pip install -r /path/to/app/requirements.txt`
7. Update examplebotapp.service and exampleworker.service with your paths
8. Move services to system folder: `mv examplebotapp.service /etc/systemd/system/erc20bot.service && mv exampleworker.service /etc/systemd/system/erc20worker.service`
9. Start your services: `systemctl start erc20bot & systemctl start erc20worker`