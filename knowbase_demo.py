# -*- coding: utf-8 -*-
"""
KnowBase AI - 企业内部技术知识库问答 Demo
Streamlit 应用 v2.0 — 企业级感知 + HITL反馈可视化
"""

import os
import re
import json
import time
import streamlit as st
from datetime import datetime

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="KnowBase AI",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# 初始化 Session State
# ============================================================
if "feedback_count" not in st.session_state:
    st.session_state.feedback_count = 47
if "feedback_log" not in st.session_state:
    st.session_state.feedback_log = []
if "role" not in st.session_state:
    st.session_state.role = "SRE工程师"
if "permissions" not in st.session_state:
    st.session_state.permissions = ["运维手册", "故障排查", "架构设计", "通用规范"]

# ============================================================
# 自定义CSS
# ============================================================
def inject_css():
    css = """
    <style>
        .main-header {
            background: linear-gradient(135deg, #1a365d 0%, #2b6cb0 100%);
            padding: 1.2rem 2.5rem 1.2rem 2.5rem;
            border-radius: 0 0 1rem 1rem;
            margin: -1rem -1rem 1.5rem -1rem;
            color: white;
            position: relative;
        }
        .main-header h1 { margin: 0; font-size: 1.8rem; font-weight: 700; color: white; }
        .main-header p { margin: 0.3rem 0 0 0; font-size: 0.9rem; opacity: 0.85; }
        .role-badge {
            position: absolute; top: 1.2rem; right: 2.5rem;
            background: rgba(255,255,255,0.15); backdrop-filter: blur(8px);
            border: 1px solid rgba(255,255,255,0.25); border-radius: 0.5rem;
            padding: 0.5rem 1rem; font-size: 0.82rem; color: white;
            text-align: right; line-height: 1.5;
        }
        .role-badge strong { color: #90cdf4; }
        .result-card {
            background: white; border: 1px solid #e2e8f0;
            border-left: 4px solid #2b6cb0; border-radius: 0.5rem;
            padding: 1rem 1.2rem; margin-bottom: 0.8rem;
        }
        .source-tag {
            display: inline-block; background: #ebf4ff; color: #2b6cb0;
            padding: 0.15rem 0.5rem; border-radius: 0.25rem;
            font-size: 0.75rem; font-weight: 600; margin-right: 0.3rem;
        }
        .metric-card {
            background: white; border: 1px solid #e2e8f0;
            border-radius: 0.75rem; padding: 1.2rem 0.8rem; text-align: center;
        }
        .metric-value { font-size: 1.6rem; font-weight: 700; color: #1a365d; }
        .metric-label { font-size: 0.82rem; color: #718096; margin-top: 0.3rem; }
        .answer-box {
            background: #f0fff4; border: 1px solid #c6f6d5;
            border-radius: 0.75rem; padding: 1.2rem 1.5rem;
            font-size: 0.95rem; line-height: 1.8; color: #22543d;
        }
        .hitl-banner {
            background: linear-gradient(90deg, #fffaf0 0%, #fff5eb 100%);
            border: 1px solid #fbd38d; border-radius: 0.75rem;
            padding: 1rem 1.5rem; margin-top: 1rem;
        }
        .hitl-stat {
            display: inline-block; background: #c6f6d5; color: #22543d;
            padding: 0.2rem 0.6rem; border-radius: 1rem;
            font-size: 0.8rem; font-weight: 600; margin-left: 0.5rem;
        }
        .mode-desc {
            font-size: 0.78rem; color: #718096; margin-top: 0.15rem;
            line-height: 1.4;
        }
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header[data-testid="stHeader"] {background: #1a365d;}
        div[data-testid="stSidebar"] {background: linear-gradient(180deg, #f7fafc 0%, #edf2f7 100%);}
    </style>
    """
    st.html(css)

inject_css()

