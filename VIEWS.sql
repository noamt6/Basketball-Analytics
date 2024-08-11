---Basketball_Analytics---
---------VIEWS------------
/*
This document contains SQL views used for analyzing basketball statistics from the Israeli Basketball Super League's 2023-2024 season.
Each view is designed to provide insights into different aspects of team and player performance.
*/

USE Basketball_Analytics

GO

-- 1. Avg_Team_Offensive_Points
CREATE VIEW Avg_Team_Offensive_Points 
AS
SELECT 
    CONCAT_WS('-', TD.TeamName, TD.City) AS FullTeamName,
    ROUND(CAST(TS.PTS AS FLOAT) / NULLIF(TS.GP, 0), 2) AS Avg_Points
FROM 
    Team_Stats TS JOIN Teams_Details TD 
		ON TS.TeamId = TD.TeamID

GO

-- 2. Avg_Team_Three_Point
CREATE VIEW Avg_Team_Three_Point 
AS
SELECT 
    CONCAT_WS('-', TD.TeamName, TD.City) AS FullTeamName,
    ROUND(CAST(TS.[3PA] AS FLOAT) / NULLIF(TS.GP, 0), 2) AS Avg_3PA,
    ROUND(CAST(TS.[3PM] AS FLOAT) / NULLIF(TS.GP, 0), 2) AS Avg_3PM,
    TS.[3P%]
FROM 
    Team_Stats TS JOIN Teams_Details TD 
		ON TS.TeamId = TD.TeamID

GO

-- 3.Avg_Team_Rebounds
CREATE VIEW Avg_Team_Rebounds 
AS
SELECT 
    CONCAT_WS('-', TD.TeamName, TD.City) AS FullTeamName,
    ROUND(CAST(TS.DREB AS FLOAT) / NULLIF(TS.GP, 0), 2) AS Avg_Defensive_Rebounds,
    ROUND(CAST(TS.OREB AS FLOAT) / NULLIF(TS.GP, 0), 2) AS Avg_Offensive_Rebounds,
    ROUND(CAST(TS.REB AS FLOAT) / NULLIF(TS.GP, 0), 2) AS Avg_Rebounds
FROM 
    Team_Stats TS JOIN Teams_Details TD 
		ON TS.TeamId = TD.TeamID

GO

-- 4.Team_Stats_Comparison
CREATE VIEW Team_Stats_Comparison 
AS
SELECT 
    CONCAT_WS('-', TD.TeamName, TD.City) AS FullTeamName,
    ROUND(CAST(TS.PTS AS FLOAT) / NULLIF(TS.GP, 0), 2) AS Avg_Points,
    ROUND(CAST(TS.AST AS FLOAT) / NULLIF(TS.GP, 0), 2) AS Avg_Asists,
    ROUND(CAST(TS.REB AS FLOAT) / NULLIF(TS.GP, 0), 2) AS Avg_Rebounds,
    ROUND(CAST(TS.BLK AS FLOAT) / NULLIF(TS.GP, 0), 2) AS Avg_Blocks,
    ROUND(CAST(TS.TOV AS FLOAT) / NULLIF(TS.GP, 0), 2) AS Avg_Turnovers,
    ROUND(CAST(TS.PIR AS FLOAT) / NULLIF(TS.GP, 0), 2) AS Avg_Pir
FROM 
    Team_Stats TS JOIN Teams_Details TD 
		ON TS.TeamId = TD.TeamID

GO

-- 5.Avg_Player_Points
CREATE VIEW Avg_Player_Points 
AS
SELECT 
    CONCAT_WS('-', PD.FirstName, PD.LastName) AS FullPlayerName,
    ROUND(CAST(PS.PTS AS FLOAT) / NULLIF(PS.GP, 0), 2) AS Avg_Points
FROM 
    Player_Stats PS JOIN Players_Details PD 
		ON PS.PlayerId = PD.PlayerId

GO

