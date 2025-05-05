import os
import pandas as pd
import xml.etree.ElementTree as ET

import config as conf


techs = ['BugLocator', 'BRTracer', 'BLIA']
groups = ['Apache', 'Wildfly', 'Spring']
projects = {
    'Apache': ['CAMEL', 'HBASE', 'HIVE'],
    'Wildfly': ['WFLY'],
    'Spring': ['ROO']
}
versions = {}

Bench4BL_path = conf.read_config([conf.Bench4BL_section], "path", None)
Bench4BL_datapath = os.path.join(Bench4BL_path, 'data')
datapath = conf.read_config([conf.data_section], "path", None)


def getPath_base(_group, _project):
    return os.path.join(Bench4BL_datapath, _group, _project)


def getPath_result_folder(_name, _tech, _group, _project, _version):
    return os.path.join(Bench4BL_path, "expresults", _name, _group, _project, f'{_tech}_{_project}_{_project}_{_version}'.replace(".", "_"))


def load_versions(_group, _project):
    f = open(os.path.join(getPath_base(_group, _project), 'versions.txt'), 'r', encoding='utf-8')
    text = f.read()
    f.close()
    data = eval(text)

    return data[_project]


def save_filelist(_tech, _group, _project, _version, _id, _file, _length):
    savepath = os.path.join(datapath, _group, _project, _version, 'recommended_IRBL', _tech)
    if not os.path.exists(savepath):
        os.makedirs(savepath)
    df = pd.read_csv(_file, sep='\\s+', header=None, encoding='utf-8', nrows=_length)
    df.iloc[:_length, 2].to_csv(os.path.join(savepath, f'{_id}.txt'), index=False, header=None, encoding='utf-8')


def save_buglist(_group, _project, _version, _xml):
    savepath = os.path.join(datapath, _group, _project, _version, 'buglist')
    if not os.path.exists(savepath):
        os.makedirs(savepath)

    root = ET.fromstring(_xml)

    # 遍历每个bug元素
    for bug in root.findall('bug'):
        bug_id = bug.get('id')
        fixed_files = bug.find('fixedFiles')

        if bug_id is not None and fixed_files is not None:
            file_list = []
            # 提取所有file元素的文本内容
            for file_elem in fixed_files.findall('file'):
                file_path = file_elem.text.strip()
                if file_path:
                    file_list.append(file_path)

            # 写入文件
            if file_list:
                filename = f"{bug_id}.txt"
                with open(os.path.join(savepath, filename), 'w', encoding='utf-8') as f:
                    f.write('\n'.join(file_list))