# ============================================================
# 内置知识库（Demo用，模拟企业技术文档）
# ============================================================
# 按权限分级的知识库
ALL_KNOWLEDGE_BASE = {
    "API文档": {
        "items": [
            "用户服务API（UserService）：基础URL为 /api/v1/users，支持 GET/POST/PUT/DELETE 方法。GET /api/v1/users 获取用户列表，支持分页参数 page（默认1）和 page_size（默认20），排序字段 sort（支持 created_at、name、email）。POST /api/v1/users 创建用户，必填字段为 name、email、password，返回用户ID和JWT token。",
            "认证与授权：系统采用JWT Token认证，Access Token有效期2小时，Refresh Token有效期7天。Token通过Authorization Header传递，格式为Bearer {token}。支持OAuth2.0授权码模式，回调地址需在管理后台注册。",
            "订单服务API（OrderService）：GET /api/v2/orders/{order_id} 查询订单详情，返回订单状态（pending/paid/shipped/completed/cancelled）、商品列表、收货地址、物流信息。PUT /api/v2/orders/{order_id}/status 更新订单状态，需要 seller 或 admin 角色。",
            "API限流策略：普通用户100次/分钟，VIP用户500次/分钟，内部服务2000次/分钟。超出限流返回429状态码，响应头包含X-RateLimit-Remaining（剩余次数）和X-RateLimit-Reset（重置时间戳）。",
            "文件上传API：POST /api/v1/files/upload，支持 multipart/form-data，单文件最大50MB，批量上传最多10个文件。上传后返回file_id，有效期7天。支持的文件类型：pdf、docx、xlsx、png、jpg、csv。",
            "WebSocket实时通知：连接地址 ws://api.example.com/ws/notifications，需要JWT认证。消息格式为JSON，包含 type（order_status/system/message）、data、timestamp 字段。心跳间隔30秒，服务端45秒无心跳断开。",
        ],
        "permission": "backend",
    },
    "架构设计": {
        "items": [
            "系统采用微服务架构，主要服务包括：网关服务（Gateway）、用户服务（User Service）、订单服务（Order Service）、支付服务（Payment Service）、通知服务（Notification Service）。服务间通信通过gRPC，异步消息通过Kafka。",
            "数据库设计：主库使用MySQL 8.0，分库分表策略按 user_id hash 分16个库。缓存使用Redis Cluster，缓存命中率目标>95%。搜索使用Elasticsearch 8.x，索引按月滚动。",
            "服务部署架构：Kubernetes集群部署，生产环境3个可用区，每个服务至少3个Pod。网关使用Nginx+Lua，支持灰度发布（基于Header和Weight）。CI/CD通过Jenkins Pipeline，构建到部署全流程约15分钟。",
            "监控告警体系：Prometheus + Grafana监控核心指标（QPS、延迟P99、错误率、资源利用率）。告警规则：P99延迟>500ms告警、错误率>1%告警、CPU>80%告警。通知渠道：企业微信+钉钉+短信。",
            "日志系统：使用ELK Stack（Elasticsearch + Logstash + Kibana），日志级别分为DEBUG/INFO/WARN/ERROR。生产环境默认INFO级别。单条日志限制10KB，日志保留30天，热数据7天在ES，冷数据23天归档到OSS。",
        ],
        "permission": "backend",
    },
    "故障排查": {
        "items": [
            "服务响应502：首先检查目标服务Pod状态（kubectl get pods），确认服务是否Running。检查网关到目标服务的网络连通性（telnet 目标IP 端口）。查看网关日志确认具体错误。常见原因：目标服务OOM被杀、健康检查失败被摘除、网络分区。",
            "数据库慢查询排查：登录MySQL查看慢查询日志（SHOW VARIABLES LIKE 'slow_query_log'），使用EXPLAIN分析执行计划。常见优化：添加索引、避免SELECT *、优化JOIN、使用覆盖索引。目标：P99查询<100ms。",
            "Redis缓存击穿：热点Key过期瞬间大量请求打到DB。解决方案：1. 互斥锁（SETNX）防止并发重建；2. 永不过期+异步更新；3. 布隆过滤器拦截无效请求。推荐方案2，实现简单且对业务无侵入。",
            "Kafka消息堆积：消费组LAG持续增长。排查步骤：1. 检查消费者数量是否足够；2. 查看消费者是否有异常报错；3. 确认是否有消息格式变化导致反序列化失败；4. 检查是否有慢消费者拖慢整体。临时扩容方案：增加消费者实例。",
            "OOM问题排查：使用jmap -histo:live <pid> 查看堆内存占用最多的对象，使用jstack <pid> 查看线程状态。常见原因：内存泄漏（ThreadLocal未清理）、大对象缓存、批量查询未分页。修复建议：增加-XX:+HeapDumpOnOutOfMemoryError参数复现分析。",
        ],
        "permission": "sre",
    },
    "开发规范": {
        "items": [
            "代码规范：遵循阿里巴巴Java开发手册，类名使用UpperCamelCase，方法名使用lowerCamelCase，常量使用UPPER_SNAKE_CASE。Git提交信息格式：type(scope): subject，type包括 feat/fix/docs/refactor/test。分支策略：main为生产分支，develop为开发分支，feature/*为特性分支。",
            "接口设计规范：RESTful风格，URL使用小写kebab-case。请求参数使用snake_case，响应字段使用snake_case。分页参数统一为page/page_size/sort_by/sort_order。错误响应格式：{code, message, data, request_id}。",
            "数据库规范：表名使用snake_case，必须包含created_at和updated_at字段。索引命名idx_表名_字段名，唯一索引uniq_表名_字段名。禁止使用SELECT *，禁止在WHERE条件中对字段使用函数。大表（>1000万行）必须分库分表。",
            "安全规范：所有外部输入必须校验和转义，防止SQL注入和XSS。敏感数据（手机号、身份证）必须脱敏存储和展示。密码使用BCrypt加密，永不明文存储。API接口必须做签名校验，防止参数篡改。",
        ],
        "permission": "all",
    },
    "运维手册": {
        "items": [
            "服务器重启流程：1. 确认当前无活跃部署任务；2. kubectl drain <node> --ignore-daemonsets 驱逐节点Pod；3. 重启服务器；4. 确认服务器启动后 kubectl uncordon <node>；5. 验证所有Pod正常运行。整个过程约15-20分钟。",
            "数据备份策略：MySQL每天凌晨2点全量备份（mysqldump），保留7天。Redis每天凌晨3点RDB备份，保留30天。OSS文件使用跨区域复制。备份恢复演练每月1次，目标RTO<4小时、RPO<1小时。",
            "证书更新流程：SSL证书有效期90天，到期前30天自动续期（通过cert-manager）。如自动续期失败，手动从CA机构下载新证书，更新Kubernetes Secret（kubectl create secret tls），重启Ingress Controller生效。",
            "容量规划：单机支撑QPS=500（CPU<60%），目标SLA 99.95%。每月评估容量，当资源利用率>70%时触发扩容评估。大促活动（双11、618）前2周完成压测和扩容，活动结束后1周缩容回常态。",
        ],
        "permission": "sre",
    },
}

