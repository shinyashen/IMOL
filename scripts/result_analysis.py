import os
import pandas as pd

import config as conf


techs = ['BugLocator', 'BRTracer', 'BLIA']
proctechs = ['combined_IRBL', 'weighted_IRBL']
BM25s = ['bm25+', 'bm25l', 'lucene', 'weighted_BM25']
groups = ['Apache', 'Wildfly', 'Spring']
projects = {
    'Apache': ['CAMEL', 'HBASE', 'HIVE'],
    'Wildfly': ['WFLY'],
    'Spring': ['ROO']
}
project_source_files = {
    'CAMEL': 14522,
    'HBASE': 2714,
    'HIVE': 4651,
    'WFLY': 8990,
    'ROO': 1109,
    '/': 31986
}
report_types = ['PE', 'ST', 'NL']
versions = {}
answers = {}
bug_counts = {}
report_count = 0

Bench4BL_path = conf.read_config([conf.Bench4BL_section], "path", None)
Bench4BL_datapath = os.path.join(Bench4BL_path, 'data')
datapath = conf.read_config([conf.data_section], "path", None)


def getPath_base(_group, _project):
    return os.path.join(Bench4BL_datapath, _group, _project)


def load_versions(_group, _project):
    return os.listdir(os.path.join(datapath, _group, _project))


def load_answers(_group, _project):
    f = open(os.path.join(getPath_base(_group, _project), 'answers.txt'), 'r', encoding='utf-8')
    text = f.read()
    f.close()
    data = eval(text)

    return data[_project]


def count_bug():
    bug_counts['/'] = 0  # bug_counts['all']
    for group in groups:
        for project in projects[group]:
            bug_counts[project] = 0
            for version in versions[project]:
                loadpath = os.path.join(datapath, group, project, version, 'recommended_IRBL', 'combined_IRBL')
                if os.path.exists(loadpath):
                    bug_counts[project] += len(os.listdir(loadpath))
            bug_counts['/'] += bug_counts[project]


def calculate_metrics(ordered_list, target_list, _tech, _group, _project, _version, _bugid):
    """计算单个查询的AP、RR及所有命中行"""
    target_set = set(target_list)
    hits = []

    # 步骤1: 记录所有命中文档及其原始排名
    for rank, file in enumerate(ordered_list, 1):  # 排名从1开始
        if file in target_set:
            hits.append((file, rank))  # (文件名, 原始排名)

    # 步骤2: 计算指标
    ap = 0.0
    total_relevant = len(hits)
    query_rows = []

    # 计算AP和生成每行数据
    for idx, (file, original_rank) in enumerate(hits, 1):
        # 计算当前命中位置的Precision@rank
        prefix_hits = len([f for f in ordered_list[:original_rank] if f in target_set])
        precision_at_rank = prefix_hits / original_rank

        ap += precision_at_rank  # 累加AP的分子部分
        top1 = 1 if original_rank == 1 else 0
        top5 = 1 if original_rank <= 5 else 0
        top10 = 1 if original_rank <= 10 else 0

        # 记录单行数据（此时AP和RR尚未计算完成）
        query_rows.append({
            "key": f'{_project}{str(_bugid).zfill(5)}'.lower(),
            "Approach": _tech,
            "Group": _group,
            "Project": _project,
            "BugID": _bugid,
            "Version": f'{_project}_{_version}'.replace(".", "_"),
            "AnsFileCount": answers[_project][int(_bugid)],
            "File": file,
            "Rank": original_rank,
            # TODO: Scores
            "Top1": top1,
            "Top5": top5,
            "Top10": top10,
            "AnsOrder": idx,
            "P(rank)": precision_at_rank,
            "AP": 0,
            "TP": 0  # RR
        })

    # 最终计算AP和RR
    ap = ap / len(target_list) if total_relevant > 0 else 0.0
    rr = 1 / hits[0][1] if len(hits) > 0 else 0.0

    # 仅为第一个命中行添加AP和RR
    for row in query_rows:
        if row["AnsOrder"] == 1:
            row["AP"] = ap
            row["TP"] = rr
            break

    df_query = pd.DataFrame(query_rows)
    return df_query


