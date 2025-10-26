
## SECTION 1 : PROJECT TITLE
## MarketLens – AI-Driven Multi-Agent Market Intelligence Platform

<img src="SystemCode/manager/static/image/login.gif"
     style="float: left; margin-right: 0px; width: 96px;" />

MarketLens is our end-to-end research console that fuses analyst, researcher, trading, and risk-management agents with a modern Vite/React control center. The repository you are viewing is the canonical submission artifact referenced throughout this README.

### 📺 Promotional Video

**[▶️ Watch Promotional Video](Video/IRS-PM-2025-08-10-GRP-1-MarketLens_PromoteVideo.mp4)**

*2-minute promotional clip summarizing MarketLens business value proposition*

---

## SECTION 2 : EXECUTIVE SUMMARY / PAPER ABSTRACT
In today's fast-paced financial markets, retail investors are inundated with an overwhelming amount of scattered data from news, social media, and financial reports. This information overload often leads to confusion, emotional decision-making, and a significant gap between the sophisticated tools used by professionals and the resources available to the everyday person. Many investors struggle to translate this noise into clear, actionable insights, making it difficult to invest with confidence.

Our team, comprised of five members from the NUS-ISS Intelligent Reasoning Systems module, recognized this challenge. We aimed to bridge this gap by creating Market Lens, an AI-driven multi-agent system designed to simplify investment research. Market Lens transforms complex financial data into simple, confident investment signals (BUY, SELL, HOLD), making institutional-grade analysis accessible to retail investors. The system emulates a professional research team, with specialized AI agents dedicated to market analysis, news sentiment, fundamentals, and risk assessment.

To build this system, we utilized a modern tech stack, including a React frontend and a FastAPI backend with WebSocket for real-time communication. The core reasoning is powered by Large Language Models (LLMs) within a multi-agent framework managed by LangChain. Data is collected from various public APIs like Yahoo Finance and Finnhub. The system's unique "Researcher" agent stages a debate between bullish and bearish viewpoints to arrive at a balanced, evidence-backed conclusion, which is then presented in a clear, easy-to-understand "Decision Card" that includes risk analysis.

Our team had an incredible experience bringing this project to life, successfully developing a functional prototype that demonstrates the power of multi-agent reasoning in a real-world application. While the project focuses on stock analysis, its core principles of turning information overload into structured insight are widely applicable. We believe Market Lens showcases a promising future for AI-augmented decision-making, empowering investors to navigate the markets with greater clarity and confidence.

---

## SECTION 3 : CREDITS / PROJECT CONTRIBUTION

| Official Full Name  | Student ID (MTech Applicable)  | Work Items (Who Did What) | Email (Optional) |
| :------------ |:---------------:| :-----| :-----|
| _Jin YanYu_ | _A0326918U_ | Team Leader & System Integrator Frontend development, Risk management module design and development, system integration, video production, and report writing. | _e1538749@u.nus.edu_ |
| _Chen ZiHao_ | _A0329043J_ | Model & Trading Agent Developer Trader module development, overall code refactoring, debugging, and report writing. | _e1553370@u.nus.edu_ |
| _Fu HaoXiang_ | _A0328896E_ | System Architect & Module Developer Analyst and Researcher module design and development, and report writing. | _e1553223@u.nus.edu_ |
| _Li Lin_ | _A0327882R_ | Backend Developer Analyst and Researcher module development, promotional video, and report writing. | _e1546637@u.nus.edu_ |
| _Yang Miao_ | _A0327007M_ | Core Developer Overall system connection, Manager module development, and report writing. | _e1538838@u.nus.edu_ |

---

## SECTION 4 : VIDEO OF SYSTEM MODELLING & USE CASE DEMO

The `Video/` folder in this repository contains the two deliverables expected by ISS:

**[▶️ System Video - Full Walkthrough](Video/IRS-PM-2025-08-10-GRP-1-MarketLens_SystemVideo.mp4)**  
Complete walkthrough covering agent orchestration, UI flows, and a full EUR/USD-equity demo session.

**[▶️ Promotional Video](Video/IRS-PM-2025-08-10-GRP-1-MarketLens_PromoteVideo.mp4)**  
Promotional clip summarizing the business value proposition for sponsors.

---

## SECTION 5 : USER GUIDE

📖 **For complete installation instructions and detailed usage guide, please refer to:**  
👉 **[SystemCode/README.md](SystemCode/README.md)** - Comprehensive setup, API reference, and troubleshooting

### Quick Start Guide

#### Prerequisites
- **Python** 3.11+
- **Node.js** 18+ LTS
- **API Keys**: Google AI Studio (Gemini), Finnhub, FMP, AlphaVantage

#### [ 1 ] Installation & Setup

**Backend Setup:**
```bash
cd SystemCode
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium  # For Twitter sentiment scraping
```

**Configure Environment Variables:**
Create a `.env` file in `SystemCode/` with:
```bash
GOOGLE_API_KEY=your_gemini_key
FINNHUB_KEY=your_finnhub_key
FMP_KEY=your_fmp_key
ALPHAVANTAGE_KEY=your_alphavantage_key
MARKET_LENS_ADMIN_EMAIL=nus@u.nus.edu
MARKET_LENS_ADMIN_PASSWORD=123
```