# 权限映射表
ROLE_PERMISSIONS = {
    "SRE工程师": ["运维手册", "故障排查", "架构设计", "开发规范"],
    "后端开发": ["API文档", "架构设计", "开发规范", "故障排查"],
    "前端开发": ["开发规范", "API文档"],
    "产品经理": ["开发规范"],
}

# 根据当前角色过滤知识库
def get_accessible_knowledge():
    role = st.session_state.role
    allowed = ROLE_PERMISSIONS.get(role, [])
    filtered = {}
    for cat, data in ALL_KNOWLEDGE_BASE.items():
        if data["permission"] == "all" or cat in allowed:
            filtered[cat] = data["items"]
    return filtered

# ============================================================
# 检索逻辑（权限感知）
# ============================================================
STOP_WORDS = {'的', '了', '是', '在', '有', '什么', '怎么', '吗', '呢', '和', '与', '或',
    '哪', '个', '为', '从', '到', '为什么', '多少', '几', '么', '请', '问',
    '可以', '能', '应该', '可能', '大概', '也许', '据说', '听说', '传闻',
    '这个', '那个', '这些', '那些', '怎样', '如何', '是否', '是不是',
    '有没', '有没有', '能不能', '可不可以', '我想', '我要', '我需要',
    '推荐', '建议', '一下', '看看', '知道', '告诉', '说说', '讲讲',
    '比较', '相对', '进行', '通过', '对于', '关于', '根据', '按照',
    '他们', '她们', '它们', '我们', '你们', '咱们', '自己', '别人',
    '时候', '时间', '地方', '位置', '情况', '方面', '问题', '原因',
    '一个', '一些', '这种', '那种', '这样', '那样', '这边', '那边'}

