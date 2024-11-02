# SimplyLove-DiscordLeaderboard

This repository is made of two parts "the Result Scraper" and "Discord Bot"


## Result Scraper

Result Scraper is a standard Module for SimplyLove theme of ITGmania. Im sure it will work even on derivatives like Z-Mod, however any information the Result Scraper gathers MUST be accessible through vanilla SimplyLove or calculated afterwards based on it.

### What does the Result Scraper scrapes:
* Transliterated name of the song
* Transliterated name of the artist
* Name of the pack the chart is part of
* The lenght of the song in mm:ss (most likely will fail on songs >= 1h)
* The block difficulty
* Description (I dont think it ever returned anything in testing, I think its a field in the chart data tho?) (Currently not sent anywhere)
* Hash of the stepchart 
* Player name (Name of the account, although it is currently not sent anywhere)
* ITG Score (two decimal places, same as in game)
* EX Score (two decimal places, same as in game)
* The scatter plot data as json (with x, y and color value for each point. Graph size arbitrary set to 1000x200)
* The lifebar information overtime as seen on the scatterplot on the result screen as json (with x, y values. First point aligned with first step, same as in game)

### How to use it
If you want to fork this and modify it for your needs, have fun. 

If you want to use it for your own discord server
1. Copy the `ResultScraper.lua` into the Modules folder of SimplyLove
2. In `Preferences.ini` make sure you enable `HttpAllowHosts=*.groovestats.com,<Bot domain/IP here>` and set `HttpEnabled=1`
3. In your profile add `DiscordLeaderboard.ini` with the following text

```
BotURL=http://<Bot IP/domain>:5000/send
APIKey=<api key you get from the discord bot>
```

4. If you have internet and you finish song and get to the result screen it should automatically send the results to the discord bot portion.

### Possible improvements, bugs or additional features

Code has been combed through so it is at least presentable, however there is minimal error handling and some of the functions could be bit more optimized. There might be more data that could be scraped, however for now I covered the most important.

Coursemode has not been tested and moste likely doesnt work like at all.

## Discord Bot
Code has been modified slightly (added .env) and has been untested (but I assume it should work). 

Discord bot includes Flask as it needs to listen to external traffic. By default it listens on `/send` How to setup a Discord bot is beyond the scope of this repository. Data is stored in sqlite database. Scatter plot is created using matplotlib

For your convenience the URL that should be prefilled in the file sent to the player is changable in the .env file, same as the discord bot token.

### How it works

After you start the bot, add it to the server, admin has to use the command `!usethischannel` in a channel where you want the results to be sent. Players can use the command `!generate` that will generate a unique key that will be sent to their DM. The message includes ready made `DiscordLeaderboard.ini`. Player should add the file to the ITGmania profile folder. They are now ready to automatically submit the scores!

Bot will announce your score as PB the first time you play a chart after joining the leaderboard, any additional attempt will only be announced if your EX score is better then your previous score. Each shoutout will also include top 3 scores on the server. Note that the result must not be a Fail.

The bot can be added to multiple servers, the shoutout will be only sent to the servers that the player is part of and the top 3 scores will be based on the players part of each server. 

### Possible improvements, bugs or additional features
* Clean the code
* Add more error handling
* Database system works although there must be better aproach in the long term
* Possibly ditch saving the results in a separate database and just lookup the results in Groovestats/Boogiestats

### Docker container

I have been able to put the application to a docker container, however I havent been able to make it work with my reverse proxy, assuming user error for now. Dockerfile and docker-compose.yaml are included.

## Major bugs
Chart `ITL2024 [1000] [07] Idol (Medium)` returns error 400 on the bot side, skipping any and all code that should actually result in such error. From all my testing it is the only chart, the json sent seems fine to me though. 
