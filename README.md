# 💰 AI Finance Manager

A modern, mobile-first AI-powered personal finance application with intelligent transaction categorization and insights. Built for Data Science Lab Project 2025.

![Version](https://img.shields.io/badge/version-2.0-blue)
![Python](https://img.shields.io/badge/python-3.13-green)
![React](https://img.shields.io/badge/react-19.1.1-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## ✨ Features

### 🎯 Core Features
- 🤖 **AI-Powered Chat**: Google Gemini AI provides personalized financial insights and answers
- 📊 **Smart Analytics**: Interactive charts showing spending by category, monthly trends, and top merchants
- 🏦 **Multi-Bank Support**: Upload statements from SBI, Kotak, Axis Bank with automatic format detection
- 🎨 **Modern UI**: Beautiful mobile-first design with gradient themes and smooth animations
- 📱 **Fully Responsive**: Works perfectly on mobile, tablet, and desktop devices
- 🎯 **Auto Categorization**: Intelligent transaction categorization (Investment, Food, Shopping, Transportation, etc.)

### 📈 Analytics Dashboard
- **Real-time Statistics**: Total spending, average transaction, transaction count, date range
- **Category Breakdown**: Pie chart showing spending distribution
- **Monthly Trends**: Line chart tracking spending over time
- **Top Merchants**: Bar chart identifying where you spend most
- **AI Insights**: Personalized spending analysis and savings suggestions

### 🔒 Privacy First
- **No Cloud Storage**: All data stays in your session
- **Local Processing**: CSV files processed locally
- **Secure**: No data persistence, complete privacy guaranteed

## 🚀 Live Demo

Try it now with sample data:
- **Production URL**: [Your Vercel URL]
- **Backend API**: [Your Render URL]

Click "Try Demo" on the welcome page to explore with 130+ sample transactions!

## 🛠️ Tech Stack

### Frontend
- **React 19.1.1**: Modern UI library
- **Vite 7.1.7**: Fast build tool and dev server
- **Chart.js**: Beautiful data visualizations
- **React Router**: Client-side routing
- **Axios**: HTTP client for API calls
- **Custom CSS**: Mobile-first responsive design (no framework dependencies)

### Backend
- **Flask 3.1.2**: Python web framework
- **Pandas 2.3.2**: Data analysis and CSV processing
- **NumPy 2.2.6**: Numerical computations
- **Google Gemini AI**: Advanced language model for insights
- **Flask-CORS**: Cross-origin resource sharing
- **Gunicorn**: Production WSGI server

### Deployment
- **Frontend**: Vercel (with automatic deployments)
- **Backend**: Render (with free tier support)
- **Version Control**: Git & GitHub

## 📦 Installation

### Prerequisites
- Python 3.13+
- Node.js 18+
- Git
- Google Gemini API key ([Get it here](https://makersuite.google.com/app/apikey))

### Local Development Setup

#### 1. Clone Repository
```bash
git clone https://github.com/vandandalvi/personalFinanceManager.git
cd personalFinanceManager
```

#### 2. Backend Setup
```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
copy .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

#### 3. Frontend Setup
```bash
cd frontend/vite-project

# Install dependencies
npm install
```

### Running Locally

#### Start Backend (Terminal 1)
```bash
cd backend
python app.py
```
Backend runs on `http://localhost:5000`

#### Start Frontend (Terminal 2)
```bash
cd frontend/vite-project
npm run dev
```
Frontend runs on `http://localhost:5173`

Open browser and navigate to `http://localhost:5173`

## 🎯 Usage Guide

### Option 1: Try Demo (Fastest)
1. Click **"Try Demo"** on welcome page
2. Instantly see dashboard with 130+ sample transactions
3. Explore all features with realistic data

### Option 2: Upload Your Own CSV
1. Click **"Get Started"** on welcome page
2. Select your bank (SBI, Kotak, or Axis)
3. Upload your bank statement CSV
4. View personalized dashboard and insights

### CSV Format Requirements

#### SBI Format
```csv
Txn Date,Value Date,Description,Ref No./Cheque No.,Debit,Credit,Balance
01/09/2025,01/09/2025,UPI/Swiggy,UPI123456,350.00,,24650.00
```

#### Kotak Format
```csv
Date,Particulars,Debit,Credit,Balance
01/09/2025,UPI/SWIGGY/Food Order,350.00,,24650.00
```

#### Axis Format
```csv
Tran Date,Chq/Ref Number,Description,Withdrawal Amt,Deposit Amt,Balance
01/09/2025,UPI123456,SWIGGY FOOD,350.00,,24650.00
```

### AI Chat Examples
Ask questions like:
- "Where can I save money?"
- "What's my total spending on food?"
- "Show my investment transactions"
- "Which merchant do I spend most at?"
- "How much did I spend in September?"
- "Give me financial advice"

## 📊 Features in Detail

### Intelligent Categorization
Transactions are automatically categorized into:
- 💰 **Investment**: Stocks, mutual funds, trading accounts (UPSTOX, ZERODHA, GROWW, INDIAN CLEARING)
- 💳 **Credit Card**: Card payments and CRED transactions
- 🍔 **Food**: Restaurant deliveries (SWIGGY, ZOMATO, restaurant names)
- 🛒 **Shopping**: E-commerce purchases (AMAZON, FLIPKART, MYNTRA)
- 🚗 **Transportation**: Travel expenses (UBER, OLA, METRO, petrol pumps)
- 🎬 **Entertainment**: Subscriptions and entertainment (NETFLIX, SPOTIFY, BOOKMYSHOW)
- 💰 **Income**: Salary, bonuses, refunds
- 📱 **Bills**: Utilities and recurring payments
- 🏥 **Healthcare**: Medical expenses
- 📚 **Education**: Course fees, books

### Dashboard Analytics
- **Overview Cards**: Key metrics at a glance
- **Category Distribution**: Visual pie chart breakdown
- **Spending Trends**: Monthly line chart tracking
- **Top Merchants**: Bar chart of frequent vendors
- **Date Range**: Automatic detection of statement period

### AI Insights
Powered by Google Gemini 2.5, provides:
- Spending pattern analysis
- Personalized savings suggestions
- Budget recommendations
- Anomaly detection
- Financial goal tracking advice

## 🚀 Deployment

See **[DEPLOYMENT.md](./DEPLOYMENT.md)** for quick deployment guide.
See **[DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)** for detailed instructions.

### Quick Deploy Steps
1. **Backend to Render**: Connect GitHub, configure build, add env variables
2. **Frontend to Vercel**: Import project, set root directory, deploy
3. **Update URLs**: Link frontend and backend, commit changes
4. **Test**: Visit live URL and try demo

## 📁 Project Structure

```
personalFinanceManager/
├── backend/                    # Flask backend
│   ├── app.py                 # Main Flask application (1052 lines)
│   ├── requirements.txt       # Python dependencies
│   ├── runtime.txt           # Python version
│   ├── Procfile              # Render deployment config
│   └── .env.example          # Environment template
├── frontend/vite-project/     # React frontend
│   ├── src/
│   │   ├── components/       # React components
│   │   │   ├── WelcomePage.jsx        # Landing page
│   │   │   ├── UploadPage.jsx         # CSV upload
│   │   │   ├── Dashboard.jsx          # Analytics dashboard
│   │   │   ├── ChatPage.jsx           # AI chat interface
│   │   │   └── AdvancedAnalytics.jsx  # Additional insights
│   │   ├── config/
│   │   │   └── api.js        # API configuration
│   │   ├── App.jsx           # Main app component
│   │   └── main.jsx          # Entry point
│   ├── public/
│   │   └── kotak_sample.csv  # Demo data file
│   ├── package.json          # Node dependencies
│   └── vite.config.js        # Vite configuration
├── kotak_sample.csv          # Sample CSV (130 transactions)
├── sbi_sample.csv            # SBI format sample
├── axis_sample.csv           # Axis format sample
├── DEPLOYMENT.md             # Quick deployment guide
├── DEPLOYMENT_GUIDE.md       # Detailed deployment instructions
├── PROJECT_REPORT.md         # Project documentation
└── README.md                 # This file
```

## 🎓 Academic Project Details

**Course**: Data Science Lab
**Year**: 2025
**Team**: Vandan Dalvi

### Technologies Demonstrated
- **Data Science**: Pandas for data manipulation, NumPy for calculations
- **Machine Learning**: Google Gemini AI for NLP and insights
- **Web Development**: Full-stack React + Flask application
- **Data Visualization**: Chart.js for interactive charts
- **Deployment**: Cloud deployment on Vercel and Render

### Learning Outcomes
- CSV data processing and cleaning
- Transaction categorization algorithms
- RESTful API design and implementation
- Modern frontend development with React
- AI integration for intelligent insights
- Responsive mobile-first UI design
- Cloud deployment and DevOps

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Guidelines
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 👨‍💻 Author

**Vandan Dalvi**
- GitHub: [@vandandalvi](https://github.com/vandandalvi)

## 🙏 Acknowledgments

- Google Gemini AI for intelligent insights
- React and Vite communities
- Chart.js for beautiful visualizations
- Vercel and Render for free hosting

## 📞 Support

For questions or issues:
- Open an issue on GitHub
- Email: [Your email if you want to add]

---

**Made with ❤️ for Data Science Lab Project 2025**
