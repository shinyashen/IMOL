import os, argparse


parser = argparse.ArgumentParser(description='LLM process', formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument('model', type=str, help="use which LLM model")
parser.add_argument('gpu', type=str, help="use gpu ids")
parser.add_argument('-u', '--url', type=str, help="LLM api url")
parser.add_argument('-f', '--force', action='store_true', help="force to analyze the file even if it exists")
args = parser.parse_args()
os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu


import html, asyncio, json, re, chardet
import tree_sitter_java as tsjava
import xml.etree.ElementTree as ET
import pandas as pd
from tree_sitter import Language, Parser
from openai import OpenAI, AsyncOpenAI
from bs4 import BeautifulSoup
from typing import List
from asyncio import Semaphore
from vllm import LLM, SamplingParams
from transformers import AutoTokenizer

import config as conf


groups = ['Apache', 'Wildfly', 'Spring']
projects = {
    'Apache': ['CAMEL', 'HBASE', 'HIVE'],
    'Wildfly': ['WFLY'],
    'Spring': ['ROO']
}
versions = {}
report_types = ['PE', 'ST', 'NL']



JAVA_LANGUAGE = Language(tsjava.language())
parser = Parser(JAVA_LANGUAGE)
parse_type = {
    'class_declaration': 'class_body',
    'interface_declaration': 'interface_body',
    'annotation_declaration': 'annotation_body',
    'enum_declaration': 'enum_body',
    'record_declaration': 'record_body',
    'module_declaration': 'module_body'
}
unimportant_type = ['line_comment', 'block_comment']


def get_base_url():
    if args.url is not None:
        return args.url
    return conf.read_config([conf.LLM_section], "base_url", None)


def get_model():
    if args.model not in LLM_models:
        print(f"Error: {args.model} is not a valid model name.")
        exit(1)
    return args.model


def get_model_path():
    return os.path.join(conf.read_config([conf.LLM_section], "model_path", None), get_model())


LLM_models = ['Meta-Llama-3-8B-Instruct', 'DeepSeek-R1-Distill-Llama-8B', 'Qwen3-8B']
model = get_model()
model_path = get_model_path()
base_url = get_base_url()
client = OpenAI(
    base_url=base_url,
    api_key=conf.read_config([conf.LLM_section], "api_key", None)
)
aclient = AsyncOpenAI(
    base_url=base_url,
    api_key=conf.read_config([conf.LLM_section], "api_key", None)
)
is_relevant = 0

Bench4BL_path = conf.read_config([conf.Bench4BL_section], "path", None)
Bench4BL_datapath = os.path.join(Bench4BL_path, 'data')
datapath = conf.read_config([conf.data_section], "path", None)


def getPath_base(_group, _project):
    return os.path.join(Bench4BL_datapath, _group, _project)


def load_versions(_group, _project):
    f = open(os.path.join(getPath_base(_group, _project), 'versions.txt'), 'r', encoding='utf-8')
    text = f.read()
    f.close()
    data = eval(text)

    return data[_project]


# 代码文件分块处理
def split_code(code):
    tree = parser.parse(bytes(code, "utf8"))
    root_node = tree.root_node

    for child1 in root_node.children:
        if child1.type in parse_type.keys():
            for child2 in child1.children:
                if child2.type == 'identifier':
                    class_name = child2.text.decode()
                elif child2.type == parse_type[child1.type]:
                    for child3 in child2.children:
                        if child3.type in unimportant_type:
                            continue
                        yield class_name, extract_node(child3, code)


def extract_node(node, code):
    return code[node.start_byte:node.end_byte]


# 缺陷报告处理
def strip_html_tags(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    return soup.get_text(separator=" ", strip=True)

def extract_issues(xml_content):
    root = ET.fromstring(xml_content)
    item = root.find('channel').find('item')

    description_elem = item.find('description')
    description_html = html.unescape(description_elem.text) if description_elem is not None and description_elem.text is not None else ""
    description_clean = strip_html_tags(description_html)

    result = {
        'title': html.unescape(item.find('title').text),
        'summary': html.unescape(item.find('summary').text),
        'description': description_clean
    }

    return result


# LLM处理函数

# 处理单个LLM请求，返回单个结果
def query_openai(query_dict, prev_msg=None):
    msg_list = prev_msg if prev_msg else []
    if prev_msg is None:
        msg_list.append(query_dict['system'])
    msg_list.append(query_dict['user'])
    completion = client.chat.completions.create(
        model=query_dict['model'],
        messages=msg_list
    )
    return completion.choices[0].message.content


# 处理单个LLM请求，异步返回单个结果
async def async_query_openai(sem: Semaphore, query_dict, prev_msg=None):
    async with sem:
        msg_list = prev_msg if prev_msg else []
        if prev_msg is None:
            msg_list.append(query_dict['system'])
        msg_list.append(query_dict['user'])
        if get_model() not in ['Qwen3-8B']:
            completion = await aclient.chat.completions.create(
                model=query_dict['model'],
                messages=msg_list
            )
        else:
            completion = await aclient.chat.completions.create(
                model=query_dict['model'],
                messages=msg_list,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}}
            )
        return completion.choices[0].message.content