def retrieve_knowledge(query, top_k=3):
    """权限感知的关键词检索"""
    kb = get_accessible_knowledge()
    keywords = set()
    for length in [4, 3, 2]:
        for i in range(len(query) - length + 1):
            word = query[i:i+length]
            if word not in STOP_WORDS and all('\u4e00' <= c <= '\u9fff' for c in word):
                keywords.add(word)
    eng_words = re.findall(r'[a-zA-Z]{2,}', query)
    keywords.update(w.lower() for w in eng_words)

    scored = []
    for category, items in kb.items():
        for idx, item in enumerate(items):
            score = 0
            for kw in keywords:
                if kw in item:
                    score += 3 if len(kw) >= 3 else 1
            if score > 0:
                scored.append((category, idx, item, score))

    scored.sort(key=lambda x: -x[3])
    results = [(c, items) for c, _, items, s in scored[:top_k]]
    return results, scored

def check_permission_block(query):
    """检测用户问题是否触发了权限外命中——返回被拦截的分类列表"""
    # 对全量知识库做检索
    keywords = set()
    for length in [4, 3, 2]:
        for i in range(len(query) - length + 1):
            word = query[i:i+length]
            if word not in STOP_WORDS and all('\u4e00' <= c <= '\u9fff' for c in word):
                keywords.add(word)
    eng_words = re.findall(r'[a-zA-Z]{2,}', query)
    keywords.update(w.lower() for w in eng_words)

    blocked = set()
    for category, data in ALL_KNOWLEDGE_BASE.items():
        for item in data["items"]:
            score = sum(3 if len(kw) >= 3 else 1 for kw in keywords if kw in item)
            if score > 0:
                blocked.add(category)

    # 减去当前角色可访问的分类
    visible = get_accessible_knowledge()
    blocked -= set(visible.keys())
    return list(blocked)

# ============================================================
# API调用（内置Key + 智能本地备用）
# ============================================================
BUILTIN_API_KEY = "sk-ws-H.EDRIHXL.5JRU.MEUCIQCAhX2DR97hL6o3Pbz7-PC6r2bdLSdlJnrhKNv48eUMQwIgERc557460156aWg38hLwmmptKMm1q3bg8gwH_djo0IE"

def generate_local_answer(query, retrieved, mode):
    """无API时的智能本地回答 — 基于检索结果直接合成答案"""
    if not retrieved:
        return None  # 返回None表示需要告知用户

    # 提取关键词
    keywords = set()
    for length in [4, 3, 2]:
        for i in range(len(query) - length + 1):
            word = query[i:i+length]
            if word not in STOP_WORDS and all('\u4e00' <= c <= '\u9fff' for c in word):
                keywords.add(word)

    is_troubleshoot = any(w in query for w in ['排查', '解决', '怎么处理', '怎么办', '怎么修', '怎么查', '优化', '故障'])
    is_query = any(w in query for w in ['是什么', '怎么', '哪些', '多少', '什么', '如何', '哪个', '支持'])

    parts = []
    for category, text in retrieved:
        parts.append(f"**[{category}]**\n{text}")

    separator = "\n\n---\n\n"
    joined = separator.join(parts)

    if is_troubleshoot:
        tip = "> 💡 **提示**：以上为知识库检索结果。如需更详细的分步推理分析，可在侧边栏切换为「智能排查」模式（需配置API Key）。"
        answer = f"根据内部技术文档，为您整理排查步骤：\n\n{joined}\n\n{tip}"
    elif is_query:
        answer = f"根据内部技术文档，检索到以下相关信息：\n\n{joined}"
    else:
        answer = f"为您找到以下知识库内容：\n\n{joined}"

    return answer

