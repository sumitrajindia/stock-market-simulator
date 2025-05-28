import os
import time
import threading
from datetime import datetime, timezone
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import requests
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from datetime import datetime, timezone

# Add these imports at the top
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from datetime import datetime, timezone
from flask import Flask
import humanize

# Create custom filter
def timesince(dt):
    return humanize.naturaltime(datetime.now(timezone.utc) - dt)


# Load environment variables
load_dotenv()
NEWS_API_KEY = os.getenv('NEWS_API_KEY')

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stock_simulator.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Add the filter to Jinja2 environment
app.jinja_env.filters['timesince'] = timesince

# Alpha Vantage API configuration
ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY')
BASE_URL = 'https://www.alphavantage.co/query'
UPDATE_INTERVAL = 1800  # 30 minutes in seconds


# Initialize LoginManager (after app creation)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Models
# class User(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     username = db.Column(db.String(80), unique=True, nullable=False)
#     balance = db.Column(db.Float, default=10000.00)  # Starting balance

# Update User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(128))
    balance = db.Column(db.Float, default=10000.00)
    # ... rest of your User model ...

    @property
    def unread_notifications(self):
        return Notification.query.filter_by(user_id=self.id, read=False)
    
    notifications = db.relationship(
        'Notification', 
        backref='notification_user',  # Changed backref name
        lazy='dynamic',
        order_by='desc(Notification.timestamp)'
    )

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(100))
    price = db.Column(db.Float)
    last_updated = db.Column(db.DateTime)

class Watchlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('watchlist', lazy=True))
    stock = db.relationship('Stock', backref=db.backref('watchlist', lazy=True))

class Portfolio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'), nullable=False)
    quantity = db.Column(db.Float, default=0)
    average_price = db.Column(db.Float)
    user = db.relationship('User', backref=db.backref('portfolio', lazy=True))
    stock = db.relationship('Stock', backref=db.backref('portfolio', lazy=True))

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'), nullable=False)
    transaction_type = db.Column(db.String(4))  # 'BUY' or 'SELL'
    quantity = db.Column(db.Float)
    price = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('transactions', lazy=True))
    stock = db.relationship('Stock', backref=db.backref('transactions', lazy=True))

    # Add after your existing models
class Algorithm(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'), nullable=False)
    active = db.Column(db.Boolean, default=True)
    threshold = db.Column(db.Float, default=1.0)  # 1% threshold
    user = db.relationship('User', backref=db.backref('algorithms', lazy=True))
    stock = db.relationship('Stock', backref=db.backref('algorithms', lazy=True))

class PriceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'), nullable=False)
    price = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    stock = db.relationship('Stock', backref=db.backref('price_history', lazy=True))

# class Notification(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
#     message = db.Column(db.String(200))
#     read = db.Column(db.Boolean, default=False)
#     timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))
#     user = db.relationship('User', backref=db.backref('notifications', lazy=True))

# Notification Model
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    message = db.Column(db.String(200))
    read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    # Remove the user relationship or rename the backref if needed

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Add login manager loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# @app.template_filter('timesince')
# def timesince_filter(dt):
#     if not dt:
#         return "Unknown time"
#     now = datetime.now(timezone.utc)
#     diff = now - dt
    
#     periods = [
#         ('year', 365*24*60*60),
#         ('month', 30*24*60*60),
#         ('day', 24*60*60),
#         ('hour', 60*60),
#         ('minute', 60)
#     ]
    
#     for period, seconds in periods:
#         value = diff.total_seconds() / seconds
#         if value >= 1:
#             return f"{int(value)} {period}{'s' if value > 1 else ''} ago"
    
#     return "just now"

@app.template_filter('timesince')
def timesince_filter(dt):
    if not dt or not hasattr(dt, 'timestamp'):
        return "just now"
    try:
        return humanize.naturaltime(datetime.now(timezone.utc) - dt)
    except:
        return dt.strftime('%Y-%m-%d %H:%M')



# Helper functions

def create_default_user():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                password_hash=generate_password_hash('admin'),
                balance=10000.00
            )
            db.session.add(admin)
            
            # Create sample notification
            from app import Notification
            notification = Notification(
                user=admin,
                message="Welcome to Stock Simulator!",
                read=False
            )
            db.session.add(notification)
            
            db.session.commit()
            print("Default admin user and notification created!")