def cal_version_res(_tech, _group, _project, _version, _mode=None, _type=report_types):
    if _tech in techs or _tech in proctechs:
        loadpart1 = 'recommended_IRBL'
        loadpart2 = ''
    if _tech in ['Qwen3-8B']:  # LLM result process
        loadpart1 = ''
        loadpart2 = 'result'
    if _tech in ['Qwen3-8B-mul']:  # LLM result process
        _tech = 'Qwen3-8B'
        loadpart1 = ''
        loadpart2 = 'result2'
    if _tech in BM25s:
        loadpart1 = 'BM25'
        loadpart2 = ''
    loadpath = os.path.join(datapath, _group, _project, _version, loadpart1, _tech, loadpart2)
    df_query = pd.DataFrame()
    query_num = 0

    if os.path.exists(loadpath):
        for file in os.listdir(loadpath):
            typepath = os.path.join(datapath, _group, _project, _version, 'qwen-max-latest', 'type')
            with open(os.path.join(typepath, f'{dir}.txt'), 'r', encoding='utf-8') as f:
                report_type = f.read()
            if report_type not in report_types:
                continue
            global report_count
            report_count += 1
            if _mode == 'B200' and report_count > 200: #  只统计前200份报告
                break
            if _mode == 'P200' and report_count <= 200: #  只统计200份以后的报告
                continue
            bug_id = os.path.splitext(file)[0]
            java_list = pd.read_csv(os.path.join(loadpath, file), header=None).iloc[:, 0].tolist()
            bugpath = os.path.join(os.path.join(datapath, _group, _project, _version, 'buglist', file))
            with open(bugpath, 'r', encoding='utf-8') as f:
                file_list = f.readlines()
            bug_list = [line.strip() for line in file_list]

            df = calculate_metrics(java_list, bug_list, _tech, _group, _project, _version, bug_id)
            df_query = pd.concat([df_query, df], ignore_index=True)
            query_num += 1

    return df_query, query_num


def cal_project_res(_tech, _group, _project, _mode=None, _type=report_types):
    df_query = pd.DataFrame()
    query_num = 0

    for version in versions[_project]:
        a, b = cal_version_res(_tech, _group, _project, version, _mode, _type)
        df_query = pd.concat([df_query, a], ignore_index=True)
        query_num += b

    return df_query, query_num


def cal_tech_res(_tech, _mode=None, _type=report_types):
    df_query = pd.DataFrame()
    query_num = 0

    for group in groups:
        for project in projects[group]:
            global report_count
            report_count = 0
            a, b = cal_project_res(_tech, group, project, _mode, _type)
            df_query = pd.concat([df_query, a], ignore_index=True)
            query_num += b

    return df_query, query_num


def cal_res(_techlist, _mode=None, _type=report_types):
    for tech in _techlist:
        a, b = cal_tech_res(tech, _mode, _type)
        yield tech, a, b


def res_analysis(tech, df_query, query_num, _isAll=True):
    project = '/' if _isAll else df_query['Project'].unique()[0]
    top1_count = ((df_query['Top1'] != 0) & (df_query['AnsOrder'] == 1)).sum()
    top5_count = ((df_query['Top5'] != 0) & (df_query['AnsOrder'] == 1)).sum()
    top10_count = ((df_query['Top10'] != 0) & (df_query['AnsOrder'] == 1)).sum()

    res_dict = {
        "Technique": tech,
        "Group": 'All' if _isAll else df_query['Group'].unique()[0],
        "Project": project,
        "Source Files": project_source_files[project],
        "Vaild Bug Count": query_num,
        "Recommended BugCount": len(set(df_query['key'])),
        "Top1 Count": top1_count,
        "Top5 Count": top5_count,
        "Top10 Count": top10_count,
        "Top1": top1_count / query_num if query_num > 0 else 0.0,
        "Top5": top5_count / query_num if query_num > 0 else 0.0,
        "Top10": top10_count / query_num if query_num > 0 else 0.0,
        "MAP": df_query['AP'].sum() / query_num if query_num > 0 else 0.0,
        "MRR": df_query['TP'].sum() / query_num if query_num > 0 else 0.0,
    }

    return res_dict


