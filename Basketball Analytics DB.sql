---- PROJECT 1 -----
-- Noam Tondovsky --

USE master

GO

IF EXISTS
	(SELECT * FROM SYSDATABASES WHERE NAME = 'Basketball_Analytics')
		DROP DATABASE Basketball_Analytics
GO

CREATE DATABASE Basketball_Analytics

GO

USE Basketball_Analytics

/*
This database is built for basketball scouts and analytics experts,
primarily focusing on the Israeli basketball league,though it can be adapted for other leagues in Europe.
It includes details and stats for all teams in the league.
Maccabi Tel Aviv is presented as an example to illustrate the type of detailed player information and statistics available.
Users can expand this to include more teams for a broader comparative analysis of players and team statistics
*/

GO

--------Table 1-------
----------------------
-----Team_Details-----

-- Stores basic information about each basketball team in the league --

CREATE TABLE Teams_Details
(
				 TeamID VARCHAR(3) ,
				 TeamName VARCHAR(20) NOT NULL , 
				 City VARCHAR(20) NOT NULL ,
				 MainSponsor VARCHAR(40) ,
				 Arena VARCHAR(30) NOT NULL 

-- CONSTRAINTS --
CONSTRAINT Team_Details_TeamId_PK PRIMARY KEY(TeamId),
CONSTRAINT Team_Details_MainSponsor_UK UNIQUE(MainSponsor)
)

GO

--------Table 2-------
----------------------
----Player_Details----

-- Stores personal information about each player --

CREATE TABLE Players_Details
(
				 PlayerId INT IDENTITY (100,1) ,
				 FirstName VARCHAR(10) NOT NULL , 
				 LastName VARCHAR(15) NOT NULL ,
				 Nationality VARCHAR(15) NOT NULL ,
				 BirthDate DATE NOT NULL ,
				 Height DECIMAL(5, 2) NOT NULL, 
				 TeamId VARCHAR(3)

-- CONSTRAINTS --
CONSTRAINT Players_Details_PlayerId_PK PRIMARY KEY(PlayerId) ,
CONSTRAINT Players_Details_BirthDate_CK CHECK (BirthDate < GETDATE()) ,
CONSTRAINT Player_Details_Height_CK CHECK (Height BETWEEN 1.50 AND 2.30) ,
CONSTRAINT Players_Details_TeamId_FK FOREIGN KEY (TeamId) REFERENCES Teams_Details(TeamID)
)

GO

--------Table 3-------
----------------------
--------Roster--------

-- Contains current season roster information for each team --

CREATE TABLE Roster
(
				 PlayerId INT ,
				 Position VARCHAR(2) NOT NULL , 
				 JerseyNumber INT NOT NULL ,
				 YearsOnTeam INT NOT NULL ,
				 TeamID VARCHAR(3) , 

-- CONSTRAINTS --
CONSTRAINT Roster_PlayerId_PK PRIMARY KEY(PlayerId) ,
CONSTRAINT Roster_PlayerId_FK FOREIGN KEY(PlayerId) REFERENCES Players_Details(PlayerId) ,
CONSTRAINT Roster_Position_CK CHECK (Position IN ('PG','SG','SF','PF','C')) ,
CONSTRAINT Roster_JerseyNumber_CK CHECK (JerseyNumber BETWEEN 0 AND 99) ,
CONSTRAINT Roster_TeamID_FK FOREIGN KEY(TeamID) REFERENCES Teams_Details(TeamID) 
)

GO

--------Table 4-------
----------------------
-----Player_Stats-----

-- Holds total and seasonal stats for each player --
-- This data enables the calculation of averages and supports extensive statistical analyses to evaluate player performance --