def get_stock_price(symbol):
    """Fetch current stock price from Alpha Vantage"""
    try:
        params = {
            'function': 'GLOBAL_QUOTE',
            'symbol': symbol,
            'apikey': ALPHA_VANTAGE_API_KEY
        }
        response = requests.get(BASE_URL, params=params)
        data = response.json()
        
        if 'Global Quote' in data:
            price = float(data['Global Quote']['05. price'])
            return price
        return None
    except Exception as e:
        print(f"Error fetching price for {symbol}: {e}")
        return None

# def update_stock_prices():
#     """Update prices for all stocks in the database"""
#     with app.app_context():
#         stocks = Stock.query.all()
#         for stock in stocks:
#             new_price = get_stock_price(stock.symbol)
#             if new_price:
#                 stock.price = new_price
#                 stock.last_updated = datetime.utcnow()
#         db.session.commit()
#         print(f"Stock prices updated at {datetime.utcnow()}")

def schedule_price_updates():
    """Schedule periodic price updates"""
    while True:
        update_stock_prices()
        time.sleep(UPDATE_INTERVAL)

# Update your existing update_stock_prices function to record history
def update_stock_prices():
    """Update prices for all stocks in the database"""
    with app.app_context():
        stocks = Stock.query.all()
        for stock in stocks:
            new_price = get_stock_price(stock.symbol)
            if new_price:
                # Record price history
                price_history = PriceHistory(
                    stock_id=stock.id,
                    price=new_price
                )
                db.session.add(price_history)
                
                stock.price = new_price
                stock.last_updated = datetime.now(timezone.utc)
        db.session.commit()
        print(f"Stock prices updated at {datetime.now(timezone.utc)}")


# Algorithmic trading logic
def check_algorithms():
    with app.app_context():
        print("Checking algorithms...")
        active_algorithms = Algorithm.query.filter_by(active=True).all()
        
        for algo in active_algorithms:
            # Get last 5 minutes of price history
            five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
            history = PriceHistory.query.filter(
                PriceHistory.stock_id == algo.stock_id,
                PriceHistory.timestamp >= five_min_ago
            ).order_by(PriceHistory.timestamp).all()
            
            if len(history) >= 2:  # Need at least 2 data points
                prices = [h.price for h in history]
                high = max(prices)
                low = min(prices)
                current_price = algo.stock.price
                
                # Calculate percentage difference
                diff_percent = ((high - low) / low) * 100
                
                if diff_percent > algo.threshold:
                    print(f"Triggering buy for {algo.stock.symbol} ({diff_percent:.2f}% movement)")
                    # Virtual buy execution
                    execute_algo_trade(algo, current_price)

def execute_algo_trade(algorithm, price):
    user = User.query.get(algorithm.user_id)
    quantity = 1  # Fixed quantity for simplicity
    
    # Check if user has enough balance
    total_cost = price * quantity
    if user.balance >= total_cost:
        # Update user balance
        user.balance -= total_cost
        
        # Update or create portfolio item
        portfolio_item = Portfolio.query.filter_by(
            user_id=user.id,
            stock_id=algorithm.stock_id
        ).first()
        
        if portfolio_item:
            # Calculate new average price
            total_quantity = portfolio_item.quantity + quantity
            total_value = (portfolio_item.average_price * portfolio_item.quantity) + total_cost
            portfolio_item.average_price = total_value / total_quantity
            portfolio_item.quantity = total_quantity
        else:
            portfolio_item = Portfolio(
                user_id=user.id,
                stock_id=algorithm.stock_id,
                quantity=quantity,
                average_price=price
            )
            db.session.add(portfolio_item)
        
        # Record transaction
        transaction = Transaction(
            user_id=user.id,
            stock_id=algorithm.stock_id,
            transaction_type='BUY',
            quantity=quantity,
            price=price,
            note="Algorithmic trade"
        )
        db.session.add(transaction)
        
        db.session.commit()
        print(f"Executed BUY order for {algorithm.stock.symbol} at {price}")

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_algorithms, trigger="interval", minutes=5)
scheduler.start()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())


