import os
import pandas as pd

import config as conf


techs = ['BugLocator', 'BRTracer', 'BLIA']
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
versions = {}
answers = {}
bug_counts = {}

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
    bug_counts['all'] = 0
    for group in groups:
        for project in projects[group]:
            bug_counts[project] = 0
            for version in versions[project]:
                loadpath = os.path.join(datapath, group, project, version, 'recommended_IRBL', 'combined_IRBL')
                if os.path.exists(loadpath):
                    bug_counts[project] += len(os.listdir(loadpath))
            bug_counts['all'] += bug_counts[project]


def calculate_metrics(ordered_list, target_list, _tech, _group, _project, _version, _id):
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
            "key": f'{_project}{str(_id).zfill(5)}'.lower(),
            "Approach": _tech,
            "Group": _group,
            "Project": _project,
            "BugID": _id,
            "Version": f'{_project}_{_version}'.replace(".", "_"),
            "AnsFileCount": answers[_project][int(_id)],
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


def cal_version_res(_tech, _group, _project, _version):
    loadpart = ''  # TODO: LLM part
    if _tech in techs or _tech == 'combined_IRBL':
        loadpart = 'recommended_IRBL'
    loadpath = os.path.join(datapath, _group, _project,_version, loadpart, _tech)
    df_query = pd.DataFrame()
    query_num = 0

    for file in os.listdir(loadpath):
        query_num += 1
        bug_id = os.path.splitext(file)[0]
        with open(os.path.join(loadpath, file), 'r', encoding='utf-8') as f:
            file_list = f.readlines()
        java_list = [line.strip() for line in file_list]
        bugpath = os.path.join(os.path.join(
            datapath, _group, _project, _version, 'buglist', file))
        with open(bugpath, 'r', encoding='utf-8') as f:
            file_list = f.readlines()
        bug_list = [line.strip() for line in file_list]

        df = calculate_metrics(java_list, bug_list, _tech, _group, _project, _version, bug_id)
        df_query = pd.concat([df_query, df], ignore_index=True)

    return df_query, query_num


def cal_project_res(_tech, _group, _project):
    df_query = pd.DataFrame()
    query_num = 0

    for version in versions[_project]:
        a, b = cal_version_res(_tech, _group, _project, version)
        df_query = pd.concat([df_query, a], ignore_index=True)
        query_num += b

    return df_query, query_num


def cal_tech_res(_tech):
    df_query = pd.DataFrame()
    query_num = 0

    for group in groups:
        for project in projects[group]:
            a, b = cal_project_res(_tech, group, project)
            df_query = pd.concat([df_query, a], ignore_index=True)
            query_num += b

    return df_query, query_num


def cal_res(_techlist):
    for tech in _techlist:
        a, b = cal_tech_res(tech)
        yield tech, a, b


def res_analysis(tech, df_query, query_num, _isAll=True):
    project = '/' if _isAll else df_query['Project'].unique()[0]
    top1_count = ((df_query['Top1'] != 0) & (df_query['AnsOrder'] == 1)).sum()
    top5_count = ((df_query['Top5'] != 0) & (df_query['AnsOrder'] == 1)).sum()
    top10_count = ((df_query['Top10'] != 0) & (df_query['AnsOrder'] == 1)).sum()
    bug_count = bug_counts['all'] if _isAll else bug_counts[project]

    res_dict = {
        "Technique": tech,
        "Group": 'All' if _isAll else df_query['Group'].unique()[0],
        "Project": project,
        "Source Files": project_source_files[project],
        "Bug Count": bug_count,
        "Recommended BugCount": len(set(df_query['key'])),
        "Top1 Count": top1_count,
        "Top5 Count": top5_count,
        "Top10 Count": top10_count,
        "Top1": top1_count / bug_count if bug_count > 0 else 0.0,
        "Top5": top5_count / bug_count if bug_count > 0 else 0.0,
        "Top10": top10_count / bug_count if bug_count > 0 else 0.0,
        "MAP": df_query['AP'].sum() / bug_count if bug_count > 0 else 0.0,
        "MRR": df_query['TP'].sum() / bug_count if bug_count > 0 else 0.0,
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

    result = []
    for a, b, c in cal_res(techs):
        result.append(res_analysis(a, b, c))
    df = pd.DataFrame(result)

    # 输出CSV
    df.to_csv(os.path.join(datapath, "query_metrics.csv"), index=False)
