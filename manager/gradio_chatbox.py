import gradio as gr
import time
from typing import Callable, Optional, Dict
from langchain.agents import AgentExecutor
from langchain_core.messages import HumanMessage, AIMessage


class MarketLensChatbox:
    """Market Lens AI Chatbox component with streaming support and status updates"""
    
    def __init__(self):
        self.CSS = """
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        
        * {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif !important;
        }
        
        .main-container {
            max-width: 1400px; 
            margin: 0 auto; 
            padding: 20px;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            height: 100vh;
            display: flex;
            flex-direction: column;
            box-sizing: border-box;
        }
        
        .header-text {
            text-align: center; 
            margin-bottom: 15px; 
            color: #2c3e50;
            font-weight: 700;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
            font-size: 2rem;
            letter-spacing: -0.02em;
        }
        
        .control-panel {
            background: white;
            border-radius: 15px;
            padding: 15px 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 15px;
        }
        
        .chat-container {
            background: white;
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            flex: 1;
            display: flex;
            flex-direction: column;
            min-height: 0;
            height: calc(100vh - 220px);
        }
        
        .analysis-status {
            background: #e8f4f8;
            border-left: 4px solid #3498db;
            padding: 10px 15px;
            margin: 10px 0;
            border-radius: 5px;
            font-style: italic;
            font-weight: 500;
        }
        
        /* Make chatbot container fill available space */
        .chat-container > div {
            flex: 1;
            display: flex;
            flex-direction: column;
            height: 100%;
        }
        
        /* Style the chatbot messages */
        .message {
            font-size: 15px;
            line-height: 1.6;
            letter-spacing: -0.01em;
        }
        
        /* Input field styling */
        textarea {
            font-size: 15px !important;
            letter-spacing: -0.01em !important;
        }
        
        /* Button styling */
        button {
            font-weight: 600 !important;
            letter-spacing: -0.01em !important;
        }
        
        /* Chatbot specific styling */
        .chatbot-container {
            flex: 1;
            overflow-y: auto;
            min-height: 0;
            height: 100%;
        }
        
        /* Ensure the chat messages area takes full height */
        .chatbot-container > div {
            height: 100%;
        }
        
        /* Remove padding from parent containers to maximize space */
        .contain {
            padding: 0 !important;
        }
        
        /* Ensure the main gradio container fills viewport */
        .gradio-container {
            height: 100vh !important;
            max-height: 100vh !important;
            display: flex;
            flex-direction: column;
        }
        
        /* Remove default gradio margins */
        body {
            margin: 0;
            padding: 0;
            overflow: hidden;
        }
        
        /* Adjust header and subtitle spacing */
        h1 {
            margin-bottom: 0.5rem !important;
        }
        
        /* Style checkboxes */
        label span {
            font-weight: 500;
            font-size: 14px;
        }
        """
    
    async def stream_response(
        self,
        agent_executor: AgentExecutor,
        user_input: str,
        chat_history: list,
        status_callback: Optional[Callable] = None
    ):
        """Execute the agent loop and stream responses."""
        try:
            # Update status indicator
            if status_callback:
                status_callback("🤖 AI Agent is thinking...")

            # Build conversation history for the agent loop
            messages = []
            for msg in chat_history:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                else:
                    messages.append(AIMessage(content=msg["content"]))

            # Invoke the agent with full chat history (using async method)
            response = await agent_executor.ainvoke({
                "input": user_input,
                "messages": messages
            })
            output = response.get("output", "Sorry, no response received.")

            # Inspect intermediate steps for status updates
            steps = response.get("intermediate_steps", [])
            for step in steps:
                if len(step) > 0 and hasattr(step[0], "tool"):
                    tool_name = step[0].tool
                    if status_callback:
                        status_callback(f"🔧 Using tool: {tool_name}")

            # Stream token-by-token output
            partial = ""
            for i, char in enumerate(output):
                partial += char
                yield partial
                # Slightly pause at punctuation for readability
                if char in "。！？，；：.!?,;:":
                    time.sleep(0.1)
                else:
                    time.sleep(0.02)

            # Clear status line
            if status_callback:
                status_callback("")
                    
        except Exception as e:
            yield f"[Error] {str(e)}"
    
    def create_interface(
        self, 
        agent_builder: Callable,
        enabled_analysis_types: Dict[str, bool]
    ) -> gr.Blocks:
        """Create the Gradio interface with a genuine agent loop."""

        # Initialize the agent once
        main_agent = agent_builder(enabled_analysis_types)
        
        with gr.Blocks(title="Market Lens AI Agent", css=self.CSS, theme=gr.themes.Soft()) as demo:
            with gr.Column(elem_classes=["main-container"]):
                gr.Markdown("# 🤖 Market Lens AI Financial Analysis Assistant", elem_classes=["header-text"])
                
                # Control Panel
                with gr.Group(elem_classes=["control-panel"]):
                    gr.Markdown("**⚙️ Analysis Configuration**")
                    with gr.Row():
                        news_toggle = gr.Checkbox(label="📰 News Analysis", value=True, scale=1)
                        fundamentals_toggle = gr.Checkbox(label="📊 Fundamentals", value=True, scale=1)
                        market_toggle = gr.Checkbox(label="📈 Market Data", value=True, scale=1)
                        sentiment_toggle = gr.Checkbox(label="💭 Sentiment", value=True, scale=1)
                    
                    config_status = gr.Markdown("✅ All analysis modules enabled", elem_classes=["analysis-status"])
                
                # Chat Interface
                with gr.Group(elem_classes=["chat-container"]):
                    chatbot = gr.Chatbot(
                        height="calc(100vh - 300px)",  # Dynamic height based on viewport
                        show_copy_button=True,
                        avatar_images=(
                            "https://cdn.jsdelivr.net/gh/twitter/twemoji@v14.0.2/assets/72x72/1f464.png",
                            "https://cdn.jsdelivr.net/gh/twitter/twemoji@v14.0.2/assets/72x72/1f916.png",
                        ),
                        bubble_full_width=False,
                        show_label=False,
                        elem_classes=["chatbot-container"],
                        type="messages",  # Updated to new format
                    )
                
                    # Analysis status display
                    analysis_status = gr.Markdown("", visible=False, elem_classes=["analysis-status"])
                    
                    with gr.Row():
                        msg = gr.Textbox(
                            placeholder="Enter your question (e.g., analyze AAPL fundamentals, check NVDA latest news)...", 
                            container=False, 
                            scale=7,
                            show_label=False,
                        )
                        submit = gr.Button("🚀 Send", scale=1, variant="primary")
                        clear = gr.Button("🗑️ Clear", scale=1)
            
            # Update configuration status
            def update_config_status(news, fundamentals, market, sentiment):
                enabled_analysis_types["news"] = news
                enabled_analysis_types["fundamentals"] = fundamentals
                enabled_analysis_types["market"] = market
                enabled_analysis_types["sentiment"] = sentiment
                
                enabled = [k for k, v in enabled_analysis_types.items() if v]
                if len(enabled) == 4:
                    return "✅ All analysis modules enabled"
                elif len(enabled) == 0:
                    return "⚠️ All analysis modules disabled"
                else:
                    return f"📊 Enabled: {', '.join(enabled)}"
            
            # Primary response function (implements the agent loop)
            async def respond(user_msg: str, chat_hist: list, news, fundamentals, market, sentiment):
                if not user_msg.strip():
                    return "", chat_hist, gr.update(visible=False)

                # Update configuration flags
                current_config = {
                    "news": news,
                    "fundamentals": fundamentals,
                    "market": market,
                    "sentiment": sentiment
                }
                update_config_status(news, fundamentals, market, sentiment)

                # Rebuild agent when configuration changes
                if enabled_analysis_types != current_config:
                    nonlocal main_agent
                    enabled_analysis_types.update(current_config)
                    main_agent = agent_builder(enabled_analysis_types)

                # Append user message to history
                chat_hist = chat_hist + [{"role": "user", "content": user_msg}]
                yield "", chat_hist, gr.update(value="🔄 Processing...", visible=True)

                # Track streaming status updates
                current_status = {"value": ""}
                def update_status(msg):
                    current_status["value"] = msg

                # Stream assistant response with full history
                assistant_message = {"role": "assistant", "content": ""}
                chat_hist.append(assistant_message)

                async for partial in self.stream_response(main_agent, user_msg, chat_hist[:-1], update_status):
                    assistant_message["content"] = partial
                    status_msg = current_status["value"]
                    if status_msg:
                        yield "", chat_hist, gr.update(value=status_msg, visible=True)
                    else:
                        yield "", chat_hist, gr.update(visible=False)
                
                # Hide status indicator
                yield "", chat_hist, gr.update(visible=False)
            
            # Clear function
            def clear_history():
                return [], "", gr.update(visible=False)
            
            # Event bindings for config toggles
            for toggle in [news_toggle, fundamentals_toggle, market_toggle, sentiment_toggle]:
                toggle.change(
                    update_config_status, 
                    [news_toggle, fundamentals_toggle, market_toggle, sentiment_toggle], 
                    config_status
                )
            
            # Event bindings for chat
            msg.submit(respond, 
                      [msg, chatbot, news_toggle, fundamentals_toggle, market_toggle, sentiment_toggle], 
                      [msg, chatbot, analysis_status])
            submit.click(respond, 
                        [msg, chatbot, news_toggle, fundamentals_toggle, market_toggle, sentiment_toggle], 
                        [msg, chatbot, analysis_status])
            clear.click(clear_history, outputs=[chatbot, msg, analysis_status])
        
        return demo
