import os
import json
import time
import asyncio
import gradio as gr
import sys
from shcema import StockAnalysisInput

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'analysts'))

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI


# Import the real financial analysis Agent
from analyst import analyze_for_manager



# Removed redundant analyze_stock function, implementing all functionality directly in call_analyst

########################################
#           Main Agent Tools           #
########################################

@tool
def read_file(path: str) -> str:
    """Read text file content."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"[read_file error] {e}"

@tool
def write_file(spec: str) -> str:
    """Write text file. Input as JSON: {"path": "...", "content": "..."}."""
    try:
        p = json.loads(spec)
        path = p["path"]
        content = p.get("content", "")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"[write_file success] Written to {path} ({len(content)} chars)"
    except Exception as e:
        return f"[write_file error] {e}"

########################################
#        Stock Analysis Tool           #
########################################



@tool(args_schema=StockAnalysisInput)
def analyze_stock(ticker: str, intent: str = "news") -> str:
    """Professional stock analysis tool.
    
    Args:
        ticker: Stock ticker symbol (e.g., AAPL, NVDA)
        intent: Analysis type - news, fundamentals, market, sentiment
    """
    try:
        # Call the financial analysis Agent directly
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(analyze_for_manager(ticker.upper(), intent))
        loop.close()
        
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Analysis failed: {str(e)}"}, ensure_ascii=False)

########################################
#        Main Agent Configuration      #
########################################

def build_main_agent():
    """Main Agent: Manages conversations, maintains context, handles files, and calls financial analysis experts."""
    tools = [read_file, write_file, analyze_stock]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "You are the Market Lens AI Main Agent, a professional financial market analysis assistant. "
         "Goal: Understand user's financial analysis needs -> Call professional analysis tools -> Provide clear market insights. "
         "Guidelines:\n"
         "1) Use the analyze_stock tool for stock analysis, which automatically identifies tickers and analysis intent.\n"
         "2) Use read_file / write_file for file operations.\n"
         "3) Provide professional, accurate, and insightful responses.\n"
         "4) analyze_stock supports: news, fundamentals, market, sentiment analysis.\n"
         "5) Always respond in Chinese."),
        MessagesPlaceholder("chat_history"),
        ("user", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0.3, api_key='') 
    agent = create_tool_calling_agent(llm, tools, prompt)
    
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        memory=memory,
        verbose=False,
        handle_parsing_errors=True,
    )
    return executor

########################################
#        Streaming Response Function   #
########################################

def stream_agent_response(agent_executor: AgentExecutor, user_input: str):
    """Stream Agent response with typewriter effect"""
    try:
        # Synchronously call Agent
        response = agent_executor.invoke({"input": user_input})
        output = response.get("output", "Sorry, no response received.")
        
        # Stream output character by character
        partial = ""
        for char in output:
            partial += char
            yield partial
            # Pause slightly at punctuation marks
            if char in "。！？，；：.!?,;:":
                time.sleep(0.2)
            else:
                time.sleep(0.03)  # Delay per character
                
    except Exception as e:
        yield f"[Error] {str(e)}"

########################################
#            Gradio Interface          #
########################################

CSS = """
.main-container {max-width: 1200px; margin: 0 auto; padding: 20px;}
.header-text {text-align: center; margin-bottom: 20px; color: #2c3e50;}
"""

def create_chatbot():
    # Global Agent instance
    main_agent = build_main_agent()
    
    with gr.Blocks(title="Market Lens AI Agent", css=CSS) as demo:
        with gr.Column(elem_classes=["main-container"]):
            gr.Markdown("# 🤖 Market Lens AI Financial Analysis Assistant", elem_classes=["header-text"])
            gr.Markdown("*Professional Stock Market Analysis & Investment Insights Platform*")
            
            chatbot = gr.Chatbot(
                height=500,
                show_copy_button=True,
                avatar_images=(
                    "https://cdn.jsdelivr.net/gh/twitter/twemoji@v14.0.2/assets/72x72/1f464.png",
                    "https://cdn.jsdelivr.net/gh/twitter/twemoji@v14.0.2/assets/72x72/1f916.png",
                ),
            )
            
            with gr.Row():
                msg = gr.Textbox(
                    placeholder="Enter your question (e.g., analyze AAPL fundamentals, check NVDA latest news)...", 
                    container=False, 
                    scale=7
                )
                submit = gr.Button("Send", scale=1, variant="primary")
                clear = gr.Button("Clear", scale=1)
        
        # Main response function (streaming)
        def respond(user_msg: str, chat_hist: list):
            if not user_msg.strip():
                return "", chat_hist
            
            # Add user message
            chat_hist = chat_hist + [(user_msg, None)]
            yield "", chat_hist
            
            # Stream response generation
            for partial in stream_agent_response(main_agent, user_msg):
                chat_hist[-1] = (user_msg, partial)
                yield "", chat_hist
        
        # Clear function
        def clear_history():
            return [], ""
        
        # Event bindings
        msg.submit(respond, [msg, chatbot], [msg, chatbot])
        submit.click(respond, [msg, chatbot], [msg, chatbot])
        clear.click(clear_history, outputs=[chatbot, msg])
    
    return demo

########################################
#            Launch Application        #
########################################

if __name__ == "__main__":
    demo = create_chatbot()
    demo.launch(
        server_name="0.0.0.0", 
        server_port=7860, 
        share=False, 
        debug=True
    )
