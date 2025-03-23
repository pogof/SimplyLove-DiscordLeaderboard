local function debugPrint(message)
    Trace("[DiscordLeaderboard] "..message)
end

--------------------------------------------------------------------------------------------------

local function printTable(t, indent)
    indent = indent or 0
    local indentStr = string.rep("  ", indent)

    for k, v in pairs(t) do
        if type(v) == "table" then
            debugPrint(indentStr .. tostring(k) .. ":")
            printTable(v, indent + 1)
        else
            debugPrint(indentStr .. tostring(k) .. ": " .. tostring(v))
        end
    end
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

-- Im only interested in what affects EX score, which should be just Holds, Rolls and Mines
-- Hands I guess are a separate thing, but might as well include them lol
-- Not interested in other Tech notation (at least for now lol)
local function getRadar(player)

    local pss = STATSMAN:GetCurStageStats():GetPlayerStageStats(player)
    local RadarCategories = { 'Hands', 'Holds', 'Mines', 'Rolls' }
    
    local radarValues = {}

    for i, RCType in ipairs(RadarCategories) do
        radarValues[RCType] = {}
        radarValues[RCType][1] = pss:GetRadarActual():GetValue( "RadarCategory_"..RCType )
        radarValues[RCType][2] = pss:GetRadarPossible():GetValue( "RadarCategory_"..RCType )
        radarValues[RCType][2] = clamp(radarValues[RCType][2], 0, 999)
    end

    return radarValues
end

--------------------------------------------------------------------------------------------------

local function comment(player)
    local pn = ToEnumShortString(player)
    
    local comment = ""
	
    
	local cmod = GAMESTATE:GetPlayerState(pn):GetPlayerOptions("ModsLevel_Preferred"):CMod()
    local mmod = GAMESTATE:GetPlayerState(pn):GetPlayerOptions("ModsLevel_Preferred"):MMod()
    local xmod = GAMESTATE:GetPlayerState(pn):GetPlayerOptions("ModsLevel_Preferred"):XMod()
    if xmod ~= nil then
        xmod = ("%.2f"):format(xmod)
    end

    if cmod ~= nil then
		comment = comment.."C"..tostring(cmod)
    elseif mmod ~= nil then
        comment = comment.."M"..tostring(mmod)
    elseif xmod ~= nil then
        comment = comment.."X"..tostring(xmod)
    end

    local mini = GAMESTATE:GetPlayerState(pn):GetPlayerOptions("ModsLevel_Preferred"):Mini()
    if mini ~= nil then comment = comment..", ".. math.floor(100 * mini + 0.5) .. "%Mini" end
    
    local visualDelay = math.floor(1000 * GAMESTATE:GetPlayerState(pn):GetPlayerOptions("ModsLevel_Preferred"):VisualDelay() + 0.5)
    if visualDelay ~= nil then comment = comment..", "..visualDelay.."ms (Vis.Del)" end

    local mirror = GAMESTATE:GetPlayerState(pn):GetPlayerOptions("ModsLevel_Preferred"):Mirror()
    local left = GAMESTATE:GetPlayerState(pn):GetPlayerOptions("ModsLevel_Preferred"):Left()
    local right = GAMESTATE:GetPlayerState(pn):GetPlayerOptions("ModsLevel_Preferred"):Right()
    local shuffle = GAMESTATE:GetPlayerState(pn):GetPlayerOptions("ModsLevel_Preferred"):Shuffle()
    --local turnnone = GAMESTATE:GetPlayerState(pn):GetPlayerOptions("ModsLevel_Preferred"):TurnNone() -- This also doens't seem to work lol
    -- These do not seem to exist in ITGMania
    -- local blender = GAMESTATE:GetPlayerState(pn):GetPlayerOptions("ModsLevel_Preferred"):Blender()
    -- local LRMirror = GAMESTATE:GetPlayerState(pn):GetPlayerOptions("ModsLevel_Preferred"):LRMirror()
    -- local UDMirror = GAMESTATE:GetPlayerState(pn):GetPlayerOptions("ModsLevel_Preferred"):UDMirror()
    
    if mirror then
        comment = comment..", Mirror"
    elseif left then
        comment = comment..", Left"
    elseif right then
        comment = comment..", Right"
    elseif shuffle then
        comment = comment..", Shuffle"
    -- elseif turnnone then
    --     comment = comment
    -- else
    --     comment = comment..", ???Turn"
    end
    -- elseif blender then
    --     comment = comment..", Blender"
    -- elseif LRMirror then
    --     comment = comment..", LRMirror"
    -- elseif UDMirror then
    --     comment = comment..", UDMirror"

    --SCREENMAN:SystemMessage(tostring(turnnone) .. " " .. comment)

    return comment
