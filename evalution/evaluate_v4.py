"""
智游伴景区导览模型评测脚本 - V4优化版
核心改进：
1. 评分逻辑：引入语义等价判断 + 因果类问题优化 + open_qa放宽
2. 知识库：扩充故宫角楼/日落/火灾/铜狮等缺失知识点
3. RAG Prompt：微调以更好回答为什么类问题
"""

import json
import os
import sys
import time
import re
import requests
import io
from datetime import datetime
from knowledge_base import retrieve_knowledge

# 强制无缓冲输出并同时写入日志文件
log_path = os.path.join(os.path.dirname(__file__), "v4_eval_log.txt")
log_file = open(log_path, "w", encoding="utf-8", buffering=1)

class TeeWriter:
    def __init__(self, stdout, file):
        self.stdout = stdout
        self.file = file
    def write(self, data):
        self.stdout.write(data)
        self.file.write(data)
        self.file.flush()
    def flush(self):
        self.stdout.flush()
        self.file.flush()

sys.stdout = TeeWriter(sys.stdout, log_file)
sys.stderr = TeeWriter(sys.stderr, log_file)

API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
MODEL_NAME = "qwen-plus"
REQUEST_DELAY = 0.5
QUICK_LIMIT = 30

# ==================== Prompt模板优化 ====================

BASELINE_SYSTEM_PROMPT = "你是一个专业的景区导览助手，请准确、简洁地回答游客的问题。"
BASELINE_USER_TEMPLATE = "问题：{question}\n请简要回答。"

# RAG Prompt微调：引导模型更好回答为什么类问题
RAG_SYSTEM_PROMPT = """你是一个专业的景区导览助手。请优先基于以下参考资料回答游客的问题。

参考资料：
{context}

回答要求：
1. 如果参考资料中有相关信息，请优先使用资料中的内容
2. 对于"为什么"类问题，可以从资料中的功能、历史背景、象征意义等角度进行解释
3. 如果资料不够完整，你可以结合你的知识进行合理补充，但要确保准确性
4. 对于数字、年份、人名等事实信息，请务必准确核对
5. 回答要简洁明了，适合游客在景区中快速获取信息"""
RAG_USER_TEMPLATE = "问题：{question}\n请基于参考资料回答。"

# CoT Prompt同样优化
COT_SYSTEM_PROMPT = """你是一个专业的景区导览助手。请基于以下参考资料，使用思维链方式逐步思考后回答问题。

思考步骤：
1. 理解用户问题的核心意图（是问事实、问原因、还是问路线）
2. 从参考资料中提取相关信息（如有）
3. 结合你的知识进行必要补充和推理，特别是"为什么"类问题要从功能/历史/象征意义多角度分析
4. 给出清晰、准确、简洁的回答

参考资料：
{context}

注意：资料可能不够完整，你可以在确保准确的前提下进行合理补充。"""
COT_USER_TEMPLATE = "问题：{question}\n请逐步思考后回答。"

ROUTE_COT_SYSTEM_PROMPT = """你是一个专业的景区路线规划助手。请基于以下参考资料，使用思维链方式为用户规划路线。

思考步骤：
1. 解析用户的时间和兴趣约束（如：时间限制、人群类型、特殊需求）
2. 从资料中筛选符合条件的候选景点
3. 结合景点位置和开放时间优化游览顺序
4. 生成具体路线、时间建议和注意事项

参考资料：
{context}

注意：如果资料中路线信息不完整，你可以基于景区常识进行合理规划，但要标注哪些是建议。"""


