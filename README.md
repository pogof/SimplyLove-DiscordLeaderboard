# SimplyLove-DiscordLeaderboard

## **To download use the Releases on the right sidebar!**

Looking to make your local ITG server more competitive? Do you want to have a real time updates about what your friends are playing or want to immediately snipe their high-score? This Module is for you!

As of now this repository has reached stable release v1! Everything that is included should be ready to use. For further explanation and installation instructions continue reading.

<div style="display: flex; flex-wrap: wrap;">
    <img src="https://github.com/pogof/readme-pics/blob/master/ITGMania-Leaderboard/score.png?raw=true" alt="Score" style="width:50%;">
    <img src="https://github.com/pogof/readme-pics/blob/master/ITGMania-Leaderboard/breakdown.png?raw=true" alt="Breakdown" style="width:50%;">
    <img src="https://github.com/pogof/readme-pics/blob/master/ITGMania-Leaderboard/compare.png?raw=true" alt="Compare" style="width:50%;">
    <img src="https://github.com/pogof/readme-pics/blob/master/ITGMania-Leaderboard/unplayed.png?raw=true" alt="Unplayed" style="width:50%;">
</div>

## Result Scraper

Result Scraper is a standard Module for SimplyLove theme for ITGmania. Im sure it will work even on derivatives like Z-Mod (it will), however any information the Result Scraper gathers MUST be accessible through vanilla SimplyLove or calculated afterwards based on it.

### What does the Result Scraper scrapes:
* Transliterated name of the song
* Transliterated name of the artist (currently not displayed)
* Name of the pack the chart is part of
* The length of the song in mm:ss (most likely will fail on songs >= 1h)
* The block difficulty
* Description (currently not displayed)
* Hash of the stepchart (not displayed but used internally)
* ITG Score (two decimal places, same as in game)
* EX Score (two decimal places, same as in game)
* The scatter plot data as json (with x, y and color value for each point. Graph size arbitrary set to 1000x200)
* The lifebar information overtime as seen on the scatterplot on the result screen as json (with x, y values. First point aligned with first step, same as in game)
* Number of holds, rolls and mines (both total and passed) 
* SUPPORTS single and double mode
* SUPPORTS marathons! (Both single and double)
* Saves EX% upscore (if better score is submitted)


### How to use it
If you want to fork this and modify it for your needs, have fun. 

#### If you want to use it for your own discord server as is:
1. Copy the `ResultScraper.lua` into the Modules folder of Simply Love
2. In `Preferences.ini` make sure you enable `HttpAllowHosts=*.groovestats.com,<Bot domain/IP here>` and set `HttpEnabled=1` 
3. In your profile add `DiscordLeaderboard.ini` with the following text

```
BotURL=http://<Bot IP/domain>:5000/send
APIKey=<api key you get from the discord bot>
```

4. If you have internet and you finish song and get to the result screen it should automatically send the results to the discord bot portion.

## Discord Bot

Discord bot includes Flask as it needs to listen to external traffic. By default it listens on `/send` How to setup a Discord bot itself is beyond the scope of this repository. Data is stored in sqlite database. Scatter plot is created using matplotlib

For your convenience `.env.template` has been provided. Rename it to `.env` and prefill your Discord Bot token and the URL your users should use to connect to the bot.

### Docker container

If you so choose you can run the bot in a Docker container. Working dockerfile has been provided for ease of setup.

### How it works

After you start the bot, add it to the server, admin has to use the command `/usethischannel` in a channel where you want the results to be sent. Players can use the command `/generate` that will generate a unique key that will be sent to their DM. The message includes ready made `DiscordLeaderboard.ini`. Player should add the file to the ITGmania profile folder. They are now ready to automatically submit the scores! (The file may download as txt instead however both .ini and .txt will work)

Bot will announce your score as PB the first time you play a chart after joining the leaderboard, any additional attempt will only be announced if your EX score is better then your previous score. Each shout out will also include top 3 scores on the server. Note that the result must not be a Fail.

The bot can be added to multiple servers, the shout out will be only sent to the servers that the player is part of and the top 3 scores will be based on the players part of each server.

### List of commands

#### Admin only:
* /usethischannel - sets the channel to receive score messages

#### General use
* /generate - generates API key (can be used to set new key also)
* /score - shows the same message as the auto submission
    * | Parameter | default state | Description |
    * song - REQUIRED - Song name (can be just partial)
    * isdouble - FALSE - true/false
    * user - () - @username from server
    * failed - FALSE - true/false, failed scores also save, but do not auto announce
    * difficulty - () - search for particular difficulty
    * pack - () - search by pack
    * private - FALSE - true/false, if only you want to see

* /breakdown - Shows extra information about score
    * | Parameter | default state | Description |
    * song - REQUIRED - Song name (can be just partial)
    * isdouble FALSE - true/false
    * iscourse - FALSE - true/false, if you want to see course score
    * user - () - @username from server
    * failed - FALSE - true/false, failed scores also save, but do not auto announce
    * difficulty - () - search for particular difficulty
    * pack - () - search by pack
    * private - FALSE - true/false, if only you want to see

* /compare - compares compares two users scores
    * | Parameter | default state | Description |
    * user_two - REQUIRED - user you want to compare against
    * user_one - your @ - if you want to compare two other users against each other
    * isdouble FALSE - true/false, if you want to compare single/double scores
    * difficulty - () - search for particular difficulty
    * pack - () - search by pack
    * private - TRUE - true/false, only you see by default
    * iscourse - FALSE - true/false, if you want to compare course scores
    * page - 1 - if you want to start halfway through the list
    * order - asc_alpha - how should the list be sorted. (asc_ex, desc_ex, asc_alpha, desc_alpha, asc_diff, desc_diff)

* /course - recalls course score
    * name - REQUIRED - course name (can be just partial)
    * isdouble FALSE - true/false
    * user - () - @username from server
    * failed - FALSE - true/false, failed scores also save, but do not auto announce
    * difficulty - () - search for particular difficulty
    * pack - () - search by pack
    * private - FALSE - true/false, if only you want to see

* /unplayed - will show list of all charts other people played and you have not
    * | Parameter | default state | Description |
    * user_two - () - user you want to compare against, if none is specified it is everyone on the server
    * isdouble FALSE - true/false, if you want to compare single/double scores
    * difficulty - () - search for particular difficulty
    * pack - () - search by pack
    * private - TRUE - true/false, only you see by default
    * iscourse - FALSE - true/false, if you want to compare course scores
    * page - 1 - if you want to start halfway through the list
    * order - asc_alpha - asc_alpha, desc_alpha, how should the list be sorted.

* /disable /enable - if you wish to disable or enable the auto announcement for yourself. You can specify time with options, else it is until you switch back.

* /help - will show *some* command descriptions.

## Possible improvements, bugs or additional features

There are minor "bugs" like some score only showing one/none decimal place when the score is XX.X% or XX%. 

Variable name use inconsistent naming schemes. Im sure some stuff is done redundantly.

/unplayed will show all unplayed charts no matter if it was submitted by someone on different server.

Some admin features (like removal of scores, banning people, etc.) have not been developed at all so far.

Apart from that both the scraper and the Discord bot are fairly robust, both in worst case just throwing error instead of crashing either the game or the bot. 