end

--------------------------------------------------------------------------------------------------

local function SongResultData(player, apiKey, style)
    
    local pn = ToEnumShortString(player)

    local song = GAMESTATE:GetCurrentSong()

    -- Song Data
    local songInfo = {
        name   = escapeString(song:GetTranslitFullTitle()),
        artist = escapeString(song:GetTranslitArtist()),
        pack   = escapeString(song:GetGroupName()),
        length = string.format("%d:%02d", math.floor(song:MusicLengthSeconds()/60), math.floor(song:MusicLengthSeconds()%60)),
        stepartist = escapeString(GAMESTATE:GetCurrentSteps(player):GetAuthorCredit()),
        difficulty = GAMESTATE:GetCurrentSteps(player):GetMeter(),
        description = escapeString(GAMESTATE:GetCurrentSteps(player):GetDescription()),
        hash = tostring(SL[pn].Streams.Hash),
        modifiers = comment(player)
    }

    -- Result Data
    local resultInfo = {
        -- playerName = escapeString(GAMESTATE:GetPlayerDisplayName(player)), -- unnecessary
        score = FormatPercentScore(STATSMAN:GetCurStageStats():GetPlayerStageStats(player):GetPercentDancePoints()):gsub("%%", ""),
        exscore = ("%.2f"):format(CalculateExScore(player)),
        grade = STATSMAN:GetCurStageStats():GetPlayerStageStats(player):GetGrade(),
        radar = getRadar(player),
    }


    local scatterplotData, worst_window = getScatterplotData(player, 1000, 200)
    local scatterplotDataJson = encode(scatterplotData)
    
    local lifebarInfo = GetLifebarData(player, 1000, 200)
    local lifebarInfoJson = encode(lifebarInfo)


    -- Prepare JSON data
    local jsonData = string.format(
        '{"api_key": "%s","songName": "%s","artist": "%s","pack": "%s","length": "%s","stepartist": "%s","difficulty": "%s", "description": "%s", "itgScore": "%s","exScore": "%s","grade": "%s", "hash": "%s", "scatterplotData": %s, "lifebarInfo": %s, "worstWindow": %s, "style": "%s", "mods": "%s", "radar": %s}',
        apiKey,
        songInfo.name,
        songInfo.artist,
        songInfo.pack,
        songInfo.length,
        songInfo.stepartist,
        songInfo.difficulty,
        songInfo.description,
        resultInfo.score,
        resultInfo.exscore,
        resultInfo.grade,
        songInfo.hash,
        scatterplotDataJson,
        lifebarInfoJson,
        ("%.4f"):format(worst_window),
        style,
        songInfo.modifiers,
        encode(resultInfo.radar)
        )  

    return jsonData

end

--------------------------------------------------------------------------------------------------