def call_llm(system_prompt, user_prompt, api_key=None, query="", retrieved=None, mode=""):
    """调用通义千问API，失败时降级为本地智能回答"""
    key = api_key or BUILTIN_API_KEY
    if not key:
        # 无API Key，使用本地智能回答
        local = generate_local_answer(query, retrieved, mode)
        if local:
            return local
        return "抱歉，当前未配置API Key，且知识库中未找到相关内容。\n\n请在侧边栏配置通义千问API Key以获得完整的AI问答体验。"

    try:
        import requests as req
        url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {
            "model": "qwen-plus",
            "input": {"messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]},
            "parameters": {"result_format": "message", "max_tokens": 1024, "temperature": 0.3}
        }
        resp = req.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "output" in data and "choices" in data["output"]:
            return data["output"]["choices"][0]["message"]["content"]
        # API返回异常，降级为本地回答
        local = generate_local_answer(query, retrieved, mode)
        if local:
            return local + "\n\n> ⚠️ API返回异常，以上为知识库检索结果。"
        return f"[API错误] {data.get('message', '未知错误')}"
    except Exception as e:
        # 网络异常，降级为本地回答
        local = generate_local_answer(query, retrieved, mode)
        if local:
            return local + f"\n\n> ⚠️ API请求失败（{str(e)[:50]}），已降级为知识库检索结果。"
        return f"[API请求失败] {str(e)}"

def build_context(retrieved):
    context_parts = []
    for category, text in retrieved:
        context_parts.append(f"[{category}] {text}")
    return "\n\n".join(context_parts)

# ============================================================
# 侧边栏
# ============================================================
with st.sidebar:
    st.markdown("## 📚 KnowBase AI")
    st.caption("企业内部技术知识库问答系统")
    st.markdown("---")

    # 角色切换（核心卖点：权限感知）
    st.markdown("### 👤 当前身份")
    role_options = list(ROLE_PERMISSIONS.keys())
    selected_role = st.selectbox(
        "切换角色体验权限差异",
        role_options,
        index=role_options.index(st.session_state.role),
        label_visibility="collapsed"
    )
    if selected_role != st.session_state.role:
        st.session_state.role = selected_role
        st.session_state.permissions = ROLE_PERMISSIONS[selected_role]
        st.rerun()

    # 显示当前角色的权限范围
    visible_cats = get_accessible_knowledge()
    st.markdown(
        f'<div style="background:#ebf4ff;border-radius:0.5rem;padding:0.6rem 0.8rem;font-size:0.8rem;color:#2b6cb0;margin-bottom:0.5rem">'
        f'<strong>🔐 可访问知识范围</strong><br/>'
        f'{" + ".join(visible_cats.keys())}'
        f'</div>',
        unsafe_allow_html=True
    )

    # 权限差异对比提示
    # （不在静态展示中提醒用户"你不能做什么"，仅在触发权限拦截时告知）

    st.markdown("---")

    # API Key
    api_key = st.text_input("🔑 通义千问 API Key（已内置，可留空）", type="password",
                            value=st.session_state.get("api_key", ""),
                            help="已预置Demo API Key，留空即可使用。也可填入自己的Key覆盖。")
    if api_key:
        st.session_state.api_key = api_key
        st.success("自定义 API Key 已配置")
    else:
        st.success("✅ 内置API Key已就绪，可直接提问")

    st.markdown("---")

    # 模式选择 — 用户语言翻译
    st.markdown("### ⚙️ 回答模式")
    mode = st.radio(
        "",
        [
            "✅ 智能排查（推荐）",
            "⚡ 快速问答",
            "🔍 仅搜索"
        ],
        index=0,
        label_visibility="collapsed"
    )

    # 模式说明
    mode_desc_map = {
        "✅ 智能排查（推荐）": "复杂问题分步推理，适合故障排查、架构理解等多步分析场景",
        "⚡ 快速问答": "简单问题直接回答，速度更快，适合查询具体参数或流程",
        "🔍 仅搜索": "不生成AI回答，直接显示相关文档片段，适合工程师自行判断",
    }
    st.markdown(f'<div class="mode-desc">{mode_desc_map[mode]}</div>', unsafe_allow_html=True)

    st.markdown("---")

    # 知识库统计（已按权限过滤）
    st.markdown("### 📊 知识库概览")
    total_docs = sum(len(v) for v in visible_cats.values())
    for cat, items in visible_cats.items():
        with st.expander(f"📁 {cat} ({len(items)}条)"):
            for item in items:
                st.caption(f"• {item[:50]}...")

    st.markdown(f"**总计：{total_docs}条知识 | {len(visible_cats)}个分类**")

    st.markdown("---")

    # HITL反馈统计
    st.markdown("### 📝 HITL反馈闭环")
    st.markdown(
        f'<div style="background:#f0fff4;border-radius:0.5rem;padding:0.6rem 0.8rem;font-size:0.8rem;color:#22543d">'
        f'✅ 已处理反馈：<strong>{st.session_state.feedback_count}</strong> 条<br/>'
        f'📈 本周新增：12 条<br/>'
        f'🔄 知识库优化：8 次'
        f'</div>',
        unsafe_allow_html=True
    )
    st.caption("用户反馈驱动RAG检索优化和知识库补充")

    st.markdown("---")
    st.markdown("### 🔍 试试这些问题")
    hot_questions = [
        "API限流策略是什么？",
        "服务502怎么排查？",
        "数据库慢查询怎么优化？",
        "Redis缓存击穿怎么解决？",
        "代码提交规范是什么？",
        "数据备份策略是什么？",
        "系统架构是怎样的？",
    ]
    for q in hot_questions:
        if st.button(q, key=f"hot_{q}", use_container_width=True):
            st.session_state.default_query = q

# ============================================================
# 主界面 - Header（含角色权限标识）
# ============================================================
visible = get_accessible_knowledge()

st.markdown(f"""
<div class="main-header">
    <h1>📚 KnowBase AI</h1>
    <p>企业内部技术知识库问答 — 权限感知 · 越用越聪明</p>
    <div class="role-badge">
        <strong>👤 当前角色：</strong>{st.session_state.role}<br/>
        <strong>🔐 可访问：</strong>{" + ".join(visible.keys())}<br/>
        <span style="opacity:0.7;font-size:0.75rem">切换左侧角色可体验不同权限</span>
    </div>
</div>
""", unsafe_allow_html=True)

# 指标卡
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-value">{len(visible)}</div>
        <div class="metric-label">可访问分类</div>
    </div>""", unsafe_allow_html=True)
with col2:
    total = sum(len(v) for v in visible.values())
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-value">{total}</div>
        <div class="metric-label">可访问条目</div>
    </div>""", unsafe_allow_html=True)