# Custom template filters
@app.template_filter('timesince')
def timesince_filter(dt):
    return humanize.naturaltime(datetime.now(timezone.utc) - dt)



# Add datetime filter
@app.template_filter('datetimeformat')
def datetimeformat_filter(value, format='%Y-%m-%d %H:%M'):
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
        except ValueError:
            return value
    if isinstance(value, datetime):
        return value.strftime(format)
    return value

# Routes

# @app.route('/')
# def index():
#     # For simplicity, we'll use a single demo user
#     user = User.query.first()
#     if not user:
#         user = User(username='demo', balance=10000.00)
#         db.session.add(user)
#         db.session.commit()
    
#     watchlist = Watchlist.query.filter_by(user_id=user.id).all()
#     portfolio = Portfolio.query.filter_by(user_id=user.id).all()
    
#     # Calculate portfolio value
#     portfolio_value = 0
#     for item in portfolio:
#         portfolio_value += item.stock.price * item.quantity
    
#     return render_template('index.html', 
#                          user=user,
#                          watchlist=watchlist,
#                          portfolio=portfolio,
#                          portfolio_value=portfolio_value)

@app.route('/')
@login_required
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    
    watchlist = Watchlist.query.filter_by(user_id=current_user.id).all()
    portfolio = Portfolio.query.filter_by(user_id=current_user.id).all()
    
    # Calculate portfolio value
    portfolio_value = sum(
        item.stock.price * item.quantity 
        for item in portfolio
        if item.stock  # Check if stock exists
    )

    portfolio_value = 0
    for item in portfolio:
        if item.stock and item.stock.price:
            portfolio_value += item.stock.price * item.quantity
    
    return render_template('index.html', 
                         user=current_user,
                         watchlist=watchlist,
                         portfolio=portfolio,
                         portfolio_value=portfolio_value)

@app.route('/add_stock', methods=['POST'])
def add_stock():
    symbol = request.form.get('symbol').upper()
    user = User.query.first()
    
    # Check if stock already exists in database
    stock = Stock.query.filter_by(symbol=symbol).first()
    
    if not stock:
        # Fetch stock data from Alpha Vantage
        params = {
            'function': 'SYMBOL_SEARCH',
            'keywords': symbol,
            'apikey': ALPHA_VANTAGE_API_KEY
        }
        response = requests.get(BASE_URL, params=params)
        data = response.json()
        
        if 'bestMatches' in data and data['bestMatches']:
            stock_data = data['bestMatches'][0]
            price = get_stock_price(symbol)
            
            if price:
                stock = Stock(
                    symbol=symbol,
                    name=stock_data['2. name'],
                    price=price,
                    last_updated=datetime.now(timezone.utc)
                )
                db.session.add(stock)
                db.session.commit()
            else:
                flash('Could not fetch price for this stock', 'error')
                return redirect(url_for('index'))
        else:
            flash('Stock symbol not found', 'error')
            return redirect(url_for('index'))
    
    # Check if stock is already in watchlist
    existing = Watchlist.query.filter_by(user_id=user.id, stock_id=stock.id).first()
    if existing:
        flash('Stock already in watchlist', 'info')
    else:
        watchlist_item = Watchlist(user_id=user.id, stock_id=stock.id)
        db.session.add(watchlist_item)
        db.session.commit()
        flash('Stock added to watchlist', 'success')
    
    return redirect(url_for('index'))

