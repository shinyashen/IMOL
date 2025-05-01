import os
import shutil

import config as conf


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
exportpath = conf.read_config([conf.data_section], "export_path", None)


def getPath_base(_group, _project):
    return os.path.join(Bench4BL_datapath, _group, _project)


def load_versions(_group, _project):
    f = open(os.path.join(getPath_base(_group, _project), 'versions.txt'), 'r', encoding='utf-8')
    text = f.read()
    f.close()
    data = eval(text)

    return data[_project]


if __name__ == '__main__':
    for group in groups:
        for project in projects[group]:
            versions[project] = load_versions(group, project)

    # 遍历所有项目和版本，复制分析代码块所需的文件
    for group in groups:
        for project in projects[group]:
            # # 复制版本文件
            # copypath = os.path.join(group, project, 'versions.txt')
            # savepath = os.path.join(exportpath, 'Bench4BL', 'data', group, project)
            # if not os.path.exists(savepath):
            #     os.makedirs(savepath)
            # shutil.copyfile(os.path.join(Bench4BL_datapath, copypath), os.path.join(savepath, 'versions.txt'))

            # # 复制报告文件
            # copypath = os.path.join(group, project, 'bugrepo', 'bugs')
            # shutil.copytree(os.path.join(Bench4BL_datapath, copypath), os.path.join(exportpath, 'Bench4BL', 'data', copypath), dirs_exist_ok=True)

            for version in versions[project]:
                basepath = os.path.join(group, project, version)
                basicpath = os.path.join(datapath, basepath)
                basicpath_exp = os.path.join(exportpath, 'data', basepath)
                if os.path.exists(basicpath):
                    # # 复制合并列表的源文件
                    # copypath = os.path.join('recommended_IRBL', 'combined_files')
                    # shutil.copytree(os.path.join(basicpath, copypath), os.path.join(basicpath_exp, copypath), dirs_exist_ok=True)

                    # # 复制报告类型文件
                    # copypath = os.path.join('qwen-max-latest', 'type')
                    # shutil.copytree(os.path.join(basicpath, copypath), os.path.join(basicpath_exp, copypath), dirs_exist_ok=True)

                    # 复制LLM相关数文件（结果）
                    copypath = os.path.join('Qwen3-8B', 'relevance')
                    shutil.copytree(os.path.join(basicpath, copypath), os.path.join(basicpath_exp, copypath), dirs_exist_ok=True)
