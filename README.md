# 📈 Stock Market Simulator with Algorithmic Trading

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Flask](https://img.shields.io/badge/flask-3.0.0-red)
![License](https://img.shields.io/badge/license-MIT-green)

A web-based platform for virtual stock trading with real-time data and customizable algorithmic strategies, designed for finance education and strategy testing.

![Dashboard Screenshot](https://i.imgur.com/placeholder-dashboard.png)

## ✨ Key Features

- **Real-time Data**: 30-min updated prices via Alpha Vantage API
- **Virtual Portfolio**: Track P/L with color-coded performance metrics
- **Algorithmic Trading**: 5-minute candle pattern detection (1-5% thresholds)
- **News Integration**: Market context from NewsAPI
- **Educational Tools**: Jupyter Notebook integration for strategy development

## 🛠️ Technology Stack

| Component       | Technology |
|----------------|------------|
| Frontend       | Bootstrap 5, Chart.js |
| Backend        | Python 3.11, Flask 3.0 |
| Database       | SQLite3 (SQLAlchemy ORM) |
| APIs           | Alpha Vantage, NewsAPI |
| Deployment     | PythonAnywhere/AWS Lightsail |

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Alpha Vantage API key (free tier)
- NewsAPI key (optional)

### Installation
```bash
# Clone repository
git clone https://github.com/yourusername/stock-market-simulator.git
cd stock-market-simulator

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
echo "ALPHA_VANTAGE_API_KEY=your_key_here" > .env
echo "NEWS_API_KEY=your_key_here" >> .env

# Initialize database
flask shell
>>> from app import db
>>> db.create_all()
>>> exit()

# Run application
flask run --host=0.0.0.0 --port=5000