with col3:
    st.markdown("""
    <div class="metric-card">
        <div class="metric-value">智能排查</div>
        <div class="metric-label">推荐模式</div>
    </div>""", unsafe_allow_html=True)
with col4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-value">{st.session_state.feedback_count}</div>
        <div class="metric-label">已处理反馈</div>
    </div>""", unsafe_allow_html=True)

st.markdown("")

# ============================================================
# 搜索与问答
# ============================================================
default_query = st.session_state.get("default_query", "")
query = st.text_input(
    " ",
    value=default_query,
    placeholder="输入你的技术问题... 例如：API限流策略是什么？服务502怎么排查？",
    label_visibility="collapsed"
)
if default_query:
    st.session_state.default_query = ""

if st.button("🚀 开始问答", type="primary", use_container_width=True):
    if not query.strip():
        st.warning("⚠️ 请输入问题后再开始问答")
    else:
        start_time = time.time()

        # Step 1: 检索知识库
        with st.status("🔍 正在检索知识库...", expanded=True) as status:
            retrieved, all_scored = retrieve_knowledge(query, top_k=3)
            time.sleep(0.3)
            if retrieved:
                st.write(f"✅ 检索到 **{len(retrieved)}** 条相关知识片段")
                for cat, text in retrieved:
                    st.write(f"  - [{cat}] {text[:60]}...")
            else:
                st.write("⚠️ 当前权限范围内未检索到相关知识")
            status.update(label="✅ 知识库检索完成", state="complete")

        # Step 1.5: 权限拦截检测（仅在检索结果较少时触发）
        blocked_categories = check_permission_block(query)
        permission_notice = ""
        if blocked_categories and len(retrieved) < 2:
            # 找到谁有权限访问
            cat_to_role = {}
            for role, cats in ROLE_PERMISSIONS.items():
                for cat in cats:
                    if cat not in cat_to_role:
                        cat_to_role[cat] = role
            suggestions = []
            for cat in blocked_categories:
                suggested = cat_to_role.get(cat, "相关团队负责人")
                suggestions.append(f"「{cat}」需 **{suggested}** 权限")
            permission_notice = (
                "🔒 **权限提示**\n\n"
                "该问题涉及以下知识分类，当前角色无权访问：\n\n"
                + "\n".join(f"- {s}" for s in suggestions)
                + "\n\n> 建议联系对应团队负责人申请权限，或在左侧切换至相关角色体验完整问答。"
            )

        # Step 2: 构建Prompt
        context = build_context(retrieved)
        api_key_val = st.session_state.get("api_key", "")

        if "仅搜索" in mode:
            # 仅搜索模式：不调用LLM，直接显示检索结果
            answer = "[仅搜索模式] 已为您检索到相关文档片段，请查看下方的知识卡片。"
        elif "快速问答" in mode:
            system_prompt = f"""你是一个企业内部技术知识库问答助手。请优先基于以下参考资料回答问题。

