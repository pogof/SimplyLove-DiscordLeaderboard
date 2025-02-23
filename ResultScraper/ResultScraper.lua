local function debugPrint(message)
    Trace("[DiscordLeaderboard] "..message)
end

--------------------------------------------------------------------------------------------------

local function readURLandKey(player)

    local pdir
    if player == PLAYER_1 then
        pdir = 0
    else
        pdir = 1
    end

    local profilePath = PROFILEMAN:GetProfileDir(pdir)


    if profilePath == "" then
        return nil, nil
    end

    --All hail the mighty browsers who decided downloading ini as txt is good idea
    local filePaths = {profilePath.."DiscordLeaderboard.ini", profilePath.."DiscordLeaderboard.txt"}

    local botURL, apiKey

    for _, filePath in ipairs(filePaths) do
        local f = RageFileUtil.CreateRageFile()
        if f:Open(filePath, 1) then
            while true do
                local line = f:GetLine()
                if line == "" then break end
                if line:match("^BotURL=") then
                    botURL = line:gsub("BotURL=", "")
                elseif line:match("^APIKey=") then
                    apiKey = line:gsub("APIKey=", "")
                end
            end
            f:destroy()
            if botURL and apiKey then
                return botURL, apiKey
            end
        else
            local fError = f:GetError()
            debugPrint("Error opening file: ".. fError)
            f:ClearError()
            f:destroy()
        end
    end

    return nil, nil

end

--------------------------------------------------------------------------------------------------

local function escapeString(str)
    local replacements = {
        ['"'] = '\\"',
        ['\\'] = '\\\\',
        ['\b'] = '\\b',
        ['\f'] = '\\f',
        ['\n'] = '\\n',
        ['\r'] = '\\r',
        ['\t'] = '\\t'
    }
    return str:gsub('[%z\1-\31\\"]', replacements)
end

local function encodeValue(value)
    local valueType = type(value)
    if valueType == "string" then
        return '"' .. escapeString(value) .. '"'
    elseif valueType == "number" or valueType == "boolean" then
        return tostring(value)
    elseif valueType == "table" then
        local isArray = true
        local maxIndex = 0
        for k, v in pairs(value) do
            if type(k) ~= "number" or k <= 0 or math.floor(k) ~= k then
                isArray = false
                break
            end
            if k > maxIndex then
                maxIndex = k
            end
        end
        local result = {}
        if isArray then
            for i = 1, maxIndex do
                table.insert(result, encodeValue(value[i]))
            end
            return "[" .. table.concat(result, ",") .. "]"
        else
            for k, v in pairs(value) do
                table.insert(result, '"' .. escapeString(k) .. '":' .. encodeValue(v))
            end
            return "{" .. table.concat(result, ",") .. "}"
        end
    else
        return "null"
    end
end

local function encode(value)
    return encodeValue(value)
end

--------------------------------------------------------------------------------------------------

local function sendData(data, botURL)
        
    -- Send HTTP POST request
    NETWORK:HttpRequest{
        url = botURL,
        method = "POST",
        body = data,
        headers = {
            ["Content-Type"] = "application/json"
        },
        onResponse = function(response)
            if type(response) == "table" then
                response = table.concat(response)
            end
            debugPrint("HTTP Response: " .. response)
        end
    }        
end

--------------------------------------------------------------------------------------------------

