## snakebot
A basic discord.py bot that tries to do everything

## Running

1. **Python 3.9 or higher**

You should be able to run it on earlier versions but I haven't tried

2. **Install dependencies**

`pip install -U -r requirements.txt`
or
`poetry install`


3. **Setup configuration**

The next step is just to create a `config.py` file in the root directory where
the bot is with the following template:

```py
token = '' # your bot's token
tenor = '' # tenor key for the hug command from https://tenor.com/developer/dashboard
coinmarketcap = '' # coinmarketcap key for crypto command from https://pro.coinmarketcap.com/
```

## Requirements

- Python 3.9+
- discord-ext-menus @ git+https://github.com/Rapptz/discord-ext-menus@master
- discord.py
- lxml
- parsedatetime
- psutil
- ujson
- youtube_dl
- python-dateutil