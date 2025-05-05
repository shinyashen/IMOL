import os, codecs, re, subprocess
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional

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


def getPath_base(_group, _project):
    return os.path.join(Bench4BL_datapath, _group, _project)


def load_versions(_group, _project):
    f = open(os.path.join(getPath_base(_group, _project), 'versions.txt'), 'r', encoding='utf-8')
    text = f.read()
    f.close()
    data = eval(text)

    return data[_project]


def filetype_fileter(filename):
    return filename.endswith(u'.java')  # not this type of files returns False


def file_loader(_f):
    log = {'hash': u'', 'commit_date': u'', 'message':u'', 'fixedFiles': {}}

    for line in _f:
        if line == u'---------------------\n':
            yield log
            log = {'hash': u'', 'commit_date': u'', 'message':u'', 'fixedFiles': {}}
            continue
        if line.startswith(u'hash:'):
            log['hash'] = line[5:-1].strip()
            continue
        if line.startswith(u'commit_date:'):
            log['commit_date'] = line[12:-1].strip()[:-5]
            continue
        if line.startswith(u'message:'):
            log['message'] = line[8:-1].strip()
            continue
        if line.startswith(u'A\t') or line.startswith(u'M\t') or line.startswith(u'D\t'):
            fname = line[2:-1].strip()
            ftype = line[:1]
            if filetype_fileter(fname) is False:
                continue
            log['fixedFiles'][fname] = ftype
            continue
    pass


def subdict(_dict, keys):
    return {key: _dict[key] for key in keys if key in _dict}


def load_logs(_group, _project):
    '''
    Load commit info from GitLogPath
    :return:  {bugID:[{'hash':u'', 'commit_date':u'', 'message':u'', 'fixedFiles':{}}, {}, ...], ...}
    '''
    savepath = os.path.join(datapath, 'gitrepo', _project, f'ordered_bugCmit_{_project}')
    if not os.path.exists(savepath):
        logs = {}
        GitLogPath = os.path.join(getPath_base(_group, _project), 'bugrepo', '.git.log')
        logfile = codecs.open(GitLogPath, 'r', 'utf-8')
        for logitem in file_loader(logfile):
            # filter unuseful logs
            if len(logitem['fixedFiles']) == 0:
                continue

            # We only use bug report id in log message
            # mapping bug report ID
            logitem['linked_bug'] = re.findall(r'%s-[0-9]+' % _project.upper(), logitem['message'])
            logitem['linked_bug'] = set(logitem['linked_bug'])

            for linked_id in logitem['linked_bug']:
                if linked_id not in logs:
                    logs[linked_id] = [logitem]
                else:
                    logs[linked_id].append(logitem)
        logfile.close()

        my_logs = []
        for key in logs:
            _id = key.split('-', 1)[1]
            _dict = max(logs[key], key=lambda d: datetime.strptime(d['commit_date'].strip(), r'%Y-%m-%d %H:%M:%S').timestamp())
            _hash = _dict['hash']
            _timestamp = int(datetime.strptime(_dict['commit_date'].strip(), r'%Y-%m-%d %H:%M:%S').timestamp())
            my_logs.append([_id, _hash, _timestamp])

        duppath = os.path.join(Bench4BL_datapath, _group, _project, 'bugrepo', 'duplicates.json')
        f = open(duppath, 'r', encoding='utf-8')
        text = f.read()
        f.close()
        dup = eval(text)
        dup_dict = {}
        for key1, value1 in dup.items():
            key2 = key1.upper()
            value2 = {sub[1]: sub[0] for sub in value1}
            dup_dict[key2] = value2

        df = pd.DataFrame(my_logs)
        res_logs = pd.DataFrame()
        basepath = os.path.join(datapath, _group, _project)
        for version in os.listdir(basepath):
            idpath = os.path.join(basepath, version, 'recommended_IRBL', 'combined_files')
            for id in os.listdir(idpath):
                # 提取id列
                column = df.iloc[:, 0]

                # 检查值是否存在
                if id not in column.values:
                    dup_index = str(dup_dict[_project][int(id)])
                    dup_row = df[df.iloc[:, 0] == dup_index].copy()
                    dup_row[df.columns[0]] = id
                    res_logs = pd.concat([res_logs, dup_row])
                else:
                    res_logs = pd.concat([res_logs, df[df.iloc[:, 0] == id]])

        res_logs = res_logs.sort_values(by=[df.columns[2], df.columns[0]], ascending=False)
        res_logs.to_csv(savepath, index=False, header=False)


