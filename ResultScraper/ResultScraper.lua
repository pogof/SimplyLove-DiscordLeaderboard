--------------------------------------------------------------------------------------------------
-- ResultScraper.lua
-- Author: PogofCZ
-- Original repo: https/github.com/Pogof/SimplyLove-DiscordLeaderboard
--
-- This module gathers all relevant data at the end of a song/course and sends it to the configured backend.
-- The original backend is intended to be a Discord leaderboard bot, but anyone is free to setup their own
-- server to receive the data and do with it as they please.
--
-- The module version corresponds to the original backend version.
-- DO NOT CHANGE THESE UNLESS YOU ARE THE SERVER ADMINISTRATOR. It will stop sending the results to the server.
local version = nil
local botURL = nil
--------------------------------------------------------------------------------------------------

-- luacheck: globals GAMESTATE PREFSMAN THEME SL PLAYER_1 PLAYER_2 STATSMAN CRYPTMAN PROFILEMAN IniFile NETWORK IsHumanPlayer FormatPercentScore CalculateExScore GetTimingWindow GetWorstJudgment BinaryToHex clamp Trace ToEnumShortString ivalues MESSAGEMAN

-- Normalize botURL to base URL
local function normalizeBotURL(url)
    if not url then return nil end
    -- Prepend https:// if no scheme is present
    if not url:match("^https?://") then
        url = "https://" .. url
    end
    -- Strip any trailing path/slash, keep only scheme + host
    return url:match("^(https?://[^/]+)") or url
end

