local u = {}

u["ScreenEvaluationNonstop"] = Def.ActorFrame {
    ModuleCommand=function(self)

        local course = GAMESTATE:GetCurrentCourse()
        local dir = course:GetCourseDir()

        local hash = BinaryToHex(CRYPTMAN:SHA1File(dir)):sub(1, 16)

        SCREENMAN:SystemMessage(hash)





    end
}


return u


--
GetAllTrails()
return: { Trail }
Returns a table of all the Trails in the Course.

GetArtists()
return: { string }
Returns an array with all the artists in the Trail.

GetLengthSeconds()
return: float
Returns the length of this Trail in seconds.

GetMeter()
return: int
Returns the Trail's difficulty rating.

GetTrailEntries()
return: { TrailEntry }
Returns a table of TrailEntry items.


GetSteps()
return: Steps
Returns the Steps used in this TrailEntry. 

----> GetMeter() from steps