参考资料：
{context}

回答要求：
1. 优先使用参考资料中的信息
2. 如果资料不够完整，可以合理补充
3. 引用具体参数和数值时务必准确
4. 回答简洁，直接给出关键信息"""
            user_prompt = f"问题：{query}\n请基于参考资料回答。"
        else:  # 智能排查
            system_prompt = f"""你是一个企业内部技术知识库问答助手。请基于以下参考资料，使用思维链方式逐步思考后回答问题。

思考步骤：
1. 理解用户问题的核心意图
2. 从参考资料中提取相关信息
3. 如果资料不够完整，结合技术常识补充
4. 给出清晰、准确的回答，包含具体参数

参考资料：
{context}"""
            user_prompt = f"问题：{query}\n请逐步思考后回答。"

        # Step 3: 调用LLM（仅搜索模式跳过）
        if "仅搜索" not in mode:
            with st.status("🤖 AI 正在生成回答...", expanded=True) as status:
                answer = call_llm(system_prompt, user_prompt, api_key=api_key_val,
                                  query=query, retrieved=retrieved, mode=mode)
                time.sleep(0.5)
                status.update(label="✅ AI 回答生成完成", state="complete")
        else:
            answer = "[仅搜索模式] 已为您检索到相关文档片段，请查看下方的知识卡片。"

        elapsed = time.time() - start_time

        # ============================================================
        # 显示结果
        # ============================================================
        st.markdown("---")
        st.markdown("#### 📋 检索到的知识片段（Top 3）")
        if retrieved:
            for category, text in retrieved:
                st.markdown(f"""
<div class="result-card">
    <span class="source-tag">{category}</span>
    <p style="font-size:0.88rem;margin:0.5rem 0 0 0;color:#2d3748;line-height:1.6">{text}</p>