CREATE TABLE Player_Stats
(				 
			     PlayerId INT ,
				 GP INT NOT NULL ,        -- Games played
				 [MIN] INT NOT NULL ,     -- Minutes played
				 PTS INT NOT NULL ,		  -- Points scored
				 FGM INT NOT NULL ,       -- Field Goals Made
				 FGA INT NOT NULL ,       -- Field Goals Attempted
				 [FG%] FLOAT NOT NULL ,   -- Field Goals Percentage
				 [3PM] INT NOT NULL ,     -- 3 Point Field Goals Made
				 [3PA] INT NOT NULL ,	  -- 3 Point Field Goals Attempted
				 [3P%] FLOAT NOT NULL ,   -- 3 Point Field Goals Percentage
				 FTM INT NOT NULL ,		  -- Free Throws Made
				 FTA INT NOT NULL ,       -- Free Throws Attempted
				 [FT%] FLOAT NOT NULL ,   -- Free Throws Percentage
				 OREB INT NOT NULL ,      -- Offensive Rebounds
				 DREB INT NOT NULL ,      -- Defensive Rebounds
				 REB INT NOT NULL ,       -- Rebounds
				 AST INT NOT NULL ,       -- Assists
				 TOV INT NOT NULL ,		  -- Turnovers 
				 STL INT NOT NULL ,       -- Steals
				 BLK INT NOT NULL ,       -- Blocks
				 PIR INT NOT NULL ,       -- Performance Index Rating

-- CONSTRAINTS --
CONSTRAINT Player_Stats_PlayerId_PK PRIMARY KEY(PlayerId),
CONSTRAINT Player_Stats_PlayerId_FK FOREIGN KEY(PlayerId) REFERENCES Players_Details(PlayerId),
CONSTRAINT Player_Stats_GP_CK CHECK (GP >= 0) ,
CONSTRAINT Player_Stats_MIN_CK CHECK ([MIN] >= 0) ,
CONSTRAINT Player_Stats_PTS_CK CHECK (PTS >= 0) ,
CONSTRAINT Player_Stats_FGM_CK CHECK (FGM >= 0) ,
CONSTRAINT Player_Stats_FGA_CK CHECK (FGA >= FGM AND FGA >= 0) ,
CONSTRAINT Player_Stats_3PM_CK CHECK ([3PM] >= 0) ,
CONSTRAINT Player_Stats_3PA_CK CHECK ([3PA] >= [3PM] AND [3PA] >= 0) ,
CONSTRAINT Player_Stats_FTM_CK CHECK (FTM >= 0) ,
CONSTRAINT Player_Stats_FTA_CK CHECK (FTA >= FTM AND FTA >= 0) ,
CONSTRAINT Player_Stats_OREB_CK CHECK (OREB >= 0) ,
CONSTRAINT Player_Stats_DREB_CK CHECK (DREB >= 0) ,
CONSTRAINT Player_Stats_REB_CK CHECK (REB >= 0) ,
CONSTRAINT Player_Stats_AST_CK CHECK (AST >= 0) ,
CONSTRAINT Player_Stats_TOV_CK CHECK (TOV >= 0) ,
CONSTRAINT Player_Stats_STL_CK CHECK (STL >= 0) ,
CONSTRAINT Player_Stats_BLK_CK CHECK (BLK >= 0) ,
CONSTRAINT Player_Stats_PIR_CK CHECK (PIR >= 0) ,
CONSTRAINT Player_Stats_FGP_CK CHECK ([FG%] BETWEEN 0 AND 100) , 
CONSTRAINT Player_Stats_3PP_CK CHECK ([3P%] BETWEEN 0 AND 100) ,
CONSTRAINT Player_Stats_FTP_CK CHECK ([FT%] BETWEEN 0 AND 100)   
)

GO

--------Table 5-------
----------------------
------Team_Stats------

-- Keeps total and seasonal stats for each team -- 
-- This data enables the calculation of averages and supports extensive statistical analyses to evaluate team performance --