@app.route('/remove_stock/<int:stock_id>')
def remove_stock(stock_id):
    user = User.query.first()
    watchlist_item = Watchlist.query.filter_by(user_id=user.id, stock_id=stock_id).first()
    
    if watchlist_item:
        db.session.delete(watchlist_item)
        db.session.commit()
        flash('Stock removed from watchlist', 'success')
    else:
        flash('Stock not found in watchlist', 'error')
    
    return redirect(url_for('index'))

@app.route('/trade', methods=['POST'])
def trade():
    user = User.query.first()
    stock_id = request.form.get('stock_id')
    action = request.form.get('action')
    quantity = float(request.form.get('quantity'))
    
    stock = Stock.query.get(stock_id)
    if not stock:
        flash('Stock not found', 'error')
        return redirect(url_for('index'))
    
    if action == 'BUY':
        total_cost = stock.price * quantity
        if user.balance < total_cost:
            flash('Insufficient funds', 'error')
            return redirect(url_for('index'))
        
        # Update user balance
        user.balance -= total_cost
        
        # Update or create portfolio item
        portfolio_item = Portfolio.query.filter_by(user_id=user.id, stock_id=stock.id).first()
        if portfolio_item:
            # Calculate new average price
            total_quantity = portfolio_item.quantity + quantity
            total_value = (portfolio_item.average_price * portfolio_item.quantity) + total_cost
            portfolio_item.average_price = total_value / total_quantity
            portfolio_item.quantity = total_quantity
        else:
            portfolio_item = Portfolio(
                user_id=user.id,
                stock_id=stock.id,
                quantity=quantity,
                average_price=stock.price
            )
            db.session.add(portfolio_item)
        
        # Record transaction
        transaction = Transaction(
            user_id=user.id,
            stock_id=stock.id,
            transaction_type='BUY',
            quantity=quantity,
            price=stock.price
        )
        db.session.add(transaction)
        
        db.session.commit()
        flash(f'Successfully bought {quantity} shares of {stock.symbol}', 'success')
    
    elif action == 'SELL':
        portfolio_item = Portfolio.query.filter_by(user_id=user.id, stock_id=stock.id).first()
        
        if not portfolio_item or portfolio_item.quantity < quantity:
            flash('Not enough shares to sell', 'error')
            return redirect(url_for('index'))
        
        # Update user balance
        total_value = stock.price * quantity
        user.balance += total_value
        
        # Update portfolio
        portfolio_item.quantity -= quantity
        if portfolio_item.quantity == 0:
            db.session.delete(portfolio_item)
        
        # Record transaction
        transaction = Transaction(
            user_id=user.id,
            stock_id=stock.id,
            transaction_type='SELL',
            quantity=quantity,
            price=stock.price
        )
        db.session.add(transaction)
        
        db.session.commit()
        flash(f'Successfully sold {quantity} shares of {stock.symbol}', 'success')
    
    return redirect(url_for('index'))

# Add these routes before the if __name__ == '__main__' block

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')  # You can create this later

# @app.route('/news')
# def news():
#     return render_template('news.html')  # You can create this later

# Add after your existing routes
# @app.route('/algo_trading')
# def algo_trading():
#     user = User.query.first()
#     algorithms = Algorithm.query.filter_by(user_id=user.id).all()
#     return render_template('algo_trading.html', algorithms=algorithms)

# @app.route('/algo_trading')
# def algo_trading():
#     user = User.query.first()
#     algorithms = Algorithm.query.filter_by(user_id=user.id).all()
#     watchlist = Watchlist.query.filter_by(user_id=user.id).all()  # Add this line
#     return render_template('algo_trading.html', 
#                          algorithms=algorithms,
#                          watchlist=watchlist)  # Pass watchlist to template

@app.route('/algo_trading')
@login_required
def algo_trading():
    algorithms = Algorithm.query.filter_by(user_id=current_user.id).all()
    watchlist = Watchlist.query.filter_by(user_id=current_user.id).join(Stock).all()
    return render_template('algo_trading.html',
                         algorithms=algorithms,
                         watchlist=watchlist)