**Start Backend:**
```bash
uvicorn manager.server.app:app --reload --port 8000
```

**Frontend Setup (in a new terminal):**
```bash
cd SystemCode/frontend
npm install
npm run dev  # Launches at http://localhost:5173
```

#### [ 2 ] Login & Usage

Open **[http://localhost:5173](http://localhost:5173)** in your browser.

**Login Options:**
- **Guest Access** - Quick exploration without account
- **Demo Account** - View saved histories
  ```
  Email: nus@u.nus.edu
  Password: 123
  ```

**Request Analysis:**
Simply chat with the agent using natural language:
> "I want an in-depth analysis of Nvidia."

**For Kronos Price Predictions** (on-demand, computationally intensive):
> "Give me a detailed analysis of Tesla using Kronos."

**Progress Tracking:**  
Monitor real-time progress on the right sidebar as agents complete data retrieval and reasoning.

#### [ 3 ] Additional Resources

- **[SystemCode/README.md](SystemCode/README.md)** - Full documentation with architecture, API reference, and troubleshooting
- **Project Report** - `ProjectReport/Project Report Market Lens.pdf`
- **Kronos Web UI** - Run `python SystemCode/Trader/Kronos/webui/run.py` for standalone forecasting dashboard

---
## SECTION 6 : PROJECT REPORT / PAPER

📄 **[View Project Report → ProjectReport/Project Report Market Lens.pdf](ProjectReport/Project%20Report%20Market%20Lens.pdf)**

### Report Structure Overview

The comprehensive project report covers the following sections:

#### 1. Executive Summary / Abstract
A concise overview summarizing the project's motivation, objectives, methodologies, and outcomes, emphasizing the integration of multi-agent reasoning for financial intelligence.

#### 2. Business and Research Context
- **2.1 Project Background and Motivation**  
  Explains the problem of information overload in retail investment decision-making.
- **2.2 Market and Academic Context**  
  Describes the gap between institutional analytics and retail investor needs, and links to relevant academic domains (MR, RS, CGS).

#### 3. Market Research
- **3.1 Market Analysis:** Demand, Trends, and Opportunities
- **3.2 Key Competitors and Existing Solutions**
- **3.3 User Needs and Potential Differentiation**

Analyzes industry trends and benchmarks existing platforms to position MarketLens within the financial intelligence ecosystem.

#### 4. Project Objectives and Scope
- Defines main goals and success criteria
- Specifies intended academic outcomes (reasoning, explainability) and practical contributions (accessible investment insights)

#### 5. Data Collection and Preparation
- Describes data sources: Yahoo Finance, Finnhub, Reddit, FMP, Playwright automation
- Explains data-cleaning, normalization, and standardization workflows
- Outlines key data challenges and mitigation strategies

#### 6. System Design
- **6.1 Architecture and Components** – Overall system design and module hierarchy
- **6.2 Reasoning Technique Selection** – Multi-agent reasoning, debate-based synthesis, LangChain integration
- **6.3 Module Interaction Overview** – Coordination between Manager, Analyst, Researcher, Trader, and Risk Manager

#### 7. Project Implementation
- **7.1 Workflow Overview** – End-to-end interaction flow (React ↔ FastAPI ↔ multi-agent pipeline)
- **7.2 Implementation Progress** – Module completion and testing results
- **7.3 Technical Stack and Tools** – Frameworks, models, APIs, and development environment
- **7.4 Technical Challenges**
  - 7.4.1 Foundation Model Selection and Reasoning Efficiency
  - 7.4.2 Frontend Technology Stack Evolution
  - 7.4.3 Sentiment Data Collection and Cost Optimization

#### 8. Results and Progress
- **8.1 Preliminary Results** – Outputs from each layer (Analyst, Researcher, Trader, Risk Manager)
- **8.2 Deviation from Initial Plan** – Improvements and architectural changes
- **8.3 Academic and Market Validation** – Mapping to MR–RS–CGS frameworks

#### 9. Challenges and Roadblocks
- **9.1 Technical and Implementation Challenges**
- **9.2 Data and Market Application Challenges**
- **9.3 Academic and Conceptual Roadblocks**
- **9.4 Mitigation Strategies and Timeline Alignment**

#### 10. Future Work
Short-term enhancements (UI refinement, concurrency support) and long-term goals (mobile app, hybrid forecasting models, scalability improvements).

#### 11. Conclusion
Project achievements, academic insights, and potential market impact. Reflects on how MarketLens bridges research and real-world application.

#### 12. Appendices
- **12.1 Project Proposal** – Initial scope, objectives, and planning documents
- **12.2 Knowledge Mapping** – MarketLens functionalities aligned with MR, RS, and CGS learning outcomes
- **12.3 Installation and User Guide** – Setup instructions, login options, quick start examples
- **12.4 Individual Reflections** – Team member contributions and learning outcomes
- **12.5 Abbreviations & References** – Glossary and cited resources


---
