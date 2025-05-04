import sys, os

import config as conf


datapath = conf.read_config([conf.data_section], "path", None)
undpath = conf.read_config([conf.data_section], "und_path", None)
sys.path.append(os.path.join(undpath, "Python"))  # Understand 模块位置
os.add_dll_directory(os.path.join(undpath))  # Understand 安装的路径


import understand
import pandas as pd
import re


groups = ['Apache', 'Wildfly', 'Spring']
projects = {
    'Apache': ['CAMEL', 'HBASE', 'HIVE'],
    'Wildfly': ['WFLY'],
    'Spring': ['ROO']
}


def extract_data_flow_dependencies(csv_file, und_folder, output_file, commits_set):
    # read csv
    df = pd.read_csv(csv_file)

    results = []
    df_head_flag = True
    skip_key = True

    # iterate over the data
    for index, row in df.iterrows():
        file_index = row['index']

        print(file_index)
        commit = row['commit']

        # select the specified commit
        if commit not in commits_set:
            continue

        buggy_file = row['filePath']
        und_file_path = os.path.join(und_folder, f"{commit}.und")

        # open .und file
        try:
            db = understand.open(und_file_path)
        except Exception as e:
            print(f"Failed to open UND file: {und_file_path}, Error: {e}")
            continue

        # search the target file entity
        all_entities = db.ents("File")
        target_file_entity = None
        target_funcs = set()

        # get the target file entitiy
        for ent in all_entities:
            if ent.longname().endswith(buggy_file):
                target_file_entity = ent

                # get all the function in target file
                for func in db.ents("function, method"):
                    parent_entity = func.parent()
                    # Loop through until find a file type entity
                    while parent_entity is not None and not parent_entity.kind().check("file"):
                        parent_entity = parent_entity.parent()
                    # If a file type entity is found, output the file name
                    if parent_entity is not None:
                        file_name = parent_entity.longname()
                        if file_name == target_file_entity.longname():
                            # print(file_name)
                            # print("func.longname: ", func.longname())
                            target_funcs.add(func)

        if target_file_entity is None:
            print(f"Entity not found for file: {buggy_file} in commit: {commit}")
            continue

        # Extract a list of files related to data flow dependencies
        data_flow_deps = set()

        for func in target_funcs:
            # Getting references related to data streams (defining, using, reading, assigning, etc.)
            for ref in func.refs():
                referenced_entity = ref.ent()
                referencing_file = ref.file()
                # Check if the referenced entity is located in a file other than the target file
                if referencing_file != target_file_entity:
                    data_flow_deps.add(referencing_file.longname())
            # print(func.longname())

        results = []  # temp
        for dep_file in data_flow_deps:
            results.append({
                'index': row['index'],
                'bugID': row['bugID'],
                'filePath': buggy_file,
                'commit': commit,
                'df_filePath': dep_file
            })

        if df_head_flag:
            output_df = pd.DataFrame(results)
            output_df.to_csv(output_file, index=False, mode='a')
            df_head_flag = False
        else:
            output_df = pd.DataFrame(results)
            output_df.to_csv(output_file, index=False, mode='a', header=0)

        # print(results)
        db.close()
        print(f"data_flow_deps: {data_flow_deps}")


def parse_dot_file(dot_file):
    nodes = {}
    edges = []

    with open(dot_file, 'r') as file:
        for line in file:
            # match nodes
            node_match = re.match(
                r'^\s*__(N\d+)\s*\[label="(.+?)"\s*.*\];', line)
            if node_match:
                node_id = node_match.group(1)
                label = re.sub(r'&#[0-9]+;', '', node_match.group(2)).strip()
                label = re.sub(r'\s*&#965\d;\s*', '', label)
                nodes[node_id] = label

            # match edges
            edge_match = re.match(
                r'^\s*__(N\d+)\s*->\s*__(N\d+)\s*\[label="(\d+)(?:\s*/\s*(\d+))?".*\];', line)
            if edge_match:
                src_node = edge_match.group(1)
                dst_node = edge_match.group(2)
                count = int(edge_match.group(3)) + (int(edge_match.group(4)) if edge_match.group(4) else 0)

                edges.append((src_node, dst_node, count))

    return nodes, edges


