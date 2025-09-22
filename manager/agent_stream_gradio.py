import os
import json
import time
import gradio as gr


from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI



########################################
#              SubAgent 工具           #
########################################

@tool
def sub_search_news(query: str) -> str:
    """子代理工具：模拟在新闻站点搜索并返回结构化结果（mock）。"""
    data = [
        {"site": "NewsSiteA", "title": f"{query} 的最新进展", "url": "https://a.example/item1", "summary": "要点A、B、C"},
        {"site": "NewsSiteB", "title": f"{query} 深度解读", "url": "https://b.example/item2", "summary": "要点1、2、3"},
    ]
    return json.dumps({"source": "news", "query": query, "items": data}, ensure_ascii=False)

@tool
def sub_search_forums(query: str) -> str:
    """子代理工具：模拟在论坛/社媒搜索并返回数据（mock）。"""
    data = [
        {"site": "ForumX", "thread": f"{query} 经验贴", "url": "https://x.example/t/777", "highlights": ["踩坑", "实践", "复盘"]},
        {"site": "ForumY", "thread": f"{query} 工具清单", "url": "https://y.example/t/888", "highlights": ["清单", "链接", "对比"]},
    ]
    return json.dumps({"source": "forums", "query": query, "items": data}, ensure_ascii=False)

@tool
def sub_aggregate(payload: str) -> str:
    """子代理工具：对搜索到的多路数据进行简要聚合（输入为JSON数组字符串）。"""
    try:
        arr = json.loads(payload)
        bullets = []
        for pack in arr:
            kind = pack.get("source")
            for it in pack.get("items", []):
                if kind == "news":
                    bullets.append(f"【新闻】{it['title']}（{it['site']}）=> {it['summary']}")
                else:
                    bullets.append(f"【论坛】{it['thread']}（{it['site']}）=> 亮点：{','.join(it['highlights'])}")
        summary = "；".join(bullets[:6])
        return json.dumps({"summary": summary, "count": len(bullets)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

########################################
#           Main Agent 工具            #
########################################

@tool
def read_file(path: str) -> str:
    """读取文本文件内容。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"[read_file错误] {e}"

@tool
def write_file(spec: str) -> str:
    """写入文本文件。输入为JSON：{"path": "...", "content": "..."}。"""
    try:
        p = json.loads(spec)
        path = p["path"]
        content = p.get("content", "")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"[write_file成功] 已写入 {path}（{len(content)}字）"
    except Exception as e:
        return f"[write_file错误] {e}"

########################################
#             SubAgent 构建            #
########################################

def build_subagent():
    """SubAgent：负责"搜索&整理"。Main Agent 通过工具调用它。"""
    sub_tools = [sub_search_news, sub_search_forums, sub_aggregate]
    
    sub_prompt = ChatPromptTemplate.from_messages([
        ("system", "你是SubAgent，擅长在不同站点搜索并进行要点整理。请根据用户意图合理调用工具，最后只输出简洁结构化结果（面向Main Agent）。"),
        MessagesPlaceholder("chat_history"),
        ("user", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0.3, api_key='') 
    sub_agent = create_tool_calling_agent(llm, sub_tools, sub_prompt)
    sub_exec = AgentExecutor(agent=sub_agent, tools=sub_tools, verbose=False, handle_parsing_errors=True)
    return sub_exec

# 将 SubAgent 暴露为 Main Agent 的一个工具
subagent_executor = build_subagent()

@tool
def call_subagent(task: str) -> str:
    """Main Agent 的工具：把任务转发给 SubAgent。"""
    try:
        resp = subagent_executor.invoke({"input": task, "chat_history": []})
        return resp.get("output") or json.dumps(resp, ensure_ascii=False)
    except Exception as e:
        return f"[SubAgent调用错误] {e}"

########################################
#             Main Agent 构建          #
########################################

def build_main_agent():
    """Main Agent：与用户对话、记忆上下文、读写文件、调用 SubAgent。"""
    tools = [read_file, write_file, call_subagent]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "你是Main Agent（顶级AI公司的高级Python算法工程师形象），会与用户自然对话。"
         "目标：理解用户需求 -> 合理使用工具（含SubAgent）-> 给出清晰汇报。"
         "注意：\n"
         "1) 若涉及信息检索，优先通过 call_subagent 工具把检索与整理交给子代理。\n"
         "2) 文件相关使用 read_file / write_file。\n"
         "3) 回答要简洁分点。\n"
         "4) 所有外部数据允许Mock，重点展示能力链路。"
         "5) 始终用中文回复。"),
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
#           流式对话函数               #
########################################

def stream_agent_response(agent_executor: AgentExecutor, user_input: str):
    """流式输出 Agent 响应"""
    try:
        # 同步调用 Agent
        response = agent_executor.invoke({"input": user_input})
        output = response.get("output", "抱歉，没有获取到响应。")
        
        # 逐字符流式输出
        partial = ""
        for char in output:
            partial += char
            yield partial
            # 在标点符号处稍作停顿
            if char in "。！？，；：":
                time.sleep(0.2)
            else:
                time.sleep(0.03)  # 每个字符的延迟
                
    except Exception as e:
        yield f"[错误] {str(e)}"

########################################
#             Gradio 界面              #
########################################

CSS = """
.main-container {max-width: 1200px; margin: 0 auto; padding: 20px;}
.header-text {text-align: center; margin-bottom: 20px; color: #2c3e50;}
"""

def create_chatbot():
    # 全局 Agent 实例
    main_agent = build_main_agent()
    
    with gr.Blocks(title="Market Lens AI Agent", css=CSS) as demo:
        with gr.Column(elem_classes=["main-container"]):
            gr.Markdown("# 🤖 Market Lens AI 智能助手", elem_classes=["header-text"])
            gr.Markdown("*基于多智能体架构的市场分析与信息检索助手*")
            
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
                    placeholder="请输入您的问题（例如：帮我查询 'LangChain 最佳实践' 的最新信息）...", 
                    container=False, 
                    scale=7
                )
                submit = gr.Button("发送", scale=1, variant="primary")
                clear = gr.Button("清空", scale=1)
        
        # 主响应函数（流式）
        def respond(user_msg: str, chat_hist: list):
            if not user_msg.strip():
                return "", chat_hist
            
            # 添加用户消息
            chat_hist = chat_hist + [(user_msg, None)]
            yield "", chat_hist
            
            # 流式生成响应
            for partial in stream_agent_response(main_agent, user_msg):
                chat_hist[-1] = (user_msg, partial)
                yield "", chat_hist
        
        # 清空函数
        def clear_history():
            return [], ""
        
        # 事件绑定
        msg.submit(respond, [msg, chatbot], [msg, chatbot])
        submit.click(respond, [msg, chatbot], [msg, chatbot])
        clear.click(clear_history, outputs=[chatbot, msg])
    
    return demo

########################################
#               启动应用               #
########################################

if __name__ == "__main__":
    demo = create_chatbot()
    demo.launch(
        server_name="0.0.0.0", 
        server_port=7860, 
        share=False, 
        debug=True
    )