if __name__ == '__main__':
    _answers = {}

    for group in groups:
        for project in projects[group]:
            versions[project] = load_versions(group, project)
            _answers[project] = load_answers(group, project)['all']
            answers[project] = dict(sorted(_answers[project].items(), key=lambda x: x[0]))
    count_bug()

    # 计算3种IRBL
    name1 = 'IRBL20'
    result1 = []
    df1 = pd.DataFrame()
    for tech in techs:
        for group in groups:
            for project in projects[group]:
                report_count = 0
                a, b = cal_project_res(tech, group, project)
                result1.append(res_analysis(tech, a, b, False))
    for a, b, c in cal_res(techs):
        result1.append(res_analysis(a, b, c))
        df1 = pd.concat([df1, b], ignore_index=True)
    df2 = pd.DataFrame(result1)
    # 输出CSV
    df1.to_csv(os.path.join(datapath, f"{name1}_raw.csv"), index=False)
    df2.to_csv(os.path.join(datapath, f"{name1}.csv"), index=False)

    # 计算3种IRBL前200个数据，以及MAP和MRR组成的权值
    name2 = 'IRBL_B200'
    result1 = []
    MAPs1 = []
    MRRs1 = []
    df1 = pd.DataFrame()
    for tech in techs:
        dict_map = {}
        dict_mrr = {}
        for group in groups:
            for project in projects[group]:
                report_count = 0
                a, b = cal_project_res(tech, group, project, 'B200')
                dict_res = res_analysis(tech, a, b, False)
                dict_map[project] = dict_res['MAP']
                dict_mrr[project] = dict_res['MRR']
                result1.append(dict_res)
        MAPs1.append(dict_map)
        MRRs1.append(dict_mrr)
    for a, b, c in cal_res(techs, 'B200'):
        result1.append(res_analysis(a, b, c))
        df1 = pd.concat([df1, b], ignore_index=True)
    df2 = pd.DataFrame(result1)
    # 输出CSV
    df1.to_csv(os.path.join(datapath, f"{name2}_raw.csv"), index=False)
    df2.to_csv(os.path.join(datapath, f"{name2}.csv"), index=False)

    df_MAP1 = pd.DataFrame(MAPs1)
    df_MRR1 = pd.DataFrame(MRRs1)

    for i in range(5):  # 5 projects
        max_map = df_MAP1.iloc[:, i].max()
        max_mrr = df_MRR1.iloc[:, i].max()
        df_MAP1.iloc[:, i] = df_MAP1.iloc[:, i] / max_map
        df_MRR1.iloc[:, i] = df_MRR1.iloc[:, i] / max_mrr
    df_weight = df_MAP1 * df_MRR1
    for i in range(5):  # 5 projects
        df_weight.iloc[:, i] = df_weight.iloc[:, i] / df_weight.iloc[:, i].sum()
    df_weight.to_csv(os.path.join(datapath, 'IRBL_weight.txt'), index=False, header=False)

    # 计算加权IRBL的200报告以后数据
    name3 = 'weighted_IRBL'
    result2 = []
    df3 = pd.DataFrame()
    for group in groups:
        for project in projects[group]:
            report_count = 0
            a, b = cal_project_res('weighted_IRBL', group, project, 'P200')
            result2.append(res_analysis('weighted_IRBL', a, b, False))
    for a, b, c in cal_res(['weighted_IRBL'], 'P200'):
        result2.append(res_analysis(a, b, c))
        df3 = pd.concat([df3, b], ignore_index=True)
    df4 = pd.DataFrame(result2)
    # 输出CSV
    df3.to_csv(os.path.join(datapath, f"{name3}_raw.csv"), index=False)
    df4.to_csv(os.path.join(datapath, f"{name3}.csv"), index=False)

    # 计算LLM处理后数据
    name4 = 'Qwen3-8B'
    result2 = []
    df5 = pd.DataFrame()
    for group in groups:
        for project in projects[group]:
            report_count = 0
            a, b = cal_project_res('Qwen3-8B', group, project, 'P200')
            result2.append(res_analysis('Qwen3-8B', a, b, False))
    for a, b, c in cal_res(['Qwen3-8B'], 'P200'):
        result2.append(res_analysis(a, b, c))
        df5 = pd.concat([df5, b], ignore_index=True)
    df6 = pd.DataFrame(result2)
    # 输出CSV
    df5.to_csv(os.path.join(datapath, f"{name4}_raw.csv"), index=False)
    df6.to_csv(os.path.join(datapath, f"{name4}.csv"), index=False)

    # 计算拓展查询后每个BM25算法的前200条数据，以及MAP和MRR组成的权值
    name6 = 'BM25_B200'
    result6 = []
    MAPs6 = []
    MRRs6 = []
    df1 = pd.DataFrame()
    for bm25 in BM25s:
        dict_map = {}
        dict_mrr = {}
        for group in groups:
            for project in projects[group]:
                report_count = 0
                a, b = cal_project_res(bm25, group, project, 'B200')
                dict_res = res_analysis(bm25, a, b, False)
                dict_map[project] = dict_res['MAP']
                dict_mrr[project] = dict_res['MRR']
                result6.append(dict_res)
        MAPs6.append(dict_map)
        MRRs6.append(dict_mrr)
    for a, b, c in cal_res(BM25s, 'B200'):
        result6.append(res_analysis(a, b, c))
        df1 = pd.concat([df1, b], ignore_index=True)
    df2 = pd.DataFrame(result6)
    # 输出CSV
    df1.to_csv(os.path.join(datapath, f"{name6}_raw.csv"), index=False)
    df2.to_csv(os.path.join(datapath, f"{name6}.csv"), index=False)

    df_MAP1 = pd.DataFrame(MAPs6)
    df_MRR1 = pd.DataFrame(MRRs6)
    print(df_MAP1)
    print(df_MRR1)

    for i in range(5):  # 5 projects
        max_map = df_MAP1.iloc[:, i].max()
        max_mrr = df_MRR1.iloc[:, i].max()
        df_MAP1.iloc[:, i] = df_MAP1.iloc[:, i] / max_map
        df_MRR1.iloc[:, i] = df_MRR1.iloc[:, i] / max_mrr
    df_weight = df_MAP1 * df_MRR1
    for i in range(5):  # 5 projects
        df_weight.iloc[:, i] = df_weight.iloc[:, i] / df_weight.iloc[:, i].sum()
    df_weight.to_csv(os.path.join(datapath, 'BM25_weight.txt'), index=False, header=False)

    # 计算加权BM25的200报告以后数据
    name7 = 'weighted_BM25'
    result7 = []
    df1 = pd.DataFrame()
    for group in groups:
        for project in projects[group]:
            report_count = 0
            a, b = cal_project_res('weighted_BM25', group, project, 'P200')
            result7.append(res_analysis('weighted_BM25', a, b, False))
    for a, b, c in cal_res(['weighted_BM25'], 'P200'):
        result7.append(res_analysis(a, b, c))
        df1 = pd.concat([df1, b], ignore_index=True)
    df2 = pd.DataFrame(result7)
    # 输出CSV
    df1.to_csv(os.path.join(datapath, f"{name7}_raw.csv"), index=False)
    df2.to_csv(os.path.join(datapath, f"{name7}.csv"), index=False)

    # 计算LLM二次处理后数据
    name8 = 'Qwen3-8B-mul'
    result8 = []
    df5 = pd.DataFrame()
    for group in groups:
        for project in projects[group]:
            report_count = 0
            a, b = cal_project_res('Qwen3-8B-mul', group, project, 'P200')
            result8.append(res_analysis('Qwen3-8B-mul', a, b, False))
    for a, b, c in cal_res(['Qwen3-8B-mul'], 'P200'):
        result8.append(res_analysis(a, b, c))
        df5 = pd.concat([df5, b], ignore_index=True)
    df6 = pd.DataFrame(result8)
    # 输出CSV
    df5.to_csv(os.path.join(datapath, f"{name8}_raw.csv"), index=False)
    df6.to_csv(os.path.join(datapath, f"{name8}.csv"), index=False)