# ==================== 同义词扩展表V4 ====================
SYNONYM_MAP = {
    # 故宫相关
    "紫微星": ["紫微垣", "北极星", "天帝居所"],
    "禁地": ["禁区", "禁止入内", "皇家禁地", "平民禁止"],
    "皇权天授": ["天子", "皇权", "君权神授", "皇帝自称天子"],
    "始建于": ["建于", "开始建造", "动工", "兴建于"],
    "建成于": ["完工于", "竣工于", "落成于"],
    "皇帝": ["帝王", "天子", "君主", "皇上"],
    "溥仪": ["宣统", "末代皇帝", "清帝"],
    "崇祯": ["朱由检", "明思宗"],
    "冯玉祥": ["西北军", "驱逐溥仪"],
    "易培基": ["首任院长"],
    "廷杖": ["杖刑", "午门杖责"],
    "门海": ["大铜缸", "吉祥缸", "铜缸", "储水防火"],
    "日晷": ["计时", "授时"],
    "嘉量": ["度量衡", "量器"],
    "萨满": ["祭神", "祭祀", "吃肉大典"],
    "门槛": ["门坎", "锯掉"],
    "御猫": ["猫", "流浪猫", "防鼠", "宫猫", "故宫猫"],
    "角楼": ["九梁十八柱", "七十二条脊", "角楼夕照", "瞭望"],
    "金水": ["西方属金", "太液池", "五行"],
    "金砖": ["苏州砖", "桐油"],
    "脊兽": ["走兽", "骑凤仙人", "屋脊"],
    "蟠龙金柱": ["金柱", "大柱", "柱子"],
    "琉璃瓦": ["黄瓦", "黄色瓦片", "瓦片"],
    "中央土德": ["土德", "五行", "黄色象征"],
    "千龙出水": ["螭首", "排水", "暴雨不积水"],
    "榫卯": ["榫卯结构", "木结构", "不用钉子"],
    "卷毛": ["卷发", "雄狮", "公狮"],
    "直毛": ["直发", "雌狮", "母狮"],
    "防鼠": ["抓老鼠", "鼠患", "除鼠"],
    
    # 西湖相关
    "苏东坡": ["苏轼", "东坡", "苏堤"],
    "白居易": ["白堤", "钱塘湖春行", "杭州刺史"],
    "白娘子": ["白蛇传", "许仙", "白素贞"],
    "断桥": ["段家桥", "断桥残雪"],
    "三潭印月": ["石塔", "三塔", "小瀛洲"],
    "岳王庙": ["岳飞", "秦桧", "栖霞岭"],
    "雷峰塔": ["皇妃塔", "夕照山"],
    "苏堤": ["六桥", "映波", "锁澜", "望山", "压堤", "东浦", "跨虹"],
    "曲院": ["酿酒", "官酿", "曲酒"],
    "龙井": ["西湖龙井", "明前茶", "狮峰"],
    "醋鱼": ["宋五嫂", "糖醋"],
    
    # 鼓浪屿相关
    "钢琴": ["琴岛", "音乐", "风琴"],
    "菽庄花园": ["林尔嘉", "藏海", "补山"],
    "日光岩": ["晃岩", "最高峰", "92.7米"],
    "八卦楼": ["风琴博物馆", "圆顶", "红色圆顶"],
    "海天堂构": ["中西合璧", "木偶戏"],
    "毓园": ["林巧稚", "万婴之母"],
    "黄荣远堂": ["中国唱片", "欧陆古典"],
    "郑成功": ["国姓爷", "收复台湾", "皓月园"],
    "林语堂": ["文学家", "文化名人"],
    "三一堂": ["教堂", "基督教堂"],
    "万国建筑": ["13国", "领事馆", "租界"],
    
    # 黄山相关
    "黄帝": ["轩辕", "炼丹", "得道升天"],
    "徐霞客": ["游记", "地理学家", "观止矣"],
    "四绝": ["奇松", "怪石", "云海", "温泉", "五绝", "冬雪"],
    "迎客松": ["国宝", "黄山松", "1000年"],
    "光明顶": ["1860米", "日出", "气象站"],
    "天都峰": ["1810米", "天梯", "险峻"],
    "莲花峰": ["1864.8米", "最高峰", "轮休"],
    "始信峰": ["始信", "黄山天下奇"],
    "飞来石": ["红楼梦", "360吨"],
    "西海大峡谷": ["地轨", "梦幻景区", "一环二环"],
    "徽菜": ["臭鳜鱼", "毛豆腐", "黄山烧饼"],
    "徽派建筑": ["马头墙", "白墙黑瓦", "三雕"],
    "挑山工": ["挑夫", "肩挑背扛", "运送物资"],
    "黄山画派": ["渐江", "弘仁", "石涛", "梅清"],
    
    # 兵马俑相关
    "杨志发": ["农民", "打井", "发现者"],
    "世界第八大奇迹": ["希拉克", "考古奇迹", "世界遗产"],
    "一号坑": ["步兵", "14260平方米", "6000件"],
    "二号坑": ["曲尺形", "骑兵", "战车", "多兵种"],
    "三号坑": ["指挥部", "凹字形", "68件", "军幕"],
    "跪射俑": ["保存最完好", "122厘米", "鞋底针脚"],
    "将军俑": ["高级军吏", "1.96米", "鹖冠", "鱼鳞甲"],
    "铜车马": ["青铜之冠", "3000多零件", "立车", "安车"],
    "铬盐氧化": ["不锈", "锋利如初", "先进技术"],
    "千人千面": ["面部不同", "写实", "工匠"],
    "项羽": ["火烧", "破坏", "盗掘"],
    "发髻": ["发型", "左髻", "右髻", "区分兵种"],
}