# 获取最新的提交SHA
def get_newest_commit_sha(repo):
    reflog = subprocess.check_output(["git", "reflog"], cwd=repo, text=True)
    newest_line = reflog.strip().split("\n")[-1]
    return newest_line.split()[0]


def create_udb(_project):
    repo_path = os.path.abspath(os.path.join(datapath, 'gitrepo', _project, 'gitrepo'))
    commit_path = os.path.join(datapath, 'gitrepo', _project, f'ordered_bugCmit_{_project}')
    und_path = conf.read_config([conf.data_section], "und_path", None)
    newest_commit_sha = get_newest_commit_sha(repo_path)

    # 遍历提交文件
    with open(commit_path, "r") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            current_commit = line.split(",")[1]  # 提取第二个字段为提交哈希
            savepath = os.path.join(datapath, 'gitrepo', _project, 'und')
            if not os.path.exists(savepath):
                os.makedirs(savepath)
            output_file = os.path.abspath(os.path.join(savepath, f"{current_commit}.udb"))

            print(f"Processing: {output_file}...",end='')
            if not os.path.exists(output_file):
                # 切换到父提交
                parent_commit = f"{current_commit}~1"
                subprocess.run(
                    ["git", "checkout", "-f", parent_commit],
                    cwd=repo_path,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                # 执行UND分析命令
                subprocess.run([
                    "und", "-quiet",
                    "create", "-db", output_file, "-languages", "java",
                    "add", repo_path,
                    "analyze", "-all"
                ], check=True, cwd=und_path)
            else:
                print("skip...",end='')
            print('ok!')

    # 切换回最新提交
    subprocess.run(
        ["git", "checkout", "-f", newest_commit_sha],
        cwd=repo_path,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


class JavaFileLocator:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.index: Dict[str, List[str]] = {}
        self.priority_dirs = {'src/test/java', 'src/main/java', 'src'}
        self._build_index()

    def _build_index(self) -> None:
        """构建文件名到路径的索引，并记录优先级"""
        for root, _, files in os.walk(self.root_dir):
            for file in files:
                if not file.endswith('.java'):
                    continue
                rel_path = os.path.relpath(root, self.root_dir).replace(os.path.sep, '/')
                full_path = os.path.join(root, file)

                # 记录优先级：标准目录中的路径优先
                priority = 0
                for dir_prefix in self.priority_dirs:
                    if rel_path.startswith(dir_prefix):
                        priority = 1
                        break

                if file not in self.index:
                    self.index[file] = []
                self.index[file].append((full_path, priority))

    def find_files(self, java_filenames: List[str]) -> Dict[str, Optional[str]]:
        """批量查找文件路径"""
        results = {}
        target_files = set()
        rel_path_map = {}

        # 预处理：生成目标文件名和相对路径
        for filename in java_filenames:
            rel_path = self._get_relative_path(filename)
            if not rel_path:
                results[filename] = None
                continue
            target_file = os.path.basename(rel_path)
            target_files.add(target_file)
            rel_path_map[filename] = (target_file, os.path.dirname(rel_path))

        # 遍历索引，匹配路径
        for orig_name in java_filenames:
            if orig_name not in rel_path_map:
                results[orig_name] = None
                continue
            target_file, target_rel_dir = rel_path_map[orig_name]

            candidates = []
            for full_path, priority in self.index.get(target_file, []):
                # 检查路径是否以目标相对目录结尾
                path_dir = os.path.dirname(full_path)
                rel_dir = os.path.relpath(path_dir, self.root_dir).replace(os.path.sep, '/')
                if rel_dir.endswith(target_rel_dir):
                    candidates.append((full_path, priority))

            if candidates:
                # 按优先级排序（优先级高的在前）
                candidates.sort(key=lambda x: -x[1])
                results[orig_name] = candidates[0][0]
            else:
                results[orig_name] = None

        return results

    @staticmethod
    def _get_relative_path(java_filename: str) -> Optional[str]:
        """将Java类名转换为相对路径"""
        if not java_filename.endswith('.java'):
            return None
        fqcn = java_filename[:-5]
        parts = fqcn.split('.')
        if len(parts) < 1:
            return None
        class_name = parts[-1]
        package_parts = parts[:-1]
        return '/'.join(package_parts) + '/' + class_name + '.java'


def load_src_file(_group, _project, _version, _filelist):
    loadpath = os.path.join(getPath_base(_group, _project), 'sources', f'{_project}_{_version}'.replace(".", "_"))
    locator = JavaFileLocator(loadpath)
    return locator.find_files(_filelist)


def search_java_file(name, search_dir):
    matched_files = []
    # 仅截取文件名
    fqcn = name[:-5]
    parts = fqcn.split('.')
    class_name = parts[-1]
    _filename = class_name + '.java'

    # 遍历目录树
    for root, _, files in os.walk(search_dir):
        for file in files:
            if file == _filename:
                matched_files.append(os.path.join(root, file))
            elif file == 'ApplicationConversionServiceFactoryBean-template._java' and _filename == 'ApplicationConversionServiceFactoryBean-template.java': # HOW
                matched_files.append(os.path.join(root, file))

    # 处理搜索结果
    if not matched_files:
        print(f"未找到文件: {_filename}")
        return None

    # 多结果时让用户选择
    if len(matched_files) > 1:
        print(f"找到多个匹配项，请选择文件：{name}")
        for idx, path in enumerate(matched_files, 1):
            print(f"[{idx}] {path}")
        while True:
            try:
                choice = int(input("输入序号: "))
                if 1 <= choice <= len(matched_files):
                    selected_path = matched_files[choice-1]
                    break
                else:
                    print("序号无效，请重新输入。")
            except ValueError:
                print("请输入数字序号。")
    else:
        selected_path = matched_files[0]

    # 输出绝对路径
    absolute_path = os.path.abspath(selected_path)
    return absolute_path


def export_truly_buggy_file_list():
    for group in groups:
        for project in projects[group]:
            versions[project] = load_versions(group, project)

    # 遍历所有项目和版本，加载并复制源文件
    for group in groups:
        for project in projects[group]:
            savepath = os.path.join(datapath, 'gitrepo', project, f'{project}_truly_buggy_file_result.csv')
            if not os.path.exists(savepath):
                logpath = os.path.join(datapath, 'gitrepo', project, f'ordered_bugCmit_{project}')
                logs = pd.read_csv(logpath, header=None)
                res_list = []

                for version in versions[project]:
                    loadpath = os.path.join(datapath, group, project, version, 'buglist')
                    if os.path.exists(loadpath):
                        version_java_list = []
                        for file in os.listdir(loadpath):  # 每个版本只进行一次全局查找
                            with open(os.path.join(loadpath, file), 'r', encoding='utf-8') as f:
                                file_list = f.readlines()
                            version_java_list.extend([line.strip() for line in file_list])
                        version_java_list = list(set(version_java_list))  # 去重
                        index_dict = load_src_file(group, project, version, version_java_list)

                        for file in os.listdir(loadpath):
                            bug_id = os.path.splitext(file)[0]
                            print(f'Get: {group}/{project}/{version} Bug{bug_id}:')
                            with open(os.path.join(loadpath, file), 'r', encoding='utf-8') as f:
                                file_list = f.readlines()
                            java_list = list(set([line.strip() for line in file_list]))  # 去重

                            for java in java_list:
                                if index_dict[java] is None:  # 二次全局查找
                                    result = search_java_file(java, os.path.join(getPath_base(group, project), 'sources', f'{project}_{version}'.replace(".", "_")))
                                    if result is None:  # 最新库查找
                                        result = search_java_file(java, os.path.join(getPath_base(group, project), 'gitrepo'))
                                        if result is not None:  # 取相对路径
                                            print('3: ', end='')
                                            result = os.path.relpath(result, os.path.join(getPath_base(group, project), 'gitrepo'))
                                    else:  # 取相对路径
                                        print('2: ', end='')
                                        result = os.path.relpath(result, os.path.join(getPath_base(group, project), 'sources', f'{project}_{version}'.replace(".", "_")))
                                else:  # 取相对路径
                                    print('1: ', end='')
                                    result = index_dict[java]
                                    result = os.path.relpath(result, os.path.join(getPath_base(group, project), 'sources', f'{project}_{version}'.replace(".", "_")))
                                if result is not None:
                                    print(result)
                                    commit = logs[logs.iloc[:, 0] == int(bug_id)].iloc[0, 1]
                                    res_list.append([bug_id, result, commit])

                # 按bugID升序排序
                sorted_list = sorted(res_list, key=lambda x: x[0])

                # 添加索引列并构造新的数据列表
                indexed_data = [[i+1, bug, path, commit] for i, (bug, path, commit) in enumerate(sorted_list)]
                df = pd.DataFrame(indexed_data, columns=['index', 'bugID', 'filePath', 'commit'])
                df.to_csv(savepath, index=False)


if __name__ == '__main__':
    for group in groups:
        for project in projects[group]:
            load_logs(group, project)
            create_udb(project)
    export_truly_buggy_file_list()