# 返回所有请求的结果列表
async def async_process_queries(queries, max_concurrent: int = 4):
    sem = Semaphore(max_concurrent)
    tasks = [async_query_openai(sem, query) for query in queries]
    return await asyncio.gather(*tasks)


def classify_bug_report(bug_report: dict):
    """将缺陷报告分类为 PE/ST/NL"""
    system = {
        "role": "system",
        "content": """
        你是一个缺陷报告分类器，请判断输入内容类型：
        - PE（含编程实体）：包含类名、方法名、变量名等代码元素
        - ST（含堆栈跟踪）：包含异常堆栈信息（如 at com.example.Class.method(File.java:123)）
        - NL（纯自然语言）：仅用自然语言描述问题，无具体代码元素
        只需返回 PE/ST/NL 中的一个，不要解释。
        """
    }
    user = {
        "role": "user",
        "content": f"缺陷报告内容:\n标题:{bug_report['title']}\n内容总结:{bug_report['summary']}\n报告描述：{bug_report['description']}"
    }
    dict = {
        'model': 'qwen-max-latest',
        'system': system,
        'user': user
    }

    result = query_openai(dict).strip().upper()  # 确保返回大写
    for type in report_types:
        if type in result:
            return type
    return 'NL'  # LLM返回结果无法处理


def clean_escape_chars_safe(s: str) -> str:
    # 仅替换 \: ，保留其他转义（如 \\、\/"）
    s = re.sub(r'(?<!\\)\\:', ':', s)   # 非 \\: 的情况
    return s


def extract_keywords(bug_report: dict, report_type: str) -> List[str]:
    """根据报告类型提取关键词"""
    type_prompt = {
        "PE": "提取编程实体（类名、方法名、变量名）",
        "ST": "提取异常类型、代码文件路径、行号",
        "NL": "提取动词短语和技术术语（如'内存泄漏'）。如果没有明确的动词短语或技术术语，请尝试从内容概括出相应的术语。"
    }[report_type]

    system = {
        "role": "system",
        "content": f"""
        你是一个信息提取专家，请从缺陷报告中：
        1. {type_prompt}
        2. 排除无关词汇（如用户描述的情感词）
        3. 输出JSON数组：{{"keywords": [...]}}
        4. 项目名称与报告编号不包括在输出列表中
        只需返回标准JSON字符串，不要解释。
        """
    }
    user = {
        "role": "user",
        "content": f"缺陷报告内容:\n标题:{bug_report['title']}\n内容总结:{bug_report['summary']}\n报告描述:{bug_report['description']}"
    }
    dict = {
        'model': 'qwen-max-latest',
        'system': system,
        'user': user
    }

    content = query_openai(dict)
    if "```json" in content:  # 清理JSON响应
        content = content.split("```json")[1].split("```")[0]
    return [str(item) for item in json.loads(clean_escape_chars_safe(content.strip())).get("keywords", [])]


def get_system_knowledge(report_type: str) -> str:
    """根据报告类型返回对应的系统知识"""
    knowledge_map = {
        "PE": """
        你正在分析包含编程实体的缺陷报告，需特别注意：
        1. 识别代码块中的特定类/方法/变量名
        2. 检查参数传递、对象初始化是否正确
        3. 验证访问修饰符（如 private/public）是否合理
        """,
        "ST": """
        你正在分析包含堆栈跟踪的缺陷报告，需特别注意：
        1. 判断代码块是否为堆栈中提到的代码文件
        2. 分析异常传播路径（从底层方法到入口）
        3. 检查异常发生时的上下文变量状态
        """,
        "NL": """
        你正在分析纯自然语言描述的缺陷报告，需特别注意：
        1. 通过语义推理猜测可能的缺陷代码位置
        2. 结合常见错误模式（如空指针、越界）分析
        3. 优先检查与缺陷报告相关的代码逻辑或函数调用
        """
    }
    return knowledge_map.get(report_type, "通用代码缺陷分析")