local function CourseResultData(player, apiKey, style)
    
    local pn = ToEnumShortString(player)

    local course = GAMESTATE:GetCurrentCourse()
    local trail = GAMESTATE:GetCurrentTrail(player)

    

    -- Course Data
    local courseInfo = {
        name   = escapeString(course:GetTranslitFullTitle()),
        pack   = escapeString(course:GetGroupName()),
        difficulty = trail:GetMeter(),
        description = escapeString(course:GetDescription()),
        entries = "[",
        hash = BinaryToHex(CRYPTMAN:SHA1File(course:GetCourseDir())):sub(1, 16),
        scripter = escapeString(course:GetScripter()),
        modifiers = comment(player)
    }


    local trailSteps = trail:GetTrailEntries()
    for i in ipairs(trailSteps) do
        courseInfo.entries = courseInfo.entries .. "{name: " .. escapeString(trailSteps[i]:GetSong():GetTranslitFullTitle()) .. ", length: " .. trailSteps[i]:GetSong():MusicLengthSeconds() .. ", artist: " .. escapeString(trailSteps[i]:GetSong():GetTranslitArtist()) .. ", difficulty:  " .. trailSteps[i]:GetSteps():GetMeter() .. "}," -- ", difficulty = " .. trailSteps:GetSteps():GetMeter() ..
    end
    -- Remove the last comma and append the closing bracket
    if courseInfo.entries:sub(-1) == "," then
        courseInfo.entries = courseInfo.entries:sub(1, -2)
    end
    courseInfo.entries = courseInfo.entries .. "]"
    

    -- Result Data
    local resultInfo = {
        --playerName = escapeString(GAMESTATE:GetPlayerDisplayName(player)), -- unnecessary
        score = FormatPercentScore(STATSMAN:GetCurStageStats():GetPlayerStageStats(player):GetPercentDancePoints()):gsub("%%", ""),
        exscore = ("%.2f"):format(CalculateExScore(player)),
        grade = STATSMAN:GetCurStageStats():GetPlayerStageStats(player):GetGrade(),
        radar = getRadar(player),
    }

    
    local lifebarInfo = GetLifebarData(player, 1000, 200) --table
    local lifebarInfoJson = encode(lifebarInfo) --string


    -- Prepare JSON data
    local jsonData = string.format(
        '{"api_key": "%s", "courseName": "%s", "pack": "%s", "entries": "%s", "hash": "%s", "scripter": "%s", "difficulty": "%s", "description": "%s", "itgScore": "%s", "exScore": "%s", "grade": "%s", "lifebarInfo": %s, "style": "%s", "mods": "%s", "radar": %s}',
        apiKey,
        courseInfo.name,
        courseInfo.pack,
        courseInfo.entries,
        courseInfo.hash,
        courseInfo.scripter,
        courseInfo.difficulty,
        courseInfo.description,
        resultInfo.score,
        resultInfo.exscore,
        resultInfo.grade,
        lifebarInfoJson,
        style,
        courseInfo.modifiers,
        encode(resultInfo.radar)
        )

    return jsonData

end


--------------------------------------------------------------------------------------------------

local u = {}

u["ScreenEvaluationStage"] = Def.Actor {
    ModuleCommand = function(self)

        
        -- single, versus, double
        local style = GAMESTATE:GetCurrentStyle():GetName()
        if style == "versus" then style = "single" end
        
        for player in ivalues(GAMESTATE:GetHumanPlayers()) do
            local partValid, allValid = ValidForGrooveStats(player)
            local botURL, apiKey = readURLandKey(player)
            if allValid and botURL ~= nil and apiKey ~= nil then 
                local data = SongResultData(player, apiKey, style)
                sendData(data, botURL)

            end
            
        end

    end
}


u["ScreenEvaluationNonstop"] = Def.ActorFrame {
    ModuleCommand=function(self)
        
        local fixed = GAMESTATE:GetCurrentCourse():AllSongsAreFixed()
        local autogen = GAMESTATE:GetCurrentCourse():IsAutogen()
        local endless = GAMESTATE:GetCurrentCourse():IsEndless()

        -- Would be kinda unfair
        if fixed and not autogen and not endless then
            
            
            -- single, versus, double
            local style = GAMESTATE:GetCurrentStyle():GetName()
            if style == "versus" then style = "single" end
            
            for player in ivalues(GAMESTATE:GetHumanPlayers()) do
                
                
                -- Doesn't return true for courses, but I can use everything else lol
                local partValid, allValid = ValidForGrooveStats(player)

                allValid = true
                for i, valid in ipairs(partValid) do
                    if i ~= 3 and not valid then
                        allValid = false
                        break
                    end
                end

                
                local botURL, apiKey = readURLandKey(player)
                if allValid and botURL ~= nil and apiKey ~= nil then
                    -- Different day different data
                    local data = CourseResultData(player, apiKey, style)
                    sendData(data, botURL)

                end
                
            end
        end



    end
}


return u