-- 6.Player_Shooting_Performance
CREATE VIEW Player_Shooting_Performance 
AS
SELECT 
    CONCAT_WS('-', PD.FirstName, PD.LastName) AS FullPlayerName,
    PS.[3P%], 
    PS.[FG%], 
    PS.[FT%]
FROM 
    Player_Stats PS JOIN Players_Details PD 
		ON PS.PlayerId = PD.PlayerId

GO

-- 7.Per36_stats
CREATE VIEW Per_36
AS
SELECT
    CONCAT_WS('-', PD.FirstName, PD.LastName) AS FullPlayerName,
    ROUND((CAST(PS.PTS AS FLOAT) / NULLIF(PS.[MIN], 0)) * 36, 2) AS Per_36_Points,
    ROUND((CAST(PS.AST AS FLOAT) / NULLIF(PS.[MIN], 0)) * 36, 2) AS Per_36_Assists,
    ROUND((CAST(PS.REB AS FLOAT) / NULLIF(PS.[MIN], 0)) * 36, 2) AS Per_36_Rebounds
FROM 
    Player_Stats PS JOIN Players_Details PD 
		ON PS.PlayerId = PD.PlayerId

GO

-- 8.Avg_Points_Vs_Avg_Minutes
CREATE VIEW Avg_Points_Vs_Avg_Minutes 
AS
SELECT 
    CONCAT_WS('-', PD.FirstName, PD.LastName) AS FullPlayerName,
    ROUND(CAST(PS.[MIN] AS FLOAT) / NULLIF(PS.GP, 0), 2) AS Avg_Minutes,
    ROUND(CAST(PS.PTS AS FLOAT) / NULLIF(PS.GP, 0), 2) AS Avg_Points
FROM 
    Player_Stats PS JOIN Players_Details PD 
		ON PS.PlayerId = PD.PlayerId

GO

-- 9.Asists_To_Turnovers_Ratio
CREATE VIEW Asists_To_Turnovers_Ratio 
AS
SELECT 
    CONCAT_WS('-', PD.FirstName, PD.LastName) AS FullPlayerName,
    ROUND(CAST(PS.AST AS FLOAT) / NULLIF(CAST(PS.TOV AS FLOAT), 0), 2) AS Ast_To_Tov_Ratio
FROM 
    Player_Stats PS JOIN Players_Details PD 
		ON PS.PlayerId = PD.PlayerId

GO

-- 10.Player_Tenure_Performance
CREATE VIEW Player_Tenure_Performance 
AS
SELECT 
    CONCAT_WS('-', PD.FirstName, PD.LastName) AS FullPlayerName,
    R.YearsOnTeam,
    ROUND(CAST((PS.PTS) AS FLOAT) / NULLIF((PS.GP), 0), 2) AS Avg_Points,
    ROUND(CAST((PS.REB) AS FLOAT) / NULLIF((PS.GP), 0), 2) AS Avg_Rebounds,
    ROUND(CAST((PS.AST) AS FLOAT) / NULLIF((PS.GP), 0), 2) AS Avg_Assists
FROM 
    Player_Stats PS JOIN Players_Details PD 
		ON PS.PlayerId = PD.PlayerId
    JOIN ROSTER R 
		ON PD.PlayerId = R.PlayerId

GO

-- 11.Position_Performance
CREATE VIEW Position_Performance 
AS
SELECT 
    CONCAT_WS('-', PD.FirstName, PD.LastName) AS FullPlayerName,
    R.Position,
    ROUND(CAST(PS.PTS AS FLOAT) / NULLIF(PS.GP, 0), 2) AS Avg_Points,
    ROUND(CAST(PS.REB AS FLOAT) / NULLIF(PS.GP, 0), 2) AS Avg_Rebounds,
    ROUND(CAST(PS.AST AS FLOAT) / NULLIF(PS.GP, 0), 2) AS Avg_Assists
FROM 
    Player_Stats PS JOIN Players_Details PD 
		ON PS.PlayerId = PD.PlayerId
    JOIN ROSTER R 
		ON PD.PlayerId = R.PlayerId

