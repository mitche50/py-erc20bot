# ERC20 Tip Bot
The ERC20 tip bot allows you to send and receive ERC20 tokens on Discord.  Running this bot does not imply any liability to the bot creator or any ERC20 token teams.

Prerequisites:
- Existing ERC20 Token contract on the ETH or Ropsten network
- MySQL Server running
- Redis Server running

Steps to run:
1. Create master key and store in a keystore JSON file under file name "keyfiles/master.json" with a blank password
2. Copy exampleconfig.ini to config.ini: `cp exampleconfig.ini config.ini`
3. Update the values of config.ini to reflect your keys / passwords
4. Create virtual environment: `sudo pip3 install virtualenv && sudo apt-get install python3-venv && python3 -m venv /home/YOUR_USERNAME/py-erc20bot/venv`
5. Activate venv: `source /home/YOUR_USERNAME/py-erc20bot/venv/bin/activate`
6. Install requirements: `pip3 install -r /home/YOUR_USERNAME/py-erc20bot/requirements.txt`
- NOTE: If you run into an issue installing MySQL try `sudo apt-get install libmysqlclient-dev` to install the development package.
7. Update examplebotapp.service and exampleworker.service with your paths
8. Move services to system folder: `mv examplebotapp.service /etc/systemd/system/erc20bot.service && mv exampleworker.service /etc/systemd/system/erc20worker.service`
9. Start your services: `systemctl start erc20bot & systemctl start erc20worker`

## Known issues
- Using Python 3.5.2 throws an error with eth-keyfile.  You need to install python3.6 and update commands to this in the shell file.  You will need to rerun dependencies using pip3.6 in the venv.
- If Python 3.6 does not come with pip, run the below commands:
    ```
    wget https://bootstrap.pypa.io/get-pip.py 
    sudo python3.6 get-pip.py
    ```
- If you're running into issues with a missing `Python.h` file, you require python dev tools, install through command `sudo apt-get install python3-dev`