@app.route('/add_algo', methods=['POST'])
def add_algo():
    user = User.query.first()
    stock_id = request.form.get('stock_id')
    threshold = float(request.form.get('threshold'))
    
    # Check if algorithm already exists
    existing = Algorithm.query.filter_by(user_id=user.id, stock_id=stock_id).first()
    if existing:
        flash('Algorithm already exists for this stock', 'info')
    else:
        algorithm = Algorithm(
            user_id=user.id,
            stock_id=stock_id,
            threshold=threshold
        )
        db.session.add(algorithm)
        db.session.commit()
        flash('Algorithm added successfully', 'success')
    
    return redirect(url_for('algo_trading'))

@app.route('/toggle_algo/<int:algo_id>')
def toggle_algo(algo_id):
    algorithm = Algorithm.query.get(algo_id)
    if algorithm:
        algorithm.active = not algorithm.active
        db.session.commit()
        status = "activated" if algorithm.active else "deactivated"
        flash(f'Algorithm {status}', 'success')
    return redirect(url_for('algo_trading'))



@app.route('/analytics')
@login_required
def portfolio_analytics():
    portfolio = Portfolio.query.filter_by(user_id=current_user.id).all()
    
    # Calculate analytics
    total_value = 0
    total_cost = 0
    for item in portfolio:
        if item.stock and item.stock.price:
            total_value += item.stock.price * item.quantity
            total_cost += item.average_price * item.quantity
    
    total_pl = total_value - total_cost
    pl_percentage = (total_pl / total_cost) * 100 if total_cost != 0 else 0
    
    return render_template('analytics.html',
                         portfolio=portfolio,
                         total_value=total_value,
                         total_pl=total_pl,
                         pl_percentage=pl_percentage)

# # News API Route (make sure this is only defined once)
# NEWS_API_KEY = "f0459c476e46415eba32ef458affdba2"  # Get from https://newsapi.org

# News route with error handling
@app.route('/news')
@login_required
def news():
    news_data = []
    
    if not NEWS_API_KEY:
        flash('News API key not configured. Showing sample news.', 'warning')
        news_data = get_sample_news()
    else:
        try:
            news_url = f"https://newsapi.org/v2/top-headlines?category=business&apiKey={NEWS_API_KEY}"
            response = requests.get(news_url, timeout=10)
            response.raise_for_status()
            news_data = response.json().get('articles', [])[:6]
            
            # Format dates
            for article in news_data:
                if 'publishedAt' in article:
                    try:
                        article['publishedAt'] = datetime.strptime(
                            article['publishedAt'], 
                            '%Y-%m-%dT%H:%M:%SZ'
                        )
                    except (ValueError, TypeError):
                        article['publishedAt'] = None
        except requests.exceptions.RequestException as e:
            flash('Could not fetch live news. Showing sample news.', 'warning')
            news_data = get_sample_news()
    
    return render_template('news.html', news=news_data)

def get_sample_news():
    """Fallback sample news data"""
    return [
        {
            'title': 'Market Hits Record High',
            'description': 'Global markets reached all-time highs amid positive earnings.',
            'url': '#',
            'publishedAt': datetime.now(),
            'source': {'name': 'Financial Times'},
            'urlToImage': 'https://via.placeholder.com/300x200?text=Market+News'
        },
        {
            'title': 'Tech Stocks Rally',
            'description': 'Major tech companies surge following positive forecasts.',
            'url': '#',
            'publishedAt': datetime.now(),
            'source': {'name': 'Wall Street Journal'},
            'urlToImage': 'https://via.placeholder.com/300x200?text=Tech+News'
        }
    ]

# User Guide Route
@app.route('/guide')
def user_guide():
    return render_template('guide.html')

# Auth Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('Username already taken', 'danger')
        else:
            hashed_password = generate_password_hash(password)
            user = User(username=username, email=email, password_hash=hashed_password)
            db.session.add(user)
            db.session.commit()
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    # Start the price update thread
    update_thread = threading.Thread(target=schedule_price_updates)
    update_thread.daemon = True
    update_thread.start()
    
    app.run(debug=True)