CREATE TABLE Team_Stats
(
				 TeamId VARCHAR(3) ,
				 GP INT NOT NULL ,        -- Games played
				 [MIN] INT NOT NULL ,     -- Minutes played
				 PTS INT NOT NULL ,		  -- Points scored
				 FGM INT NOT NULL ,       -- Field Goals Made
				 FGA INT NOT NULL ,       -- Field Goals Attempted
				 [FG%] FLOAT NOT NULL ,   -- Field Goals Percentage
				 [3PM] INT NOT NULL ,     -- 3 Point Field Goals Made
				 [3PA] INT NOT NULL ,	  -- 3 Point Field Goals Attempted
				 [3P%] FLOAT NOT NULL ,   -- 3 Point Field Goals Percentage
				 FTM INT NOT NULL ,		  -- Free Throws Made
				 FTA INT NOT NULL ,       -- Free Throws Attempted
				 [FT%] FLOAT NOT NULL ,   -- Free Throws Percentage
				 OREB INT NOT NULL ,      -- Offensive Rebounds
				 DREB INT NOT NULL ,      -- Defensive Rebounds
				 REB INT NOT NULL ,       -- Rebounds
				 AST INT NOT NULL ,       -- Assists
				 TOV INT NOT NULL ,		  -- Turnovers 
				 STL INT NOT NULL ,       -- Steals
				 BLK INT NOT NULL ,       -- Blocks
				 PIR INT NOT NULL ,       -- Performance Index Rating

-- CONSTRAINTS --
CONSTRAINT Team_Stats_TeamId_PK PRIMARY KEY (TeamId) ,
CONSTRAINT Team_Stats_TeamId_FK FOREIGN KEY (TeamId) REFERENCES Teams_Details (TeamID) ,
CONSTRAINT Team_Stats_GP_CK CHECK (GP >= 0) ,
CONSTRAINT Team_Stats_MIN_CK CHECK ([MIN] >= 0) ,
CONSTRAINT Team_Stats_PTS_CK CHECK (PTS >= 0) ,
CONSTRAINT Team_Stats_FGM_CK CHECK (FGM >= 0) ,
CONSTRAINT Team_Stats_FGA_CK CHECK (FGA >= FGM AND FGA >= 0) ,
CONSTRAINT Team_Stats_3PM_CK CHECK ([3PM] >= 0) ,
CONSTRAINT Team_Stats_3PA_CK CHECK ([3PA] >= [3PM] AND [3PA] >= 0) ,
CONSTRAINT Team_Stats_FTM_CK CHECK (FTM >= 0) ,
CONSTRAINT Team_Stats_FTA_CK CHECK (FTA >= FTM AND FTA >= 0) ,
CONSTRAINT Team_Stats_OREB_CK CHECK (OREB >= 0) ,
CONSTRAINT Team_Stats_DREB_CK CHECK (DREB >= 0) ,
CONSTRAINT Team_Stats_REB_CK CHECK (REB >= 0) ,
CONSTRAINT Team_Stats_AST_CK CHECK (AST >= 0) ,
CONSTRAINT Team_Stats_TOV_CK CHECK (TOV >= 0) ,
CONSTRAINT Team_Stats_STL_CK CHECK (STL >= 0) ,
CONSTRAINT Team_Stats_BLK_CK CHECK (BLK >= 0) ,
CONSTRAINT Team_Stats_PIR_CK CHECK (PIR >= 0) ,
CONSTRAINT Team_Stats_FGP_CK CHECK ([FG%] BETWEEN 0 AND 100) ,  
CONSTRAINT Team_Stats_3PP_CK CHECK ([3P%] BETWEEN 0 AND 100) ,	
CONSTRAINT Team_Stats_FTP_CK CHECK ([FT%] BETWEEN 0 AND 100)	
)

GO

------Team_Details------
------------------------
INSERT INTO Teams_Details (TeamId, TeamName, City, MainSponsor, Arena)
VALUES
    ('MTA', 'Maccabi', 'Tel Aviv', 'Playtika', 'Menora Mivtachim Arena') ,
    ('HTA', 'Hapoel', 'Tel Aviv', 'Shlomo Group', 'Shlomo Group Arena') ,
    ('IRG', 'Maccabi Ironi', 'Ramat Gan', 'A.E Business Entrepreneurship Ltd', 'Zisman Arena') ,
    ('EKA', 'Elitzur', 'Kiryat Ata', 'Lati', 'Remez Arena') ,
    ('INZ', 'Ironi', 'Nes Ziona', 'Motors', 'Lev Hamoshava Arena') ,
    ('HHF', 'Hapoel', 'Haifa', 'Shoval' , 'Romema Arena') , 
    ('HBS', 'Hapoel', 'Beer Sheva/Dimona', 'Altshuler Shaham', 'The Shell Arena') ,
    ('HHL', 'Hapoel', 'Holon', 'Moreinvest', 'Toto Arena') ,
    ('HAF', 'Hapoel', 'Afula', 'Blue-Sky', 'The City Sports Arena Of Afula') ,
    ('BNH', 'Bnei', 'Herzliya', 'Ofek Dist', 'Hayovel Arena') ,
    ('HGE', 'Hapoel', 'Galil Elyon', 'Nofar Energy', 'Kfar Blum Arena') ,
    ('HJM', 'Hapoel', 'Jerusalem', 'Bank Yahav', 'Pais Arena') ,
    ('HEL', 'Hapoel', 'Eilat', 'Yossi Avrahami', 'Begin Arena')