local function normalizeBotHost(url)
    local normalized = normalizeBotURL(url)
    if not normalized then return nil end
    local host = normalized:gsub("^https?://", "")
    host = host:match("^[^/]+") or host
    host = host:match("^([^:]+)") or host

    local parts = {}
    for part in host:gmatch("[^.]+") do
        table.insert(parts, part)
    end

    if #parts >= 2 then
        return "*." .. parts[#parts - 1] .. "." .. parts[#parts]
    end

    return host
end

--------------------------------------------------------------------------------------------------

local function debugPrint(message)
    Trace("[DiscordLeaderboard] " .. message)
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

local invalidMapping = {
    [1] = "Wrong Game (Only DANCE or PUMP is supported)",
    [2] = "Solo (6panel) is not supported",
    [3] = "Course mode (You shouldn't be getting this,\ncheck for other errors first)",
    [4] = "Not in ITG/FA+ mode (No casuals allowed!)",
    [5] = "Timing window set too lose. Must be 4 or higher.",
    [6] = "Life difficulty set too low. Must be 4 or higher.",
    [7] = "Something in Preferences.ini is set wrong. Reset the file.",
    [8] = "Music Rate must be between 1x and 3x.",
    [9] = "Notes were removed (Little, NoHolds, NoMines,...)",
    [10] = "Notes were added (Wide, Echo, Quick,...)",
    [11] = "Fail type not Immediate or ImmediateContinue.",
    [12] = "Autoplay is enabled.",
    [13] = "Rescoring or other errors"
}

--------------------------------------------------------------------------------------------------

local function readURLandKey(player)
    local playerIndex = (player == PLAYER_1) and 0 or 1
    local profilePath = PROFILEMAN:GetProfileDir(playerIndex)


    if profilePath == "" then
        return nil, nil
    end


    local filePath = profilePath .. "DiscordLeaderboard.ini"

    local APIKey

    local contents = IniFile.ReadFile(filePath)
    if contents["DiscordLeaderboard"] then
        if contents["DiscordLeaderboard"]["APIKey"] then
            APIKey = contents["DiscordLeaderboard"]["APIKey"]
            return normalizeBotURL(botURL), APIKey
        end
    else
        debugPrint("DiscordLeaderboard.ini not found or has an incorrect format.")
        return nil, nil
    end
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
            -- Special handling for scatterplot data points to maintain x, y, color order
            if value.x and value.y and value.color then
                table.insert(result, '"x":' .. encodeValue(value.x))
                table.insert(result, '"y":' .. encodeValue(value.y))
                table.insert(result, '"color":' .. encodeValue(value.color))
            else
                -- Use original method for other objects
                for k, v in pairs(value) do
                    table.insert(result, '"' .. escapeString(k) .. '":' .. encodeValue(v))
                end
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

local function sendData(data, botURL, callback)
    -- Check data size before sending
    local dataSize = string.len(data)
    debugPrint("Sending data of size: " .. dataSize .. " bytes to " .. botURL)

    if dataSize > 1048576 then -- 1MB limit
        debugPrint("Warning: Data size is very large (" .. math.floor(dataSize / 1024) .. "KB), this might cause issues")
    end

    -- Send HTTP POST request
    NETWORK:HttpRequest {
        url = botURL,
        method = "POST",
        body = data,
        headers = {
            ["Content-Type"] = "application/json"
        },
        onResponse = function(response)
            local code = response.statusCode or 0
            local response_body = response.body or ""

            debugPrint("HTTP Response - Code: " .. tostring(code) .. ", Body length: " .. string.len(response_body))

            if code == 0 or response_body == "" then
                if callback then
                    callback(code, "Network error or timeout - no response received")
                end
                return
            end

            local decoded = JsonDecode(response_body)
            local body = decoded and decoded.status or response_body
            if callback then
                callback(code, body)
            end
        end
    }
end

--------------------------------------------------------------------------------------------------

-- Send data in chunks for large datasets
local function sendDataInChunks(data, botURL, callback)
    local dataSize = string.len(data)
    debugPrint("Total data size: " .. dataSize .. " bytes")

    -- If data is small enough, send normally
    if dataSize < 500000 then -- 500KB limit
        debugPrint("Data size is manageable, sending normally")
        return sendData(data, botURL .. "/send", callback)
    end

    debugPrint("Data is large, attempting to send in chunks")

    -- Parse the JSON to extract large arrays
    local decoded = JsonDecode(data)
    if not decoded then
        debugPrint("Failed to parse data for chunking, sending normally")
        return sendData(data, botURL .. "/send", callback)
    end

    local scatterplotData = decoded.scatterplotData
    local lifebarInfo = decoded.lifebarInfo

    -- Check if we have large arrays to chunk
    local needsChunking = false
    if scatterplotData and #scatterplotData > 1000 then
        needsChunking = true
    elseif lifebarInfo and #lifebarInfo > 500 then
        needsChunking = true
    end

    if not needsChunking then
        debugPrint("No large arrays found, sending normally")
        return sendData(data, botURL .. "/send", callback)
    end

    -- Remove large arrays from main payload
    decoded.scatterplotData = nil
    decoded.lifebarInfo = nil
    decoded.isChunked = true

    -- Calculate number of chunks needed
    local chunkSize = 1000 -- points per chunk
    local scatterChunks = 0
    local lifebarChunks = 0

    if scatterplotData then
        scatterChunks = math.ceil(#scatterplotData / chunkSize)
    end
    if lifebarInfo then
        lifebarChunks = math.ceil(#lifebarInfo / chunkSize)
    end

    decoded.totalChunks = scatterChunks + lifebarChunks + 1 -- +1 for main data
    decoded.scatterplotChunks = scatterChunks
    decoded.lifebarChunks = lifebarChunks

    local mainData = encode(decoded)

    -- botURL is already normalized to base URL
    local sendURL = botURL .. "/send"
    local chunkURL = botURL .. "/chunk"

    debugPrint("Using URLs - Chunks: " .. chunkURL .. ", Main data: " .. sendURL)
    debugPrint("Sending " ..
        scatterChunks .. " scatterplot chunks and " .. lifebarChunks .. " lifebar chunks first, then main data")

    local chunksToSend = scatterChunks + lifebarChunks
    local chunksCompleted = 0
    local hasError = false

    local function checkAllChunksSent()
        chunksCompleted = chunksCompleted + 1
        debugPrint("Chunk completed: " .. chunksCompleted .. "/" .. chunksToSend)

        if chunksCompleted >= chunksToSend and not hasError then
            debugPrint("All chunks sent successfully, now sending main data")
            sendData(mainData, sendURL, callback)
        end
    end

    local function handleChunkError(code, body, chunkType, chunkIndex)
        if not hasError then
            hasError = true
            debugPrint("Failed to send " ..
                chunkType .. " chunk " .. chunkIndex .. ": " .. tostring(code) .. " - " .. tostring(body))
            if callback then
                callback(code, "Failed to send " .. chunkType .. " chunk " .. chunkIndex .. ": " .. tostring(body))
            end
        end
    end

    -- Send scatterplot chunks first
    if scatterplotData then
        for i = 1, scatterChunks do
            local startIdx = (i - 1) * chunkSize + 1
            local endIdx = math.min(i * chunkSize, #scatterplotData)
            local chunk = {}
            for j = startIdx, endIdx do
                table.insert(chunk, scatterplotData[j])
            end

            local chunkData = encode({
                hash = decoded.hash,
                api_key = decoded.api_key,
                chunkType = "scatterplot",
                chunkIndex = i,
                totalChunks = scatterChunks,
                data = chunk
            })

            debugPrint("Sending scatterplot chunk " .. i .. "/" .. scatterChunks .. " (" .. #chunk .. " points)")
            sendData(chunkData, chunkURL, function(code, body)
                if code == 200 then
                    checkAllChunksSent()
                else
                    handleChunkError(code, body, "scatterplot", i)
                end
            end)
        end
    end

    -- Send lifebar chunks
    if lifebarInfo then
        for i = 1, lifebarChunks do
            local startIdx = (i - 1) * chunkSize + 1
            local endIdx = math.min(i * chunkSize, #lifebarInfo)
            local chunk = {}
            for j = startIdx, endIdx do
                table.insert(chunk, lifebarInfo[j])
            end

            local chunkData = encode({
                hash = decoded.hash,
                api_key = decoded.api_key,
                chunkType = "lifebar",
                chunkIndex = i,
                totalChunks = lifebarChunks,
                data = chunk
            })

            debugPrint("Sending lifebar chunk " .. i .. "/" .. lifebarChunks .. " (" .. #chunk .. " points)")
            sendData(chunkData, chunkURL, function(code, body)
                if code == 200 then
                    checkAllChunksSent()
                else
                    handleChunkError(code, body, "lifebar", i)
                end
            end)
        end
    end

    -- If no chunks to send, send main data immediately
    if chunksToSend == 0 then
        debugPrint("No chunks to send, sending main data immediately")
        sendData(mainData, sendURL, callback)
    end
end

--------------------------------------------------------------------------------------------------

local function roundToDecimalPlaces(value, decimalPlaces)
    -- Round a number to the specified number of decimal places
    local multiplier = 10 ^ decimalPlaces
    return math.floor(value * multiplier + 0.5) / multiplier
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
        -- Reduce precision to 3 decimal places
        xValue = roundToDecimalPlaces(xValue, 3)
        yValue = roundToDecimalPlaces(yValue, 3)
        table.insert(lifebarData, { x = xValue, y = yValue })
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
        x = roundToDecimalPlaces(x, 3)

        if Offset ~= "Miss" then
            local TimingWindow = DetermineTimingWindow(Offset)
            local y = scale(Offset, worst_window, -worst_window, 0, GraphHeight)
            y = roundToDecimalPlaces(y, 3)

            local c = colors[TimingWindow]


            local abs_offset = math.abs(Offset)
            if abs_offset > GetTimingWindow(1, "FA+") and abs_offset <= GetTimingWindow(2, "FA+") then
                c = SL.JudgmentColors["FA+"][2]
            end


            local r = roundToDecimalPlaces(c[1], 3)
            local g = roundToDecimalPlaces(c[2], 3)
            local b = roundToDecimalPlaces(c[3], 3)

            table.insert(scatterplotData, { x = x, y = y, color = { r, g, b, 0.666 } })
        else
            table.insert(scatterplotData, { x = x, y = 0, color = { 1, 0, 0, 0.466 } })
            table.insert(scatterplotData, { x = x + 1, y = 0, color = { 1, 0, 0, 0.466 } })
            table.insert(scatterplotData, { x = x + 1, y = GraphHeight, color = { 1, 0, 0, 0.466 } })
            table.insert(scatterplotData, { x = x, y = GraphHeight, color = { 1, 0, 0, 0.466 } })
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
        radarValues[RCType][1] = pss:GetRadarActual():GetValue("RadarCategory_" .. RCType)
        radarValues[RCType][2] = pss:GetRadarPossible():GetValue("RadarCategory_" .. RCType)
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
        comment = comment .. "C" .. tostring(cmod)
    elseif mmod ~= nil then
        comment = comment .. "M" .. tostring(mmod)
    elseif xmod ~= nil then
        comment = comment .. "X" .. tostring(xmod)
    end

    local mini = GAMESTATE:GetPlayerState(pn):GetPlayerOptions("ModsLevel_Preferred"):Mini()
    if mini ~= nil then comment = comment .. ", " .. math.floor(100 * mini + 0.5) .. "% Mini" end

    local visualDelay = math.floor(1000 *
        GAMESTATE:GetPlayerState(pn):GetPlayerOptions("ModsLevel_Preferred"):VisualDelay() + 0.5)
    if visualDelay ~= nil and visualDelay ~= 0 then comment = comment .. ", " .. visualDelay .. "ms (Vis.Del)" end

    local turn = GAMESTATE:GetPlayerState(pn):GetPlayerOptionsArray("ModsLevel_Preferred")

    local turnLabels = {
        Mirror       = ", Mirror",
        Left         = ", Left",
        Right        = ", Right",
        LRMirror     = ", LR-Mirror",
        UDMirror     = ", UD-Mirror",
        Shuffle      = ", Shuffle",
        SuperShuffle = ", Blender",
        HyperShuffle = ", Random",
        Backwards    = ", Backwards"
    }

    for i, o in ipairs(turn) do
        if turnLabels[o] then
            comment = comment .. turnLabels[o]
        end
    end

    return comment
end

--------------------------------------------------------------------------------------------------

local function SongResultData(player, APIKey, style, gameMode)
    local pn = ToEnumShortString(player)

    local song = GAMESTATE:GetCurrentSong()

    -- Song Data
    local songInfo = {
        name        = escapeString(song:GetTranslitFullTitle()),
        artist      = escapeString(song:GetTranslitArtist()),
        pack        = escapeString(song:GetGroupName()),
        length      = string.format("%d:%02d", math.floor(song:MusicLengthSeconds() / 60),
            math.floor(song:MusicLengthSeconds() % 60)),
        stepartist  = escapeString(GAMESTATE:GetCurrentSteps(player):GetAuthorCredit()),
        difficulty  = GAMESTATE:GetCurrentSteps(player):GetMeter(),
        description = escapeString(GAMESTATE:GetCurrentSteps(player):GetDescription()),
        hash        = tostring(SL[pn].Streams.Hash),
        modifiers   = comment(player)
    }

    -- Result Data
    local resultInfo = {
        score = FormatPercentScore(STATSMAN:GetCurStageStats():GetPlayerStageStats(player):GetPercentDancePoints()):gsub(
            "%%", ""),
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
        '{"api_key": "%s","songName": "%s","artist": "%s","pack": "%s","length": "%s","stepartist": "%s","difficulty": "%s", "description": "%s", "itgScore": "%s","exScore": "%s","grade": "%s", "hash": "%s", "scatterplotData": %s, "lifebarInfo": %s, "worstWindow": %s, "style": "%s", "mods": "%s", "radar": %s, "gameMode": "%s", "version": "%s"}',
        APIKey,
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
        encode(resultInfo.radar),
        gameMode,
        version
    )

    return jsonData
end

--------------------------------------------------------------------------------------------------

local function CourseResultData(player, APIKey, style, gameMode)
    local pn = ToEnumShortString(player)

    local course = GAMESTATE:GetCurrentCourse()
    local trail = GAMESTATE:GetCurrentTrail(player)



    -- Course Data
    local courseInfo = {
        name        = escapeString(course:GetTranslitFullTitle()),
        pack        = escapeString(course:GetGroupName()),
        difficulty  = trail:GetMeter(),
        description = escapeString(course:GetDescription()),
        entries     = "",
        hash        = BinaryToHex(CRYPTMAN:SHA1File(course:GetCourseDir())):sub(1, 16),
        scripter    = escapeString(course:GetScripter()),
        modifiers   = comment(player)
    }

    local trailSteps = trail:GetTrailEntries()
    local entries = {}
    for i in ipairs(trailSteps) do
        table.insert(entries,
            {
                name = escapeString(trailSteps[i]:GetSong():GetTranslitFullTitle()),
                length = trailSteps[i]:GetSong():MusicLengthSeconds(),
                artist = escapeString(trailSteps[i]:GetSong():GetTranslitArtist()),
                difficulty = trailSteps[i]:GetSteps():GetMeter()
            }
        )
    end
    courseInfo.entries = encode(entries)

    -- Result Data
    local resultInfo = {
        --playerName = escapeString(GAMESTATE:GetPlayerDisplayName(player)), -- unnecessary
        score = FormatPercentScore(STATSMAN:GetCurStageStats():GetPlayerStageStats(player):GetPercentDancePoints()):gsub(
            "%%", ""),
        exscore = ("%.2f"):format(CalculateExScore(player)),
        grade = STATSMAN:GetCurStageStats():GetPlayerStageStats(player):GetGrade(),
        radar = getRadar(player),
    }


    local lifebarInfo = GetLifebarData(player, 1000, 200) --table
    local lifebarInfoJson = encode(lifebarInfo)           --string


    -- Prepare JSON data
    local jsonData = string.format(
        '{"api_key": "%s", "courseName": "%s", "pack": "%s", "entries": %s, "hash": "%s", "scripter": "%s", "difficulty": "%s", "description": "%s", "itgScore": "%s", "exScore": "%s", "grade": "%s", "lifebarInfo": %s, "style": "%s", "mods": "%s", "radar": %s, "gameMode": "%s", "version": "%s"}',
        APIKey,
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
        encode(resultInfo.radar),
        gameMode,
        version
    )

    return jsonData
end

--------------------------------------------------------------------------------------------------

local u = {}

u["ScreenEvaluationStage"] = Def.ActorFrame {
    ModuleCommand = function(self)
        local p1Text = self:GetChild("ACSubmitP1")
        local p2Text = self:GetChild("ACSubmitP2")
        local p1ErrMsg = self:GetChild("ACErrorP1")
        local p2ErrMsg = self:GetChild("ACErrorP2")
        if p1Text then p1Text:settext("") end
        if p2Text then p2Text:settext("") end
        if p1ErrMsg then p1ErrMsg:settext("") end
        if p2ErrMsg then p2ErrMsg:settext("") end

        -- "dance" or "pump"
        local gameMode = GAMESTATE:GetCurrentGame():GetName()
        -- single, versus, double
        local style = GAMESTATE:GetCurrentStyle():GetName()
        if style == "versus" then style = "single" end

        for player in ivalues(GAMESTATE:GetHumanPlayers()) do
            local partValid, allValid = ValidForGrooveStats(player)

            local pn = ToEnumShortString(player)
            local label = (pn == "P1") and p1Text or p2Text
            local errLabel = (pn == "P1") and p1ErrMsg or p2ErrMsg

            local botURL, APIKey = readURLandKey(player)
            if botURL == nil and APIKey == nil then
                label:settext("❌ DiscordLeaderboard: Invalid Data.")
                errLabel:settext("Your INI file is missing or invalid.")
                return
            end

            if allValid then
                label:settext("DiscordLeaderboard: Submitting…")
                errLabel:settext("")
            else
                local failed = {}
                for i, valid in ipairs(partValid) do
                    if not valid then
                        table.insert(failed,
                            invalidMapping[i] or ("Unknown error (check " .. tostring(i) .. ")"))
                    end
                end
                label:settext("❌ DiscordLeaderboard: Invalid Score.")
                errLabel:settext(table.concat(failed, "\n"))
                return
            end

            local data = SongResultData(player, APIKey, style, gameMode)

            -- Use chunked sending for potentially large data
            sendDataInChunks(data, botURL, function(code, body)
                if code == 200 then
                    label:settext("✔ DiscordLeaderboard: Submitted!")
                else
                    label:settext("❌ DiscordLeaderboard: Submission Failed.")
                    errLabel:settext("Error: " .. tostring(code) .. ". Response: " .. tostring(body))
                end
            end)
        end
    end,
    LoadFont("Common Normal") .. {
        Name = "ACSubmitP1",
        InitCommand = function(self)
            self:xy(10, 50):zoom(0.6):halign(0):valign(0)
            self:settext("")
        end
    },
    LoadFont("Common Normal") .. {
        Name = "ACSubmitP2",
        InitCommand = function(self)
            self:xy(_screen.w - 10, 50):zoom(0.6):halign(1):valign(0)
            self:settext("")
        end
    },
    LoadFont("Common Normal") .. {
        Name = "ACErrorP1",
        InitCommand = function(self)
            self:xy(10, 64):zoom(0.5):halign(0):valign(0)
            self:settext("")
            self:diffusecolor({ 1, 1, 1, 1 })
        end
    },
    LoadFont("Common Normal") .. {
        Name = "ACErrorP2",
        InitCommand = function(self)
            self:xy(_screen.w - 10, 64):zoom(0.5):halign(1):valign(0)
            self:settext("")
            self:diffusecolor({ 1, 1, 1, 1 })
        end
    },
}


u["ScreenEvaluationNonstop"] = Def.ActorFrame {
    ModuleCommand = function(self)
        local p1Text = self:GetChild("ACSubmitP1")
        local p2Text = self:GetChild("ACSubmitP2")
        local p1ErrMsg = self:GetChild("ACErrorP1")
        local p2ErrMsg = self:GetChild("ACErrorP2")
        if p1Text then p1Text:settext("") end
        if p2Text then p2Text:settext("") end
        if p1ErrMsg then p1ErrMsg:settext("") end
        if p2ErrMsg then p2ErrMsg:settext("") end

        local fixed = GAMESTATE:GetCurrentCourse():AllSongsAreFixed()
        local autogen = GAMESTATE:GetCurrentCourse():IsAutogen()
        local endless = GAMESTATE:GetCurrentCourse():IsEndless()

        -- "dance" or "pump"
        local gameMode = GAMESTATE:GetCurrentGame():GetName()
        -- single, versus, double
        local style = GAMESTATE:GetCurrentStyle():GetName()
        if style == "versus" then style = "single" end

        for player in ivalues(GAMESTATE:GetHumanPlayers()) do

            local pn = ToEnumShortString(player)
            local label = (pn == "P1") and p1Text or p2Text
            local errLabel = (pn == "P1") and p1ErrMsg or p2ErrMsg

            -- Would be kinda unfair
            if not fixed or autogen or endless then
                label:settext("❌ DiscordLeaderboard: Unsupported Course Type.")
                errLabel:settext("Autogen or Endless course")
                return
            end


            local botURL, APIKey = readURLandKey(player)
            if botURL == nil and APIKey == nil then
                label:settext("❌ DiscordLeaderboard: Invalid Data.")
                errLabel:settext("Your INI file is missing or invalid.")
                return
            end

            -- Doesn't return true for courses, but I can use everything else lol
            local partValid, allValid = ValidForGrooveStats(player)
            allValid = true
            local failed = {}
            for i, valid in ipairs(partValid) do
                if i ~= 3 and not valid then
                    allValid = false
                    table.insert(failed, invalidMapping[i] or ("Unknown error (check " .. tostring(i) .. ")"))
                end
            end

            if allValid then
                label:settext("DiscordLeaderboard: Submitting…")
                errLabel:settext("")
            else
                label:settext("❌ DiscordLeaderboard: Invalid Score.")
                errLabel:settext(table.concat(failed, "\n"))
                return
            end

            -- Different day different data
            local data = CourseResultData(player, APIKey, style, gameMode)

            -- Use chunked sending for potentially large data
            sendDataInChunks(data, botURL, function(code, body)
                if code == 200 then
                    label:settext("✔ DiscordLeaderboard: Submitted!")
                else
                    label:settext("❌ DiscordLeaderboard: Submission Failed.")
                    errLabel:settext("Error: " .. tostring(code) .. ". Response: " .. tostring(body))
                end
             end)
        end
    end,
    LoadFont("Common Normal") .. {
        Name = "ACSubmitP1",
        InitCommand = function(self)
            self:xy(10, 50):zoom(0.6):halign(0):valign(0)
            self:settext("")
        end
    },
    LoadFont("Common Normal") .. {
        Name = "ACSubmitP2",
        InitCommand = function(self)
            self:xy(_screen.w - 10, 50):zoom(0.6):halign(1):valign(0)
            self:settext("")
        end
    },
    LoadFont("Common Normal") .. {
        Name = "ACErrorP1",
        InitCommand = function(self)
            self:xy(10, 64):zoom(0.5):halign(0):valign(0)
            self:settext("")
            self:diffusecolor({ 1, 1, 1, 1 })
        end
    },
    LoadFont("Common Normal") .. {
        Name = "ACErrorP2",
        InitCommand = function(self)
            self:xy(_screen.w - 10, 64):zoom(0.5):halign(1):valign(0)
            self:settext("")
            self:diffusecolor({ 1, 1, 1, 1 })
        end
    },
}

-- This has been borrowed from ArrowCloud Blue Shift Module
-- that has been based on this module actually lol
-- https://arrowcloud.dance/
u["ScreenTitleMenu"] = Def.ActorFrame {
    InitCommand = function(self)
        self:xy(SCREEN_LEFT + 8, SCREEN_TOP + 50):zoom(0.8)
    end,
    ModuleCommand = function(self)
        self:queuecommand("CheckConnection")
    end,

    -- Perform the auth check.
    CheckConnectionCommand = function(self)
        local bmt = self:GetChild("Status")
        local errMsg = self:GetChild("ErrorMessage")
        if not bmt then return end

        -- start with a neutral label while checking
        bmt:settext("DiscordLeaderboard: checking…")

        -- Hit the hello-world endpoint (root) without auth headers.
        local url = normalizeBotURL(botURL) .. "/hello"
        NETWORK:HttpRequest {
            url = url,
            method = "GET",
            connectTimeout = 6,
            transferTimeout = 6,
            onResponse = function(response)
                -- Treat HTTP 200 as success; anything else (including errors) as failure.
                local ok = false
                if type(response) == "table" and response.statusCode == 200 then
                    ok = true
                end
                -- Log details safely (truncate body, avoid secrets)
                local status = response and response.statusCode or "(nil)"
                local err = response and response.error and ToEnumShortString(response.error) or nil
                local body = response and response.body or ""
                if type(body) ~= "string" then body = tostring(body) end
                if #body > 256 then body = body:sub(1, 256) .. "…" end

                local decoded = JsonDecode((response and response.body) or "")
                local versionReceived = decoded and decoded.status or nil

                if versionReceived ~= version then
                    ok = false
                    err = "Mismatch"
                end

                debugPrint("Hello-check: status=" ..
                    tostring(status) .. (err and (" error=" .. err) or "") .. " body=" .. body)

                if ok then
                    bmt:settext("✔ DiscordLeaderboard")
                else
                    bmt:settext("❌ DiscordLeaderboard")
                    if err == "Blocked" then
                        errMsg:settext("Host not configured in Preferences.ini\nAdd " ..
                            normalizeBotHost(botURL) .. " to HttpAllowHosts")
                    elseif err == "Mismatch" then
                        errMsg:settext("Version mismatch! Module version: " ..
                            version .. ", expected: " .. versionReceived)
                    else
                        errMsg:settext("Error connecting to bot: " .. (err or "Unknown error"))
                    end
                end
            end
        }
    end,

    -- The text node we update
    LoadFont("Common Normal") .. {
        Name = "Status",
        InitCommand = function(self)
            self:halign(0)
            self:settext("DiscordLeaderboard")
        end
    },

    LoadFont("Common Normal") .. {
        Name = "ErrorMessage",
        InitCommand = function(self)
            self:xy(0, 24):halign(0)
            self:zoom(0.6)
            self:settext("")
        end
    }
}

return u
