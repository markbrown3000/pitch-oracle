# Pitch Oracle: Match Predictor (web)

Home, draw and away chances for every match in 22 European leagues, plus ATP and WTA tennis. The whole app is `index.html`, with the data built in. Open it in any browser, including Safari on iPhone.

## Keeping it up to date
A GitHub Actions job (`.github/workflows/update-data.yml`) downloads the latest results and fixtures from football-data.co.uk into `data/` every 3 hours. The page reads those files each time it's opened, then rebuilds the tables and picks.

## Tennis
The Tennis tab shows ATP and WTA singles picks, live chances, tournament winner chances and a track record. Its data is `data/tennis.json`, rebuilt every hour by a GitHub Actions job (`.github/workflows/update-tennis.yml`): it reads match prices and results from Kalshi and Polymarket and runs the same model as the Claude version (`tools/tennis.js`). Player ratings start from `data/tennis_elo_*.csv` (Tennis Abstract) and move with every result.

## On an iPhone
Open the link in Safari, tap **Share**, then **Add to Home Screen**. It then opens full-screen like an app.

Data: football-data.co.uk. For fun, not for staking money.