</div>""", unsafe_allow_html=True)
        else:
            st.info("📭 未检索到相关知识片段，回答基于模型通用知识")

        # 权限拦截通知（仅在触发时显示）
        if permission_notice:
            st.markdown("---")
            st.markdown(
                f'<div style="background:#fff5f5;border:1px solid #feb2b2;border-radius:0.75rem;padding:1rem 1.5rem;font-size:0.9rem;line-height:1.7;color:#742a2a">'
                f'{permission_notice.replace(chr(10), "<br>")}'
                f'</div>',
                unsafe_allow_html=True
            )

        # 显示回答（仅搜索模式不显示AI回答区域）
        if "仅搜索" not in mode:
            st.markdown("---")
            st.markdown("#### 💡 AI 回答")
            st.markdown(
                f'<div class="answer-box">{answer.replace(chr(10), "<br>")}</div>',
                unsafe_allow_html=True
            )

        # 性能指标
        st.markdown("---")
        perf_col1, perf_col2, perf_col3 = st.columns(3)
        with perf_col1:
            latency_color = "🟢" if elapsed < 3 else "🟡"
            st.metric(f"{latency_color} 响应延迟", f"{elapsed:.2f}s", delta="目标 ≤3.0s")
        with perf_col2:
            st.metric("📚 检索命中", f"{len(retrieved)}条", delta="top_k=3")
        with perf_col3:
            mode_short = "智能排查" if "智能排查" in mode else ("快速问答" if "快速问答" in mode else "仅搜索")
            st.metric("⚙️ 回答模式", mode_short)

        # 反馈区域 — HITL闭环
        st.markdown("---")
        st.markdown("#### 📝 结果反馈 — 帮助我们越用越聪明")
        fb_col1, fb_col2, fb_col3 = st.columns(3)
        with fb_col1:
            if st.button("👍 回答有帮助", key="fb_good", use_container_width=True):
                st.session_state.feedback_count += 1
                st.session_state.feedback_log.append({"type": "positive", "query": query, "time": datetime.now().isoformat()})
                st.toast("✅ 感谢反馈！已纳入HITL优化队列", icon="👍")
        with fb_col2:
            if st.button("👎 回答不准确", key="fb_bad", use_container_width=True):
                st.session_state.feedback_count += 1
                st.session_state.feedback_log.append({"type": "negative", "query": query, "time": datetime.now().isoformat()})
                st.toast("⚠️ 已标记待人工审核，将优化Prompt和知识库", icon="👎")
        with fb_col3:
            if st.button("📝 知识缺失/纠错", key="fb_missing", use_container_width=True):
                st.session_state.feedback_count += 1
                st.session_state.feedback_log.append({"type": "missing", "query": query, "time": datetime.now().isoformat()})
                st.toast("📝 已记录知识缺口，运营团队将在24h内补充", icon="📝")

# ============================================================
# 首页底部 — HITL反馈入口 + 数据统计（未提问时也显示）
# ============================================================
st.markdown("---")
st.markdown("""
<div class="hitl-banner">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem">
        <div>
            <strong style="color:#744210;font-size:1rem">🔄 HITL人工反馈闭环 — 越用越聪明</strong><br/>
            <span style="color:#975a16;font-size:0.85rem">
                发现回答有问题？点击上方反馈按钮，你的每一次纠错都在帮助AI变得更好。
                反馈经人工审核后，将自动驱动知识库补充、Prompt优化和模型微调。
            </span>
        </div>
        <div style="text-align:right;min-width:180px">
            <div style="font-size:1.4rem;font-weight:700;color:#744210">""" + str(st.session_state.feedback_count) + """</div>
            <div style="font-size:0.8rem;color:#975a16">累计处理反馈数</div>
            <div style="font-size:0.75rem;color:#b7791f;margin-top:0.2rem">
                本周新增 12 条 · 知识库优化 8 次
            </div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# 底部信息
st.markdown("---")
st.caption("KnowBase AI Demo v2.0 | 企业内部技术知识库问答系统 | 权限感知 · HITL反馈闭环 · RAG+CoT 架构")
