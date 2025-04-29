import os
import bm25s
import pandas as pd

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


def normalize_list_manual(scores, target_min=0, target_max=1):
    min_val = min(scores)
    max_val = max(scores)
    if max_val == min_val:  # 避免除以零
        return [target_min] * len(scores)

    # 归一化公式
    scale = (target_max - target_min) / (max_val - min_val)
    normalized = [(x - min_val) * scale + target_min for x in scores]
    return normalized


if __name__ == '__main__':
    for group in groups:
        for project in projects[group]:
            versions[project] = load_versions(group, project)

    # 遍历所有项目和版本，加载并复制源文件
    for group in groups:
        for project in projects[group]:
            for version in versions[project]:
                model = 'qwen-max-latest'
                method = 'lucene'  # bm25l, bm25+
                basicpath = os.path.join(datapath, group, project, version)
                loadpath = os.path.join(basicpath, 'recommended_IRBL', 'combined_files')
                if os.path.exists(loadpath):
                    for dir in os.listdir(loadpath):
                        print(f'process: {project}/{version}/{dir}')
                        filepath = os.path.join(loadpath, dir)
                        file_list = []
                        for file in os.listdir(filepath):
                            with open(os.path.join(filepath, file), 'r', encoding='utf-8') as f:
                                file_list.append(f.read())

                        keypath = os.path.join(basicpath, model, 'keywords', f'{dir}.txt')
                        with open(keypath, 'r', encoding='utf-8') as f:
                            keys = f.readlines()
                        key_list = [line.strip() for line in keys]

                        # Tokenize the corpus and index it
                        corpus_tokens = bm25s.tokenize(file_list)
                        retriever = bm25s.BM25(method=method)
                        retriever.index(corpus_tokens)

                        # Search the corpus with a query
                        query_tokens = bm25s.tokenize(' '.join(key_list))
                        docs, scores = retriever.retrieve(query_tokens, k=len(file_list), corpus=range(len(file_list)))

                        docs_flat = docs.flatten().tolist()
                        scores_flat = scores.flatten().tolist()
                        normalized_scores = normalize_list_manual(scores_flat)

                        result_list = []
                        for i in range(len(docs_flat)):
                            result_list.append([os.listdir(filepath)[docs_flat[i]], normalized_scores[i], scores_flat[i]])
                        savepath = os.path.join(basicpath, model, 'BM25', method)
                        if not os.path.exists(savepath):
                            os.makedirs(savepath)
                        df = pd.DataFrame(result_list)
                        df.to_csv(os.path.join(savepath, f'{dir}.txt'), index=False, header=False)