# 异步处理代码块
async def async_analyze_chunks(report, type, chunks):
    queries = []
    for chunk in chunks:
        system = {
            "role": "system",
            "content": f"""
                # 任务说明
                {get_system_knowledge(type)}

                # 规则（必须严格遵循）
                你是一个二分类器，判断代码块是否与缺陷报告相关。规则：
                1. 输出只能是**单个数字** 0 或 1：
                - 0 = 不相关
                - 1 = 相关
                2. **禁止**任何解释、标点、空格或额外文本。

                # 输出示例
                用户输入：缺陷报告 + 代码块
                你应返回：0
                或
                你应返回：1
                """
        }
        user = {
            "role": "user",
            "content": f"""
            ## 缺陷报告
            [标题] {report['title']}
            [内容总结] {report['summary']}
            [报告描述] {report['description']}

            ## 待分析代码块
            [文件名] {chunk['filename']}
            [类名] {chunk['class']}
            [代码块内容]
            {chunk['code']}

            ## 指令
            请根据上述信息，判断代码块是否与缺陷报告相关，严格按规则返回 0 或 1。
            """,
        }
        dict = {
            'model': model_path,
            'system': system,
            'user': user
        }
        queries.append(dict)

    results = await async_process_queries(queries)
    global is_relevant  # 使用全局变量存储分析结果
    is_relevant = 1 if '1' in results else 0


# vllm 处理函数

def auto_tensor_parallel():
    """根据 CUDA_VISIBLE_DEVICES 自动计算并行度"""
    # 获取环境变量值
    visible_devices = os.getenv("CUDA_VISIBLE_DEVICES", "")

    # 分割数字（支持逗号、空格分隔）
    devices = [d.strip() for d in visible_devices.replace(' ', ',').split(',') if d.strip()]
    # 过滤有效数字
    valid_devices = [d for d in devices if d.isdigit()]
    num_gpus = len(valid_devices)
    # print(num_gpus)

    return num_gpus if num_gpus >= 1 else 1  # 至少返回1


# 初始化tokenizer
model_name = get_model_path()
llm = LLM(model=model_name, max_model_len=7168, tensor_parallel_size=auto_tensor_parallel())
tokenizer = AutoTokenizer.from_pretrained(model_name)


# 定义截断函数
def truncate_messages(messages, max_tokens, tokenizer):
    """
    动态截断消息内容，优先保留前段消息
    策略：正向遍历（从旧到新），超出限制时截断后部内容
    """
    total_tokens = 0
    truncated_messages = []

    # 正向遍历消息（从旧到新）
    for msg in messages:
        content = msg.get("content", "")
        tokens = tokenizer.encode(content, add_special_tokens=False)

        # 如果当前消息加入后超出限制
        if total_tokens + len(tokens) > max_tokens:
            remaining_space = max_tokens - total_tokens
            if remaining_space > 0:
                # 截断当前消息的前部内容（保留开头）
                truncated_tokens = tokens[:remaining_space]
                msg["content"] = tokenizer.decode(truncated_tokens)
                truncated_messages.append(msg)
            break  # 停止处理后续消息
        else:
            truncated_messages.append(msg)
            total_tokens += len(tokens)

    return truncated_messages  # 直接返回旧到新顺序


def extract_last_zero_or_one(text: str) -> int:
    # 反向查找最后一个 0 或 1
    match = re.search(r'(?s)(.*)([01])(?!.*[01])', text.strip())
    return int(match.group(2)) if match else 0


# 批量处理代码块
def analyze_chunks(report, type, chunks):
    queries = []
    for chunk in chunks:
        system = {
            "role": "system",
            "content": f"""
                # 任务说明
                {get_system_knowledge(type)}

                # 规则（必须严格遵循）
                你是一个二分类器，判断代码块是否与缺陷报告相关。规则：
                1. 输出只能是**单个数字** 0 或 1：
                - 0 = 不相关
                - 1 = 相关
                2. **禁止**任何解释、标点、空格或额外文本。

                # 输出示例
                用户输入：缺陷报告 + 代码块
                你应返回：0
                或
                你应返回：1
                """
        }
        user = {
            "role": "user",
            "content": f"""
            ## 缺陷报告
            [标题] {report['title']}
            [内容总结] {report['summary']}
            [报告描述] {report['description']}

            ## 待分析代码块
            [文件名] {chunk['filename']}
            [类名] {chunk['class']}
            [代码块内容]
            {chunk['code']}

            ## 指令
            请根据上述信息，判断代码块是否与缺陷报告相关，严格按规则返回 0 或 1。
            """,
        }
        messages = [system, user]
        queries.append(truncate_messages(messages, 7130, tokenizer))

    if get_model() == 'Qwen3-8B':
        with open(os.path.join(get_model_path(), 'qwen3_nonthinking.jinja'), 'r', encoding='utf-8') as f:
            tokenizer.chat_template = f.read()

    prompts = [
        tokenizer.apply_chat_template(
            messages,
            tokenize=False,  # 不进行tokenize
            add_generation_prompt=True
        )
        for messages in queries
    ]

    # 执行批量推理
    sampling_params = SamplingParams(temperature=0.7, max_tokens=20480)
    results = llm.generate(prompts, sampling_params)
    # print([result.outputs[0].text for result in results])

    global is_relevant  # 使用全局变量存储分析结果
    is_relevant = 1 if 1 in [extract_last_zero_or_one(result.outputs[0].text) for result in results] else 0