GO

------Player_Details------
--------------------------
INSERT INTO Players_Details (FirstName, LastName, Nationality, BirthDate, Height,TeamId)
VALUES
    ('Antonius', 'Cleveland', 'USA', '1994-02-02', 1.96, 'MTA'),
    ('James', 'Webb', 'USA', '1993-08-19', 2.06, 'MTA'),
    ('Lorenzo', 'Brown', 'USA/Spain', '1990-08-26', 1.96, 'MTA'),
    ('Wade', 'Baldwin', 'USA', '1996-03-29', 1.93, 'MTA'),
    ('Rafi', 'Menco', 'Israel', '1994-03-05', 2.00, 'MTA'),
    ('Roman', 'Sorkin', 'Israel', '1996-08-11', 2.08, 'MTA'),
    ('Omer', 'Mayer', 'Israel', '2006-10-08', 1.91, 'MTA'),
    ('John', 'Dibartolomeo', 'USA/Israel', '1991-06-20', 1.83, 'MTA'),
    ('Jasiel', 'Rivero', 'Cuba', '1993-10-31', 2.06, 'MTA'),
    ('Jake', 'Cohen', 'USA/Israel', '1990-09-25', 2.10, 'MTA'),
    ('Josh', 'Nebo', 'USA', '1997-07-17', 2.06, 'MTA'),
    ('Tamir', 'Blatt', 'Israel', '1997-05-04', 1.83, 'MTA'),
    ('Bonzie', 'Colson', 'USA', '1996-01-12', 1.98, 'MTA'),
    ('Joe', 'Thomasson', 'USA', '1993-08-16', 1.93, 'MTA')

GO


----------Roster----------
--------------------------
INSERT INTO Roster( PlayerId, Position, JerseyNumber, YearsOnTeam, TeamID)
VALUES
	(100, 'SF' , 1 , 1 , 'MTA') ,
    (101, 'PF' , 3 , 1 , 'MTA') ,
    (102, 'PG' , 4 , 2 , 'MTA') ,
    (103, 'SG' , 5 , 2 , 'MTA') ,
    (104, 'SF' , 8 , 2 , 'MTA') ,
    (105, 'C'  , 9 , 3 , 'MTA') ,
	(106, 'PG' , 17 , 1 ,'MTA') ,
    (107, 'SG' , 12 , 7 ,'MTA') ,
    (108, 'C'  , 14 , 1 ,'MTA') ,
    (109, 'PF' , 15 , 8 ,'MTA') ,
    (110, 'C'  , 32 , 2 ,'MTA') ,
    (111, 'PG' , 45 , 1 ,'MTA') ,
    (112, 'SF' , 50 , 2 ,'MTA') ,
    (113, 'SG' , 24 , 1 ,'MTA')

GO

