# Pitch Oracle: Match Predictor (web)

Home, draw and away chances for every match in 22 European leagues. The whole app is `index.html`, with the data built in. Open it in any browser, including Safari on iPhone.

## Keeping it up to date
A GitHub Actions job (`.github/workflows/update-data.yml`) downloads the latest results and fixtures from football-data.co.uk into `data/` every 3 hours. The page reads those files each time it's opened, then rebuilds the tables and picks.

## On an iPhone
Open the link in Safari, tap **Share**, then **Add to Home Screen**. It then opens full-screen like an app.

Data: football-data.co.uk. For fun, not for staking money.