if __name__ == '__main__':
    run_name = 'IRBL2'

    for group in groups:
        for project in projects[group]:
            versions[project] = load_versions(group, project)

    # 读取Top20可疑文件列表
    for tech in techs:
        for group in groups:
            for project in projects[group]:
                for version in versions[project]:
                    recommeneded_filepath = os.path.join(getPath_result_folder(run_name, tech, group, project, version), 'recommended')
                    if os.path.exists(recommeneded_filepath):
                        for file in os.listdir(recommeneded_filepath):
                            bug_id = os.path.splitext(file)[0]
                            with open(os.path.join(recommeneded_filepath, file), 'r', encoding='utf-8') as f:
                                save_filelist(tech, group, project, version, bug_id, f, 20)
    # 合并列表
    for group in groups:
        for project in projects[group]:
            for version in versions[project]:
                idpath = os.path.join(datapath, group, project, version, 'recommended_IRBL', techs[0])
                if os.path.exists(idpath):
                    for file in os.listdir(idpath):
                        lists = []
                        for tech in techs:
                            loadpath = os.path.join(datapath, group, project, version, 'recommended_IRBL', tech)
                            if os.path.exists(os.path.join(loadpath, file)):
                                with open(os.path.join(loadpath, file), 'r', encoding='utf-8') as f:
                                    file_list = f.readlines()
                                lists.append([line.strip() for line in file_list])
                            else: # TODO: 为啥会少文件
                                print(f'WARNING: {group}/{project}/{version} {tech}/{file} not exists!')
                                lists.append([])

                        presence_dict = {}
                        # 动态构建存在标记字典
                        for list_idx, lst in enumerate(lists):
                            for rank, elem in enumerate(lst):
                                if elem not in presence_dict:
                                    # 初始化标记为全零列表，长度等于列表数量
                                    presence_dict[elem] = [0] * len(lists)
                                presence_dict[elem][list_idx] = (20.0 - rank) / 20.0  # 标记当前列表存在

                        # 创建DataFrame并排序索引
                        df = pd.DataFrame.from_dict(
                            presence_dict,
                            orient='index',
                            columns=[f'List{i+1}' for i in range(len(lists))]
                        ).sort_index().reset_index().rename(columns={'index': 'filename'})

                        savepath = os.path.join(datapath, group, project, version, 'recommended_IRBL', 'combined_IRBL')
                        if not os.path.exists(savepath):
                            os.makedirs(savepath)
                        df.to_csv(os.path.join(savepath, file), index=False, header=False)

    # 获取bug文件列表
    for group in groups:
        for project in projects[group]:
            for version in versions[project]:
                report_filepath = os.path.join(Bench4BL_datapath, group, project, 'bugrepo', 'repository')
                file = os.path.join(report_filepath, f'{project}_{version}'.replace(".", "_")+'.xml')
                if os.path.exists(file):
                    with open(file, 'r', encoding='utf-8') as f:
                        xml_content = f.read()
                        save_buglist(group, project, version, xml_content)

    # 计算IRBL赋权后的合并文件列表
    weights = {}
    df_weights = pd.read_csv(os.path.join(datapath, 'IRBL_weight.txt'), header=None, encoding='utf-8')
    index = 0
    for group in groups:
        for project in projects[group]:
            weights[project] = df_weights.iloc[:, index].tolist()
            index += 1

    for group in groups:
        for project in projects[group]:
            for version in versions[project]:
                idpath = os.path.join(datapath, group, project, version, 'recommended_IRBL', techs[0])
                if os.path.exists(idpath):
                    for file in os.listdir(idpath):
                        combined_file = os.path.join(datapath, group, project, version, 'recommended_IRBL', 'combined_IRBL', file)
                        df = pd.read_csv(combined_file, header=None)
                        df[df.columns[1:]] = df[df.columns[1:]].astype(float)

                        index = len(weights[project]) + 1
                        df.iloc[:, 1:index] = df.iloc[:, 1:index] * weights[project]  # 赋权
                        df[index] = df.iloc[:, 1:index].sum(axis=1)  # 计算总分
                        result_df = df.iloc[:, [0, index]].copy()  # 只保留文件名和总分
                        result_df = result_df.sort_values(result_df.columns[1], ascending=False)  # 按照总分降序排序

                        savepath = os.path.join(datapath, group, project, version, 'recommended_IRBL', 'weighted_IRBL')
                        if not os.path.exists(savepath):
                            os.makedirs(savepath)
                        result_df.to_csv(os.path.join(savepath, file), index=False, header=False)

    # 计算LLM判断相关性后的文件列表
    for group in groups:
        for project in projects[group]:
            for version in versions[project]:
                basepath = os.path.join(datapath, group, project, version)
                idpath = os.path.join(basepath, 'recommended_IRBL', 'weighted_IRBL')
                if os.path.exists(idpath):
                    for file in os.listdir(idpath):
                        weighted_file = os.path.join(idpath, file)
                        df1 = pd.read_csv(weighted_file, header=None)
                        df1 = df1.rename(columns={df1.columns[0]: 'name', df1.columns[1]: 'score1'})
                        LLM_rel_file = os.path.join(basepath, 'Qwen3-8B', 'relevance', file)
                        df2 = pd.read_csv(LLM_rel_file, header=None)
                        df2 = df2.rename(columns={df2.columns[0]: 'name', df2.columns[1]: 'rel'})
                        merged_df = pd.merge(df1, df2, on='name').sort_values(by=["rel", "score1"], ascending=[False, False])

                        savepath = os.path.join(basepath, 'Qwen3-8B', 'result')
                        if not os.path.exists(savepath):
                            os.makedirs(savepath)
                        merged_df.to_csv(os.path.join(savepath, file), header=None, index=None)