-------Player_Stats-------
--------------------------
INSERT INTO Player_Stats (PlayerId, GP, [MIN], PTS, FGM, FGA, [FG%], [3PM], [3PA], [3P%], FTM, FTA, [FT%], OREB, DREB, REB, AST, TOV, STL, BLK, PIR)
VALUES
    (100, 14, 267, 116, 36, 54, 66.67, 10, 27, 37.04, 14, 19, 73.68, 8, 43, 51, 19, 17, 16, 7, 149) ,
    (101, 11, 226, 86, 14, 20, 70.00, 16, 45, 35.56, 10, 12, 83.33, 17, 44, 61, 7, 4, 6, 5, 111) ,
    (102, 12, 270, 137, 36, 77, 46.75, 17, 41, 41.46, 14, 20, 70.00, 7, 29, 36, 59, 28, 13, 1, 146) ,
    (103, 16, 358, 194, 51, 97, 52.58, 8, 55, 14.55, 68, 78, 87.18, 6, 27, 33, 82, 46, 14, 6, 206) ,
    (104, 21, 463, 182, 43, 64, 67.19, 28, 90, 31.11, 12, 22, 54.55, 20, 86, 106, 21, 25, 17, 5, 186) ,
    (105, 20, 472, 320, 123, 181, 67.96, 11, 27, 40.74, 41, 64, 64.06, 54, 69, 123, 25, 38, 14, 19, 379) ,
    (106, 16, 190, 61, 12, 25, 48.00, 11, 35, 31.43, 4, 6, 66.67, 1, 21, 22, 25, 17, 4, 1, 40) ,
    (107, 20, 434, 184, 16, 27, 59.26, 44, 90, 48.89, 20, 25, 80.00, 22, 39, 61, 29, 12, 26, 0, 213) ,
    (108, 15, 291, 183, 65, 100, 65.00, 1, 3, 33.33, 50, 70, 71.43, 49, 48, 97, 13, 13, 8, 3, 269) ,
    (109, 24, 416, 126, 33, 48, 68.75, 9, 30, 30.00, 33, 37, 89.19, 20, 76, 96, 54, 22, 12, 8, 223) ,
    (110, 18, 374, 197, 79, 104, 75.96, 0, 0, 0.00, 39, 51, 76.47, 33, 76, 109, 9, 22, 8, 7, 278) ,
    (111, 21, 461, 186, 18, 30, 60.00, 41, 131, 31.30, 27, 31, 87.10, 9, 32, 41, 132, 51, 11, 0, 219) ,
    (112, 13, 326, 153, 37, 71, 52.11, 13, 41, 31.71, 40, 45, 88.89, 10, 45, 55, 6, 9, 15, 4, 160) ,  
    (113, 9, 182, 62, 12, 28, 42.86, 11, 24, 45.83, 5, 5, 100.00, 1, 21, 22, 28, 13, 6, 3, 67)

GO

-------Team_Stats-------
------------------------
INSERT INTO Team_Stats (TeamId, GP, [MIN], PTS, FGM, FGA, [FG%], [3PM], [3PA], [3P%], FTM, FTA, [FT%], OREB, DREB, REB, AST, STL, BLK, TOV, PIR)
VALUES
    ('MTA', 24, 960, 2202, 801, 1580, 50.7, 223, 645, 34.6, 377, 485, 77.7, 296, 700, 996, 512, 173, 69, 329, 2709),
    ('HTA', 22, 880, 2067, 741, 1456, 50.9, 177, 455, 38.9, 408, 554, 73.6, 232, 577, 809, 505, 176, 59, 246, 2514),
    ('IRG', 23, 920, 1946, 713, 1526, 46.7, 186, 528, 35.2, 334, 485, 68.9, 270, 623, 893, 405, 166, 41, 276, 2135),
    ('INZ', 23, 930, 1899, 658, 1456, 45.2, 179, 541, 33.1, 404, 564, 71.6, 271, 662, 933, 410, 142, 76, 315, 2136),
    ('HHF', 23, 925, 1899, 667, 1466, 45.5, 233, 642, 36.3, 332, 417, 79.6, 214, 579, 793, 409, 152, 64, 308, 2020),
    ('HAF', 23, 935, 1874, 690, 1600, 43.1, 163, 555, 29.4, 331, 491, 67.4, 327, 647, 974, 408, 183, 69, 292, 2036),
    ('EKA', 22, 885, 1819, 652, 1501, 43.4, 181, 544, 33.3, 334, 490, 68.2, 299, 539, 839, 369, 201, 54, 260, 1980),
    ('HHL', 22, 880, 1810, 659, 1390, 47.4, 215, 583, 36.9, 277, 397, 69.8, 208, 564, 772, 466, 179, 65, 286, 2064),
    ('HBS', 22, 879, 1807, 647, 1466, 44.1, 204, 558, 36.6, 309, 419, 73.7, 265, 543, 808, 397, 145, 66, 294, 1905),
    ('BNH', 22, 880, 1792, 633, 1413, 44.8, 220, 633, 34.8, 306, 416, 73.6, 218, 592, 810, 383, 119, 81, 286, 2120),
    ('HJM', 22, 880, 1782, 629, 1415, 44.5, 217, 628, 34.6, 307, 423, 72.6, 263, 576, 839, 370, 154, 43, 273, 1925),
    ('HGE', 22, 895, 1781, 612, 1437, 42.6, 226, 627, 36.0, 331, 448, 73.9, 254, 572, 824, 415, 123, 36, 291, 1972),
    ('HEL', 22, 880, 1670, 592, 1415, 41.8, 178, 562, 31.7, 308, 397, 77.6, 222, 512, 734, 293, 152, 70, 263, 1633)

GO

