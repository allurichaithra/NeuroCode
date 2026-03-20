# 🧠 NeuroCode — AI Coding Agent

NeuroCode is an intelligent, personalized, and stateful AI coding mentor built with a 5-agent pipeline. It combines robust code analysis, gamification, and long-term memory to help students improve their coding skills over time without repeating the same mistakes.

## ✨ Key Features

- **5-Agent Pipeline:**
  1. **Analyzer:** Ruthlessly precise code analysis engine to catch syntax errors, logic bugs, etc.
  2. **Memory:** Leverages Hindsight vector memory to recall past mistakes and identify patterns.
  3. **Fixer:** Corrects code with inline explanations of changes and extracts mistakes for memory storage.
  4. **Mentor:** Provides warm, personalized feedback and calls out repeating mistakes.
  5. **Roadmap Builder:** Generates an actionable 7-day learning plan based on the student's weaknesses.
- **Hindsight Vector Memory:** Long-term memory storage of student mistakes (with local disk JSON fallback).
- **Gamification:** Tracks XP, user levels, streaks, and awards badges (e.g., First Blood, On Fire, Polyglot) across sessions.
- **Modern Responsive UI:** A futuristic vanilla HTML/CSS/JS frontend featuring interactive metrics, code visualizations, and animated feedback.

## 🛠️ Technology Stack

- **Backend:** Python, Flask
- **LLM Provider:** Groq (using `llama-3.3-70b-versatile`)
- **Memory/Vector DB:** Hindsight API (Vectorize.io)
- **Frontend:** Vanilla HTML5, CSS3, JavaScript
- **Local Storage:** `profiles.json` and `fallback_memory.json`

## 🚀 Getting Started

### 1. Prerequisites

- Python 3.8+
- [Groq AI API Key](https://console.groq.com/keys)
- *(Optional)* [Hindsight API Key](https://hindsight.vectorize.io/) for persistent vector memory

### 2. Installation

Clone the repository and install the dependencies:

```bash
# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 3. Environment Configuration

Create a `.env` file in the root directory and add your API keys:

```ini
GROQ_API_KEY=your_groq_api_key_here
HINDSIGHT_API_KEY=your_hindsight_api_key_here
```

### 4. Running the Application

Start the Flask development server:

```bash
flask run
# OR
python -m flask run
```

The application will be available at [http://127.0.0.1:5000](http://127.0.0.1:5000).

## 🎮 How it Works

1. **Submit Code:** Enter your Student ID, pick a language, write the problem description, and paste your code.
2. **Analysis:** The agents will sequentially analyze, fix, and explain your code.
3. **Memory:** Any logical/syntax mistakes are extracted and saved. In future sessions, the Mentor Agent will remind you if you make the exact same mistake again.
4. **Grow:** Earn XP, level up (from Seedling to Wizard), and collect badges as your code improves!
