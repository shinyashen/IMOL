import os

import config as conf
import shutil
from typing import List, Dict, Optional

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


if __name__ == '__main__':
    for group in groups:
        for project in projects[group]:
            versions[project] = load_versions(group, project)

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