def get_file_path(entity_name, udb):
    # Find the file path corresponding to the entity name
    for ent in udb.ents("file ~unknown ~unresolved"):
        if entity_name in ent.longname():
            return ent.longname()
    return entity_name


def get_n1_edges(edges, nodes, udb):
    n1_edges = []
    for src, dst, count in edges:
        # N1 points to (file called by target file)
        if src == "N1":
            dst_file = get_file_path(nodes[dst], udb)
            n1_edges.append((dst_file, count))
        # Points to N1 (the file that calls the target file)
        elif dst == "N1":
            src_file = get_file_path(nodes[src], udb)
            n1_edges.append((src_file, count))
    return n1_edges


def extract_control_flow_dependencies(csv_file, und_folder, butterfly_folder, output_file, commits_set):
    # read csv
    df = pd.read_csv(csv_file)
    head_flag = True

    for _, row in df.iterrows():
        index = row['index']

        print(index)
        commit = row['commit']
        # select specificed commit
        if commit not in commits_set:
            continue

        und_file_path = os.path.join(und_folder, f"{commit}.und")
        dot_file = os.path.join(butterfly_folder, f"{index}.dot")

        # open .und file
        try:
            udb = understand.open(und_file_path)
        except Exception as e:
            print(f"Failed to open UND file: {und_file_path}, Error: {e}")
            continue

        # check the existence of .dot
        if not os.path.exists(dot_file):
            print(f"Dot file not found: {dot_file}")
            continue

        # parse .dot file
        nodes, edges = parse_dot_file(dot_file)
        n1_edges = get_n1_edges(edges, nodes, udb)

        # print("N1 Edges (Dependencies):")
        # for src, dst, count in n1_edges:
        #     print(f"{src} -> {dst} : {count} time(s)")

        cf_info = {}
        print("cf_files", len(n1_edges))
        for edge, count in n1_edges:
            cf_info[edge] = count

        results = [{
            'index': index,
            'bugId': row['bugID'],
            'filePath': row['filePath'],
            'commit': row['commit'],
            'cf_file': cf_info
        }]

    # save csv
        if head_flag:
            output_df = pd.DataFrame(results)
            output_df.to_csv(output_file, index=False, mode='a')
            head_flag = False
        else:
            output_df = pd.DataFrame(results)
            output_df.to_csv(output_file, index=False, mode='a', header=0)
        udb.close()
    print(f"Results saved to {output_file}")


if __name__ == "__main__":
    for group in groups:
        for project in projects[group]:
            dataset = project
            path = os.path.join(datapath, 'gitrepo', project, f'ordered_bugCmit_{dataset}')
            with open(path, 'r') as f:
                commits = [line.strip().split(',') for line in f.readlines()]
                df_commits = pd.DataFrame(commits, columns=['bugId', 'cmit', 'date'])
            commits_set = df_commits['cmit'].values.tolist()

            csv_file = os.path.join(datapath, 'gitrepo', project, f'{dataset}_truly_buggy_file_result.csv')
            und_folder = os.path.join(datapath, 'gitrepo', project, 'und')
            data_flow_file = os.path.join(datapath, 'gitrepo', project, f'{dataset}_df_list.csv')

            #  Data Flow Dependency File List Extraction
            extract_data_flow_dependencies(csv_file, und_folder, data_flow_file, commits_set)

            butterfly_folder = os.path.join(datapath, 'gitrepo', project, 'Butterfly_time')
            control_flow_file = os.path.join(datapath, 'gitrepo', project, f'{dataset}_cf_list.csv')

            # Control Flow Dependency File List Extraction
            extract_control_flow_dependencies(csv_file, und_folder, butterfly_folder, control_flow_file, commits_set)
