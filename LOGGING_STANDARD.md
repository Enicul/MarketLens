# MarketLens Logging Guidelines

## Unified Logging Emoji Standard

Every module uses a common emoji set to signal log status:

### General states
- 🚀 **Launch / Start** – a module or task has begun
- ✅ **Completed** – the operation finished successfully
- ❌ **Error / Failure** – the operation failed or raised an exception
- ⚠️ **Warning** – something needs attention but execution can continue
- 🔄 **Processing** – work is currently in progress
- 💾 **Caching** – cache-related activity

### Domain-specific variants
- 📊 **Data Processing** – data ingestion, transformation, or analysis
- 📥 **Data Intake** – loading or fetching data
- 📁 **File Operations** – read / write / persistence
- 📈 **Charts / Forecasts** – Kronos forecasts or charting
- 📝 **Metadata** – metadata capture
- 📰 **News** – news collection workflows
- 🐦 **Social** – Twitter / X sentiment analysis
- 💹 **Trading** – trading decision flows
- 🔬 **Research** – research analysis
- 🛡️ **Risk Management** – risk control tasks
- 💬 **Debate** – bull vs. bear debate
- 🎯 **Decision** – final synthesis and recommendation
- 🔍 **Search / Query** – data search utilities
- 💡 **Prompting** – prompt generation or tips
- 👥 **User Activity** – internal trader or user-facing actions

## Module Log Tags

Each module should adopt a consistent tag prefix:

| Module | Tag | Example |
|--------|-----|---------|
| Analyst | `[ANALYST]` | `logger.info(f"[ANALYST] 🚀 Starting analysis {ticker}")` |
| Fundamentals | `[FUNDAMENTALS]` | `logger.info(f"[FUNDAMENTALS] 📊 Fetching fundamentals data")` |
| News | `[NEWS]` | `logger.info(f"[NEWS] 📰 Pulling news flow")` |
| Sentiment | `[SENTIMENT]` | `logger.info(f"[SENTIMENT] 🐦 Launching Twitter sentiment run")` |
| Yahoo | `[YAHOO]` | `logger.info(f"[YAHOO] 📊 Retrieving market snapshot")` |
| Trader | `[TRADER]` | `logger.info(f"[TRADER] 💹 Building trading decision")` |
| Kronos | `[TRADER][KRONOS]` | `logger.info(f"[TRADER][KRONOS] 📈 Forecast complete")` |
| Researcher | `[RESEARCHER]` | `logger.info(f"[RESEARCHER] 🔬 Initiating research cycle")` |
| Risk | `[RISK]` | `logger.info(f"[RISK] 🛡️ Running risk management")` |

## Log Level Guidance

### INFO
- Module start or completion
- Major workflow checkpoints
- Successful outcomes
- Essential updates for users

Example:
```python
logger.info(f"[ANALYST] 🚀 Starting analysis {ticker}")
logger.info(f"[ANALYST] ✅ Analysis complete: {ticker}")
```

### DEBUG
- Detailed execution trace
- Intermediate outputs
- Data validation checks
- Troubleshooting insight

Example:
```python
logger.debug(f"[FUNDAMENTALS] 📥 Loaded fundamentals for {ticker}")
logger.debug(f"[NEWS] 📥 Feed counts – Finnhub={len(finnhub)}, FMP={len(fmp)}")
```

### WARNING
- Recoverable issues
- Exceptional but non-fatal conditions
- Fallback or degraded modes
- Incomplete data with continued execution

Example:
```python
logger.warning(f"[ANALYST] ⚠️ Cache fallback in use: {ticker}/{intent}")
logger.warning(f"[NEWS] ⚠️ Primary API empty, switching to RSS backup")
```

### ERROR
- Operation failure
- Data loading errors
- Non-recoverable exceptions
- Issues requiring manual intervention

Example:
```python
logger.error(f"[ANALYST] ❌ Error: {ticker}/{intent} - {error_msg}")
logger.error(f"[RESEARCHER] ❌ Bullish research failed: {e}")
```

## Completed Refactors

### ✅ Analysts module
- [x] `analysts/analyst.py` – migrated `print()` to structured logging with emojis
- [x] `analysts/lib/fundamentals.py` – added missing logs and emoji cues
- [x] `analysts/lib/news.py` – optimized log output and emoji usage
- [x] `analysts/lib/X_search/tool.py` – replaced `print()` with logger
- [x] `analysts/lib/X_search/search.py` – refined log levels
- [x] `analysts/lib/yahoo/yahoo.py` – expanded coverage with emojis

### ✅ Trader module
- [x] `Trader/trader.py` – standardized logger usage and formatting

### ✅ Researchers module
- [x] `researchers/manager.py` – added structured logs with emojis

### ✅ Risk Management module
- [x] `risk_management/orchestrator.py` – replaced `print()` with logger

## Best Practices

1. **Prefer the logger over `print()`** – except in bootstrap scripts or isolated tests.
2. **Keep language consistent** – use English for team-wide clarity.
3. **Apply meaningful emojis** – they improve readability and scanning.
4. **Include critical context** – e.g., ticker, file path, counters.
5. **Choose log levels intentionally** – avoid spamming INFO.
6. **Maintain formatting** – reuse shared tags and templates.

## Example Pattern

```python
import logging

logger = logging.getLogger(__name__)

# Startup
logger.info(f"[MODULE] 🚀 Handling request: {param}")

# Optional detail
logger.debug(f"[MODULE] 📥 Loaded {len(data)} records")

# Success
logger.info(f"[MODULE] ✅ Completed: {result}")

# Warning
logger.warning(f"[MODULE] ⚠️ Partial data; defaults applied")

# Error handling
try:
    # ... operations
    pass
except Exception as e:
    logger.error(f"[MODULE] ❌ Operation failed: {e}")
```

## Configuration Notes

`manager/agent_stream_gradio.py` already tunes noisy HTTP clients:

```python
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
```

These guards keep third-party chatter out of the console.

---

**Last updated**: 2025-10-23  
**Maintainers**: MarketLens Team
