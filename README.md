## snakebot
A basic discord.py bot that tries to do everything

## Running

1. **Python 3.9 or higher**

You should be able to run it on earlier versions but I haven't tried

2. **Install dependencies**

<details>
<summary><span style="font-size:1.43em;">Windows</span></summary>

```bash
pip install -U -r requirements.txt
```

On windows you will also need plyvel-win32

```bash
pip install plyvel-win32
```

</details>

<details>

<summary><span style="font-size:1.43em;">Linux</span></summary>

Note: you might need to use pip3 rather than pip
```bash
pip install -U -r requirements.txt
```

On linux you will need plyvel

```bash
pip install plyvel
```

If it fails to install on Debian or Ubuntu try
```bash
apt-get install libleveldb1v5 libleveldb-dev
```

</details>

3. **Setup configuration**

The next step is just to create a `config.py` file in the root directory where
the bot is with the following template:

```py
token = ''  # your bot's token
```

&nbsp;

**Note:**

You will probably want to remove my discord id from the owner_ids in [bot.py](/bot.py#L30) and replace it with your own

&nbsp;

## Requirements

- Python 3.9+
- discord-ext-menus @ git+https://github.com/Rapptz/discord-ext-menus@master
- discord.py[voice]
- lxml
- psutil
- orjson
- youtube_dl
- plyvel
- pillow
