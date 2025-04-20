import os
import shutil
import re
from typing import List, Dict, Optional

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


def load_versions(_group, _project):
    f = open(os.path.join(getPath_base(_group, _project), 'versions.txt'), 'r', encoding='utf-8')
    text = f.read()
    f.close()
    data = eval(text)

    return data[_project]

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


def search_java_file(_group, _project, _version, _name):
    search_dir = os.path.join(getPath_base(_group, _project), 'sources', f'{_project}_{_version}'.replace(".", "_"))
    matched_files = []
    # 仅截取文件名
    fqcn = _name[:-5]
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
        print("找到多个匹配项，请选择：")
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


if __name__ == '__main__':
    for group in groups:
        for project in projects[group]:
            versions[project] = load_versions(group, project)

    # 遍历所有项目和版本，加载并复制源文件
    for group in groups:
        for project in projects[group]:
            for version in versions[project]:
                loadpath = os.path.join(datapath, group, project, version, 'recommended_IRBL', 'combined_IRBL')
                if os.path.exists(loadpath):
                    for file in os.listdir(loadpath):
                        bug_id = os.path.splitext(file)[0]
                        with open(os.path.join(loadpath, file), 'r', encoding='utf-8') as f:
                            file_list = f.readlines()
                        java_list = [line.strip() for line in file_list]
                        index_dict = load_src_file(group, project, version, java_list)
                        for java in java_list:
                            if index_dict[java] is None:
                                print(f'WARNING: {group}/{project}/{version} Bug{bug_id}:{java} not found!')
                            else:
                                copypath = os.path.join(datapath, group, project, version, 'recommended_IRBL', 'combined_files', bug_id)
                                if not os.path.exists(copypath):
                                    os.makedirs(copypath)
                                shutil.copyfile(index_dict[java], os.path.join(copypath, java))

    # 针对ROO项目的特殊处理，处理奇怪的文件名
    # 编译正则表达式模式，匹配Java文件名
    # pattern = re.compile(
    #     r'^WARNING:\s+'          # 日志头
    #     r'([a-zA-Z]+)/'          # group (字母)
    #     r'([a-zA-Z]+)/'          # project (字母)
    #     r'([\d.]+)'              # version (数字+小数点)
    #     r'\s+Bug(\d+):'          # bug_id (纯数字)
    #     r'([a-zA-Z0-9_.$\-]+)'   # java_file (支持_、.、$等合法字符)
    #     r'\s+not found!$'        # 日志结尾
    # )

    # 存储提取结果的字典列表
    # extracted_data = []

    # 读取并处理文件
    # with open(os.path.join(datapath, 'notfound_files.txt'), 'r') as file:
    #     for line_number, line in enumerate(file, 1):
    #         line = line.strip()
    #         match = pattern.match(line)

    #         if not match:
    #             print(f"警告：第{line_number}行格式异常，已跳过 | {line}")
    #             continue

    #         # 结构化存储提取结果
    #         extracted_data.append({
    #             "group": match.group(1),
    #             "project": match.group(2),
    #             "version": match.group(3),
    #             "bug_id": match.group(4),
    #             "java_file": match.group(5)
    #         })

    # 遍历搜索文件名，有需要手动选择
    # for item in extracted_data:
    #     print(f'{item['group']}/{item['project']}/{item['version']} Bug{item['bug_id']}:{item['java_file']}')
    #     newpath = search_java_file(item['group'], item['project'], item['version'], item['java_file'])
    #     copypath = os.path.join(datapath, item['group'], item['project'], item['version'], 'recommended_IRBL', 'combined_files', item['bug_id'])
    #     if not os.path.exists(copypath):
    #         os.makedirs(copypath)
    #     print(newpath)
    #     print(os.path.join(copypath, item['java_file']))
    #     print()
    #     shutil.copyfile(newpath, os.path.join(copypath, item['java_file']))
