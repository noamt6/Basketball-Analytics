# Israeli Basketball Super League Analytics (2023-2024)

This project is a **comprehensive data analysis** of the 2023-2024 Israeli Basketball Super League season. It combines **SQL-based database management** with **Python data exploration** to provide deep insights into player and team performance.

## Key Features
* **Advanced Metrics**: Calculation of professional statistics such as **Assist-to-Turnover ratios** and **Per 36 Minutes** performance.
* **Shooting Efficiency**: Detailed analysis of **player shooting percentages** and offensive productivity across the league.
* **Positional Analysis**: Benchmarking performance trends based on **player positions** (Guards, Forwards, Centers).
* **Team Comparison**: Statistical evaluation of teams in categories like **offensive rebounding**, **three-point accuracy**, and **total points**.
* **Experience Correlation**: Studying the relationship between **player tenure** and on-court impact.

## Project Structure
* **Basketball Analytics.ipynb**: The main Jupyter Notebook containing data cleaning, calculations, and visualizations.
* **VIEWS.sql**: SQL scripts defining the logic for relational database views used in the analysis.
* **Datasets**: Various CSV files containing raw data for Players, Teams, and Season Stats.
* **Analysis Outputs**: Processed data files reflecting the results of SQL and Python analytical queries.



## Tech Stack
* **SQL**: Database design, data aggregation, and complex view creation.
* **Python (Jupyter Notebook)**: Data manipulation, mathematical modeling, and visualization.
* **Excel/CSV**: Data storage and interchange format.

## How to Run
1. Ensure **Python 3.x** and **Jupyter Notebook** are installed.
2. Keep all **CSV files** in the same directory as the notebook to ensure data loading works correctly.
3. Open your terminal in the project folder and run:
   ```bash
   jupyter notebook "Basketball Analytics.ipynb"
