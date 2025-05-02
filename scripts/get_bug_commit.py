import os, codecs, re, subprocess
import pandas as pd
from datetime import datetime

import config as conf


groups = ['Apache', 'Wildfly', 'Spring']
projects = {
    'Apache': ['CAMEL', 'HBASE', 'HIVE'],
    'Wildfly': ['WFLY'],
    'Spring': ['ROO']
}

Bench4BL_path = conf.read_config([conf.Bench4BL_section], "path", None)
Bench4BL_datapath = os.path.join(Bench4BL_path, 'data')
datapath = conf.read_config([conf.data_section], "path", None)


def getPath_base(_group, _project):
    return os.path.join(Bench4BL_datapath, _group, _project)


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

        df = pd.DataFrame(my_logs)
        df.to_csv(savepath, index=False, header=False)


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

            # 切换到父提交
            parent_commit = f"{current_commit}~1"
            subprocess.run(
                ["git", "checkout", "-f", parent_commit],
                cwd=repo_path,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # 生成UND数据库文件
            savepath = os.path.join(datapath, 'gitrepo', _project, 'und')
            if not os.path.exists(savepath):
                os.makedirs(savepath)
            output_file = os.path.abspath(os.path.join(savepath, f"{current_commit}.und"))
            print(f"Processing: {output_file}")

            # 执行UND分析命令
            subprocess.run([
                "und", "create",
                "-quiet",
                "-db", output_file,
                "-languages", "java",
                "add", repo_path,
                "analyze", "-all"
            ], check=True, cwd=und_path)

    # 切换回最新提交
    subprocess.run(
        ["git", "checkout", "-f", newest_commit_sha],
        cwd=repo_path,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


if __name__ == '__main__':
    for group in groups:
        for project in projects[group]:
            load_logs(group, project)
            create_udb(project)