if __name__ == '__main__':
    for group in groups:
        for project in projects[group]:
            versions[project] = load_versions(group, project)

    # 遍历所有项目和版本，加载相关源文件
    for group in groups:
        for project in projects[group]:
            for version in versions[project]:
                basicpath = os.path.join(datapath, group, project, version)
                loadpath = os.path.join(basicpath, 'recommended_IRBL', 'combined_files')
                if os.path.exists(loadpath):
                    for dir in os.listdir(loadpath):
                        print(f'Processing {group}/{project}/{version}/{dir}...')
                        # 缺陷报告处理
                        print(f'处理缺陷报告...', end="")
                        reportpath = os.path.join(Bench4BL_datapath, group, project, 'bugrepo', 'bugs', f'{project}-{dir}.xml')
                        with open(reportpath, 'r', encoding='utf-8') as f:
                            xml_content = f.read()
                        report_dict = extract_issues(xml_content)
                        typepath = os.path.join(basicpath, 'qwen-max-latest', 'type')
                        if not os.path.exists(typepath):
                            os.makedirs(typepath)
                        if os.path.exists(os.path.join(typepath, f'{dir}.txt')):
                            print('文件已存在，跳过分析...', end="")
                            with open(os.path.join(typepath, f'{dir}.txt'), 'r', encoding='utf-8') as f:
                                report_type = f.read()
                        else:
                            report_type = classify_bug_report(report_dict)  # 报告类型判断
                            with open(os.path.join(typepath, f'{dir}.txt'), 'w', encoding='utf-8') as f:
                                f.write(report_type)
                        print(f'类型为{report_type}...', end="")
                        print('ok')

                        # # 关键词总结
                        # print(f'总结关键词...', end="")
                        # keywordpath = os.path.join(basicpath, 'qwen-max-latest', 'keywords')
                        # if not os.path.exists(keywordpath):
                        #     os.makedirs(keywordpath)
                        # if not os.path.exists(os.path.join(keywordpath, f'{dir}.txt')):
                        #     report_keywords = extract_keywords(report_dict, report_type)
                        #     with open(os.path.join(keywordpath, f'{dir}.txt'), 'w', encoding='utf-8') as f:
                        #         f.write('\n'.join(report_keywords))
                        # else:
                        #     print('文件已存在，跳过分析...', end="")
                        # print('ok')

                        # 对每个代码文件进行分析
                        filepath = os.path.join(loadpath, dir)
                        savepath = os.path.join(basicpath, model, 'relevance')
                        if not os.path.exists(savepath):
                            os.makedirs(savepath)

                        if (not os.path.exists(os.path.join(savepath, f"{dir}.txt"))) or args.force:
                            result_list = []
                            for file in os.listdir(filepath):
                                print(f"处理文件{file}...", end="")
                                with open(os.path.join(filepath, file), 'rb') as f:  # 判断可能的文件编码类型
                                    detected_encoding = chardet.detect(f.read())['encoding']
                                with open(os.path.join(filepath, file), 'r', encoding=detected_encoding) as f:
                                    code = f.read()

                                # 分割代码
                                chunks = []
                                for name, splited_code in split_code(code):
                                    chunk = {
                                        'filename': file,
                                        'class': name,
                                        'code': splited_code
                                    }
                                    chunks.append(chunk)
                                if (len(chunks) == 0):
                                    print(f'Warning: {project}/{version}/{dir} {file}解析代码块长度为0!', end="")

                                # 异步执行
                                print(f"LLM分析相关度...", end="")
                                analyze_chunks(report_dict, report_type, chunks)
                                result_list.append([file, is_relevant])
                                print(f"ok: {'不' if is_relevant == 0 else ''}相关")


                            df = pd.DataFrame(result_list)
                            df.to_csv(os.path.join(savepath, f"{dir}.txt"), index=False, header=False, encoding='utf-8')

                        else:
                            print('文件已存在，跳过分析...')

                        print(f'{group}/{project}/{version}/{dir}处理完成！\n')