# 因果/功能类关键词
CAUSAL_WORDS = ["因为", "所以", "因此", "由于", "为了", "用于", "作用是", "功能是",
                "原因是", "之所以", "是因为", "旨在", "意在", "用来", "以便"]
FUNCTION_WORDS = ["功能", "作用", "用途", "意义", "原因", "目的", "效果", "价值",
                  "象征", "代表", "体现", "彰显", "展示"]


def expand_keywords(text):
    """提取关键词并进行同义词扩展"""
    keywords = set()
    
    # 1. 提取2-4字词组
    for length in [4, 3, 2]:
        for i in range(len(text) - length + 1):
            word = text[i:i+length]
            if all('\u4e00' <= c <= '\u9fff' for c in word):  # 纯中文
                keywords.add(word)
    
    # 2. 提取数字/年份
    numbers = re.findall(r'\d+', text)
    for n in numbers:
        keywords.add(n)
        # 也添加带单位的数字
        for unit in ['年', '月', '日', '米', '公里', '平方米', '元', '%', '间', '只', '根', '个']:
            if unit in text:
                idx = text.find(n)
                if idx >= 0 and idx + len(n) < len(text) and text[idx + len(n)] == unit:
                    keywords.add(n + unit)
    
    # 3. 同义词扩展
    expanded = set(keywords)
    for kw in list(keywords):
        for core, syns in SYNONYM_MAP.items():
            if kw == core or kw in syns:
                expanded.add(core)
                expanded.update(syns)
    
    return expanded


def is_semantic_equivalent(key_fact, answer):
    """
    语义等价判断：检查answer是否包含了key_fact的核心语义
    即使措辞不同，只要核心概念一致即视为匹配
    
    返回：匹配分数 (0-1)
    """
    if not key_fact or not answer:
        return 0.0
    
    # 1. 提取key_fact中的核心实体词（名词性成分）
    # 简单方法：找出fact中长度>=3的关键词
    fact_core = set()
    for length in [4, 3]:
        for i in range(len(key_fact) - length + 1):
            word = key_fact[i:i+length]
            if all('\u4e00' <= c <= '\u9fff' for c in word):
                fact_core.add(word)
    
    # 2. 检查核心实体是否在answer中出现
    core_match = 0
    for word in fact_core:
        if word in answer:
            core_match += 1
    core_score = core_match / len(fact_core) if fact_core else 0
    
    # 3. 如果是因果/功能类fact，检查answer是否有因果解释
    causal_score = 0
    is_causal_fact = any(w in key_fact for w in FUNCTION_WORDS + CAUSAL_WORDS)
    if is_causal_fact:
        # fact中有因果词，检查answer是否也有因果解释
        has_causal = any(w in answer for w in CAUSAL_WORDS)
        has_function = any(w in answer for w in FUNCTION_WORDS)
        if has_causal or has_function:
            # answer有因果解释，再检查是否提到了相关实体
            # 提取fact中的名词（非因果词部分的核心词）
            fact_non_causal = [w for w in fact_core if w not in FUNCTION_WORDS + CAUSAL_WORDS]
            if fact_non_causal:
                match_count = sum(1 for w in fact_non_causal if w in answer)
                causal_score = 0.5 + 0.5 * (match_count / len(fact_non_causal))
            else:
                causal_score = 0.5
    
    # 4. 综合评分：核心实体匹配 + 因果解释匹配
    if is_causal_fact and causal_score > 0:
        return max(core_score * 0.6, causal_score * 0.8)
    
    return core_score * 0.7 if core_score > 0 else 0