local function GetLifebarData(player, GraphWidth, GraphHeight)
    local steps = GAMESTATE:GetCurrentSteps(player)
    local timingData = steps:GetTimingData()
    local firstSecond = math.min(timingData:GetElapsedTimeFromBeat(0), 0)
    local chartStartSecond = GAMESTATE:GetCurrentSong():GetFirstSecond()
    local lastSecond = GAMESTATE:GetCurrentSong():GetLastSecond()
    local duration = lastSecond - firstSecond

    local lifebarData = {}
    local playerStageStats = STATSMAN:GetCurStageStats():GetPlayerStageStats(player)
    local lifeRecord = playerStageStats:GetLifeRecord(lastSecond, 100) -- Use lastSecond and default samples

    for i, lifebarValue in ipairs(lifeRecord) do
    local stepSecond = chartStartSecond + (i - 1) * (duration / #lifeRecord)
    local xValue = ((stepSecond - firstSecond) / duration) * GraphWidth
    local yValue = lifebarValue * GraphHeight -- Scale y value to fit within GraphHeight
    table.insert(lifebarData, {x = xValue, y = yValue})
    end

    return lifebarData
end

--------------------------------------------------------------------------------------------------

local function getScatterplotData(player, GraphWidth, GraphHeight)

    local pn = ToEnumShortString(player)
    local mods = SL[pn].ActiveModifiers

    -- sequential_offsets gathered in ./BGAnimations/ScreenGameplay overlay/JudgmentOffsetTracking.lua
    local sequential_offsets = SL[pn].Stages.Stats[SL.Global.Stages.PlayedThisGame + 1].sequential_offsets

    local Steps = GAMESTATE:GetCurrentSteps(player)
    local TimingData = Steps:GetTimingData()
    local FirstSecond = math.min(TimingData:GetElapsedTimeFromBeat(0), 0)
    local LastSecond = GAMESTATE:GetCurrentSong():GetLastSecond()

    local worst_window = GetTimingWindow(math.max(2, GetWorstJudgment(sequential_offsets)))

    local colors = {}
    for w = NumJudgmentsAvailable(), 1, -1 do
        if SL[pn].ActiveModifiers.TimingWindows[w] == true then
            colors[w] = DeepCopy(SL.JudgmentColors[SL.Global.GameMode][w])
        else
            colors[w] = DeepCopy(colors[w + 1] or SL.JudgmentColors[SL.Global.GameMode][w + 1])
        end
    end

    local scatterplotData = {}

    for t in ivalues(sequential_offsets) do
        local CurrentSecond = t[1]
        local Offset = t[2]

        if Offset ~= "Miss" then
            CurrentSecond = CurrentSecond - Offset
        else
            CurrentSecond = CurrentSecond - worst_window
        end

        local x = scale(CurrentSecond, FirstSecond, LastSecond + 0.05, 0, GraphWidth)

        if Offset ~= "Miss" then
            local TimingWindow = DetermineTimingWindow(Offset)
            local y = scale(Offset, worst_window, -worst_window, 0, GraphHeight)
            

            local c = colors[TimingWindow]


                local abs_offset = math.abs(Offset)
                if abs_offset > GetTimingWindow(1, "FA+") and abs_offset <= GetTimingWindow(2, "FA+") then
                    c = SL.JudgmentColors["FA+"][2]
                end


            local r = c[1]
            local g = c[2]
            local b = c[3]

            table.insert(scatterplotData, {x = x, y = y, color = {r, g, b, 0.666}})
        else
            table.insert(scatterplotData, {x = x, y = 0, color = {1, 0, 0, 0.466}})
            table.insert(scatterplotData, {x = x + 1, y = 0, color = {1, 0, 0, 0.466}})
            table.insert(scatterplotData, {x = x + 1, y = GraphHeight, color = {1, 0, 0, 0.466}})
            table.insert(scatterplotData, {x = x, y = GraphHeight, color = {1, 0, 0, 0.466}})
        end
    end

    return scatterplotData, worst_window
end

--------------------------------------------------------------------------------------------------

local function SongResultData(player, apiKey, style)
    
    local pn = ToEnumShortString(player)

    local song = GAMESTATE:GetCurrentSong()

    --Song Data
    local songInfo = {
        name   = escapeString(song:GetTranslitFullTitle()),
        artist = escapeString(song:GetTranslitArtist()),
        pack   = escapeString(song:GetGroupName()),
        length = string.format("%d:%02d", math.floor(song:GetStepsSeconds()/60), math.floor(song:GetStepsSeconds()%60)),
        stepartist = escapeString(GAMESTATE:GetCurrentSteps(player):GetAuthorCredit()),
        difficulty = GAMESTATE:GetCurrentSteps(player):GetMeter(),
        description = escapeString(GAMESTATE:GetCurrentSteps(player):GetDescription()),
        hash = tostring(SL[pn].Streams.Hash),
        modifiers = ""
    }

    --Song modifiers
    local mods = SL[pn].ActiveModifiers
    local modString = ""
    for k, v in pairs(mods) do
        if v then
            modString = modString .. k .. ","
        end
    end
    songInfo.modifiers = modString
    SCREENMAN:SystemMessage(modString)

    -- Result Data
    local resultInfo = {
        playerName = escapeString(GAMESTATE:GetPlayerDisplayName(player)),
        score = FormatPercentScore(STATSMAN:GetCurStageStats():GetPlayerStageStats(player):GetPercentDancePoints()):gsub("%%", ""),
        exscore = ("%.2f"):format(CalculateExScore(player)),
        grade = STATSMAN:GetCurStageStats():GetPlayerStageStats(player):GetGrade(),
    }

    if GAMESTATE:IsCourseMode() then 
        local scatterplotDataJson = ""
    else
        local scatterplotData, worst_window = getScatterplotData(player, 1000, 200)
        local scatterplotDataJson = encode(scatterplotData)
    end

    local lifebarInfo = GetLifebarData(player, 1000, 200)
    local lifebarInfoJson = encode(lifebarInfo)

    -- Prepare JSON data
    local jsonData = string.format(
        '{"api_key": "%s","songName": "%s","artist": "%s","pack": "%s","length": "%s","stepartist": "%s","difficulty": "%s","itgScore": "%s","exScore": "%s","grade": "%s", "hash": "%s", "scatterplotData": %s, "lifebarInfo": %s, "worstWindow": %s, "style": "%s", "modifiers": "%s", "isCourse": "%s"}',
        apiKey,
        songInfo.name,
        songInfo.artist,
        songInfo.pack,
        songInfo.length,
        songInfo.stepartist,
        songInfo.difficulty,
        resultInfo.score,
        resultInfo.exscore,
        resultInfo.grade,
        songInfo.hash,
        scatterplotDataJson,
        lifebarInfoJson,
        ("%.4f"):format(worst_window),
        style,
        resultInfo.modifiers,
        tostring(GAMESTATE:IsCourseMode())
        )
        
    debugPrint("JSON Data: "..jsonData)    

    return jsonData

end

--------------------------------------------------------------------------------------------------

local u = {}

u["ScreenEvaluationStage"] = Def.Actor {
    ModuleCommand = function(self)

        -- single, versus, double
        local style = GAMESTATE:GetCurrentStyle():GetName()
        if style == "versus" then style = "single" end

        local isCourse = GAMESTATE:IsCourseMode()

        if not isCourse then

            for player in ivalues(GAMESTATE:GetHumanPlayers()) do
                local partValid, allValid = ValidForGrooveStats(player)
                local botURL, apiKey = readURLandKey(player)
                if allValid and botURL ~= nil and apiKey ~= nil then 
                    local data = SongResultData(player, apiKey, style)
                    sendData(data, botURL)

                end
                
             end
        end

        -- if isCourse then
        --     for player in ivalues(GAMESTATE:GetHumanPlayers()) do
        --         local partValid, allValid = ValidForGrooveStats(player)
        --         local botURL, apiKey = readURLandKey(player)
        --         if allValid and botURL ~= nil and apiKey ~= nil then 
        --             local data = SongResultData(player, apiKey, style)
        --             sendData(data, botURL)

        --         end
                
        --      end
        -- end


    end
}

return u