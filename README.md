# Basel Jabour — Professional Projects

A responsive portfolio for financial risk analytics and applied data-science work, designed to present professional background, model evidence, operating choices, and limitations clearly.

**Live site:** [bjabour.github.io/professional-projects](https://bjabour.github.io/professional-projects/)

## Featured projects

### Early Alzheimer Diagnosis

An interactive brain-MRI screening case study comparing deterministic and CNN-based paths before selecting a two-stage multilayer perceptron. The selected operating point reached 96.82% observed test sensitivity with a 3.18% missed-dementia rate. These are development estimates from an image-classification workflow, not a clinical diagnosis or medical-device claim.

### Electricity Usage & Alert Forecast

A dual cubic B-spline workflow translating temperature, humidity, and weekend status into expected household electricity use and critical-demand alert probability. Cross-validation reached 20.43 kWh² MSE for usage and 0.461 log loss for alerts.

### Housing Price & Distress Prediction

Two linked models answer separate questions: OLS estimates a home's price, while calibrated LDA ranks its probability of a distressed sale. The price model reached 31.6 kEUR cross-validated RMSE, while the top 20% risk queue captured 24 of 47 known distressed cases.

## Site structure

- `index.html` — portfolio landing page
- `about.html` — professional background, company experience, risk-management methods, research and data-science skills, and technical toolkit
- `early-alzheimer-diagnosis.html` — self-contained healthcare project deck
- `electricity-usage-alert-forecast.html` — self-contained energy project deck
- `distressed-housing-investment-screen.html` — self-contained real-estate project deck
- `assets/favicon.svg` — site mark

## Local preview

Open `index.html` directly in a browser. No build step or external dependency is required.