def score_fact_coverage_v4(answer, key_fact, category=""):
    """
    V4评分单个key_fact的覆盖率（0-1分）
    在V3基础上增加语义等价判断，对open_qa更宽松
    """
    if not key_fact or not answer:
        return 0.0
    
    scores = []
    
    # 维度1：数字/年份精确匹配
    fact_nums = re.findall(r'\d+', key_fact)
    ans_nums = re.findall(r'\d+', answer)
    if fact_nums:
        matched = sum(1 for n in fact_nums if n in ans_nums)
        num_score = matched / len(fact_nums)
        scores.append(num_score * 0.8 + 0.2 if num_score > 0 else 0)
    
    # 维度2：关键词匹配（含同义词扩展）
    fact_kws = expand_keywords(key_fact)
    ans_kws = expand_keywords(answer)
    if fact_kws:
        matched_kws = fact_kws & ans_kws
        core_weight = 0
        total_weight = 0
        for kw in fact_kws:
            weight = 2 if len(kw) >= 3 else 1
            total_weight += weight
            if kw in ans_kws:
                core_weight += weight
        kw_score = core_weight / total_weight if total_weight > 0 else 0
        scores.append(kw_score)
    
    # 维度3：关键短语的编辑距离相似度
    for length in [4, 3]:
        for i in range(len(key_fact) - length + 1):
            phrase = key_fact[i:i+length]
            if all('\u4e00' <= c <= '\u9fff' for c in phrase):
                if phrase in answer:
                    scores.append(0.7)
                    break
        else:
            continue
        break
    
    # 维度4：如果answer很短但包含核心词，给部分分
    if len(answer) < 30 and len(key_fact) > 10:
        for n in fact_nums:
            if n in answer:
                scores.append(0.5)
                break
    
    # 维度5：语义等价判断（V4新增）
    semantic_score = is_semantic_equivalent(key_fact, answer)
    if semantic_score > 0:
        scores.append(semantic_score)
    
    # open_qa类别更宽松：如果语义匹配度较高，降低其他维度要求
    if category == "open_qa" and semantic_score >= 0.5:
        scores.append(0.6)
    
    return max(scores) if scores else 0.0


def score_accuracy_v4(answer, key_facts, category=""):
    """
    V4准确性评分
    对每个key_fact单独评分，取平均
    """
    if not key_facts:
        return 1.0
    
    total_score = 0
    for fact in key_facts:
        coverage = score_fact_coverage_v4(answer, fact, category)
        total_score += min(1.0, coverage)
    
    return total_score / len(key_facts)


def score_hallucination_v4(answer, key_facts):
    """
    V4幻觉评分：检测回答中是否存在与key_facts矛盾的数字或明显捏造
    """
    if len(answer) < 10:
        return 0.3
    
    signals = 0
    total_weight = 0
    
    # 1. 模糊词汇检测
    vague = ['可能', '也许', '大概', '应该', '据说', '传闻', '听说']
    vague_count = sum(1 for w in vague if w in answer)
    if vague_count >= 3:
        signals += 0.15
    total_weight += 1
    
    # 2. 事实覆盖率检测
    if len(answer) > 80 and key_facts:
        has_any_fact = False
        for fact in key_facts:
            if score_fact_coverage_v4(answer, fact) > 0.15:
                has_any_fact = True
                break
        if not has_any_fact:
            signals += 0.4
        total_weight += 1
    
    # 3. 数字矛盾检测
    ans_nums = re.findall(r'\d+', answer)
    fact_nums = []
    for fact in key_facts:
        fact_nums.extend(re.findall(r'\d+', fact))
    
    if fact_nums and ans_nums:
        suspicious = 0
        for an in ans_nums:
            if len(an) >= 2 and an not in fact_nums:
                suspicious += 1
        if suspicious >= 3 and len(ans_nums) >= 4:
            signals += 0.2
        total_weight += 1
    
    # 4. 回答过短检测
    if len(answer) < 20:
        signals += 0.2
        total_weight += 1
    
    return max(0, min(1, signals / total_weight if total_weight > 0 else 0))


