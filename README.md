# Membership Classifier

A smart tool to analyze your bank statements and identify recurring subscription and membership expenses.

## Features

- 📄 **Bank Statement Parsing**: Upload PDF or CSV bank statements (supports French date formats)
- 🤖 **Smart Classification**: Uses AI or pattern matching to identify memberships
- 🔄 **Recurring Detection**: Automatically filters out one-time payments, only shows subscriptions
- 📊 **Frequency Analysis**: Detects payment frequencies (Monthly, Yearly, Weekly, etc.)
- 🎯 **Categorization**: Groups expenses by type (Sport, Software, Streaming, Services, etc.)
- 💻 **Clean Web Interface**: Simple, modern UI with model status indicator

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure AI Models (Optional)

The app works out-of-the-box with fast rule-based classification. For AI-powered classification, choose one:

**Groq (Recommended - Fast & Free)**:
```bash
export GROQ_API_KEY="your-groq-api-key"
export USE_AI_CLASSIFICATION=true
```

**Ollama (Free, Local)**:
```bash
# Install Ollama from https://ollama.ai/download
ollama pull llama3.2
export USE_AI_CLASSIFICATION=true
```

**OpenAI (Paid)**:
```bash
export OPENAI_API_KEY="your-openai-api-key"
export USE_AI_CLASSIFICATION=true
```

### 3. Run the Application

```bash
python main.py
```

Or using uvicorn directly:

```bash
uvicorn main:app --reload
```

The web interface will be available at `http://localhost:8000`

## Usage

### Upload Bank Statements

1. Go to the web interface
2. Click "Upload Bank Statement"
3. Select a PDF or CSV file from your bank
4. The system will automatically parse and classify transactions

### View Results

The dashboard shows:
- Current AI model being used
- Total number of recurring memberships
- Total spending on memberships
- Estimated monthly costs
- Breakdown by membership type (Sport, Software, Streaming, etc.)
- Detailed list of all subscription transactions

## Project Structure

```
├── main.py              # FastAPI application and routes
├── models.py            # Database models
├── bank_parser.py       # Bank statement parser (PDF/CSV, French dates)
├── llm_classifier.py    # AI/rule-based classification
├── config.py            # Configuration settings
├── requirements.txt     # Python dependencies
├── static/
│   └── index.html      # Web interface
└── README.md           # This file
```

## API Endpoints

- `GET /api/model-info` - Get current AI model information
- `POST /api/upload/statement` - Upload bank statement file
- `GET /api/transactions` - Get all transactions (with optional filters)
- `GET /api/summary` - Get expense summary grouped by type
- `GET /api/frequency-analysis` - Get frequency analysis for recurring payments
- `DELETE /api/transactions` - Clear all transactions

## How It Works

1. **Parsing**: Extracts transaction data from PDF or CSV bank statements
2. **Pattern Analysis**: Analyzes merchant frequency across all transactions
3. **Classification**: Uses AI (Groq/Ollama/OpenAI) or pattern matching
4. **Filtering**: Automatically excludes one-time payments, only shows subscriptions
5. **Frequency Detection**: Analyzes payment dates to determine frequency
6. **Visualization**: Clean web UI displays the model and results

## AI Configuration

- **Groq AI** (Recommended - Fast & Free tier available)
  - Set `GROQ_API_KEY` environment variable
  - Very fast inference with llama-3.3-70b
- **Ollama** (Free, Local)
  - Install from https://ollama.ai and run locally
  - Slow but no API costs
- **OpenAI GPT** (Paid)
  - Set `OPENAI_API_KEY` environment variable
  - Most accurate but costs per request

**Default**: Fast rule-based classification (no setup required)

## Notes

- Supported formats: PDF (French & English dates), CSV
- Automatically detects recurring vs one-time payments
- Shows only subscriptions, filters out one-time purchases
- Displays which AI model is running on the website

## License

MIT License


