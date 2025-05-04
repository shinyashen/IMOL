import sys, os

import config as conf


datapath = conf.read_config([conf.data_section], "path", None)
undpath = conf.read_config([conf.data_section], "und_path", None)
sys.path.append(os.path.join(undpath, "Python"))  # Understand 模块位置
os.add_dll_directory(os.path.join(undpath))  # Understand 安装的路径


import understand
import pandas as pd


groups = ['Apache', 'Wildfly', 'Spring']
projects = {
    'Apache': ['CAMEL', 'HBASE', 'HIVE'],
    'Wildfly': ['WFLY'],
    'Spring': ['ROO']
}


def generate_butterfly_dot(csv_file, und_folder, output_folder):
    path = os.path.join(datapath, 'gitrepo', project, f'ordered_bugCmit_{dataset}')
    with open(path, 'r')as f:
        commits = [line.strip().split(',') for line in f.readlines()]
        df_commits = pd.DataFrame(commits, columns=['bugId', 'cmit', 'date'])
    commits_set = df_commits['cmit'].values.tolist()

    # read csv file
    df = pd.read_csv(csv_file, encoding='utf-8')

    # Iterate through each row of data
    for index, row in df.iterrows():
        file_index = row['index']
        commit = row['commit']
        if commit not in commits_set:
            continue
        buggy_file = row['filePath']
        buggy_file = buggy_file.replace('/', '\\')
        print(buggy_file)
        und_file_path = os.path.join(und_folder, f"{commit}.und")
        print(und_file_path)
        # check for the existence of .und files
        if not os.path.exists(und_file_path):
            print(f"UND file not found: {und_file_path}")
            continue

        # open .und file
        try:
            db = understand.open(und_file_path)
            print("db", db)
        except Exception as e:
            print(f"Failed to open UND file: {und_file_path}, Error: {e}")
            continue

        # Get the target file entity
        all_entities = db.ents("File")
        target_file_entity = None
        for ent in all_entities:
            # print(f"und name,{ent.longname()}")
            if ent.longname().endswith(buggy_file):
                print(ent.longname())
                target_file_entity = ent
        if target_file_entity is None:
            print(
                f"Entity not found for file: {buggy_file} in commit: {commit}")
            continue

        # generate a Butterfly diagram and save it as a .dot file
        output_dot_file = os.path.join(output_folder, f"{row['index']}.dot")
        print(type(target_file_entity))
        print("target_file_entity", target_file_entity)
        try:
            target_file_entity.draw("Butterfly", output_dot_file)
            print(f"Butterfly dot file saved: {output_dot_file}")
        except Exception as e:
            print(
                f"Failed to generate Butterfly graph for {buggy_file}, Error: {e}")

        # 关闭数据库
        db.close()


if __name__ == "__main__":
    for group in groups:
        for project in projects[group]:
            dataset = project
            csv_file = os.path.join(datapath, 'gitrepo', project, f'{dataset}_truly_buggy_file_result.csv')
            und_folder = os.path.join(datapath, 'gitrepo', project, 'und')
            output_folder = os.path.join(datapath, 'gitrepo', project, 'Butterfly_time')
            if not os.path.exists(output_folder):
                os.makedirs(output_folder)

            # generate a Butterfly diagram
            try:
                generate_butterfly_dot(csv_file, und_folder, output_folder)
            except Exception as e:
                print(f"An error occurred: {e}")