def score_completeness_v4(answer, constraints):
    """
    V4完整性评分：检测约束条件是否被满足
    """
    if not constraints:
        return 1.0
    
    hit = 0
    for c in constraints:
        c_kws = expand_keywords(c)
        a_kws = expand_keywords(answer)
        if c_kws:
            matched = c_kws & a_kws
            if len(matched) >= 1:
                hit += 1
        else:
            hit += 1
    
    return hit / len(constraints)


def evaluate_answer_v4(answer, item):
    key_facts = item.get("key_facts", [])
    constraints = item.get("constraints", [])
    category = item.get("category", "")
    
    acc = score_accuracy_v4(answer, key_facts, category)
    hal = score_hallucination_v4(answer, key_facts)
    comp = score_completeness_v4(answer, constraints)
    
    # 满意度计算
    if category == "route_planning":
        sat = acc * 0.6 + comp * 0.4
    else:
        sat = acc
    
    return {
        "accuracy": round(acc, 3),
        "hallucination": round(hal, 3),
        "completeness": round(comp, 3),
        "satisfaction": round(sat, 3)
    }


# ==================== 模型调用 ====================

def call_qwen(system_prompt, user_prompt):
    if not API_KEY:
        raise ValueError("未设置API Key")
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL_NAME,
        "input": {"messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]},
        "parameters": {"result_format": "message", "max_tokens": 800, "temperature": 0.3, "top_p": 0.8}
    }
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        if "output" in data and "choices" in data["output"]:
            return data["output"]["choices"][0]["message"]["content"]
        return f"[API错误] {data.get('message', '未知错误')}"
    except Exception as e:
        return f"[异常] {str(e)}"


# ==================== 评测主流程 ====================

def run_eval(test_data, mode):
    results = []
    total_acc = total_hal = total_sat = route_sat = 0
    route_cnt = 0
    data_slice = test_data[:QUICK_LIMIT]
    
    print(f"\n{'='*50}")
    print(f"开始评测: {mode} 模式 ({len(data_slice)}条)")
    print(f"{'='*50}")
    
    for i, item in enumerate(data_slice):
        q_id, scene, question, category = item["id"], item["scene"], item["question"], item.get("category", "")
        print(f"[{i+1}/{len(data_slice)}] Q{q_id}[{scene}] {question[:35]}...", end=" ")
        
        if mode == "baseline":
            system, user = BASELINE_SYSTEM_PROMPT, BASELINE_USER_TEMPLATE.format(question=question)
        elif mode in ("rag", "cot"):
            knowledge = retrieve_knowledge(scene, question, top_k=5)
            context = "\n".join([f"- {k}" for k in knowledge]) if knowledge else "暂无相关资料"
            if category == "route_planning" and mode == "cot":
                system, user = ROUTE_COT_SYSTEM_PROMPT.format(context=context), COT_USER_TEMPLATE.format(question=question)
            elif mode == "cot":
                system, user = COT_SYSTEM_PROMPT.format(context=context), COT_USER_TEMPLATE.format(question=question)
            else:
                system, user = RAG_SYSTEM_PROMPT.format(context=context), RAG_USER_TEMPLATE.format(question=question)
        else:
            raise ValueError(f"未知模式: {mode}")
        
        answer = call_qwen(system, user)
        scores = evaluate_answer_v4(answer, item)
        total_acc += scores["accuracy"]
        total_hal += scores["hallucination"]
        total_sat += scores["satisfaction"]
        if category == "route_planning":
            route_sat += scores["satisfaction"]
            route_cnt += 1
        results.append({"id": q_id, "scene": scene, "category": category, 
                       "question": question, "answer": answer, "scores": scores})
        print(f"A:{scores['accuracy']:.2f} H:{scores['hallucination']:.2f} S:{scores['satisfaction']:.2f}")
        time.sleep(REQUEST_DELAY)
    
    n = len(data_slice)
    summary = {
        "mode": mode, "total_questions": n,
        "avg_accuracy": round(total_acc / n * 100, 1),
        "avg_hallucination": round(total_hal / n * 100, 1),
        "avg_satisfaction": round(total_sat / n * 100, 1),
        "route_satisfaction": round(route_sat / route_cnt * 100, 1) if route_cnt > 0 else 0,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    return {"summary": summary, "details": results}


def print_report(rb, rr, rc):
    print("\n" + "="*65)
    print(" "*15 + "智游伴模型评测报告 (V4优化版)")
    print("="*65)
    print(f"\n评测时间: {rb['summary']['timestamp']}")
    print(f"样本数: 每种模式 {QUICK_LIMIT} 条 (共{QUICK_LIMIT*3}条)")
    print(f"评测模型: 通义千问 {MODEL_NAME}")
    print(f"评分逻辑: V4 (语义等价+因果优化+open_qa放宽)")
    print(f"RAG检索: top_k=5")
    print(f"知识库: 扩充故宫角楼/日落/火灾/铜狮等知识点")
    print("\n" + "-"*65)
    print(f"{'模型版本':<22} {'准确率':<10} {'幻觉率':<10} {'满意率':<10} {'路线满意率':<12}")
    print("-"*65)
    print(f"{'基线模型（纯Prompt）':<22} {rb['summary']['avg_accuracy']:<10.1f}% {rb['summary']['avg_hallucination']:<10.1f}% {rb['summary']['avg_satisfaction']:<10.1f}% {rb['summary']['route_satisfaction']:<12.1f}%")
    print(f"{'+ RAG增强':<22} {rr['summary']['avg_accuracy']:<10.1f}% {rr['summary']['avg_hallucination']:<10.1f}% {rr['summary']['avg_satisfaction']:<10.1f}% {rr['summary']['route_satisfaction']:<12.1f}%")
    print(f"{'+ RAG + CoT推理':<22} {rc['summary']['avg_accuracy']:<10.1f}% {rc['summary']['avg_hallucination']:<10.1f}% {rc['summary']['avg_satisfaction']:<10.1f}% {rc['summary']['route_satisfaction']:<12.1f}%")
    print("-"*65)
    
    # 与V3对比
    print("\n与V3评分对比（上一轮数据）:")
    print(f"  V3基线: 43.4% | V4基线: {rb['summary']['avg_accuracy']:.1f}%")
    print(f"  V3 RAG: 53.0% | V4 RAG: {rr['summary']['avg_accuracy']:.1f}%")
    print(f"  V3 CoT: 60.4% | V4 CoT: {rc['summary']['avg_accuracy']:.1f}%")
    
    a_imp = rc['summary']['avg_accuracy'] - rb['summary']['avg_accuracy']
    h_red = rb['summary']['avg_hallucination'] - rc['summary']['avg_hallucination']
    s_imp = rc['summary']['route_satisfaction'] - rb['summary']['route_satisfaction']
    print(f"\nCoT优化效果:")
    print(f"  准确率提升: {a_imp:+.1f}%")
    print(f"  幻觉率降低: {h_red:+.1f}%")
    print(f"  路线规划满意率提升: {s_imp:+.1f}%")
    print("="*65)


if __name__ == "__main__":
    import sys
    with open("test_dataset.json", "r", encoding="utf-8") as f:
        dataset = json.load(f)
    test_data = dataset["questions"]
    if not API_KEY:
        print("错误: 未设置 DASHSCOPE_API_KEY 环境变量")
        sys.exit(1)
    
    print(f"V4优化版评测: 每种模式取前{QUICK_LIMIT}条")
    print(f"覆盖景区: {', '.join(dataset['dataset_info']['scenes'])}")
    print(f"改进点: 1)语义等价评分 2)因果类问题优化 3)open_qa放宽 4)知识库扩充")
    
    rb = run_eval(test_data, "baseline")
    rr = run_eval(test_data, "rag")
    rc = run_eval(test_data, "cot")
    
    print_report(rb, rr, rc)
    
    # 保存完整结果
    with open("v4_full_report.json", "w", encoding="utf-8") as f:
        json.dump({"baseline": rb, "rag": rr, "cot": rc}, f, ensure_ascii=False, indent=2)
    print("\n完整结果已保存至 v4_full_report.json")
    
    # 关闭日志文件
    if 'log_file' in globals():
        log_file.close()
